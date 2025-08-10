# app.py — Gymapp (Streamlit + Supabase)
# UI på svenska, mobilvänligt. Ingen PIN.
# Databas:
#   exercises(id, name, cue, icon_path)
#   program_weeks(week, day, exercise_id, sets, rep_min, rep_max)
#   workouts(id, date, day_label)
#   sets(workout_id, exercise_id, set_no, reps, weight_kg, pr_flag)

from datetime import date
from uuid import uuid4
from typing import List, Dict, Any, Optional, Tuple
import os
import pandas as pd
import streamlit as st
import sys, inspect

# ==================== Build-tag för felsökning ====================
BUILD = "2025-08-10-20:45 no-asc-v3"
st.set_page_config(page_title="Gymapp", page_icon="💪", layout="centered", initial_sidebar_state="collapsed")
st.caption(f"Build: {BUILD}")
st.caption("asc= i filen? " + ("JA" if "asc=" in inspect.getsource(sys.modules[__name__]) else "NEJ"))

DAY_COL = "day"  # kolumnnamn i program_weeks

# ---------------- Mobil CSS ----------------
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] * { font-size: 17px; }
[data-testid="stAppViewContainer"]{padding-top:.5rem;padding-bottom:5rem}
[data-testid="stHeader"]{position:sticky;top:0;background:var(--background-color);z-index:1000}
.stButton>button,[data-testid="stFormSubmitButton"] button{min-height:56px;padding:.9rem 1.1rem;border-radius:14px}
[data-testid="stFormSubmitButton"] button{min-height:60px;padding:1rem 1.25rem;border-radius:16px;font-weight:600}
input,select,textarea{min-height:52px!important;border-radius:12px!important}
.block-container{padding-left:.8rem;padding-right:.8rem; max-width: 760px;}
.muted{opacity:.8}
.badge{display:inline-block;padding:.25rem .5rem;border-radius:999px;background:#EFEFEF;margin-left:.5rem;font-size:.85em}
.pill{display:inline-flex;align-items:center;gap:.4rem;padding:.15rem .5rem;border-radius:999px;font-size:.85em}
.pill-live{background:#e8fff0;border:1px solid #b3f0c7}
.hr{height:1px;background:rgba(0,0,0,.08);margin:.5rem 0 1rem}
.card{border:1px solid rgba(0,0,0,.08);border-radius:14px;padding:12px;margin-bottom:10px}
.card h4{margin:0 0 4px 0}
</style>
""", unsafe_allow_html=True)

# ---------------- Secrets / Supabase ----------------
def _read_supabase_creds():
    # 1) st.secrets
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY")
    if not url or not key:
        sec = st.secrets.get("supabase") or {}
        url = url or sec.get("url")
        key = key or sec.get("anon_key")
    if url and key:
        return url, key
    # 2) env
    url = os.environ.get("SUPABASE_URL") or url
    key = os.environ.get("SUPABASE_KEY") or key
    if url and key:
        return url, key
    # 3) minimal TOML-läsare (lokalt fallback)
    def _load_toml_min(path: str):
        data, current = {}, None
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("[") and line.endswith("]"):
                    current = line[1:-1].strip(); data.setdefault(current, {}); continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip(); v = v.strip()
                    if v[:1] in "'\"" and v[-1:] in "'\"": v = v[1:-1]
                    (data[current] if current else data)[k] = v
        return data
    # relativ
    here = os.path.dirname(os.path.abspath(__file__))
    alt_rel = os.path.join(here, "streamlit_config", "secrets.toml")
    if os.path.exists(alt_rel):
        try:
            data = _load_toml_min(alt_rel)
            sec = data.get("supabase", data)
            url = sec.get("url") or sec.get("SUPABASE_URL")
            key = sec.get("anon_key") or sec.get("SUPABASE_KEY")
            if url and key: return url, key
        except Exception:
            pass
    # absolut
    alt_abs = "/Users/tobias/Documents/Gymapp/streamlit_config/secrets.toml"
    if os.path.exists(alt_abs):
        try:
            data = _load_toml_min(alt_abs)
            sec = data.get("supabase", data)
            url = sec.get("url") or sec.get("SUPABASE_URL")
            key = sec.get("anon_key") or sec.get("SUPABASE_KEY")
            if url and key: return url, key
        except Exception:
            pass
    return None, None

def get_supabase_client():
    url, key = _read_supabase_creds()
    if not url or not key:
        st.error("Hittar inte Supabase‑nycklar. Lägg dem under [supabase] url/anon_key eller SUPABASE_URL/SUPABASE_KEY.")
        st.stop()
    from supabase import create_client
    return create_client(url, key)

sb = get_supabase_client()

# ---------------- Hjälp & logik ----------------
def get_week_index(d: date) -> int:
    # 0..11
    return (d.isocalendar().week - 1) % 12

def phase_for_week(idx: int) -> str:
    v = idx + 1
    if 1 <= v <= 8: return "Hypertrofi"
    if 9 <= v <= 11: return "Styrka"
    return "Deload"

def is_lower_body(name: str) -> bool:
    return any(w in name.lower() for w in
               ["böj","squat","mark","rdl","hip","thrust","vad","lung","front","goblet","pull-through"])

def weight_round(w: float) -> float:
    return round(w * 2) / 2 if w is not None else 0.0

def _extract_date_col(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    def _safe_date(x):
        if isinstance(x, dict):
            return x.get("date")
        return None
    if "workouts" in df.columns:
        df["date"] = df["workouts"].apply(_safe_date)
    elif "workouts(date)" in df.columns:
        df["date"] = df["workouts(date)"]
    return df

def best_previous_weight(ex_id: str) -> float:
    rows = sb.from_("sets").select("weight_kg").eq("exercise_id", ex_id)\
            .order("weight_kg", desc=True).limit(1).execute().data or []
    return float(rows[0]["weight_kg"]) if rows and rows[0]["weight_kg"] is not None else 0.0

def best_previous_reps_at_weight(ex_id: str, weight: float) -> int:
    rows = sb.from_("sets").select("reps").eq("exercise_id", ex_id).eq("weight_kg", weight)\
            .order("reps", desc=True).limit(1).execute().data or []
    return int(rows[0]["reps"]) if rows and rows[0]["reps"] is not None else 0

def last_two_sessions_under_min(ex_id: str, rep_min: int) -> bool:
    rows = (
        sb.from_("sets")
        .select("workout_id, reps, workouts(date)")
        .eq("exercise_id", ex_id)
        .limit(500)
        .execute().data or []
    )
    if not rows:
        return False
    df = _extract_date_col(rows)
    if df.empty:
        return False
    df = df.dropna(subset=["date"]).sort_values("date", ascending=False)
    medel = (
        df.groupby(["workout_id","date"])["reps"]
        .mean()
        .reset_index()
        .sort_values("date", ascending=False)["reps"]
        .tolist()
    )
    return len(medel) >= 2 and (medel[0] or 0) < rep_min and (medel[1] or 0) < rep_min

def propose_weight(ex_name: str, ex_id: str, rep_min: int, rep_max: int, week_idx: int) -> float:
    rows = sb.from_("sets").select("weight_kg").eq("exercise_id", ex_id).limit(50).execute().data or []
    default = 40.0 if is_lower_body(ex_name) else 20.0
    base = float(pd.DataFrame(rows)["weight_kg"].dropna().max()) if rows else default
    if not base or base <= 0:
        base = default

    if last_two_sessions_under_min(ex_id, rep_min):
        base = base * 0.95

    last_rows = (
        sb.from_("sets")
        .select("workout_id, set_no, reps, workouts(date)")
        .eq("exercise_id", ex_id)
        .limit(200)
        .execute().data or []
    )
    if last_rows:
        df = _extract_date_col(last_rows)
        df = df.dropna(subset=["date"]).sort_values(["date","set_no"], ascending=[False, True])
        if not df.empty:
            last_wid = df.iloc[0]["workout_id"]
            last_set_reps = df[df["workout_id"] == last_wid]["reps"].astype(int).tolist()
            if last_set_reps and all(r >= rep_max for r in last_set_reps):
                inc = 5.0 if is_lower_body(ex_name) else 2.5
                base = base + inc

    suggested = weight_round(base)
    if week_idx == 11:  # deload v12
        suggested = weight_round(suggested * 0.6)
    return suggested

def is_pr(ex_id: str, reps: int, weight_kg: float) -> bool:
    prev_best_w = best_previous_weight(ex_id)
    if weight_kg > prev_best_w:
        return True
    if weight_kg == prev_best_w:
        return reps > best_previous_reps_at_weight(ex_id, weight_kg)
    return False

# ---------------- DB helpers ----------------
def fetch_program_for_day(week_idx: int, day_value: str) -> List[Dict[str, Any]]:
    return (
        sb.from_("program_weeks")
        .select(f"week, {DAY_COL}, exercise_id, sets, rep_min, rep_max, exercises(name,cue)")
        .eq("week", week_idx + 1)
        .eq(DAY_COL, day_value)
        .order("exercise_id")  # default stigande
        .execute()
        .data or []
    )

def create_workout(d: date, day_value: str) -> str:
    wid = str(uuid4())
    sb.from_("workouts").insert({"id": wid, "date": d.isoformat(), "day_label": day_value}).execute()
    return wid

def upsert_set(wid: str, ex_id: str, set_no: int, reps: int, weight_kg: float, pr_flag: bool):
    payload = {"workout_id": wid, "exercise_id": ex_id, "set_no": set_no,
               "reps": reps, "weight_kg": weight_kg, "pr_flag": pr_flag}
    exists = sb.from_("sets").select("workout_id").eq("workout_id", wid)\
            .eq("exercise_id", ex_id).eq("set_no", set_no).execute().data or []
    if exists:
        sb.from_("sets").update(payload).eq("workout_id", wid)\
          .eq("exercise_id", ex_id).eq("set_no", set_no).execute()
    else:
        sb.from_("sets").insert(payload).execute()

# ---------------- Header ----------------
today = date.today()
widx = get_week_index(today)
st.markdown(
    f"### 💪 Gymapp  &nbsp;&nbsp; **{today.strftime('%Y-%m-%d')}**  &nbsp;&nbsp; **Vecka {widx+1}** "
    f"<span class='badge'>{phase_for_week(widx)}</span>  &nbsp;&nbsp; <span class='pill pill-live'>🟢 LIVE</span>",
    unsafe_allow_html=True
)
tabs = st.tabs(["Idag", "Program", "Historik", "Export"])

# ---------------- IDAG ----------------
with tabs[0]:
    st.subheader("Idag")
    day_value = st.selectbox("Dagens pass", ["Upper A","Lower A","Upper B","Lower B"], index=0)

    plan = fetch_program_for_day(widx, day_value)
    if not plan:
        st.info("Inget program hittat för den här veckan/dagen. Gå till fliken **Program** och klicka ”Initiera programdata”.")
    else:
        # EN vikt per övning + reps per set
        with st.form("today_form"):
            collected: List[Tuple[str, str, int, int, float, List[int]]] = []
            for row in plan:
                ex = row.get("exercises") or {}
                ex_id = row["exercise_id"]
                name = ex.get("name", f"Övning {ex_id[:8]}")
                sets_n = int(row.get("sets") or 3)
                rep_min = int(row.get("rep_min") or 6)
                rep_max = int(row.get("rep_max") or 10)
                suggested = propose_weight(name, ex_id, rep_min, rep_max, widx)

                st.markdown(f"<div class='card'><h4>{name}</h4>", unsafe_allow_html=True)
                if ex.get("cue"): st.caption(ex["cue"])

                c_w, c_info = st.columns([1.2, 1])
                with c_w:
                    weight = st.number_input("Vikt (kg) för ALLA set", min_value=0.0, max_value=2000.0, step=0.5,
                                             value=float(suggested), key=f"w_{ex_id}")
                with c_info:
                    st.markdown(f"<div class='muted'>Målreps per set: <b>{rep_min}-{rep_max}</b></div>", unsafe_allow_html=True)

                reps_inputs = []
                ccols = st.columns([1,1,1])
                for s_no in range(1, sets_n + 1):
                    col = ccols[(s_no-1) % 3]
                    with col:
                        reps = st.number_input(f"Reps – set {s_no}", min_value=0, max_value=30, step=1,
                                               value=rep_min, key=f"r_{ex_id}_{s_no}")
                        reps_inputs.append(int(reps))

                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("<div class='hr'></div>", unsafe_allow_html=True)

                collected.append((ex_id, name, rep_min, rep_max, float(weight), reps_inputs))

            submitted = st.form_submit_button("💾 Spara hela passet", use_container_width=True)

        if submitted:
            try:
                wid = create_workout(today, day_value)
                for (ex_id, _name, _rmin, _rmax, weight, reps_list) in collected:
                    for i, reps in enumerate(reps_list, start=1):
                        pr = is_pr(ex_id, int(reps), float(weight))
                        upsert_set(wid, ex_id, i, int(reps), float(weight), pr)
                st.success("Passet sparades! Grymt jobbat.")
            except Exception as e:
                st.error(f"Kunde inte spara: {e}")

# ---------------- PROGRAM ----------------
def seed_program() -> int:
    ex_rows = sb.from_("exercises").select("id,name").execute().data or []
    name_to_id = {r["name"]: r["id"] for r in ex_rows}

    def _resolve(name_to_id: Dict[str,str], *aliases: str) -> Optional[str]:
        for a in aliases:
            if a in name_to_id:
                return name_to_id[a]
        lowmap = {k.lower(): v for k,v in name_to_id.items()}
        for a in aliases:
            a_low = a.lower()
            for k_low, v in lowmap.items():
                if a_low in k_low:
                    return v
        return None

    plan = {
        "Upper A": [
            ("Lutande hantelpress", True, 4, ("Lutande hantelpress",)),
            ("Kabel-flyes (hög→låg)", False, 3, ("Kabel-flyes (hög→låg)","Kabel-flyes hög","Kabel flyes hög")),
            ("Enarms kabelpress", False, 3, ("Enarms kabelpress",)),
            ("Enarms hantelrodd", True, 4, ("Enarms hantelrodd","Hantelrodd")),
            ("Sidolyft hantlar", False, 3, ("Sidolyft hantlar","Sidolyft")),
            ("Triceps pushdown", False, 3, ("Triceps pushdown","Pushdown")),
        ],
        "Lower A": [
            ("Knäböj", True, 4, ("Knäböj","Böj","Squat")),
            ("Raka marklyft (RDL)", True, 4, ("Raka marklyft (RDL)","RDL","Raka marklyft")),
            ("Bulgarian split squat", False, 3, ("Bulgarian split squat","Bulgarian")),
            ("Kabel pull-through", False, 3, ("Kabel pull-through","Pull-through")),
            ("Vadpress", False, 3, ("Vadpress","Calf raise")),
            ("Kabel-crunch", False, 3, ("Kabel-crunch","Cable crunch")),
        ],
        "Upper B": [
            ("Hantelpress plan bänk", True, 4, ("Hantelpress plan bänk","Hantelpress")),
            ("Kabel-flyes (låg→hög)", False, 3, ("Kabel-flyes (låg→hög)","Kabel-flyes låg","Kabel flyes låg")),
            ("Lutande kabelpress", False, 3, ("Lutande kabelpress","Incline cable press")),
            ("Sittande kabelrodd", True, 4, ("Sittande kabelrodd","Kabelrodd")),
            ("Face pull", False, 3, ("Face pull","Facepull")),
            ("Axelpress hantlar", True, 3, ("Axelpress hantlar","Axelpress")),
            ("Bicepscurl hantlar", False, 3, ("Bicepscurl hantlar","Hantelcurl")),
        ],
        "Lower B": [
            ("Marklyft", True, 3, ("Marklyft","Deadlift")),
            ("Frontböj eller goblet squat", True, 3, ("Frontböj eller goblet squat","Frontböj","Goblet squat")),
            ("Hip thrust", True, 4, ("Hip thrust","Hipthrust")),
            ("Bakåtlunges", False, 3, ("Bakåtlunges","Lunges bakåt")),
            ("Vadpress", False, 3, ("Vadpress","Calf raise")),
            ("Kabel woodchop", False, 3, ("Kabel woodchop","Woodchop")),
        ],
    }

    def rep_range(is_base: bool, week: int):
        if 1 <= week <= 8: return (6,10) if is_base else (8,12)
        if 9 <= week <= 11: return (3,5) if is_base else (6,8)
        return (6,10) if is_base else (8,12)

    rows = []
    for week in range(1, 13):
        for day_name, ex_list in plan.items():
            for (name, is_base, base_sets, aliases) in ex_list:
                ex_id = _resolve(name_to_id, *aliases)
                if not ex_id:
                    continue
                sets = max(1, round(base_sets*0.5)) if week == 12 else base_sets
                rmin, rmax = rep_range(is_base, week)
                rows.append({
                    "week": week,
                    DAY_COL: day_name,
                    "exercise_id": ex_id,
                    "sets": sets,
                    "rep_min": rmin,
                    "rep_max": rmax,
                })
    if rows:
        sb.from_("program_weeks").upsert(rows, on_conflict=f"week,{DAY_COL},exercise_id").execute()
    return len(rows)

with tabs[1]:
    st.subheader("Program")
    st.caption("v1–8 Hypertrofi • v9–11 Styrka • v12 Deload")
    if st.button("⚙️ Initiera programdata (12 veckor)", use_container_width=True):
        try:
            n = seed_program()
            st.success(f"Programdata skapad/uppdaterad ({n} rader).")
        except Exception as e:
            st.error(f"Kunde inte initiera: {e}")

    sel_week = st.number_input("Vecka (1–12)", min_value=1, max_value=12, step=1, value=get_week_index(date.today()) + 1)
    sel_day  = st.selectbox("Dag", ["Upper A","Lower A","Upper B","Lower B"])
    data = fetch_program_for_day(sel_week - 1, sel_day)
    if not data:
        st.info("Inget program hittat för vald vecka/dag.")
    else:
        with st.form("program_edit"):
            rows_to_save = []
            for i, row in enumerate(data, start=1):
                ex = row["exercises"] or {}
                name = ex.get("name", f"Övning {row['exercise_id'][:8]}")
                c1,c2,c3,c4 = st.columns([2,1,1,1])
                with c1: st.markdown(f"**{name}**")
                with c2: sets_v = st.number_input("Set", 1, 8, int(row["sets"]), key=f"pg_sets_{i}")
                with c3: rmin_v = st.number_input("Rep min", 1, 30, int(row["rep_min"]), key=f"pg_min_{i}")
                with c4: rmax_v = st.number_input("Rep max", 1, 30, int(row["rep_max"]), key=f"pg_max_{i}")
                rows_to_save.append((row["exercise_id"], sets_v, rmin_v, rmax_v))
            saved = st.form_submit_button("💾 Spara program", use_container_width=True)
            if saved:
                try:
                    for (ex_id, s, rmin, rmax) in rows_to_save:
                        if int(rmax) < int(rmin):
                            rmax = rmin
                        sb.from_("program_weeks").update({"sets": int(s), "rep_min": int(rmin), "rep_max": int(rmax)})\
                          .eq("week", sel_week).eq(DAY_COL, sel_day).eq("exercise_id", ex_id).execute()
                    st.success("Programmet uppdaterades.")
                except Exception as e:
                    st.error(f"Misslyckades spara: {e}")

# ---------------- HISTORIK ----------------
with tabs[2]:
    st.subheader("Historik")
    ws = sb.from_("workouts").select("id, date, day_label").order("date", desc=True).limit(30).execute().data or []
    if not ws:
        st.info("Ingen historik ännu.")
    else:
        for w in ws:
            st.markdown(f"### {w['date']} — {w['day_label']}")
            rows = (
                sb.from_("sets")
                .select("exercise_id, set_no, reps, weight_kg, pr_flag, exercises(name)")
                .eq("workout_id", w["id"])
                .order("exercise_id")   # stigande
                .order("set_no")        # stigande
                .execute().data or []
            )
            if not rows:
                st.caption("Inga set."); st.divider(); continue
            df = pd.DataFrame(rows)
            df["övning"] = df["exercises"].apply(lambda x: x["name"] if isinstance(x, dict) else "")
            df["PR"] = df["pr_flag"].apply(lambda x: "🏆" if x else "")
            df = df[["övning","set_no","weight_kg","reps","PR"]].rename(columns={"set_no":"set","weight_kg":"kg","reps":"reps"})
            st.dataframe(df, use_container_width=True); st.divider()

# ---------------- EXPORT ----------------
with tabs[3]:
    st.subheader("Export")
    st.caption("Ladda ner all data som CSV.")
    with st.form("export_form"):
        include_pr = st.checkbox("Inkludera PR-flagga", value=True)
        go = st.form_submit_button("⤓ Ladda ner CSV", use_container_width=True)
        if go:
            data = (
                sb.from_("sets")
                .select("workout_id, exercise_id, set_no, reps, weight_kg, pr_flag, workouts(date,day_label), exercises(name)")
                .order("workout_id")   # stigande
                .order("exercise_id")  # stigande
                .order("set_no")       # stigande
                .execute().data or []
            )
            if not data:
                st.warning("Inget att exportera ännu.")
            else:
                df = pd.DataFrame(data)
                df["date"] = df["workouts"].apply(lambda x: x.get("date") if isinstance(x, dict) else "")
                df["day_label"] = df["workouts"].apply(lambda x: x.get("day_label") if isinstance(x, dict) else "")
                df["exercise"] = df["exercises"].apply(lambda x: x.get("name") if isinstance(x, dict) else "")
                cols = ["date","day_label","exercise","set_no","weight_kg","reps"]
                if include_pr: cols.append("pr_flag")
                csv = df[cols].to_csv(index=False).encode("utf-8")
                st.download_button("⤓ Spara CSV", data=csv, file_name="gymapp_export.csv", mime="text/csv", use_container_width=True)
