# app.py — Gymapp (mobilvänlig, Supabase + fallback)
# Läser nycklar från:
#  - SUPABASE_URL / SUPABASE_KEY (platta)
#  - st.secrets["supabase"]["url"] / ["anon_key"] (din nuvarande)
# Har även demo‑fallback om nycklar saknas.

from datetime import date
from typing import List
import os
import pandas as pd
import streamlit as st

# ================
# Page + mobil CSS
# ================
st.set_page_config(page_title="Gymapp", page_icon="💪", layout="wide", initial_sidebar_state="collapsed")

def inject_mobile_css():
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"] * { font-size: 17px; }
        [data-testid="stAppViewContainer"] { padding-top: .5rem; padding-bottom: 5rem; }
        [data-testid="stHeader"] { position: sticky; top: 0; background: var(--background-color); z-index: 1000; }
        .stButton > button, [data-testid="baseButton-secondary"], [data-testid="baseButton-primary"] {
            min-height: 56px; padding: .9rem 1.1rem; border-radius: 14px;
        }
        [data-testid="stFormSubmitButton"] button {
            min-height: 60px; padding: 1rem 1.25rem; font-weight: 600; border-radius: 16px;
        }
        input, select, textarea { min-height: 52px !important; border-radius: 12px !important; }
        [data-testid="column"] { padding-bottom: .35rem; }
        .block-container { padding-left: .8rem; padding-right: .8rem; }
        .sticky-top { position: sticky; top: 0; z-index: 999; background: var(--background-color); padding: .25rem 0 .5rem 0; }
        .muted { opacity:.8; }
        .badge { display:inline-block; padding:.25rem .5rem; border-radius:999px; background:#EFEFEF; margin-left:.5rem; font-size:.85em;}
        .card { border-radius:16px; padding: .75rem; border: 1px solid rgba(0,0,0,.06); box-shadow: 0 6px 18px rgba(0,0,0,.06); }
        
        .sticky-footer { position: sticky; bottom: 0; z-index: 1000; background: var(--background-color); padding: .5rem .25rem; border-top: 1px solid rgba(255,255,255,.08); }
        /* Mikro-spacing */
        [data-testid="column"] { padding-bottom: .2rem; }
        .block-container { padding-top: .5rem; padding-bottom: 5rem; }
        .stNumberInput input, .stTextInput input { padding: .6rem .8rem; }
        </style>
            
        """,
        unsafe_allow_html=True,
    )
inject_mobile_css()

# ================================
# Supabase-klient + demo‑fallback
# ================================
def _read_supabase_creds():
    # 1) Platta nycklar
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    # 2) Din befintliga [supabase] sektion
    if not url or not key:
        sb_section = st.secrets.get("supabase") or {}
        url = url or sb_section.get("url")
        key = key or sb_section.get("anon_key")
    return url, key

def get_supabase_client():
    url, key = _read_supabase_creds()
    try:
        from supabase import create_client  # type: ignore
        if url and key:
            return create_client(url, key), False
        raise RuntimeError("Saknar nycklar")
    except Exception:
        # Minimal dummy-klient så appen inte kraschar
        class _Res:
            def __init__(self, data=None): self.data = data or []
        class _Q:
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def order(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def insert(self, *a, **k): return self
            def update(self, *a, **k): return self
            def delete(self, *a, **k): return self
            def execute(self): return _Res([])
        class _From:
            def __init__(self, t): self.t=t; self.q=_Q()
            def select(self, *a, **k): return self.q
            def eq(self, *a, **k): return self.q
            def order(self, *a, **k): return self.q
            def limit(self, *a, **k): return self.q
            def insert(self, *a, **k): return self.q
            def update(self, *a, **k): return self.q
            def delete(self, *a, **k): return self.q
            def execute(self): return self.q.execute()
        class _Dummy:
            def from_(self, t): return _From(t)
            def rpc(self, *a, **k): return _Res([])
        return _Dummy(), True

sb, IS_DUMMY = get_supabase_client()
if IS_DUMMY:
    st.warning("⚠️ Kör utan Supabase‑nycklar (demo‑läge). Lägg till SUPABASE_URL/SUPABASE_KEY eller [supabase].", icon="⚠️")

# =========
# PIN-lås
# =========
def pin_gate():
    pin_required = st.secrets.get("PIN")
    if not pin_required: return
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if not st.session_state.authed:
        with st.form("pin_form"):
            st.markdown("### 🔒 Ange PIN för att öppna appen")
            pin = st.text_input("PIN", type="password")
            ok = st.form_submit_button("Öppna", use_container_width=True)
            if ok:
                if pin == pin_required:
                    st.session_state.authed = True
                    st.success("Välkommen!")
                else:
                    st.error("Fel PIN. Försök igen.")
        st.stop()
pin_gate()

# =================
# Hjälpfunktioner
# =================
def get_week_index(today: date) -> int:
    return (today.isocalendar().week - 1) % 12

def phase_for_week(idx: int) -> str:
    v = idx + 1
    if 1 <= v <= 8: return "Hypertrofi"
    if 9 <= v <= 11: return "Styrka"
    return "Deload"

def is_lower_body(name: str) -> bool:
    lower_words = ["böj", "squat", "mark", "rdl", "hip", "thrust", "vad", "lung", "front", "goblet", "pull-through"]
    n = name.lower()
    return any(w in n for w in lower_words)

def progression_increment(name: str) -> float:
    return 5.0 if is_lower_body(name) else 2.5

def weight_round(w: float) -> float:
    return round(w * 2) / 2 if w is not None else 0.0

def fetch_program_for_day(week_idx: int, day_label: str) -> List[dict]:
    return (
        sb.from_("program_weeks")
        .select("week, day, exercise_id, sets, rep_min, rep_max, exercises(name,cue,icon_path)")
        .eq("week", week_idx + 1)
        .eq("day", day_label)
        .order("exercise_id", desc=False)
        .execute()
        .data or []
    )

def last_two_sessions_under_min(ex_id: int, rep_min: int) -> bool:
    res = (
        sb.from_("sets").select("workout_id, reps")
        .eq("exercise_id", ex_id).order("workout_id", desc=True).limit(200)
        .execute().data or []
    )
    if not res: return False
    df = pd.DataFrame(res)
    if df.empty: return False
    medel = df.groupby("workout_id")["reps"].mean().sort_index(ascending=False).tolist()
    if len(medel) < 2: return False
    return (medel[0] < rep_min) and (medel[1] < rep_min)

def best_previous_weight(ex_id: int) -> float:
    rows = (
        sb.from_("sets").select("weight_kg")
        .eq("exercise_id", ex_id).order("weight_kg", desc=True).limit(1)
        .execute().data or []
    )
    return float(rows[0]["weight_kg"]) if rows else 0.0

def best_previous_reps_at_weight(ex_id: int, weight: float) -> int:
    rows = (
        sb.from_("sets").select("reps")
        .eq("exercise_id", ex_id).eq("weight_kg", weight)
        .order("reps", desc=True).limit(1).execute().data or []
    )
    return int(rows[0]["reps"]) if rows else 0

def propose_weight(ex_name: str, ex_id: int, rep_min: int, rep_max: int) -> float:
    res = (
        sb.from_("sets").select("weight_kg")
        .eq("exercise_id", ex_id).order("workout_id", desc=True).limit(12)
        .execute().data or []
    )
    if not res:
        return 40.0 if is_lower_body(ex_name) else 20.0
    df = pd.DataFrame(res)
    base = float(df["weight_kg"].max())
    inc = progression_increment(ex_name)
    if last_two_sessions_under_min(ex_id, rep_min):
        return weight_round(base * 0.95)
    last_ids = (
        sb.from_("sets").select("workout_id")
        .eq("exercise_id", ex_id).order("workout_id", desc=True).limit(1)
        .execute().data or []
    )
    if not last_ids: return weight_round(base)
    wid = last_ids[0]["workout_id"]
    reps = (
        sb.from_("sets").select("reps")
        .eq("exercise_id", ex_id).eq("workout_id", wid)
        .order("set_no", asc=True).execute().data or []
    )
    if reps and all(int(r["reps"]) >= rep_max for r in reps):
        return weight_round(base + inc)
    return weight_round(base)

def create_workout(d: date, day_label: str) -> int:
    if IS_DUMMY:
        st.session_state["FAKE_WID"] = st.session_state.get("FAKE_WID", 0) + 1
        return st.session_state["FAKE_WID"]
    r = (
        sb.from_("workouts").insert({"date": d.isoformat(), "day_label": day_label})
        .select("id").execute().data
    )
    return int(r[0]["id"])

def upsert_set(wid: int, ex_id: int, set_no: int, reps: int, weight_kg: float, pr_flag: bool):
    if IS_DUMMY:
        return
    exists = (
        sb.from_("sets").select("workout_id, exercise_id, set_no")
        .eq("workout_id", wid).eq("exercise_id", ex_id).eq("set_no", set_no)
        .execute().data or []
    )
    if exists:
        sb.from_("sets").update({"reps": reps, "weight_kg": weight_kg, "pr_flag": pr_flag})\
          .eq("workout_id", wid).eq("exercise_id", ex_id).eq("set_no", set_no).execute()
    else:
        sb.from_("sets").insert({"workout_id": wid, "exercise_id": ex_id, "set_no": set_no,
                                 "reps": reps, "weight_kg": weight_kg, "pr_flag": pr_flag}).execute()

def is_pr(ex_id: int, reps: int, weight_kg: float) -> bool:
    prev_best_w = best_previous_weight(ex_id)
    if weight_kg > prev_best_w: return True
    if weight_kg == prev_best_w:
        return reps > best_previous_reps_at_weight(ex_id, weight_kg)
    return False

# =================
# Sticky header + UI
# =================
with st.container():
    st.markdown('<div class="sticky-top">', unsafe_allow_html=True)
    cols = st.columns([1,1,1,2])
    with cols[0]:
        st.markdown("### 💪 Gymapp")
    with cols[1]:
        today = date.today()
        st.markdown(f"**{today.strftime('%Y-%m-%d')}**")
    with cols[2]:
        widx = get_week_index(today)
        st.markdown(f"**Vecka {widx+1}** <span class='badge'>{phase_for_week(widx)}</span>", unsafe_allow_html=True)
    with cols[3]:
        st.caption("Dubbel progression • PB-markering • Mobilvy")
    st.markdown('</div>', unsafe_allow_html=True)

tabs = st.tabs(["Idag", "Program", "Historik", "Export"])

# =====
# IDAG
# =====
with tabs[0]:
    st.subheader("Idag")
    day_label = st.selectbox("Dagens pass", ["Upper A", "Lower A", "Upper B", "Lower B"], index=0)

    plan = fetch_program_for_day(widx, day_label)
    if not plan:
        st.info("Inget program hittat för den här veckan/dagen. (Tips: initiera i fliken Program.)")

    
    with st.expander("💡 Tips", expanded=False):
        st.write("• Skriv **vikt** en gång per övning.")
        st.write("• Välj **reps** per set via knapparna.")
        st.write("• Tryck **Spara pass** i nederkanten.")
    with st.form("today_form"):
        wid = create_workout(today, day_label)
        if plan:
            for row in plan:
                ex = row.get("exercises") or {}
                ex_id = row["exercise_id"]
                name = ex.get("name", f"Ex #{ex_id}")
                sets_n = int(row.get("sets") or 3)
                rep_min = int(row.get("rep_min") or 6)
                rep_max = int(row.get("rep_max") or 10)

                suggested = propose_weight(name, ex_id, rep_min, rep_max)
                
                # Header with rep-range badge
                st.markdown(f"#### {name} <span class='badge'>{rep_min}–{rep_max} reps</span>", unsafe_allow_html=True)
                if ex.get("cue"): st.caption(ex["cue"])

                # One weight for the whole exercise
                st.number_input("Vikt (kg)", min_value=0.0, max_value=2000.0, step=0.5,
                                value=float(suggested or 0.0), key=f"w_{ex_id}")

                # Reps per set as chips (radio horizontal)
                rep_options = list(range(rep_min, rep_max + 1))
                for s_no in range(1, sets_n + 1):
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        st.caption(f"Set {s_no}")
                    with c2:
                        st.radio("Reps", rep_options, horizontal=True, key=f"r_{ex_id}_{s_no}", label_visibility="collapsed")
#### {name}")
                if ex.get("cue"): st.caption(ex["cue"])
                for s_no in range(1, sets_n + 1):
                    c1, c2, c3 = st.columns([1.2, 1, 1])
                    with c1:
                        st.number_input(f"Vikt (kg) – set {s_no}", min_value=0.0, max_value=2000.0, step=0.5,
                                        value=float(suggested), key=f"w_{ex_id}_{s_no}")
                    with c2:
                        st.number_input(f"Reps – set {s_no}", min_value=0, max_value=30, step=1,
                                        value=rep_min, key=f"r_{ex_id}_{s_no}")
                    with c3:
                        
                # Header with rep-range badge
                st.markdown(f"#### {name} <span class='badge'>{rep_min}–{rep_max} reps</span>", unsafe_allow_html=True)
                if ex.get("cue"): st.caption(ex["cue"])

                # One weight for the whole exercise
                st.number_input("Vikt (kg)", min_value=0.0, max_value=2000.0, step=0.5,
                                value=float(suggested or 0.0), key=f"w_{ex_id}")

                # Reps per set as chips (radio horizontal)
                rep_options = list(range(rep_min, rep_max + 1))
                for s_no in range(1, sets_n + 1):
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        st.caption(f"Set {s_no}")
                    with c2:
                        st.radio("Reps", rep_options, horizontal=True, key=f"r_{ex_id}_{s_no}", label_visibility="collapsed")
<div class='muted'>Mål: {rep_min}-{rep_max}</div>", unsafe_allow_html=True)
                st.divider()
        footer = st.container()
        with footer:
            st.markdown('<div class="sticky-footer">', unsafe_allow_html=True)
            submitted = st.form_submit_button("💾 Spara pass", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
    
    if submitted and plan:
        try:
            for row in plan:
                ex_id = row["exercise_id"]
                sets_n = int(row.get("sets") or 3)
                for s_no in range(1, sets_n + 1):
                    w = float(st.session_state.get(f"w_{ex_id}_{s_no}", 0.0))
                    r = int(st.session_state.get(f"r_{ex_id}_{s_no}", 0))
                    pr = is_pr(ex_id, r, w) if not IS_DUMMY else False
                    upsert_set(wid, ex_id, s_no, r, w, pr)
            st.success("Passet sparades!" if not IS_DUMMY else "Passet *låtsas* sparat (demo‑läge).")
        except Exception as e:
            st.error(f"Kunde inte spara: {e}")

# ========
# PROGRAM
# ========
def seed_program(sb_client) -> int:
    """Initierar exercises + 12 veckors program enligt din mall."""
    exercises = [
        # Upper A
        ("Lutande hantelpress", "Kontrollerad sänk, full ROM"),
        ("Kabel-flyes (hög→låg)", "Håll skulderbladen bakåt"),
        ("Enarms kabelpress", "Stabil bål, pressa rakt fram"),
        ("Enarms hantelrodd", "Neutral rygg, dra armbågen mot höften"),
        ("Sidolyft hantlar", "Lätt böjda armbågar"),
        ("Triceps pushdown", "Armbågar nära kroppen"),
        # Lower A
        ("Knäböj", "Djup du kan kontrollera"),
        ("Raka marklyft (RDL)", "Höfter bakåt, rak rygg"),
        ("Bulgarian split squat", "Kontrollerad sänk"),
        ("Kabel pull-through", "Höftgång, spänn rumpan"),
        ("Vadpress", "Fullt sträck och bottenläge"),
        ("Kabel-crunch", "Runda överkroppen, andas ut"),
        # Upper B
        ("Hantelpress plan bänk", "Kontrollerat tempo"),
        ("Kabel-flyes (låg→hög)", "Lyft upp mot ansiktet"),
        ("Lutande kabelpress", "Press snett uppåt"),
        ("Sittande kabelrodd", "Dra mot naveln"),
        ("Face pull", "Extern rotation"),
        ("Axelpress hantlar", "Stabil core"),
        ("Bicepscurl hantlar", "Kontrollerad excentrisk"),
        # Lower B
        ("Marklyft", "Spänd bål, stång nära"),
        ("Frontböj", "Armbågar fram"),
        ("Goblet squat", "Vikt nära bröstet"),
        ("Hip thrust", "Toppspänn rumpan"),
        ("Bakåtlunges", "Steg bakåt"),
        ("Kabel woodchop", "Rotera genom bålen"),
    ]
    name_to_id = {}
    for name, cue in exercises:
        found = sb_client.from_("exercises").select("id").eq("name", name).limit(1).execute().data
        if found:
            ex_id = found[0]["id"]
            sb_client.from_("exercises").update({"cue": cue}).eq("id", ex_id).execute()
        else:
            ex_id = sb_client.from_("exercises").insert({"name": name, "cue": cue}).select("id").execute().data[0]["id"]
        name_to_id[name] = ex_id

    days = {
        "Upper A": [
            ("Lutande hantelpress", True, 3),
            ("Kabel-flyes (hög→låg)", False, 3),
            ("Enarms kabelpress", False, 3),
            ("Enarms hantelrodd", True, 3),
            ("Sidolyft hantlar", False, 3),
            ("Triceps pushdown", False, 3),
        ],
        "Lower A": [
            ("Knäböj", True, 3),
            ("Raka marklyft (RDL)", True, 3),
            ("Bulgarian split squat", False, 3),
            ("Kabel pull-through", False, 3),
            ("Vadpress", False, 3),
            ("Kabel-crunch", False, 3),
        ],
        "Upper B": [
            ("Hantelpress plan bänk", True, 3),
            ("Kabel-flyes (låg→hög)", False, 3),
            ("Lutande kabelpress", False, 3),
            ("Sittande kabelrodd", True, 3),
            ("Face pull", False, 3),
            ("Axelpress hantlar", True, 3),
            ("Bicepscurl hantlar", False, 3),
        ],
        "Lower B": [
            ("Marklyft", True, 3),
            ("Frontböj", True, 3),  # eller Goblet
            ("Hip thrust", True, 3),
            ("Bakåtlunges", False, 3),
            ("Vadpress", False, 3),
            ("Kabel woodchop", False, 3),
        ],
    }

    def rep_range(is_base: bool, week: int):
        if 1 <= week <= 8:  # Hypertrofi
            return (6,10) if is_base else (8,12)
        elif 9 <= week <= 11:  # Styrka
            return (3,5) if is_base else (6,8)
        else:  # v12 Deload (behåll intervall, halvera set)
            return (6,10) if is_base else (8,12)

    rows = []
    for week in range(1, 13):
        for day_label, ex_list in days.items():
            for (ex_name, is_base, base_sets) in ex_list:
                sets = max(1, round(base_sets * 0.5)) if week == 12 else base_sets
                rmin, rmax = rep_range(is_base, week)
                rows.append({
                    "week": week,
                    "day": day_label,
                    "exercise_id": name_to_id[ex_name],
                    "sets": sets,
                    "rep_min": rmin,
                    "rep_max": rmax,
                })

    # Rensa veckorna 1–12 och skriv in på nytt (enkelt och säkert)
    sb_client.from_("program_weeks").delete().gte("week", 1).lte("week", 12).execute()
    # Batch-insert
    chunk = 200
    for i in range(0, len(rows), chunk):
        sb_client.from_("program_weeks").insert(rows[i:i+chunk]).execute()
    return len(rows)

with tabs[1]:
    st.subheader("Program")
    st.caption("12 veckor: v1–8 Hypertrofi, v9–11 Styrka, v12 Deload.")

    if not IS_DUMMY:
        st.info("Saknar program? Klicka för att lägga in 12 veckor enligt mallen.")
        if st.button("⚙️ Initiera programdata (12 veckor)", use_container_width=True):
            try:
                n = seed_program(sb)
                st.success(f"Programdata skapad/uppdaterad ({n} rader).")
            except Exception as e:
                st.error(f"Kunde inte initiera: {e}")
    else:
        st.caption("Demo‑läge: initiering inaktiverad tills Supabase‑nycklar finns.")

    sel_week = st.number_input("Vecka (1–12)", min_value=1, max_value=12, step=1, value=get_week_index(date.today()) + 1)
    sel_day = st.selectbox("Dag", ["Upper A", "Lower A", "Upper B", "Lower B"])
    data = fetch_program_for_day(sel_week - 1, sel_day)
    if not data:
        st.info("Inget program hittat för vald vecka/dag.")
    else:
        with st.form("program_edit"):
            rows = []
            for i, row in enumerate(data, start=1):
                ex = row["exercises"] or {}
                name = ex.get("name", f"Ex #{row['exercise_id']}")
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                with c1: st.markdown(f"**{name}**")
                with c2: sets_v = st.number_input("Set", 1, 8, int(row["sets"]), key=f"pg_sets_{i}")
                with c3: rmin_v = st.number_input("Rep min", 1, 30, int(row["rep_min"]), key=f"pg_min_{i}")
                with c4: rmax_v = st.number_input("Rep max", 1, 30, int(row["rep_max"]), key=f"pg_max_{i}")
                rows.append((row["exercise_id"], sets_v, rmin_v, rmax_v))
            saved = st.form_submit_button("💾 Spara program", use_container_width=True)
            if saved:
                if IS_DUMMY:
                    st.info("Demo‑läge: sparar inte till DB.")
                else:
                    try:
                        for (ex_id, s, rmin, rmax) in rows:
                            sb.from_("program_weeks").update({"sets": int(s), "rep_min": int(rmin), "rep_max": int(rmax)})\
                              .eq("week", sel_week).eq("day", sel_day).eq("exercise_id", ex_id).execute()
                        st.success("Programmet uppdaterades.")
                    except Exception as e:
                        st.error(f"Misslyckades spara: {e}")

# =========
# HISTORIK
# =========
with tabs[2]:
    st.subheader("Historik")
    ws = (
        sb.from_("workouts").select("id, date, day_label")
        .order("date", desc=True).limit(30).execute().data or []
    )
    if not ws:
        st.info("Ingen historik ännu.")
    else:
        for w in ws:
            st.markdown(f"### {w['date']} — {w['day_label']}")
            rows = (
                sb.from_("sets")
                .select("exercise_id, set_no, reps, weight_kg, pr_flag, exercises(name)")
                .eq("workout_id", w["id"])
                .order("exercise_id", asc=True)
                .order("set_no", asc=True)
                .execute().data or []
            )
            if not rows:
                st.caption("Inga set.")
                continue
            df = pd.DataFrame(rows)
            df["övning"] = df["exercises"].apply(lambda x: x["name"] if isinstance(x, dict) else "")
            df = df[["övning", "set_no", "weight_kg", "reps", "pr_flag"]].rename(
                columns={"set_no": "set", "weight_kg": "kg", "reps": "reps", "pr_flag": "PR"}
            )
            st.dataframe(df, use_container_width=True)
            st.divider()

# =======
# EXPORT
# =======
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
                .order("workout_id", asc=True)
                .order("exercise_id", asc=True)
                .order("set_no", asc=True)
                .execute().data or []
            )
            if not data:
                st.warning("Inget att exportera ännu.")
            else:
                df = pd.DataFrame(data)
                df["date"] = df["workouts"].apply(lambda x: x.get("date") if isinstance(x, dict) else "")
                df["day_label"] = df["workouts"].apply(lambda x: x.get("day_label") if isinstance(x, dict) else "")
                df["exercise"] = df["exercises"].apply(lambda x: x.get("name") if isinstance(x, dict) else "")
                cols = ["date", "day_label", "exercise", "set_no", "weight_kg", "reps"]
                if include_pr: cols.append("pr_flag")
                csv = df[cols].to_csv(index=False).encode("utf-8")
                st.download_button("⤓ Spara CSV", data=csv, file_name="gymapp_export.csv", mime="text/csv", use_container_width=True)
