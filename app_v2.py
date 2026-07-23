from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from supabase import Client, create_client
except Exception:  # Supabase is only required in cloud mode.
    Client = Any
    create_client = None


APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "gymapp.db"
DAY_NAMES = ["Pass 1", "Pass 2", "Pass 3", "Pass 4"]
VIEWS = ["Idag", "Program", "PB", "Trend", "Historik", "Profiler", "Export"]
TECHNIQUE_DEMOS = {
    "lat pulldown": "lat_pulldown.html",
    "lat pull down": "lat_pulldown.html",
    "latsdrag": "lat_pulldown.html",
}

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


@dataclass(frozen=True)
class Profile:
    id: int
    name: str


@dataclass(frozen=True)
class ProgramExercise:
    id: int
    exercise_id: int
    name: str
    day_name: str
    sort_order: int
    sets: int
    rep_min: int
    rep_max: int
    start_weight_kg: float | None = None
    start_reps: tuple[int, ...] = ()


@dataclass(frozen=True)
class WeightSuggestion:
    weight: float
    label: str
    reason: str


def _secret_value(section: str, key: str) -> str | None:
    env_key = f"{section}_{key}".upper()
    if os.environ.get(env_key):
        return os.environ[env_key]
    try:
        if section in st.secrets and key in st.secrets[section]:
            return str(st.secrets[section][key])
    except Exception:
        return None
    return None


def app_pin() -> str | None:
    if os.environ.get("APP_PIN"):
        return os.environ["APP_PIN"]
    try:
        if "APP_PIN" in st.secrets:
            return str(st.secrets["APP_PIN"])
    except Exception:
        return None
    return _secret_value("app", "pin")


def require_pin_if_configured() -> None:
    pin = app_pin()
    if not pin or st.session_state.get("unlocked"):
        return

    st.markdown(
        """
        <div class="hero login-hero">
            <div class="eyebrow">Privat app</div>
            <div class="title">Lyftlogg</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    typed = st.text_input("PIN", type="password", placeholder="Ange din PIN")
    if st.button("Lås upp", use_container_width=True, type="primary"):
        if typed == pin:
            st.session_state["unlocked"] = True
            st.rerun()
        else:
            st.error("Fel PIN.")
    st.stop()


def supabase_credentials() -> tuple[str | None, str | None]:
    url = _secret_value("supabase", "url")
    # A server-only key lets RLS block direct public API access. Keep anon_key as migration fallback.
    key = (
        _secret_value("supabase", "service_role_key")
        or _secret_value("supabase", "secret_key")
        or _secret_value("supabase", "anon_key")
    )
    return url, key


def use_supabase() -> bool:
    url, key = supabase_credentials()
    return bool(url and key)


def uses_server_key() -> bool:
    return bool(
        _secret_value("supabase", "service_role_key")
        or _secret_value("supabase", "secret_key")
    )


@st.cache_resource
def supabase_client() -> Client:
    if create_client is None:
        st.error("Supabase-paketet saknas.")
        st.stop()
    url, key = supabase_credentials()
    if not url or not key:
        st.error("Supabase-inställningarna saknas.")
        st.stop()
    return create_client(url, key)


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


def _sqlite_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _sqlite_has_legacy_program_constraint(conn: sqlite3.Connection) -> bool:
    for index in conn.execute("PRAGMA index_list(program_exercises)"):
        if not index["unique"]:
            continue
        columns = [
            row["name"]
            for row in conn.execute(f"PRAGMA index_info('{index['name']}')")
        ]
        if columns == ["day_name", "exercise_id"]:
            return True
    return False


def _migrate_local_program_profiles(conn: sqlite3.Connection, default_profile_id: int) -> None:
    has_profile_id = _sqlite_column_exists(conn, "program_exercises", "profile_id")
    if has_profile_id and not _sqlite_has_legacy_program_constraint(conn):
        return

    conn.execute("ALTER TABLE program_exercises RENAME TO program_exercises_legacy")
    conn.execute(
        """
        CREATE TABLE program_exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            day_name TEXT NOT NULL,
            exercise_id INTEGER NOT NULL REFERENCES exercises(id),
            sort_order INTEGER NOT NULL,
            sets INTEGER NOT NULL,
            rep_min INTEGER NOT NULL,
            rep_max INTEGER NOT NULL,
            start_weight_kg REAL,
            start_reps TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(profile_id, day_name, exercise_id)
        )
        """
    )
    if has_profile_id:
        conn.execute(
            """
            INSERT INTO program_exercises
                (id, profile_id, day_name, exercise_id, sort_order, sets, rep_min, rep_max, active)
            SELECT id, COALESCE(profile_id, ?), day_name, exercise_id,
                   sort_order, sets, rep_min, rep_max, active
            FROM program_exercises_legacy
            """,
            (default_profile_id,),
        )
    else:
        conn.execute(
            """
            INSERT INTO program_exercises
                (id, profile_id, day_name, exercise_id, sort_order, sets, rep_min, rep_max, active)
            SELECT id, ?, day_name, exercise_id, sort_order, sets, rep_min, rep_max, active
            FROM program_exercises_legacy
            """,
            (default_profile_id,),
        )
    conn.execute("DROP TABLE program_exercises_legacy")


def init_db() -> None:
    if use_supabase():
        return
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS program_exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                day_name TEXT NOT NULL,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id),
                sort_order INTEGER NOT NULL,
                sets INTEGER NOT NULL,
                rep_min INTEGER NOT NULL,
                rep_max INTEGER NOT NULL,
                start_weight_kg REAL,
                start_reps TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER REFERENCES profiles(id),
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
                is_pr INTEGER NOT NULL DEFAULT 0,
                UNIQUE(workout_id, exercise_id, set_no)
            );
            """
        )

        default = conn.execute("SELECT id FROM profiles ORDER BY id LIMIT 1").fetchone()
        if not default:
            default_id = conn.execute(
                "INSERT INTO profiles(name, created_at) VALUES (?, ?)",
                ("Tobias", datetime.now().isoformat(timespec="seconds")),
            ).lastrowid
        else:
            default_id = default["id"]

        _migrate_local_program_profiles(conn, int(default_id))
        if not _sqlite_column_exists(conn, "program_exercises", "start_weight_kg"):
            conn.execute("ALTER TABLE program_exercises ADD COLUMN start_weight_kg REAL")
        if not _sqlite_column_exists(conn, "program_exercises", "start_reps"):
            conn.execute("ALTER TABLE program_exercises ADD COLUMN start_reps TEXT")
        if not _sqlite_column_exists(conn, "workouts", "profile_id"):
            conn.execute("ALTER TABLE workouts ADD COLUMN profile_id INTEGER REFERENCES profiles(id)")
        conn.execute("UPDATE workouts SET profile_id = ? WHERE profile_id IS NULL", (default_id,))
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS program_profile_exercise_idx "
            "ON program_exercises(profile_id, day_name, exercise_id)"
        )


def clear_data_cache() -> None:
    st.cache_data.clear()


@st.cache_data(ttl=30, show_spinner=False)
def list_profiles() -> list[Profile]:
    if use_supabase():
        rows = supabase_client().table("profiles").select("id,name").order("id").execute().data or []
        return [Profile(int(row["id"]), row["name"]) for row in rows]
    with db_connection() as conn:
        rows = conn.execute("SELECT id,name FROM profiles ORDER BY id").fetchall()
    return [Profile(int(row["id"]), row["name"]) for row in rows]


def _ensure_exercise(name: str) -> int:
    if use_supabase():
        sb = supabase_client()
        rows = sb.table("exercises").select("id").eq("name", name).limit(1).execute().data or []
        if rows:
            return int(rows[0]["id"])
        return int(sb.table("exercises").insert({"name": name}).execute().data[0]["id"])
    with db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO exercises(name) VALUES (?)", (name,))
        return int(conn.execute("SELECT id FROM exercises WHERE name = ?", (name,)).fetchone()["id"])


def seed_program_for_profile(profile_id: int) -> None:
    if use_supabase():
        sb = supabase_client()
        existing = (
            sb.table("program_exercises")
            .select("id")
            .eq("profile_id", profile_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            return
        rows = []
        for day_name, exercises in STARTER_PROGRAM.items():
            for order, (name, sets, rep_min, rep_max) in enumerate(exercises, start=1):
                rows.append(
                    {
                        "profile_id": profile_id,
                        "day_name": day_name,
                        "exercise_id": _ensure_exercise(name),
                        "sort_order": order,
                        "sets": sets,
                        "rep_min": rep_min,
                        "rep_max": rep_max,
                        "active": True,
                    }
                )
        sb.table("program_exercises").insert(rows).execute()
        return

    with db_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM program_exercises WHERE profile_id = ? LIMIT 1", (profile_id,)
        ).fetchone()
        if exists:
            return
        for day_name, exercises in STARTER_PROGRAM.items():
            for order, (name, sets, rep_min, rep_max) in enumerate(exercises, start=1):
                conn.execute("INSERT OR IGNORE INTO exercises(name) VALUES (?)", (name,))
                exercise_id = conn.execute(
                    "SELECT id FROM exercises WHERE name = ?", (name,)
                ).fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO program_exercises
                        (profile_id, day_name, exercise_id, sort_order, sets, rep_min, rep_max, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (profile_id, day_name, exercise_id, order, sets, rep_min, rep_max),
                )


def create_profile(name: str) -> Profile:
    clean_name = " ".join(name.strip().split())
    if not clean_name:
        raise ValueError("Skriv ett namn på profilen.")
    if len(clean_name) > 40:
        raise ValueError("Profilnamnet får vara högst 40 tecken.")

    if use_supabase():
        rows = supabase_client().table("profiles").insert(
            {"name": clean_name, "created_at": datetime.now().isoformat(timespec="seconds")}
        ).execute().data
        profile = Profile(int(rows[0]["id"]), rows[0]["name"])
    else:
        with db_connection() as conn:
            profile_id = conn.execute(
                "INSERT INTO profiles(name, created_at) VALUES (?, ?)",
                (clean_name, datetime.now().isoformat(timespec="seconds")),
            ).lastrowid
        profile = Profile(int(profile_id), clean_name)

    seed_program_for_profile(profile.id)
    clear_data_cache()
    return profile


def list_program(profile_id: int, day_name: str) -> list[ProgramExercise]:
    if use_supabase():
        rows = (
            supabase_client()
            .table("program_exercises")
            .select("id,exercise_id,day_name,sort_order,sets,rep_min,rep_max,start_weight_kg,start_reps,exercises(name)")
            .eq("profile_id", profile_id)
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
                exercise_id=int(row["exercise_id"]),
                name=(row.get("exercises") or {}).get("name", "Okänd övning"),
                day_name=row["day_name"],
                sort_order=int(row["sort_order"]),
                sets=int(row["sets"]),
                rep_min=int(row["rep_min"]),
                rep_max=int(row["rep_max"]),
                start_weight_kg=float(row["start_weight_kg"]) if row.get("start_weight_kg") is not None else None,
                start_reps=tuple(int(value) for value in (row.get("start_reps") or [])),
            )
            for row in rows
        ]

    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT pe.id, pe.exercise_id, e.name, pe.day_name, pe.sort_order,
                   pe.sets, pe.rep_min, pe.rep_max, pe.start_weight_kg, pe.start_reps
            FROM program_exercises pe
            JOIN exercises e ON e.id = pe.exercise_id
            WHERE pe.profile_id = ? AND pe.day_name = ? AND pe.active = 1
            ORDER BY pe.sort_order, e.name
            """,
            (profile_id, day_name),
        ).fetchall()
    return [
        ProgramExercise(
            id=int(row["id"]),
            exercise_id=int(row["exercise_id"]),
            name=row["name"],
            day_name=row["day_name"],
            sort_order=int(row["sort_order"]),
            sets=int(row["sets"]),
            rep_min=int(row["rep_min"]),
            rep_max=int(row["rep_max"]),
            start_weight_kg=float(row["start_weight_kg"]) if row["start_weight_kg"] is not None else None,
            start_reps=tuple(int(value) for value in json.loads(row["start_reps"] or "[]")),
        )
        for row in rows
    ]


@st.cache_data(ttl=30, show_spinner=False)
def profile_overview(profile_id: int) -> tuple[int, str | None]:
    if use_supabase():
        result = (
            supabase_client()
            .table("workouts")
            .select("id,day_name", count="exact")
            .eq("profile_id", profile_id)
            .order("workout_date", desc=True)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return int(result.count or 0), rows[0]["day_name"] if rows else None
    with db_connection() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM workouts WHERE profile_id = ?", (profile_id,)).fetchone()[0])
        row = conn.execute(
            "SELECT day_name FROM workouts WHERE profile_id = ? ORDER BY workout_date DESC, id DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
    return count, row["day_name"] if row else None


def suggested_day(profile_id: int) -> str:
    _, last_day = profile_overview(profile_id)
    if last_day not in DAY_NAMES:
        return DAY_NAMES[0]
    return DAY_NAMES[(DAY_NAMES.index(last_day) + 1) % len(DAY_NAMES)]


@st.cache_data(ttl=30, show_spinner=False)
def history_dataframe(profile_id: int) -> pd.DataFrame:
    columns = ["workout_id", "set_id", "datum", "pass", "anteckning", "ovning", "exercise_id", "set_nr", "vikt_kg", "reps", "pb"]
    if use_supabase():
        rows = (
            supabase_client()
            .table("workout_sets")
            .select(
                "id,exercise_id,set_no,weight_kg,reps,is_pr,"
                "workouts!inner(id,profile_id,workout_date,day_name,notes),exercises(name)"
            )
            .eq("workouts.profile_id", profile_id)
            .order("id")
            .execute()
            .data
            or []
        )
        data = []
        for row in rows:
            workout = row.get("workouts") or {}
            exercise = row.get("exercises") or {}
            data.append(
                {
                    "workout_id": workout.get("id"),
                    "set_id": row.get("id"),
                    "datum": workout.get("workout_date"),
                    "pass": workout.get("day_name"),
                    "anteckning": workout.get("notes") or "",
                    "ovning": exercise.get("name"),
                    "exercise_id": row.get("exercise_id"),
                    "set_nr": row.get("set_no"),
                    "vikt_kg": row.get("weight_kg"),
                    "reps": row.get("reps"),
                    "pb": row.get("is_pr"),
                }
            )
        return pd.DataFrame(data, columns=columns)

    with db_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT w.id AS workout_id, ws.id AS set_id, w.workout_date AS datum,
                   w.day_name AS pass, w.notes AS anteckning, e.name AS ovning,
                   ws.exercise_id, ws.set_no AS set_nr, ws.weight_kg AS vikt_kg,
                   ws.reps, ws.is_pr AS pb
            FROM workout_sets ws
            JOIN workouts w ON w.id = ws.workout_id
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE w.profile_id = ?
            ORDER BY w.workout_date, w.id, ws.id
            """,
            conn,
            params=(profile_id,),
        )


def best_for_exercise(name: str, history: pd.DataFrame) -> tuple[float, int] | None:
    rows = history[history["ovning"] == name]
    if rows.empty:
        return None
    max_weight = float(rows["vikt_kg"].max())
    max_reps = int(rows.loc[rows["vikt_kg"].astype(float) == max_weight, "reps"].max())
    return max_weight, max_reps


def weight_step_for(name: str) -> float:
    barbell_lower = ["knäböj", "frontböj", "marklyft", "raka marklyft"]
    return 5.0 if any(term in name.lower() for term in barbell_lower) else 2.5


def suggest_weight(exercise: ProgramExercise, history: pd.DataFrame) -> WeightSuggestion:
    rows = history[history["exercise_id"].astype(str) == str(exercise.exercise_id)] if not history.empty else history
    if rows.empty:
        if exercise.start_weight_kg is not None:
            return WeightSuggestion(
                exercise.start_weight_kg,
                f"Börja på {exercise.start_weight_kg:g} kg",
                "Startvärde från din tidigare träningslogg.",
            )
        return WeightSuggestion(0.0, "Välj startvikt", "Första gången du loggar övningen.")

    rows = rows.sort_values(["datum", "workout_id", "set_nr"])
    latest_workout = rows.iloc[-1]["workout_id"]
    latest = rows[rows["workout_id"] == latest_workout].sort_values("set_nr")
    last_weight = float(latest.iloc[-1]["vikt_kg"])
    reps = [int(value) for value in latest["reps"].tolist()]
    step = weight_step_for(exercise.name)

    if len(reps) < exercise.sets:
        return WeightSuggestion(last_weight, f"Behåll {last_weight:g} kg", "Förra loggen hade färre set än programmet.")
    if all(rep >= exercise.rep_max for rep in reps):
        suggested = last_weight + step
        return WeightSuggestion(suggested, f"Höj till {suggested:g} kg", "Alla set nådde övre repmålet senast.")
    if all(rep < exercise.rep_min for rep in reps):
        suggested = max(0.0, last_weight - step)
        return WeightSuggestion(suggested, f"Sänk till {suggested:g} kg", "Alla set låg under repmålet senast.")
    return WeightSuggestion(last_weight, f"Behåll {last_weight:g} kg", f"Senast: {', '.join(map(str, reps))} reps.")


def suggested_reps(exercise: ProgramExercise, history: pd.DataFrame) -> list[int]:
    rows = history[history["exercise_id"].astype(str) == str(exercise.exercise_id)] if not history.empty else history
    if rows.empty:
        values = list(exercise.start_reps)
    else:
        rows = rows.sort_values(["datum", "workout_id", "set_nr"])
        latest_workout = rows.iloc[-1]["workout_id"]
        values = [int(value) for value in rows[rows["workout_id"] == latest_workout]["reps"].tolist()]
    return (values + [exercise.rep_min] * exercise.sets)[: exercise.sets]


def _pr_flags(exercise_id: int, weight: float, reps: list[int], history: pd.DataFrame) -> list[bool]:
    if history.empty:
        running_best = 0
    else:
        previous = history[
            (history["exercise_id"].astype(str) == str(exercise_id))
            & (history["vikt_kg"].astype(float) == float(weight))
        ]
        running_best = int(previous["reps"].max()) if not previous.empty else 0
    flags = []
    for rep in reps:
        flags.append(rep > running_best)
        running_best = max(running_best, rep)
    return flags


def save_workout(profile_id: int, day_name: str, workout_date: date, notes: str, logged: list[dict], history: pd.DataFrame) -> None:
    if not logged:
        raise ValueError("Markera minst en övning som klar.")

    set_rows = []
    for item in logged:
        flags = _pr_flags(item["exercise_id"], item["weight_kg"], item["reps"], history)
        for set_no, (reps, is_pr) in enumerate(zip(item["reps"], flags), start=1):
            set_rows.append(
                {
                    "exercise_id": item["exercise_id"],
                    "set_no": set_no,
                    "reps": int(reps),
                    "weight_kg": float(item["weight_kg"]),
                    "is_pr": bool(is_pr),
                }
            )

    now = datetime.now().isoformat(timespec="seconds")
    if use_supabase():
        sb = supabase_client()
        try:
            sb.rpc(
                "save_workout_atomic",
                {
                    "p_profile_id": profile_id,
                    "p_workout_date": workout_date.isoformat(),
                    "p_day_name": day_name,
                    "p_notes": notes.strip(),
                    "p_sets": set_rows,
                },
            ).execute()
        except Exception as exc:
            raise RuntimeError("Kunde inte spara passet atomiskt. Databasen behöver v3-migreringen.") from exc
        clear_data_cache()
        return

    with db_connection() as conn:
        workout_id = conn.execute(
            """
            INSERT INTO workouts(profile_id, workout_date, day_name, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, workout_date.isoformat(), day_name, notes.strip(), now),
        ).lastrowid
        conn.executemany(
            """
            INSERT INTO workout_sets(workout_id, exercise_id, set_no, reps, weight_kg, is_pr)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (workout_id, row["exercise_id"], row["set_no"], row["reps"], row["weight_kg"], int(row["is_pr"]))
                for row in set_rows
            ],
        )
    clear_data_cache()


def update_program_exercise(row_id: int, profile_id: int, sets: int, rep_min: int, rep_max: int, sort_order: int) -> None:
    payload = {"sets": sets, "rep_min": rep_min, "rep_max": rep_max, "sort_order": sort_order}
    if use_supabase():
        supabase_client().table("program_exercises").update(payload).eq("id", row_id).eq("profile_id", profile_id).execute()
    else:
        with db_connection() as conn:
            conn.execute(
                "UPDATE program_exercises SET sets=?, rep_min=?, rep_max=?, sort_order=? WHERE id=? AND profile_id=?",
                (sets, rep_min, rep_max, sort_order, row_id, profile_id),
            )
    clear_data_cache()


def add_program_exercise(profile_id: int, day_name: str, name: str, sets: int, rep_min: int, rep_max: int) -> None:
    clean_name = " ".join(name.strip().split())
    if not clean_name:
        raise ValueError("Skriv ett övningsnamn först.")
    if rep_max < rep_min:
        raise ValueError("Rep max måste vara minst lika högt som rep min.")
    exercise_id = _ensure_exercise(clean_name)

    if use_supabase():
        sb = supabase_client()
        existing = (
            sb.table("program_exercises")
            .select("id")
            .eq("profile_id", profile_id)
            .eq("day_name", day_name)
            .eq("exercise_id", exercise_id)
            .limit(1)
            .execute().data or []
        )
        orders = (
            sb.table("program_exercises")
            .select("sort_order")
            .eq("profile_id", profile_id)
            .eq("day_name", day_name)
            .order("sort_order", desc=True)
            .limit(1)
            .execute().data or []
        )
        order = int(orders[0]["sort_order"]) + 1 if orders else 1
        payload = {
            "profile_id": profile_id,
            "day_name": day_name,
            "exercise_id": exercise_id,
            "sort_order": order,
            "sets": sets,
            "rep_min": rep_min,
            "rep_max": rep_max,
            "active": True,
        }
        if existing:
            sb.table("program_exercises").update(payload).eq("id", existing[0]["id"]).execute()
        else:
            sb.table("program_exercises").insert(payload).execute()
    else:
        with db_connection() as conn:
            order = int(conn.execute(
                "SELECT COALESCE(MAX(sort_order),0)+1 FROM program_exercises WHERE profile_id=? AND day_name=?",
                (profile_id, day_name),
            ).fetchone()[0])
            conn.execute(
                """
                INSERT INTO program_exercises(profile_id,day_name,exercise_id,sort_order,sets,rep_min,rep_max,active)
                VALUES (?,?,?,?,?,?,?,1)
                ON CONFLICT(profile_id,day_name,exercise_id) DO UPDATE SET
                    active=1, sets=excluded.sets, rep_min=excluded.rep_min, rep_max=excluded.rep_max
                """,
                (profile_id, day_name, exercise_id, order, sets, rep_min, rep_max),
            )
    clear_data_cache()


def deactivate_program_exercise(row_id: int, profile_id: int) -> None:
    if use_supabase():
        supabase_client().table("program_exercises").update({"active": False}).eq("id", row_id).eq("profile_id", profile_id).execute()
    else:
        with db_connection() as conn:
            conn.execute("UPDATE program_exercises SET active=0 WHERE id=? AND profile_id=?", (row_id, profile_id))
    clear_data_cache()


@st.cache_data(ttl=30, show_spinner=False)
def recent_workouts(profile_id: int, limit: int = 20) -> list[dict]:
    if use_supabase():
        return (
            supabase_client().table("workouts")
            .select("id,workout_date,day_name,notes,workout_sets(id,set_no,reps,weight_kg,is_pr,exercises(name))")
            .eq("profile_id", profile_id)
            .order("workout_date", desc=True)
            .order("id", desc=True)
            .limit(limit)
            .execute().data or []
        )
    with db_connection() as conn:
        workouts = [dict(row) for row in conn.execute(
            "SELECT id,workout_date,day_name,notes FROM workouts WHERE profile_id=? ORDER BY workout_date DESC,id DESC LIMIT ?",
            (profile_id, limit),
        ).fetchall()]
        for workout in workouts:
            workout["workout_sets"] = [dict(row) for row in conn.execute(
                """
                SELECT ws.id,ws.set_no,ws.reps,ws.weight_kg,ws.is_pr,e.name
                FROM workout_sets ws JOIN exercises e ON e.id=ws.exercise_id
                WHERE ws.workout_id=? ORDER BY ws.id
                """,
                (workout["id"],),
            ).fetchall()]
    return workouts


def delete_workout(workout_id: int, profile_id: int) -> None:
    if use_supabase():
        supabase_client().table("workouts").delete().eq("id", workout_id).eq("profile_id", profile_id).execute()
    else:
        with db_connection() as conn:
            conn.execute("DELETE FROM workouts WHERE id=? AND profile_id=?", (workout_id, profile_id))
    clear_data_cache()


def pb_summary_dataframe(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history
    df = history.copy()
    df["volym"] = df["vikt_kg"].astype(float) * df["reps"].astype(int)
    df["est_1rm"] = df["vikt_kg"].astype(float) * (1 + df["reps"].astype(int) / 30)
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


def trend_dataframe(exercise_name: str, history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history
    df = history[history["ovning"] == exercise_name].copy()
    if df.empty:
        return df
    df["est_1rm"] = df["vikt_kg"].astype(float) * (1 + df["reps"].astype(int) / 30)
    df["volym"] = df["vikt_kg"].astype(float) * df["reps"].astype(int)
    return (
        df.groupby("datum", as_index=False)
        .agg(est_1rm=("est_1rm", "max"), volym=("volym", "sum"), toppvikt=("vikt_kg", "max"))
        .sort_values("datum")
    )


def technique_demo_path(exercise_name: str) -> Path | None:
    normalized_name = " ".join(exercise_name.strip().split()).casefold()
    filename = TECHNIQUE_DEMOS.get(normalized_name)
    if not filename:
        return None
    path = APP_DIR / "assets" / "demos" / filename
    return path if path.exists() else None


dialog_decorator = getattr(st, "dialog", None) or st.experimental_dialog


@dialog_decorator("Utförande", width="large")
def render_technique_dialog(exercise_name: str) -> None:
    path = technique_demo_path(exercise_name)
    if not path:
        st.error("Det finns ingen animation för övningen ännu.")
        return
    st.markdown(
        f"<div class='technique-dialog-title'>{escape(exercise_name)}</div>",
        unsafe_allow_html=True,
    )
    components.html(path.read_text(encoding="utf-8"), height=460, scrolling=False)


def page_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        :root {
            --ink:#111111; --muted:#69707d; --line:#dfe3ea; --paper:#f7f8fa;
            --panel:#ffffff; --accent:#0e7c66; --gold:#c09342; --soft:#edf7f4;
        }
        html, body, [class*="css"] { font-family:Inter,system-ui,sans-serif; letter-spacing:0; }
        body, [data-testid="stAppViewContainer"] {
            background:radial-gradient(circle at 20% 0%,rgba(14,124,102,.10),transparent 28rem),
                       linear-gradient(180deg,#fbfbfc 0%,#f4f6f8 100%);
            color:var(--ink);
        }
        .block-container { padding-top:1rem; padding-bottom:6rem; max-width:820px; }
        [data-testid="stHeader"] { background:rgba(251,251,252,.82); backdrop-filter:blur(16px); }
        h1,h2,h3 { letter-spacing:0; color:var(--ink); }
        h2 { font-size:1.25rem; } h3 { font-size:1.02rem; }
        .hero {
            border:1px solid rgba(17,17,17,.08); border-radius:8px; padding:1rem;
            background:linear-gradient(135deg,rgba(17,17,17,.96),rgba(38,42,48,.94)),#111;
            color:white; box-shadow:0 18px 44px rgba(17,17,17,.16); margin:1.2rem 0 .9rem;
        }
        .hero .eyebrow { color:rgba(255,255,255,.62); font-size:.78rem; font-weight:800; text-transform:uppercase; letter-spacing:.12rem; }
        .hero .title { font-size:clamp(2.2rem,11vw,4rem); line-height:.9; font-weight:800; margin-top:.35rem; }
        .metric-row { display:grid; grid-template-columns:repeat(3,1fr); gap:.65rem; margin:.9rem 0 1rem; }
        .mini-card { border:1px solid var(--line); border-radius:8px; padding:.75rem .8rem; background:rgba(255,255,255,.88); box-shadow:0 10px 28px rgba(17,17,17,.05); }
        .mini-card span { display:block; color:var(--muted); font-size:.76rem; font-weight:700; }
        .mini-card strong { display:block; color:var(--ink); font-size:1.12rem; margin-top:.14rem; }
        .profile-line { display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin:.2rem 0 .8rem; }
        .profile-name { font-weight:800; font-size:1.05rem; }
        .suggestion { border:1px solid rgba(14,124,102,.22); background:var(--soft); border-radius:8px; padding:.7rem .78rem; margin:.45rem 0 .7rem; }
        .suggestion strong { color:var(--accent); font-size:.96rem; }
        .suggestion span { color:#4f5f5b; font-size:.82rem; display:block; margin-top:.12rem; }
        .exercise-head { display:flex; justify-content:space-between; align-items:flex-start; gap:.8rem; margin-bottom:.35rem; }
        .exercise-title { font-weight:800; font-size:1.12rem; line-height:1.15; }
        .hint { color:var(--muted); font-size:.88rem; margin-top:.16rem; }
        .technique-dialog-title { color:var(--ink); font-size:1.08rem; font-weight:800; margin-bottom:.35rem; }
        div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:8px; border-color:rgba(17,17,17,.10); box-shadow:0 14px 34px rgba(17,17,17,.055); background:rgba(255,255,255,.9); }
        .stButton>button,[data-testid="stFormSubmitButton"] button,.stDownloadButton button { min-height:3.25rem; border-radius:8px; font-weight:800; border:1px solid rgba(17,17,17,.12); }
        [data-testid="stFormSubmitButton"] button[kind="primary"],.stButton>button[kind="primary"] { background:#111!important; color:white!important; }
        div[role="radiogroup"] { gap:.35rem; flex-wrap:wrap; }
        div[role="radiogroup"] label { border:1px solid rgba(17,17,17,.14); border-radius:999px; padding:.18rem .55rem; background:white; color:#111!important; opacity:1!important; }
        div[role="radiogroup"] label span,div[role="radiogroup"] label p { color:#111!important; opacity:1!important; }
        label,.stTextInput label,.stNumberInput label,.stTextArea label,.stSelectbox label { font-weight:700!important; color:#343841!important; }
        [data-testid="stCheckbox"] label,[data-testid="stCheckbox"] label span,[data-testid="stCheckbox"] p { color:#111!important; opacity:1!important; font-weight:800!important; }
        input,textarea { border-radius:8px!important; background:#fff!important; color:#111!important; caret-color:#111!important; }
        div[data-baseweb="input"],div[data-baseweb="textarea"],div[data-baseweb="select"]>div { background:#fff!important; color:#111!important; border-color:var(--line)!important; }
        div[data-baseweb="select"] span,div[data-baseweb="select"] svg { color:#111!important; fill:#111!important; }
        @media (max-width:620px) {
            .block-container { padding-left:.8rem; padding-right:.8rem; padding-top:.65rem; }
            .hero { padding:.95rem; } .metric-row { grid-template-columns:1fr 1fr; gap:.5rem; }
            .metric-row .mini-card:last-child { grid-column:1/-1; }
            .exercise-head { align-items:flex-start; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_today(profile: Profile) -> None:
    default_day = suggested_day(profile.id)
    key = f"selected_day_{profile.id}"
    selected_day = st.selectbox("Pass", DAY_NAMES, index=DAY_NAMES.index(st.session_state.get(key, default_day)), key=key)
    plan = list_program(profile.id, selected_day)
    history = history_dataframe(profile.id)
    if not plan:
        st.info("Det finns inga övningar i det här passet.")
        return

    logged: list[dict] = []
    with st.expander("Datum och anteckning"):
        workout_date = st.date_input("Datum", value=date.today(), key=f"date_{profile.id}")
        notes = st.text_area(
            "Anteckning",
            placeholder="Valfritt, t.ex. sömn, energi eller skada.",
            key=f"notes_{profile.id}_{selected_day}",
        )
    for exercise in plan:
        pb = best_for_exercise(exercise.name, history)
        suggestion = suggest_weight(exercise, history)
        rep_defaults = suggested_reps(exercise, history)
        demo_path = technique_demo_path(exercise.name)
        with st.container(border=True):
            hint = f"{exercise.sets} set · {exercise.rep_min}-{exercise.rep_max} reps"
            if pb:
                hint += f" · PB {pb[0]:g} kg x {pb[1]}"
            if demo_path:
                title_col, demo_col = st.columns(
                    [5, 1],
                    gap="small",
                    vertical_alignment="top",
                )
                with title_col:
                    st.markdown(
                        f"""
                        <div class="exercise-head"><div><div class="exercise-title">{escape(exercise.name)}</div>
                        <div class="hint">{escape(hint)}</div></div></div>
                        """,
                        unsafe_allow_html=True,
                    )
                with demo_col:
                    show_demo = st.button(
                        "▶",
                        key=f"technique_{profile.id}_{exercise.id}",
                        help="Visa utförande",
                    )
                if show_demo:
                    render_technique_dialog(exercise.name)
            else:
                st.markdown(
                    f"""
                    <div class="exercise-head"><div><div class="exercise-title">{escape(exercise.name)}</div>
                    <div class="hint">{escape(hint)}</div></div></div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown(
                f"""
                <div class="suggestion"><strong>{escape(suggestion.label)}</strong><span>{escape(suggestion.reason)}</span></div>
                """,
                unsafe_allow_html=True,
            )
            done = st.checkbox("Klar", key=f"done_{profile.id}_{exercise.id}")
            weight = st.number_input("Vikt kg", min_value=0.0, max_value=500.0, value=float(suggestion.weight), step=0.5, key=f"weight_{profile.id}_{exercise.id}")
            reps: list[int] = []
            columns = st.columns(min(exercise.sets, 4))
            for set_index in range(1, exercise.sets + 1):
                with columns[(set_index - 1) % len(columns)]:
                    reps.append(st.number_input(f"Set {set_index}", min_value=0, max_value=100, value=rep_defaults[set_index - 1], step=1, key=f"reps_{profile.id}_{exercise.id}_{set_index}"))
        if done:
            logged.append({"exercise_id": exercise.exercise_id, "name": exercise.name, "weight_kg": float(weight), "reps": reps})
    submitted = st.button(
        "Spara pass",
        key=f"save_workout_{profile.id}_{selected_day}",
        use_container_width=True,
        type="primary",
    )

    if submitted:
        try:
            save_workout(profile.id, selected_day, workout_date, notes, logged, history)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.session_state[key] = DAY_NAMES[(DAY_NAMES.index(selected_day) + 1) % len(DAY_NAMES)]
            st.success("Passet är sparat.")
            st.rerun()


def render_program(profile: Profile) -> None:
    selected_day = st.selectbox("Välj pass att redigera", DAY_NAMES, key=f"program_day_{profile.id}")
    rows = list_program(profile.id, selected_day)
    for row in rows:
        with st.expander(f"{row.sort_order}. {row.name} · {row.sets} set · {row.rep_min}-{row.rep_max} reps"):
            with st.form(f"edit_program_{profile.id}_{row.id}"):
                order = st.number_input("Ordning", 1, 50, int(row.sort_order), key=f"sort_{profile.id}_{row.id}")
                sets = st.number_input("Set", 1, 10, int(row.sets), key=f"sets_{profile.id}_{row.id}")
                rep_min = st.number_input("Rep min", 1, 50, int(row.rep_min), key=f"min_{profile.id}_{row.id}")
                rep_max = st.number_input("Rep max", 1, 50, int(row.rep_max), key=f"max_{profile.id}_{row.id}")
                save_col, remove_col = st.columns(2)
                with save_col:
                    save = st.form_submit_button("Spara", use_container_width=True, type="primary")
                with remove_col:
                    remove = st.form_submit_button("Ta bort", use_container_width=True)
            if save:
                if rep_max < rep_min:
                    st.error("Rep max måste vara minst lika högt som rep min.")
                else:
                    update_program_exercise(row.id, profile.id, int(sets), int(rep_min), int(rep_max), int(order))
                    st.rerun()
            if remove:
                deactivate_program_exercise(row.id, profile.id)
                st.rerun()

    st.subheader("Lägg till övning")
    with st.form(f"add_exercise_{profile.id}_{selected_day}"):
        name = st.text_input("Övningsnamn", placeholder="T.ex. Latsdrag")
        c1, c2, c3 = st.columns(3)
        with c1:
            sets = st.number_input("Set", 1, 10, 3, key=f"add_sets_{profile.id}")
        with c2:
            rep_min = st.number_input("Rep min", 1, 50, 8, key=f"add_min_{profile.id}")
        with c3:
            rep_max = st.number_input("Rep max", 1, 50, 12, key=f"add_max_{profile.id}")
        add = st.form_submit_button("Lägg till", use_container_width=True, type="primary")
    if add:
        try:
            add_program_exercise(profile.id, selected_day, name, int(sets), int(rep_min), int(rep_max))
        except Exception as exc:
            st.error(str(exc))
        else:
            st.rerun()


def render_personal_bests(profile: Profile) -> None:
    summary = pb_summary_dataframe(history_dataframe(profile.id))
    if summary.empty:
        st.info("Spara några pass först, så bygger appen en PB-sida åt profilen.")
        return
    top = summary.iloc[0]
    st.markdown(
        f"""
        <div class="metric-row"><div class="mini-card"><span>Starkaste lyft</span><strong>{escape(str(top['ovning']))}</strong></div>
        <div class="mini-card"><span>Estimerat max</span><strong>{top['basta_est_1rm']:g} kg</strong></div>
        <div class="mini-card"><span>Tyngsta vikt</span><strong>{top['tyngsta_vikt']:g} kg</strong></div></div>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(summary.rename(columns={"ovning":"Övning","tyngsta_vikt":"Tyngsta vikt","basta_reps":"Bästa reps","basta_est_1rm":"Est. 1RM","total_volym":"Total volym","antal_set":"Set"}), use_container_width=True, hide_index=True)


def render_charts(profile: Profile) -> None:
    history = history_dataframe(profile.id)
    summary = pb_summary_dataframe(history)
    if summary.empty:
        st.info("När profilen har sparat pass syns utvecklingen här.")
        return
    exercise_name = st.selectbox("Övning", summary["ovning"].tolist(), key=f"trend_exercise_{profile.id}")
    trend = trend_dataframe(exercise_name, history)
    chart = trend.set_index("datum")[["est_1rm","toppvikt"]].rename(columns={"est_1rm":"Est. 1RM","toppvikt":"Toppvikt"})
    st.line_chart(chart, use_container_width=True)
    st.bar_chart(trend.set_index("datum")[["volym"]].rename(columns={"volym":"Volym"}), use_container_width=True)


def render_history(profile: Profile) -> None:
    workouts = recent_workouts(profile.id)
    if not workouts:
        st.info("Ingen historik ännu.")
        return
    for workout in workouts:
        with st.expander(f"{workout['workout_date']} · {workout['day_name']}"):
            if workout.get("notes"):
                st.caption(workout["notes"])
            sets = workout.get("workout_sets") or []
            for row in sets:
                exercise = row.get("exercises") or {}
                name = row.get("name") or exercise.get("name", "Okänd övning")
                marker = " · PB" if row.get("is_pr") else ""
                st.write(f"{name} · set {row['set_no']}: {float(row['weight_kg']):g} kg x {row['reps']} reps{marker}")
            confirm = st.checkbox("Jag vill radera det här passet", key=f"confirm_delete_{profile.id}_{workout['id']}")
            if st.button("Radera pass", key=f"delete_{profile.id}_{workout['id']}", disabled=not confirm, use_container_width=True):
                delete_workout(int(workout["id"]), profile.id)
                st.rerun()


def render_profiles(active_profile: Profile) -> None:
    for profile in list_profiles():
        count, _ = profile_overview(profile.id)
        marker = " · aktiv" if profile.id == active_profile.id else ""
        st.write(f"**{profile.name}** · {count} pass{marker}")
    st.subheader("Ny profil")
    with st.form("create_profile"):
        name = st.text_input("Namn", placeholder="T.ex. Erik")
        submitted = st.form_submit_button("Skapa profil", use_container_width=True, type="primary")
    if submitted:
        try:
            profile = create_profile(name)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.session_state["profile_id"] = profile.id
            st.success(f"Profilen {profile.name} är skapad med ett eget startprogram.")
            st.rerun()


def render_export(profile: Profile) -> None:
    df = history_dataframe(profile.id)
    if df.empty:
        st.info("Det finns inget att exportera ännu.")
        return
    visible = df[["datum","pass","ovning","set_nr","vikt_kg","reps","pb"]]
    st.dataframe(visible, use_container_width=True, hide_index=True)
    st.download_button("Ladda ner CSV", data=visible.to_csv(index=False).encode("utf-8"), file_name=f"lyftlogg-{profile.name.lower()}.csv", mime="text/csv", use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Lyftlogg", page_icon="🏋️", layout="centered")
    page_styles()
    require_pin_if_configured()
    init_db()

    try:
        profiles = list_profiles()
    except Exception:
        st.error("Databasen behöver uppgraderas till Lyftlogg v3 innan appen kan starta.")
        st.caption("Kör filen supabase_migration_profiles_v3.sql i Supabase SQL Editor.")
        st.stop()

    if not profiles:
        profile = create_profile("Tobias")
        profiles = [profile]

    st.markdown("<div class='hero'><div class='title'>Lyftlogg</div></div>", unsafe_allow_html=True)

    profile_ids = [profile.id for profile in profiles]
    selected_id = st.session_state.get("profile_id", profile_ids[0])
    if selected_id not in profile_ids:
        selected_id = profile_ids[0]
    selected_index = profile_ids.index(selected_id)
    selected_name = st.selectbox("Tränar som", [profile.name for profile in profiles], index=selected_index, key="profile_selector")
    profile = next(profile for profile in profiles if profile.name == selected_name)
    st.session_state["profile_id"] = profile.id
    initialized_profiles = st.session_state.setdefault("initialized_profiles", [])
    if profile.id not in initialized_profiles:
        seed_program_for_profile(profile.id)
        initialized_profiles.append(profile.id)

    workout_count, _ = profile_overview(profile.id)
    st.markdown(
        f"""
        <div class="metric-row"><div class="mini-card"><span>Profil</span><strong>{escape(profile.name)}</strong></div>
        <div class="mini-card"><span>Träningspass</span><strong>{workout_count}</strong></div>
        <div class="mini-card"><span>Nästa pass</span><strong>{suggested_day(profile.id)}</strong></div></div>
        """,
        unsafe_allow_html=True,
    )

    view = st.radio("Vy", VIEWS, horizontal=True, label_visibility="collapsed", key="active_view")
    if view == "Idag":
        render_today(profile)
    elif view == "Program":
        render_program(profile)
    elif view == "PB":
        render_personal_bests(profile)
    elif view == "Trend":
        render_charts(profile)
    elif view == "Historik":
        render_history(profile)
    elif view == "Profiler":
        render_profiles(profile)
    else:
        render_export(profile)

    if use_supabase() and not uses_server_key():
        st.caption("Säkerhetsuppgradering väntar: lägg till service_role_key i Streamlit Secrets.")


if __name__ == "__main__":
    main()
