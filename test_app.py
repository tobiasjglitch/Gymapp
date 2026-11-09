import inspect
import re
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import app


class LocalProfileTests(unittest.TestCase):
    def test_screen_wake_lock_reacquires_when_app_becomes_visible(self):
        source = inspect.getsource(app.keep_screen_awake)
        self.assertIn('navigator.wakeLock.request("screen")', source)
        self.assertIn('document.addEventListener("visibilitychange"', source)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "gymapp.db"
        self.supabase_patch = patch.object(app, "use_supabase", return_value=False)
        self.supabase_patch.start()
        self.path_patch = patch.object(app, "DB_PATH", self.db_path)
        self.path_patch.start()
        app.clear_data_cache()

    def tearDown(self):
        app.clear_data_cache()
        self.path_patch.stop()
        self.supabase_patch.stop()
        self.temp_dir.cleanup()

    def test_profiles_have_separate_programs_and_history(self):
        app.init_db()
        tobias = app.list_profiles()[0]
        app.seed_program_for_profile(tobias.id)
        brother = app.create_profile("Brorsan")

        self.assertEqual(len(app.list_program(tobias.id, "Pass 1")), 5)
        self.assertEqual(len(app.list_program(brother.id, "Pass 1")), 5)

        exercise = app.list_program(tobias.id, "Pass 1")[0]
        app.save_workout(
            tobias.id,
            "Pass 1",
            date(2026, 7, 22),
            "Testpass",
            [{"exercise_id": exercise.exercise_id, "weight_kg": 20, "reps": [10]}],
            pd.DataFrame(),
        )

        self.assertEqual(app.profile_overview(tobias.id), (1, "Pass 1"))
        self.assertEqual(app.profile_overview(brother.id), (0, None))
        self.assertEqual(len(app.history_dataframe(tobias.id)), 1)
        self.assertTrue(app.history_dataframe(brother.id).empty)
        self.assertEqual(app.suggested_day(tobias.id), "Pass 2")
        self.assertEqual(app.suggested_day(brother.id), "Pass 1")

        workout_id = int(app.recent_workouts(tobias.id)[0]["id"])
        app.delete_workout(workout_id, tobias.id)
        self.assertTrue(app.history_dataframe(tobias.id).empty)

    def test_draft_round_trip_and_idempotent_workout_save(self):
        app.init_db()
        profile = app.list_profiles()[0]
        app.seed_program_for_profile(profile.id)
        exercise = app.list_program(profile.id, "Pass 1")[0]
        payload = [
            {
                "exercise_id": exercise.exercise_id,
                "done": True,
                "weight_kg": 22.5,
                "reps": [8, 8, 7, 7],
            }
        ]

        app.save_workout_draft(
            profile.id,
            "Pass 1",
            date(2026, 10, 4),
            "Utkast",
            payload,
        )
        draft = app.load_workout_draft(profile.id, "Pass 1")
        self.assertEqual(draft["notes"], "Utkast")
        self.assertEqual(draft["payload"], payload)

        token = "same-workout-token-123"
        first_id = app.save_workout(
            profile.id,
            "Pass 1",
            date(2026, 10, 4),
            "Test",
            [{"exercise_id": exercise.exercise_id, "weight_kg": 22.5, "reps": [8]}],
            pd.DataFrame(),
            client_token=token,
        )
        second_id = app.save_workout(
            profile.id,
            "Pass 1",
            date(2026, 10, 4),
            "Test",
            [{"exercise_id": exercise.exercise_id, "weight_kg": 22.5, "reps": [8]}],
            pd.DataFrame(),
            client_token=token,
        )
        self.assertEqual(first_id, second_id)
        self.assertEqual(app.profile_overview(profile.id)[0], 1)

        app.clear_workout_draft(profile.id, "Pass 1")
        self.assertIsNone(app.load_workout_draft(profile.id, "Pass 1"))

    def test_old_sqlite_program_schema_is_migrated(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE exercises (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
                CREATE TABLE program_exercises (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_name TEXT NOT NULL,
                    exercise_id INTEGER NOT NULL REFERENCES exercises(id),
                    sort_order INTEGER NOT NULL,
                    sets INTEGER NOT NULL,
                    rep_min INTEGER NOT NULL,
                    rep_max INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(day_name, exercise_id)
                );
                CREATE TABLE workouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workout_date TEXT NOT NULL,
                    day_name TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE workout_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
                    exercise_id INTEGER NOT NULL REFERENCES exercises(id),
                    set_no INTEGER NOT NULL,
                    reps INTEGER NOT NULL,
                    weight_kg REAL NOT NULL,
                    is_pr INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO exercises(name) VALUES ('Knäböj');
                INSERT INTO program_exercises(day_name, exercise_id, sort_order, sets, rep_min, rep_max)
                VALUES ('Pass 1', 1, 1, 3, 5, 8);
                """
            )

        app.init_db()
        tobias = app.list_profiles()[0]
        brother = app.create_profile("Brorsan")
        app.add_program_exercise(brother.id, "Pass 1", "Knäböj", 3, 5, 8)

        self.assertEqual(app.list_program(tobias.id, "Pass 1")[0].name, "Knäböj")
        self.assertTrue(any(row.name == "Knäböj" for row in app.list_program(brother.id, "Pass 1")))

    def test_imported_start_values_are_used_before_first_workout(self):
        exercise = app.ProgramExercise(
            id=1,
            exercise_id=2,
            name="Pullups",
            day_name="Pass 2",
            sort_order=1,
            sets=4,
            rep_min=6,
            rep_max=10,
            start_weight_kg=30,
            start_reps=(10, 6, 12, 6),
        )

        suggestion = app.suggest_weight(exercise, pd.DataFrame())

        self.assertEqual(suggestion.weight, 30)
        self.assertEqual(app.suggested_reps(exercise, pd.DataFrame()), [10, 6, 12, 6])

    def test_configured_weight_step_controls_progression(self):
        exercise = app.ProgramExercise(
            id=1,
            exercise_id=2,
            name="Sidolyft maskin",
            day_name="Pass 1",
            sort_order=1,
            sets=2,
            rep_min=10,
            rep_max=12,
            weight_step_kg=1.0,
        )
        history = pd.DataFrame(
            [
                {"exercise_id": 2, "workout_id": 1, "datum": "2026-10-01", "set_nr": 1, "vikt_kg": 10, "reps": 12},
                {"exercise_id": 2, "workout_id": 1, "datum": "2026-10-01", "set_nr": 2, "vikt_kg": 10, "reps": 12},
            ]
        )

        suggestion = app.suggest_weight(exercise, history)

        self.assertEqual(suggestion.weight, 11.0)

    def test_technique_demo_aliases_and_template_resolve(self):
        expected = app.APP_DIR / "assets" / "demos" / "exercise_3d.html"

        self.assertEqual(app.technique_demo_path(" Lat   Pulldown "), expected)
        self.assertEqual(app.technique_demo_path("LATSDRAG"), expected)
        self.assertEqual(app.technique_demo_mode("Knäböj"), "squat")
        self.assertEqual(app.technique_demo_mode("Face Pulls 3 set"), "face_pull")
        self.assertEqual(app.technique_demo_mode("Bulgarian Split Squat 3"), "split_squat")

        html = app.technique_demo_html("Lat Pulldown")
        self.assertIsNotNone(html)
        self.assertNotIn("__DEMO_CONFIG__", html)
        self.assertIn('"mode":"lat_pulldown"', html)
        self.assertIn("#exercise-status[hidden]", html)

        legacy_demo = (app.APP_DIR / "assets" / "demos" / "lat_pulldown.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("#lat-pulldown-status[hidden]", legacy_demo)

    def test_active_tobias_exercises_use_anatomical_gifs(self):
        names = [
            "Lutande hantelpress",
            "Kabel-flyes",
            "Bröststödd roddmaskin",
            "Sidolyft hantlar",
            "Bröststödd high row",
            "Hip thrust-maskin/Smith",
            "Benpress",
            "Sittande lårcurl",
            "Kabel-crunch",
            "Hantelpress plan bänk",
            "Enarms hantelrodd med stöd mot bänk",
            "Cable cross",
            "Latsdrag, neutralt grepp",
            "Sittande roddmaskin",
            "Triceps pushdown",
            "Höftabduktion i kabel/maskin",
        ]
        expected_template = app.APP_DIR / "assets" / "demos" / "exercise_gif.html"

        for name in names:
            with self.subTest(name=name):
                gif_path = app.technique_gif_path(name)
                self.assertIsNotNone(gif_path)
                self.assertGreater(gif_path.stat().st_size, 100_000)
                self.assertEqual(app.technique_demo_path(name), expected_template)
                html = app.technique_demo_html(name)
                self.assertIsNotNone(html)
                self.assertIn("data:image/gif;base64,", html)
                self.assertNotIn("__DEMO_IMAGE__", html)
                self.assertNotIn("__DEMO_CONFIG__", html)

    def test_mobility_library_uses_3d_modes_and_timer(self):
        expected_modes = {
            "dead_hang": "mobility_dead_hang",
            "deep_squat": "mobility_deep_squat",
            "thoracic_rotation": "mobility_thoracic_rotation",
            "hip_flexor": "mobility_hip_flexor",
            "chest_opener": "mobility_chest_opener",
        }
        template = (app.APP_DIR / "assets" / "demos" / "exercise_3d.html").read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            app.mobility_for_exercise("Triceps pushdown", 4, 5),
            "dead_hang",
        )
        self.assertEqual(
            app.mobility_for_exercise("Benpress", 0, 4),
            "thoracic_rotation",
        )
        for mobility_key, mode in expected_modes.items():
            with self.subTest(mobility_key=mobility_key):
                html = app.mobility_demo_html(mobility_key)
                self.assertIsNotNone(html)
                self.assertIn(f'"mode":"{mode}"', html)
                self.assertIn('"duration":25', html)
                self.assertIn(mode, template)
                self.assertIn('id="mobility-timer"', html)

    def test_tobias_active_program_uses_exact_technique_modes(self):
        expected_modes = {
            "Lutande hantelpress": "incline_press",
            "Kabel-flyes": "cable_fly",
            "Bröststödd roddmaskin": "chest_supported_machine_row",
            "Sidolyft hantlar": "lateral_raise",
            "Bröststödd high row": "chest_supported_high_row",
            "Hip thrust-maskin/Smith": "hip_thrust",
            "Benpress": "leg_press",
            "Sittande lårcurl": "leg_curl",
            "Kabel-crunch": "cable_crunch",
            "Hantelpress plan bänk": "bench_press",
            "Enarms hantelrodd med stöd mot bänk": "one_arm_row",
            "Cable cross": "cable_fly",
            "Latsdrag, neutralt grepp": "neutral_grip_pulldown",
            "Sittande roddmaskin": "seated_machine_row",
            "Triceps pushdown": "triceps_pushdown",
            "Höftabduktion i kabel/maskin": "hip_abduction",
        }

        for name, expected_mode in expected_modes.items():
            with self.subTest(name=name):
                self.assertEqual(app.technique_demo_mode(name), expected_mode)
                html = app.technique_demo_html(name)
                self.assertIsNotNone(html)
                self.assertIn(f'"mode":"{expected_mode}"', html)

        gallery = (app.APP_DIR / "prototypes" / "all_exercises_gallery.html").read_text(
            encoding="utf-8"
        )
        gallery_modes = re.findall(r'\["[^"]+", "([a-z_]+)"\]', gallery)
        self.assertEqual(len(gallery_modes), 15)
        self.assertEqual(set(gallery_modes), set(expected_modes.values()))
        gif_template = (app.APP_DIR / "assets" / "demos" / "exercise_gif.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("#101714", gif_template)
        self.assertIn("exercise-toggle", gif_template)

    def test_free_weight_pass_three_migration_is_scoped_and_preserves_history(self):
        migration = (
            app.APP_DIR / "supabase_program_tobias_free_weights_v9.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("p.name = 'Tobias'", migration)
        self.assertIn("pe.day_name = 'Pass 3'", migration)
        self.assertIn("'Hantelpress plan bänk'", migration)
        self.assertIn("'Enarms hantelrodd med stöd mot bänk'", migration)
        self.assertIn("'Sidolyft hantlar'", migration)
        self.assertIn("'Cable cross'", migration)
        self.assertNotRegex(migration.lower(), r"\bdelete\b")
        self.assertNotRegex(migration.lower(), r"\b(update|insert into)\s+public\.workouts\b")
        self.assertNotRegex(migration.lower(), r"\b(update|insert into)\s+public\.workout_sets\b")

    def test_glute_program_migration_is_scoped_and_preserves_history(self):
        migration = (
            app.APP_DIR / "supabase_program_tobias_glutes_v8.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("p.name = 'Tobias'", migration)
        self.assertIn("'Hip thrust-maskin/Smith'", migration)
        self.assertIn("'Höftabduktion i kabel/maskin'", migration)
        self.assertIn("e.name = 'Benspark'", migration)
        self.assertIn("e.name = 'Vadpress i maskin'", migration)
        self.assertNotRegex(migration.lower(), r"\bdelete\b")
        self.assertNotRegex(migration.lower(), r"\b(update|insert into)\s+public\.workouts\b")
        self.assertNotRegex(migration.lower(), r"\b(update|insert into)\s+public\.workout_sets\b")

    def test_brand_logo_asset_can_be_embedded(self):
        self.assertTrue(app.LOGO_PATH.is_file())
        self.assertTrue(app.logo_data_uri().startswith("data:image/svg+xml;base64,"))

    def test_all_current_program_exercises_have_technique_demos(self):
        tobias_exercises = [
            name
            for exercises in app.STARTER_PROGRAM.values()
            for name, _, _, _ in exercises
        ]
        johan_exercises = [
            "Incline DB Press",
            "Flat Press",
            "Cable Flyes",
            "Pushdown",
            "Overhead Extensions",
            "Abs Bench",
            "Woodchopper",
            "Landmine Rotation",
            "Pullups",
            "Chest Supported Rows",
            "Lat Pulldown",
            "Face Pulls",
            "Spider Curls",
            "Incl./Preacher Curls",
            "Barbell Hip Thrust",
            "Sumo Squats",
            "Leg Curls (Hamstrings)",
            "Hip Abduction",
            "Calf Raises",
            "Ab Roller?",
            "Lateral Raises",
            "Rear Delt Flies",
            "Hammer Curls",
            "Triceps Pushdown",
            "Farmers Walk",
        ]

        missing = [
            name
            for name in tobias_exercises + johan_exercises
            if app.technique_demo_mode(name) is None
        ]
        self.assertEqual(missing, [])


class WorkoutUiTests(unittest.TestCase):
    @staticmethod
    def _app_with_history(db_path: Path) -> AppTest:
        script = f"""
from datetime import date
from pathlib import Path
import app

app.DB_PATH = Path({str(db_path)!r})
app.use_supabase = lambda: False
app.clear_data_cache()
app.init_db()
profile = app.list_profiles()[0]
app.seed_program_for_profile(profile.id)
if app.profile_overview(profile.id)[0] == 0:
    exercise = app.list_program(profile.id, "Pass 1")[0]
    app.save_workout(
        profile.id,
        "Pass 1",
        date(2026, 8, 1),
        "Testhistorik",
        [{{
            "exercise_id": exercise.exercise_id,
            "weight_kg": 20,
            "reps": [8] * exercise.sets,
        }}],
        app.history_dataframe(profile.id),
    )
app.main()
"""
        return AppTest.from_string(script, default_timeout=10).run()

    def test_save_workout_advances_to_next_day_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "gymapp.db"
            script = f"""
from pathlib import Path
import app

app.DB_PATH = Path({str(db_path)!r})
app.use_supabase = lambda: False
app.clear_data_cache()
app.main()
"""
            tested_app = AppTest.from_string(script, default_timeout=10).run()
            self.assertEqual(len(tested_app.exception), 0)

            current_day = next(box for box in tested_app.selectbox if box.label == "Pass").value
            tested_app.checkbox[0].check().run()
            save_button = next(button for button in tested_app.button if button.label == "Spara pass")
            save_button.click().run()

            self.assertEqual(len(tested_app.exception), 0)
            pass_selector = next(box for box in tested_app.selectbox if box.label == "Pass")
            expected_day = app.DAY_NAMES[(app.DAY_NAMES.index(current_day) + 1) % len(app.DAY_NAMES)]
            self.assertEqual(pass_selector.value, expected_day)
            self.assertEqual(len(tested_app.success), 1)

            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0], 1)
                self.assertGreater(conn.execute("SELECT COUNT(*) FROM workout_sets").fetchone()[0], 0)

    def test_completed_exercise_offers_optional_mobility_pause(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "gymapp.db"
            script = f"""
from pathlib import Path
import app

app.DB_PATH = Path({str(db_path)!r})
app.use_supabase = lambda: False
app.clear_data_cache()
app.main()
"""
            tested_app = AppTest.from_string(script, default_timeout=10).run()
            tested_app.checkbox[0].check().run()

            labels = [button.label for button in tested_app.button]
            self.assertIn("Starta 25 s", labels)
            self.assertIn("Hoppa över", labels)
            self.assertTrue(
                any("Rörlighetspaus" in element.value for element in tested_app.markdown)
            )

            next(button for button in tested_app.button if button.label == "Hoppa över").click().run()
            self.assertEqual(len(tested_app.exception), 0)
            self.assertNotIn("Hoppa över", [button.label for button in tested_app.button])

    def test_every_view_and_management_flow_runs_without_exceptions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "gymapp.db"
            tested_app = self._app_with_history(db_path)

            for view in app.VIEWS:
                tested_app.radio[0].set_value(view).run()
                self.assertEqual(
                    len(tested_app.exception),
                    0,
                    f"Vyn {view} kraschade: {[exc.message for exc in tested_app.exception]}",
                )

            tested_app.radio[0].set_value("Program").run()
            tested_app.expander[0].number_input[1].set_value(5).run()
            tested_app.expander[0].button[0].click().run()
            self.assertEqual(len(tested_app.exception), 0)
            self.assertIn("5 set", tested_app.expander[0].label)

            tested_app.text_input[0].set_value("Agenttestövning").run()
            next(button for button in tested_app.button if button.label == "Lägg till").click().run()
            self.assertEqual(len(tested_app.exception), 0)
            self.assertTrue(any("Agenttestövning" in row.label for row in tested_app.expander))

            added_row = next(row for row in tested_app.expander if "Agenttestövning" in row.label)
            added_row.button[1].click().run()
            self.assertEqual(len(tested_app.exception), 0)
            self.assertFalse(any("Agenttestövning" in row.label for row in tested_app.expander))

            # Re-open the app after removing a dynamic expander. Streamlit's
            # AppTest tree otherwise retains the deleted form's widget ids.
            tested_app = self._app_with_history(db_path)
            tested_app.radio[0].set_value("PB").run()
            self.assertEqual(len(tested_app.dataframe), 1)
            tested_app.radio[0].set_value("Trend").run()
            self.assertEqual(len(tested_app.get("arrow_vega_lite_chart")), 2)
            tested_app.radio[0].set_value("Export").run()
            self.assertEqual(len(tested_app.dataframe), 1)
            self.assertEqual(len(tested_app.get("download_button")), 1)

            tested_app.radio[0].set_value("Profiler").run()
            tested_app.text_input[0].set_value("Agenttest").run()
            next(button for button in tested_app.button if button.label == "Skapa profil").click().run()
            self.assertEqual(len(tested_app.exception), 0)
            self.assertTrue(
                any("Agenttest" in element.value for element in tested_app.markdown)
            )
            self.assertEqual(len(tested_app.success), 1)

            delete_db_path = Path(temp_dir) / "delete-gymapp.db"
            delete_app = self._app_with_history(delete_db_path)
            delete_app.radio[0].set_value("Historik").run()
            self.assertTrue(delete_app.expander[0].button[0].disabled)
            delete_app.expander[0].checkbox[0].check().run()
            self.assertEqual(len(delete_app.exception), 0)
            self.assertFalse(delete_app.expander[0].button[0].disabled)


if __name__ == "__main__":
    unittest.main()
