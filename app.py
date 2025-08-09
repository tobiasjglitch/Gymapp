# app.py — Gymapp "Idag"-sidan (stabil version utan RPC)

import datetime as dt
from typing import Dict, List, Optional, Tuple

import streamlit as st
import toml
from supabase import Client, create_client

# ---------- Konfig ----------
st.set_page_config(page_title="Gymapp – Idag", page_icon="💪", layout="centered")

# Läs Supabase-nycklar (från streamlit_config/secrets.toml)
secrets = toml.load("streamlit_config/secrets.toml")
SUPABASE_URL = secrets["supabase"]["url"]
SUPABASE_KEY = secrets["supabase"]["anon_key"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DAY_LABELS = ["Upper A", "Lower A", "Upper B", "Lower B"]

# Övningsgrupper för progressionens viktökning
PRESS_BACK = {
    "Lutande hantelpress", "Kabel-flyes (hög→låg)", "Enarms kabelpress",
    "Enarms hantelrodd", "Sidolyft hantlar", "Triceps pushdown",
    "Hantelpress plan bänk", "Kabel-flyes (låg→hög)", "Lutande kabelpress",
    "Sittande kabelrodd", "Face pull", "Axelpress hantlar", "Bicepscurl hantlar"
}
LEGS_HIP = {
    "Knäböj", "RDL", "Bulgarian split squat", "Kabel pull-through",
    "Vadpress", "Kabel-crunch", "Marklyft", "Frontböj/Goblet squat",
    "Hip thrust", "Bakåtlunges", "Kabel woodchop"
}


# ---------- Hjälpfunktioner ----------
def fetch_program(week: int, day_label: str) -> List[dict]:
    """Hämta dagens planerade övningar och repintervall."""
    res = (
        supabase.table("program_weeks")
        .select("exercise_id, sets, rep_min, rep_max, exercises(name,cue)")
        .eq("week", week)
        .eq("day_label", day_label)
        .execute()
    )
    return res.data or []


def get_or_create_workout(date_: dt.date, day_label: str) -> dict:
    """Hämta eller skapa ett workout-rad för valt datum + dag-label."""
    q = (
        supabase.table("workouts")
        .select("*")
        .eq("date", str(date_))
        .eq("day_label", day_label)
        .limit(1)
        .execute()
        .data
    )
    if q:
        return q[0]
    new_w = (
        supabase.table("workouts")
        .insert({"date": str(date_), "day_label": day_label})
        .execute()
        .data[0]
    )
    return new_w


def last_two_sessions(exercise_id: str) -> List[dict]:
    """
    Hämta senaste seten för en övning med inbäddad workout-info.
    Ingen RPC behövs. Vi sorterar i Python: datum fallande, set_no stigande.
    """
    rows = (
        supabase.table("sets")
        .select("workout_id,set_no,reps,weight_kg,pr_flag,workouts(date,day_label)")
        .eq("exercise_id", exercise_id)
        .limit(200)
        .execute()
        .data
        or []
    )

    # Sortera: först set_no (1,2,3...), sedan datum fallande
    rows.sort(key=lambda r: r["set_no"])
    rows.sort(key=lambda r: r["workouts"]["date"], reverse=True)
    return rows


def load_exercise_history_summary(ex_id: str, rep_min: int, rep_max: int) -> Tuple[Optional[float], bool, int]:
    """Hämta senaste vikt + om alla set nådde rep_max i senaste passet + under_min_streak."""
    rows = last_two_sessions(ex_id)
    if not rows:
        return None, False, 0

    # Gruppéra per workout
    by_w: Dict[str, List[dict]] = {}
    for r in rows:
        by_w.setdefault(r["workout_id"], []).append(r)

    # Senaste passet
    last_sets = list(by_w.values())[0]

    # Kolla om ALLA set nådde rep_max
    meets_top = False
    reps_list = [s["reps"] for s in last_sets if s.get("reps") is not None]
    if reps_list and all(r >= rep_max for r in reps_list):
        meets_top = True

    # Senaste arbetsvikt = max vikt i passet
    last_weight = max(
        [float(s["weight_kg"]) for s in last_sets if s.get("weight_kg") is not None] or [0.0]
    ) or None

    # Streak under min (två pass i rad)
    under_min_streak = 0
    for idx, sets_ in enumerate(by_w.values()):
        rlist = [s["reps"] for s in sets_ if s.get("reps") is not None]
        if rlist and all(r < rep_min for r in rlist):
            under_min_streak += 1
        else:
            break
        if idx == 1:
            break

    return last_weight, meets_top, under_min_streak


def suggested_weight(
    ex_name: str,
    rep_min: int,
    rep_max: int,
    last_weight: Optional[float],
    under_min_streak: int,
    last_pass_meets_top: bool,
) -> Optional[float]:
    """
    Double progression:
      - Om alla set i senaste passet var på övre repgränsen -> +2.5 kg (press/rygg) / +5 kg (ben/hip)
      - Två pass i rad under rep_min -> -5%
      - Annars: behåll senaste vikten
    Om vi saknar historik: returnera None (du fyller manuellt första gången).
    """
    if last_weight is None or last_weight == 0:
        return None

    if under_min_streak >= 2:
        return round(last_weight * 0.95, 1)

    if last_pass_meets_top:
        inc = 2.5 if ex_name in PRESS_BACK else 5.0 if ex_name in LEGS_HIP else 2.5
        return round(last_weight + inc, 1)

    return last_weight


def is_pr(ex_id: str, weight: float, reps: int) -> bool:
    """PR om vikten är större än tidigare maxvikt för övningen, eller lika vikt med fler reps."""
    prev = (
        supabase.table("sets")
        .select("weight_kg,reps")
        .eq("exercise_id", ex_id)
        .execute()
        .data
        or []
    )
    if not prev:
        return True
    # Högsta vikt hittills
    max_w = max([float(p["weight_kg"]) for p in prev if p.get("weight_kg") is not None] or [0.0])
    if weight > max_w:
        return True
    # Om samma vikt: kolla max reps på den vikten
    same_w_reps = max([int(p["reps"]) for p in prev if p.get("weight_kg") == weight and p.get("reps") is not None] or [0])
    return reps > same_w_reps


# ---------- UI ----------
st.title("Idag 💪")

# Val för vecka / dag / datum
col1, col2, col3 = st.columns(3)
with col1:
    week = st.number_input("Vecka", min_value=1, max_value=12, value=1, step=1, help="Programvecka 1–12")
with col2:
    day_label = st.selectbox("Pass", DAY_LABELS, index=0)
with col3:
    pass_datum = st.date_input("Datum", value=dt.date.today())

program_rows = fetch_program(week, day_label)

if not program_rows:
    st.warning("Inget program hittades för valt pass. Lägg in rader i `program_weeks` för denna vecka/dag.")
    st.stop()

# Hämta/Skapa workout-rad för valt datum + dag_label
workout = get_or_create_workout(pass_datum, day_label)

st.info(f"Loggar pass **{day_label}** för **{pass_datum}** (vecka {week}).")

# Form för att logga alla set
with st.form(key=f"log_form_{workout['id']}"):
    inputs: List[Tuple[str, str, int, int, List[Tuple[int, float, int]]]] = []
    # (exercise_id, name, rep_min, rep_max, [(set_no, weight, reps), ...])

    for row in program_rows:
        ex = row["exercises"]
        ex_id = row["exercise_id"]
        ex_name = ex["name"]
        cue = ex.get("cue", "")
        sets_n = int(row["sets"])
        rep_min = int(row["rep_min"])
        rep_max = int(row["rep_max"])

        st.subheader(ex_name)
        if cue:
            st.caption(cue)

        # Historik / auto-förslag
        last_w, meets_top, under_streak = load_exercise_history_summary(ex_id, rep_min, rep_max)
        auto = suggested_weight(ex_name, rep_min, rep_max, last_w, under_streak, meets_top)

        # Visa enkel förslagsrad
        if auto is None:
            st.write(f"💡 Första gången? Ange startvikt (sikta på {rep_min}–{rep_max} reps).")
        else:
            if under_streak >= 2:
                st.write(f"📉 Två pass i rad under rep-min → förslag **{auto} kg** (−5%).")
            elif meets_top:
                inc_txt = "+2.5 kg" if ex_name in PRESS_BACK else "+5 kg"
                st.write(f"📈 Alla set på rep-max senast → förslag **{auto} kg** ({inc_txt}).")
            else:
                st.write(f"➡️ Förslag **{auto} kg** (ingen ändring).")

        set_inputs: List[Tuple[int, float, int]] = []
        for s_no in range(1, sets_n + 1):
            c1, c2 = st.columns(2)
            with c1:
                w_default = auto if auto is not None else 0.0
                weight = st.number_input(
                    f"Vikt set {s_no} (kg)",
                    min_value=0.0,
                    max_value=1000.0,
                    value=float(w_default),
                    step=0.5,
                    key=f"{ex_id}_w_{s_no}",
                )
            with c2:
                reps = st.number_input(
                    f"Reps set {s_no}",
                    min_value=0,
                    max_value=100,
                    value=rep_min,
                    step=1,
                    key=f"{ex_id}_r_{s_no}",
                )
            set_inputs.append((s_no, float(weight), int(reps)))

        inputs.append((ex_id, ex_name, rep_min, rep_max, set_inputs))

    submitted = st.form_submit_button("💾 Spara pass", use_container_width=True)

if submitted:
    # Spara alla set, räkna PR flagg
    try:
        for ex_id, ex_name, rep_min, rep_max, set_list in inputs:
            for s_no, weight, reps in set_list:
                pr = is_pr(ex_id, weight, reps)
                (
                    supabase.table("sets")
                    .upsert(
                        {
                            "workout_id": workout["id"],
                            "exercise_id": ex_id,
                            "set_no": s_no,
                            "reps": reps,
                            "weight_kg": weight,
                            "pr_flag": pr,
                        }
                    )
                    .execute()
                )
        st.success("Pass sparat ✅")
    except Exception as e:
        st.error(f"Kunde inte spara: {e}")

# Visa tidigare set i detta pass
hist = (
    supabase.table("sets")
    .select("exercise_id,set_no,reps,weight_kg,pr_flag,exercises(name)")
    .eq("workout_id", workout["id"])
    .order("exercise_id")
    .order("set_no")
    .execute()
    .data
    or []
)

if hist:
    st.subheader("Loggade set")
    current_ex = None
    for row in hist:
        name = row["exercises"]["name"]
        if name != current_ex:
            st.markdown(f"**{name}**")
            current_ex = name
        pr_txt = " 🔥 PR" if row.get("pr_flag") else ""
        st.write(f"- Set {row['set_no']}: {row.get('weight_kg', 0)} kg × {row.get('reps', 0)}{pr_txt}")
else:
    st.caption("Inga set loggade ännu för detta pass.")
