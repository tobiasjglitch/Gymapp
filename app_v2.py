from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from supabase import Client, create_client
except Exception:  # Supabase behövs bara i molnläget.
    Client = None
    create_client = None


APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "gymapp.db"

DAY_NAMES = ["Pass 1", "Pass 2", "Pass 3", "Pass 4"]

STARTER_PROGRAM = {
    "Pass 1": [
        ("Lutande hantelpress", 4, 6, 10),
        ("Kabel-flyes", 3, 8, 12),
        ("Enarms hantelrodd", 3, 8, 12),
        ("Sidolyft hantlar", 3, 10, 15),
        ("Triceps pushdown", 3, 8, 12),
    ],
    "Pass 2": [
        ("Knäböj", 4, 5, 8),
        ("Raka marklyft", 4, 6, 10),
        ("Bulgarian split squat", 3, 8, 12),
        ("Kabel-crunch", 3, 10, 15),
    ],
    "Pass 3": [
        ("Hantelpress plan bänk", 4, 6, 10),
        ("Push-ups med vikt", 3, 6, 12),
        ("Face pull", 3, 10, 15),
        ("Axelpress hantlar", 3, 6, 10),
        ("Bicepscurl hantlar", 3, 8, 12),
    ],
    "Pass 4": [
        ("Marklyft", 3, 3, 6),
        ("Frontböj", 3, 5, 8),
        ("Goblet squat", 3, 8, 12),
        ("Bakåtlunges", 3, 8, 12),
        ("Kabel woodchop", 3, 10, 15),
    ],
}


def _secret_value(section: str, key: str) -> str | None:
    try:
        if section in st.secrets and key in st.secrets[section]:
            return str(st.secrets[section][key])
    except Exception:
        return None
    return None


def app_pin() -> str | None:
    try:
        if "APP_PIN" in st.secrets:
            return str(st.secrets["APP_PIN"])
    except Exception:
        return None
    return _secret_value("app", "pin")


def require_pin_if_configured() -> None:
    pin = app_pin()
    if not pin:
        return
    if st.session_state.get("unlocked"):
        return

    st.markdown(
        """
        <div class="hero">
            <div class="eyebrow">Privat app</div>
            <div class="title">Lyftlogg</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    typed = st.text_input("PIN", type="password", placeholder="Ange din PIN")
    if st.button("Lås upp", use_container_width=True):
        if typed == pin:
            st.session_state["unlocked"] = True
            st.rerun()
        else:
            st.error("Fel PIN.")
    st.stop()


def use_supabase() -> bool:
    return bool(_secret_value("supabase", "url") and _secret_value("supabase", "anon_key"))


@st.cache_resource
def supabase_client() -> Client:
    if create_client is None:
        st.error("Supabase saknas. Lägg till paketet `supabase` i requirements.txt.")
        st.stop()
    url = _secret_value("supabase", "url")
    key = _secret_value("supabase", "anon_key")
    if not url or not key:
        st.error("Supabase-nycklar saknas i Streamlit Secrets.")
        st.stop()
    return create_client(url, key)


@dataclass(frozen=True)
class ProgramExercise:
    id: int
    name: str
    day_name: str
    sort_order: int
    sets: int
    rep_min: int
    rep_max: int


@dataclass(frozen=True)
class WeightSuggestion:
    weight: float
    label: str
    reason: str


@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    if use_supabase():
        return
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS program_exercises (
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

            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_date TEXT NOT NULL,
                day_name TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workout_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id),
                set_no INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight_kg REAL NOT NULL,
                is_pr INTEGER NOT NULL DEFAULT 0
            );
            """
        )


def seed_starter_program() -> None:
    if use_supabase():
        sb = supabase_client()
        existing = sb.table("program_exercises").select("id").limit(1).execute().data or []
        if existing:
            return

        for day_name, rows in STARTER_PROGRAM.items():
            for sort_order, (name, sets, rep_min, rep_max) in enumerate(rows, start=1):
                existing_exercise = (
                    sb.table("exercises").select("id").eq("name", name).limit(1).execute().data or []
                )
                if existing_exercise:
                    exercise_id = existing_exercise[0]["id"]
                else:
                    exercise_id = sb.table("exercises").insert({"name": name}).execute().data[0]["id"]
                sb.table("program_exercises").insert(
                    {
                        "day_name": day_name,
                        "exercise_id": exercise_id,
                        "sort_order": sort_order,
                        "sets": sets,
                        "rep_min": rep_min,
                        "rep_max": rep_max,
                        "active": True,
                    }
                ).execute()
        return

    with db_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM program_exercises").fetchone()[0]
        if existing:
            return

        for day_name, rows in STARTER_PROGRAM.items():
            for sort_order, (name, sets, rep_min, rep_max) in enumerate(rows, start=1):
                conn.execute("INSERT OR IGNORE INTO exercises(name) VALUES (?)", (name,))
                exercise_id = conn.execute(
                    "SELECT id FROM exercises WHERE name = ?",
                    (name,),
                ).fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO program_exercises
                        (day_name, exercise_id, sort_order, sets, rep_min, rep_max)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (day_name, exercise_id, sort_order, sets, rep_min, rep_max),
                )


def list_program(day_name: str) -> list[ProgramExercise]:
    if use_supabase():
        rows = (
            supabase_client()
            .table("program_exercises")
            .select("id, day_name, sort_order, sets, rep_min, rep_max, exercises(name)")
            .eq("day_name", day_name)
            .eq("active", True)
            .order("sort_order")
            .execute()
            .data
            or []
        )
        return [
            ProgramExercise(
                id=int(row["id"]),
                name=(row.get("exercises") or {}).get("name", "Okänd övning"),
                day_name=row["day_name"],
                sort_order=int(row["sort_order"]),
                sets=int(row["sets"]),
                rep_min=int(row["rep_min"]),
                rep_max=int(row["rep_max"]),
            )
            for row in rows
        ]

    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                pe.id,
                e.name,
                pe.day_name,
                pe.sort_order,
                pe.sets,
                pe.rep_min,
                pe.rep_max
            FROM program_exercises pe
            JOIN exercises e ON e.id = pe.exercise_id
            WHERE pe.day_name = ? AND pe.active = 1
            ORDER BY pe.sort_order, e.name
            """,
            (day_name,),
        ).fetchall()

    return [ProgramExercise(**dict(row)) for row in rows]


def count_workouts() -> int:
    if use_supabase():
        res = supabase_client().table("workouts").select("id", count="exact").execute()
        return int(res.count or 0)
    with db_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0])


def suggested_day() -> str:
    return DAY_NAMES[count_workouts() % len(DAY_NAMES)]


def best_for_exercise(name: str) -> tuple[float, int] | None:
    if use_supabase():
        rows = (
            supabase_client()
            .table("workout_sets")
            .select("weight_kg, reps, exercises!inner(name)")
            .eq("exercises.name", name)
            .execute()
            .data
            or []
        )
        if not rows:
            return None
        max_weight = max(float(row["weight_kg"]) for row in rows)
        max_reps = max(int(row["reps"]) for row in rows if float(row["weight_kg"]) == max_weight)
        return max_weight, max_reps

    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT ws.weight_kg, MAX(ws.reps) AS reps
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE e.name = ?
            GROUP BY ws.weight_kg
            ORDER BY ws.weight_kg DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    if not row:
        return None
    return float(row["weight_kg"]), int(row["reps"])


def last_weight_for_exercise(name: str) -> float:
    if use_supabase():
        rows = (
            supabase_client()
            .table("workout_sets")
            .select("weight_kg, set_no, workouts!inner(workout_date, id), exercises!inner(name)")
            .eq("exercises.name", name)
            .order("workout_date", desc=True, foreign_table="workouts")
            .order("id", desc=True, foreign_table="workouts")
            .order("set_no", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        return float(rows[0]["weight_kg"]) if rows else 0.0

    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT ws.weight_kg
            FROM workout_sets ws
            JOIN workouts w ON w.id = ws.workout_id
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE e.name = ?
            ORDER BY w.workout_date DESC, w.id DESC, ws.set_no DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    return float(row["weight_kg"]) if row else 0.0


def last_session_for_exercise(name: str) -> list[int] | None:
    if use_supabase():
        sb = supabase_client()
        latest = (
            sb.table("workout_sets")
            .select("workout_id, workouts!inner(workout_date, id), exercises!inner(name)")
            .eq("exercises.name", name)
            .order("workout_date", desc=True, foreign_table="workouts")
            .order("id", desc=True, foreign_table="workouts")
            .limit(1)
            .execute()
            .data
            or []
        )
        if not latest:
            return None
        workout_id = latest[0]["workout_id"]
        rows = (
            sb.table("workout_sets")
            .select("reps, set_no, exercises!inner(name)")
            .eq("workout_id", workout_id)
            .eq("exercises.name", name)
            .order("set_no")
            .execute()
            .data
            or []
        )
        return [int(row["reps"]) for row in rows]

    with db_connection() as conn:
        workout = conn.execute(
            """
            SELECT w.id
            FROM workouts w
            JOIN workout_sets ws ON ws.workout_id = w.id
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE e.name = ?
            ORDER BY w.workout_date DESC, w.id DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        if not workout:
            return None
        rows = conn.execute(
            """
            SELECT ws.reps
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.workout_id = ? AND e.name = ?
            ORDER BY ws.set_no
            """,
            (workout["id"], name),
        ).fetchall()
    return [int(row["reps"]) for row in rows]


def weight_step_for(name: str) -> float:
    lower_body_words = ["böj", "squat", "mark", "lunges", "utfall", "goblet", "front"]
    return 5.0 if any(word in name.lower() for word in lower_body_words) else 2.5


def suggest_weight(exercise: ProgramExercise) -> WeightSuggestion:
    last_weight = last_weight_for_exercise(exercise.name)
    if last_weight <= 0:
        return WeightSuggestion(0.0, "Välj startvikt", "Första gången du loggar övningen.")

    reps = last_session_for_exercise(exercise.name)
    if not reps:
        return WeightSuggestion(last_weight, "Samma som sist", "Jag hittade vikt men inga set att jämföra.")

    step = weight_step_for(exercise.name)
    if all(rep >= exercise.rep_max for rep in reps):
        return WeightSuggestion(
            last_weight + step,
            f"Höj till {last_weight + step:g} kg",
            f"Du nådde övre repmålet senast: {', '.join(map(str, reps))}.",
        )
    if all(rep < exercise.rep_min for rep in reps):
        return WeightSuggestion(
            max(0.0, last_weight - step),
            f"Sänk till {max(0.0, last_weight - step):g} kg",
            f"Alla set låg under målet senast: {', '.join(map(str, reps))}.",
        )
    return WeightSuggestion(
        last_weight,
        f"Behåll {last_weight:g} kg",
        f"Bygg klart repmålet först: {', '.join(map(str, reps))}.",
    )


def existing_best_reps(exercise_name: str, weight_kg: float) -> int:
    if use_supabase():
        rows = (
            supabase_client()
            .table("workout_sets")
            .select("reps, exercises!inner(name)")
            .eq("exercises.name", exercise_name)
            .eq("weight_kg", weight_kg)
            .execute()
            .data
            or []
        )
        return max([int(row["reps"]) for row in rows] or [0])

    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(ws.reps) AS reps
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE e.name = ? AND ws.weight_kg = ?
            """,
            (exercise_name, weight_kg),
        ).fetchone()
    return int(row["reps"] or 0)


def save_workout(
    day_name: str,
    workout_date: date,
    notes: str,
    logged: list[dict],
) -> None:
    if not logged:
        raise ValueError("Du måste markera minst en övning som klar.")

    now = datetime.now().isoformat(timespec="seconds")
    if use_supabase():
        sb = supabase_client()
        workout_id = sb.table("workouts").insert(
            {
                "workout_date": workout_date.isoformat(),
                "day_name": day_name,
                "notes": notes.strip(),
                "created_at": now,
            }
        ).execute().data[0]["id"]

        set_rows = []
        for item in logged:
            exercise = sb.table("exercises").select("id").eq("name", item["name"]).limit(1).execute().data
            if not exercise:
                raise ValueError(f"Hittar inte övningen: {item['name']}")
            exercise_id = exercise[0]["id"]
            previous_best = existing_best_reps(item["name"], item["weight_kg"])
            for set_no, reps in enumerate(item["reps"], start=1):
                set_rows.append(
                    {
                        "workout_id": workout_id,
                        "exercise_id": exercise_id,
                        "set_no": set_no,
                        "reps": reps,
                        "weight_kg": item["weight_kg"],
                        "is_pr": reps > previous_best,
                    }
                )
        if set_rows:
            sb.table("workout_sets").insert(set_rows).execute()
        return

    with db_connection() as conn:
        workout_id = conn.execute(
            """
            INSERT INTO workouts(workout_date, day_name, notes, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (workout_date.isoformat(), day_name, notes.strip(), now),
        ).lastrowid

        for item in logged:
            exercise_id = conn.execute(
                "SELECT id FROM exercises WHERE name = ?",
                (item["name"],),
            ).fetchone()["id"]
            previous_best_row = conn.execute(
                """
                SELECT MAX(ws.reps) AS reps
                FROM workout_sets ws
                WHERE ws.exercise_id = ? AND ws.weight_kg = ?
                """,
                (exercise_id, item["weight_kg"]),
            ).fetchone()
            previous_best = int(previous_best_row["reps"] or 0)
            for set_no, reps in enumerate(item["reps"], start=1):
                is_pr = reps > previous_best
                conn.execute(
                    """
                    INSERT INTO workout_sets
                        (workout_id, exercise_id, set_no, reps, weight_kg, is_pr)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (workout_id, exercise_id, set_no, reps, item["weight_kg"], int(is_pr)),
                )


def update_program_exercise(row_id: int, sets: int, rep_min: int, rep_max: int, sort_order: int) -> None:
    if use_supabase():
        supabase_client().table("program_exercises").update(
            {
                "sets": sets,
                "rep_min": rep_min,
                "rep_max": rep_max,
                "sort_order": sort_order,
            }
        ).eq("id", row_id).execute()
        return

    with db_connection() as conn:
        conn.execute(
            """
            UPDATE program_exercises
            SET sets = ?, rep_min = ?, rep_max = ?, sort_order = ?
            WHERE id = ?
            """,
            (sets, rep_min, rep_max, sort_order, row_id),
        )


def add_program_exercise(day_name: str, name: str, sets: int, rep_min: int, rep_max: int) -> None:
    clean_name = " ".join(name.strip().split())
    if not clean_name:
        raise ValueError("Skriv ett övningsnamn först.")
    if rep_max < rep_min:
        raise ValueError("Rep max måste vara minst lika högt som rep min.")

    if use_supabase():
        sb = supabase_client()
        existing_exercise = sb.table("exercises").select("id").eq("name", clean_name).limit(1).execute().data
        if existing_exercise:
            exercise_id = existing_exercise[0]["id"]
        else:
            exercise_id = sb.table("exercises").insert({"name": clean_name}).execute().data[0]["id"]

        rows = (
            sb.table("program_exercises")
            .select("id")
            .eq("day_name", day_name)
            .eq("exercise_id", exercise_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        order_rows = (
            sb.table("program_exercises")
            .select("sort_order")
            .eq("day_name", day_name)
            .order("sort_order", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        sort_order = int(order_rows[0]["sort_order"]) + 1 if order_rows else 1
        payload = {
            "day_name": day_name,
            "exercise_id": exercise_id,
            "sort_order": sort_order,
            "sets": sets,
            "rep_min": rep_min,
            "rep_max": rep_max,
            "active": True,
        }
        if rows:
            sb.table("program_exercises").update(payload).eq("id", rows[0]["id"]).execute()
        else:
            sb.table("program_exercises").insert(payload).execute()
        return

    with db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO exercises(name) VALUES (?)", (clean_name,))
        exercise_id = conn.execute(
            "SELECT id FROM exercises WHERE name = ?",
            (clean_name,),
        ).fetchone()["id"]
        sort_order = int(
            conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM program_exercises WHERE day_name = ?",
                (day_name,),
            ).fetchone()[0]
        )
        conn.execute(
            """
            INSERT INTO program_exercises(day_name, exercise_id, sort_order, sets, rep_min, rep_max, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(day_name, exercise_id) DO UPDATE SET
                active = 1,
                sets = excluded.sets,
                rep_min = excluded.rep_min,
                rep_max = excluded.rep_max
            """,
            (day_name, exercise_id, sort_order, sets, rep_min, rep_max),
        )


def deactivate_program_exercise(row_id: int) -> None:
    if use_supabase():
        supabase_client().table("program_exercises").update({"active": False}).eq("id", row_id).execute()
        return

    with db_connection() as conn:
        conn.execute("UPDATE program_exercises SET active = 0 WHERE id = ?", (row_id,))


def pb_summary_dataframe() -> pd.DataFrame:
    df = export_dataframe()
    if df.empty:
        return df
    df["volym"] = df["vikt_kg"] * df["reps"]
    df["est_1rm"] = df["vikt_kg"] * (1 + df["reps"] / 30)
    summary = (
        df.groupby("ovning", as_index=False)
        .agg(
            tyngsta_vikt=("vikt_kg", "max"),
            basta_reps=("reps", "max"),
            basta_est_1rm=("est_1rm", "max"),
            total_volym=("volym", "sum"),
            antal_set=("set_nr", "count"),
        )
        .sort_values(["basta_est_1rm", "tyngsta_vikt"], ascending=False)
    )
    summary["basta_est_1rm"] = summary["basta_est_1rm"].round(1)
    summary["total_volym"] = summary["total_volym"].round(0).astype(int)
    return summary


def trend_dataframe(exercise_name: str) -> pd.DataFrame:
    df = export_dataframe()
    if df.empty:
        return df
    df = df[df["ovning"] == exercise_name].copy()
    if df.empty:
        return df
    df["est_1rm"] = df["vikt_kg"] * (1 + df["reps"] / 30)
    df["volym"] = df["vikt_kg"] * df["reps"]
    return (
        df.groupby("datum", as_index=False)
        .agg(est_1rm=("est_1rm", "max"), volym=("volym", "sum"), toppvikt=("vikt_kg", "max"))
        .sort_values("datum")
    )


def recent_workouts(limit: int = 20) -> list[sqlite3.Row]:
    if use_supabase():
        return (
            supabase_client()
            .table("workouts")
            .select("id, workout_date, day_name, notes")
            .order("workout_date", desc=True)
            .order("id", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )

    with db_connection() as conn:
        return conn.execute(
            """
            SELECT id, workout_date, day_name, notes
            FROM workouts
            ORDER BY workout_date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def sets_for_workout(workout_id: int) -> list[sqlite3.Row]:
    if use_supabase():
        return (
            supabase_client()
            .table("workout_sets")
            .select("set_no, reps, weight_kg, is_pr, exercises(name)")
            .eq("workout_id", workout_id)
            .order("set_no")
            .execute()
            .data
            or []
        )

    with db_connection() as conn:
        return conn.execute(
            """
            SELECT e.name, ws.set_no, ws.reps, ws.weight_kg, ws.is_pr
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.workout_id = ?
            ORDER BY e.name, ws.set_no
            """,
            (workout_id,),
        ).fetchall()


def export_dataframe() -> pd.DataFrame:
    if use_supabase():
        rows = (
            supabase_client()
            .table("workout_sets")
            .select("set_no, weight_kg, reps, is_pr, workouts(workout_date, day_name), exercises(name)")
            .order("id")
            .execute()
            .data
            or []
        )
        data = [
            {
                "datum": (row.get("workouts") or {}).get("workout_date"),
                "pass": (row.get("workouts") or {}).get("day_name"),
                "ovning": (row.get("exercises") or {}).get("name"),
                "set_nr": row.get("set_no"),
                "vikt_kg": row.get("weight_kg"),
                "reps": row.get("reps"),
                "pb": row.get("is_pr"),
            }
            for row in rows
        ]
        return pd.DataFrame(data)

    with db_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT
                w.workout_date AS datum,
                w.day_name AS pass,
                e.name AS ovning,
                ws.set_no AS set_nr,
                ws.weight_kg AS vikt_kg,
                ws.reps AS reps,
                ws.is_pr AS pb
            FROM workout_sets ws
            JOIN workouts w ON w.id = ws.workout_id
            JOIN exercises e ON e.id = ws.exercise_id
            ORDER BY w.workout_date, w.id, e.name, ws.set_no
            """,
            conn,
        )


def page_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        :root {
            --ink: #111111;
            --muted: #69707d;
            --line: #dfe3ea;
            --paper: #f7f8fa;
            --panel: #ffffff;
            --accent: #0e7c66;
            --accent-2: #c09342;
            --soft: #edf7f4;
        }
        html, body, [class*="css"] { font-family: Inter, system-ui, sans-serif; letter-spacing: 0; }
        body, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 20% 0%, rgba(14,124,102,.10), transparent 28rem),
                linear-gradient(180deg, #fbfbfc 0%, #f4f6f8 100%);
            color: var(--ink);
        }
        .block-container { padding-top: 1rem; padding-bottom: 6rem; max-width: 820px; }
        [data-testid="stHeader"] { background: rgba(251,251,252,.82); backdrop-filter: blur(16px); }
        h1, h2, h3 { letter-spacing: 0; color: var(--ink); }
        h1 { font-size: clamp(2.1rem, 8vw, 3.4rem); line-height: .95; margin-bottom: .4rem; }
        h2 { font-size: 1.25rem; }
        h3 { font-size: 1.02rem; }
        .topline { color: var(--muted); margin: -0.2rem 0 1.1rem; font-size: 1rem; }
        .hero {
            border: 1px solid rgba(17,17,17,.08);
            border-radius: 8px;
            padding: 1rem;
            background:
                linear-gradient(135deg, rgba(17,17,17,.96), rgba(38,42,48,.94)),
                #111;
            color: white;
            box-shadow: 0 18px 44px rgba(17,17,17,.16);
            margin: 1.2rem 0 .9rem;
        }
        .hero .eyebrow {
            color: rgba(255,255,255,.62);
            font-size: .78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .12rem;
        }
        .hero .title {
            font-size: clamp(2.2rem, 11vw, 4rem);
            line-height: .9;
            font-weight: 800;
            margin-top: .35rem;
        }
        .metric-row {
            display: grid; grid-template-columns: repeat(3, 1fr); gap: .65rem; margin: .9rem 0 1rem;
        }
        .mini-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: .75rem .8rem;
            background: rgba(255,255,255,.88);
            box-shadow: 0 10px 28px rgba(17,17,17,.05);
        }
        .mini-card span { display: block; color: var(--muted); font-size: .76rem; font-weight: 700; }
        .mini-card strong { display: block; color: var(--ink); font-size: 1.12rem; margin-top: .14rem; }
        .section-note { color: var(--muted); margin-bottom: .8rem; }
        .suggestion {
            display: flex;
            justify-content: space-between;
            gap: .8rem;
            align-items: center;
            border: 1px solid rgba(14,124,102,.22);
            background: var(--soft);
            border-radius: 8px;
            padding: .7rem .78rem;
            margin: .45rem 0 .7rem;
        }
        .suggestion strong { color: var(--accent); font-size: .96rem; }
        .suggestion span { color: #4f5f5b; font-size: .82rem; display: block; margin-top: .12rem; }
        .exercise-head {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: .8rem;
            margin-bottom: .35rem;
        }
        .exercise-title { font-weight: 800; font-size: 1.12rem; line-height: 1.15; }
        .hint { color: var(--muted); font-size: .88rem; margin-top: .16rem; }
        .chip {
            white-space: nowrap;
            border: 1px solid rgba(192,147,66,.35);
            background: rgba(192,147,66,.11);
            color: #77531c;
            border-radius: 999px;
            padding: .22rem .54rem;
            font-size: .74rem;
            font-weight: 800;
        }
        .pb { color: var(--accent); font-weight: 800; }
        .pr { color: var(--accent); font-weight: 800; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px;
            border-color: rgba(17,17,17,.10);
            box-shadow: 0 14px 34px rgba(17,17,17,.055);
            background: rgba(255,255,255,.9);
        }
        .stButton > button, [data-testid="stFormSubmitButton"] button, .stDownloadButton button {
            min-height: 3.25rem;
            border-radius: 8px;
            font-weight: 800;
            border: 1px solid rgba(17,17,17,.12);
        }
        [data-testid="stFormSubmitButton"] button {
            background: #111 !important;
            color: white !important;
        }
        div[data-baseweb="tab-list"] { gap: .35rem; }
        button[data-baseweb="tab"] {
            border-radius: 999px;
            padding: .45rem .7rem;
            background: rgba(255,255,255,.75);
            border: 1px solid rgba(17,17,17,.08);
            color: #111 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: #111;
            color: white !important;
        }
        label, .stTextInput label, .stNumberInput label, .stTextArea label, .stSelectbox label {
            font-weight: 700 !important;
            color: #343841 !important;
        }
        [data-testid="stCheckbox"] label,
        [data-testid="stCheckbox"] label span,
        [data-testid="stCheckbox"] p {
            color: #111111 !important;
            opacity: 1 !important;
            font-weight: 800 !important;
        }
        input, textarea {
            border-radius: 8px !important;
            background: #ffffff !important;
            color: #111111 !important;
            caret-color: #111111 !important;
        }
        div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
            background: #ffffff !important;
            color: #111111 !important;
            border-color: #dfe3ea !important;
        }
        div[data-baseweb="select"] span, div[data-baseweb="select"] svg {
            color: #111111 !important;
            fill: #111111 !important;
        }
        @media (max-width: 620px) {
            .block-container { padding-left: .8rem; padding-right: .8rem; padding-top: .65rem; }
            .hero { padding: .95rem; }
            .metric-row { grid-template-columns: 1fr 1fr; gap: .5rem; }
            .metric-row .mini-card:last-child { grid-column: 1 / -1; }
            .suggestion { align-items: flex-start; flex-direction: column; }
            .exercise-head { flex-direction: column; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_today() -> None:
    default_day = suggested_day()
    st.markdown("<div class='section-note'>Logga snabbt. Appen föreslår vikt från din senaste prestation.</div>", unsafe_allow_html=True)
    selected_day = st.selectbox(
        "Pass",
        DAY_NAMES,
        index=DAY_NAMES.index(st.session_state.get("selected_day", default_day)),
        key="selected_day",
    )
    workout_date = st.date_input("Datum", value=date.today())
    plan = list_program(selected_day)

    if not plan:
        st.info("Det finns inget program än. Gå till Program och skapa startprogrammet.")
        return

    logged: list[dict] = []
    with st.form("log_workout_form", clear_on_submit=False):
        notes = st.text_area("Anteckning", placeholder="Valfritt, t.ex. sömn, energi eller skada.")

        for exercise in plan:
            pb = best_for_exercise(exercise.name)
            suggestion = suggest_weight(exercise)
            with st.container(border=True):
                safe_name = escape(exercise.name)
                hint = f"{exercise.sets} set · {exercise.rep_min}-{exercise.rep_max} reps"
                if pb:
                    hint += f" · PB {pb[0]:g} kg x {pb[1]}"
                st.markdown(
                    f"""
                    <div class="exercise-head">
                        <div>
                            <div class="exercise-title">{safe_name}</div>
                            <div class="hint">{escape(hint)}</div>
                        </div>
                        <div class="chip">Mål</div>
                    </div>
                    <div class="suggestion">
                        <div>
                            <strong>{escape(suggestion.label)}</strong>
                            <span>{escape(suggestion.reason)}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                done = st.checkbox("Klar", key=f"done_{exercise.id}")
                weight = st.number_input(
                    "Vikt kg",
                    min_value=0.0,
                    max_value=500.0,
                    value=float(suggestion.weight),
                    step=0.5,
                    key=f"weight_{exercise.id}",
                )

                reps: list[int] = []
                columns = st.columns(min(exercise.sets, 4))
                for set_index in range(1, exercise.sets + 1):
                    column = columns[(set_index - 1) % len(columns)]
                    with column:
                        reps.append(
                            st.number_input(
                                f"Set {set_index}",
                                min_value=0,
                                max_value=100,
                                value=exercise.rep_min,
                                step=1,
                                key=f"reps_{exercise.id}_{set_index}",
                            )
                        )

            if done:
                logged.append({"name": exercise.name, "weight_kg": float(weight), "reps": reps})

        submitted = st.form_submit_button("Spara pass", use_container_width=True)

    if submitted:
        try:
            save_workout(selected_day, workout_date, notes, logged)
        except Exception as exc:
            st.error(str(exc))
        else:
            next_index = (DAY_NAMES.index(selected_day) + 1) % len(DAY_NAMES)
            st.session_state["selected_day"] = DAY_NAMES[next_index]
            st.success("Passet är sparat.")
            st.rerun()


def render_program() -> None:
    st.markdown("<div class='section-note'>Ändra programmet direkt här. Historiken påverkas inte.</div>", unsafe_allow_html=True)
    selected_day = st.selectbox("Välj pass att redigera", DAY_NAMES, key="program_editor_day")
    rows = list_program(selected_day)

    if rows:
        for row in rows:
            with st.expander(f"{row.sort_order}. {row.name} · {row.sets} set · {row.rep_min}-{row.rep_max} reps"):
                with st.form(f"edit_program_{row.id}"):
                    sort_order = st.number_input("Ordning", 1, 50, int(row.sort_order), key=f"sort_{row.id}")
                    sets = st.number_input("Set", 1, 10, int(row.sets), key=f"sets_{row.id}")
                    rep_min = st.number_input("Rep min", 1, 50, int(row.rep_min), key=f"min_{row.id}")
                    rep_max = st.number_input("Rep max", 1, 50, int(row.rep_max), key=f"max_{row.id}")
                    col_save, col_remove = st.columns(2)
                    with col_save:
                        save = st.form_submit_button("Spara ändring", use_container_width=True)
                    with col_remove:
                        remove = st.form_submit_button("Ta bort från pass", use_container_width=True)

                if save:
                    if rep_max < rep_min:
                        st.error("Rep max måste vara minst lika högt som rep min.")
                    else:
                        update_program_exercise(row.id, int(sets), int(rep_min), int(rep_max), int(sort_order))
                        st.success("Programmet är uppdaterat.")
                        st.rerun()
                if remove:
                    deactivate_program_exercise(row.id)
                    st.success("Övningen är borttagen från passet.")
                    st.rerun()
    else:
        st.info("Det här passet har inga övningar än.")

    st.subheader("Lägg till övning")
    with st.form("add_program_exercise"):
        name = st.text_input("Övningsnamn", placeholder="T.ex. Latsdrag")
        col1, col2, col3 = st.columns(3)
        with col1:
            sets = st.number_input("Set", 1, 10, 3, key="add_sets")
        with col2:
            rep_min = st.number_input("Rep min", 1, 50, 8, key="add_min")
        with col3:
            rep_max = st.number_input("Rep max", 1, 50, 12, key="add_max")
        add = st.form_submit_button("Lägg till i passet", use_container_width=True)

    if add:
        try:
            add_program_exercise(selected_day, name, int(sets), int(rep_min), int(rep_max))
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Övningen är tillagd.")
            st.rerun()


def render_personal_bests() -> None:
    summary = pb_summary_dataframe()
    if summary.empty:
        st.info("Spara några pass först, så bygger appen en PB-sida åt dig.")
        return

    top = summary.iloc[0]
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="mini-card"><span>Starkaste lyft</span><strong>{escape(str(top['ovning']))}</strong></div>
            <div class="mini-card"><span>Estimerat max</span><strong>{top['basta_est_1rm']:g} kg</strong></div>
            <div class="mini-card"><span>Tyngsta vikt</span><strong>{top['tyngsta_vikt']:g} kg</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    visible = summary.rename(
        columns={
            "ovning": "Övning",
            "tyngsta_vikt": "Tyngsta vikt",
            "basta_reps": "Bästa reps",
            "basta_est_1rm": "Est. 1RM",
            "total_volym": "Total volym",
            "antal_set": "Set",
        }
    )
    st.dataframe(visible, use_container_width=True, hide_index=True)


def render_charts() -> None:
    summary = pb_summary_dataframe()
    if summary.empty:
        st.info("När du har sparat pass kan du se utvecklingen här.")
        return

    exercise_name = st.selectbox("Övning", summary["ovning"].tolist())
    trend = trend_dataframe(exercise_name)
    if trend.empty:
        st.info("Ingen trend hittades för den övningen.")
        return

    chart = trend.set_index("datum")[["est_1rm", "toppvikt"]]
    chart = chart.rename(columns={"est_1rm": "Est. 1RM", "toppvikt": "Toppvikt"})
    st.line_chart(chart, use_container_width=True)
    volume = trend.set_index("datum")[["volym"]].rename(columns={"volym": "Volym"})
    st.bar_chart(volume, use_container_width=True)


def render_history() -> None:
    workouts = recent_workouts()
    if not workouts:
        st.info("Ingen historik än. Spara ditt första pass så dyker det upp här.")
        return

    for workout in workouts:
        with st.expander(f"{workout['workout_date']} · {workout['day_name']}"):
            if workout["notes"]:
                st.caption(workout["notes"])
            for row in sets_for_workout(workout["id"]):
                name = row["name"] if isinstance(row, sqlite3.Row) else (row.get("exercises") or {}).get("name", "Okänd övning")
                marker = " PB" if row["is_pr"] else ""
                st.write(
                    f"{name} · set {row['set_no']}: "
                    f"{row['weight_kg']:g} kg x {row['reps']} reps{marker}"
                )


def render_export() -> None:
    df = export_dataframe()
    if df.empty:
        st.info("Det finns inget att exportera än.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "Ladda ner CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="gymapp-export.csv",
        mime="text/csv",
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(page_title="Gymapp v2", page_icon="🏋️", layout="centered")
    page_styles()
    require_pin_if_configured()
    init_db()
    seed_starter_program()

    workouts_done = count_workouts()
    st.markdown(
        """
        <div class="hero">
            <div class="eyebrow">Gymapp v2.1</div>
            <div class="title">Lyftlogg</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="mini-card"><span>Träningspass</span><strong>{workouts_done}</strong></div>
            <div class="mini-card"><span>Nästa förslag</span><strong>{suggested_day()}</strong></div>
            <div class="mini-card"><span>Databas</span><strong>Lokal</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    today_tab, program_tab, pb_tab, chart_tab, history_tab, export_tab = st.tabs(
        ["Idag", "Program", "PB", "Trend", "Historik", "Export"]
    )
    with today_tab:
        render_today()
    with program_tab:
        render_program()
    with pb_tab:
        render_personal_bests()
    with chart_tab:
        render_charts()
    with history_tab:
        render_history()
    with export_tab:
        render_export()


if __name__ == "__main__":
    main()
