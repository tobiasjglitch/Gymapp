import os
import streamlit as st

LOCAL_MODE = os.getenv("GYMAPP_LOCAL", "1") == "1"  # defaulta till lokal körning

if LOCAL_MODE:
    st.sidebar.success("Körs i **LOKALT LÄGE** – data lagras i .gymapp_data/ (ingen Supabase).")
    from local_mode import get_local_client
    supabase = get_local_client(seed=True)  # supabase-API-shim
else:
    # *** ORIGINAL SUPABASE-KOD HÄR *** (låt vara kvar för framtiden)
    from supabase import create_client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    supabase = create_client(url, key)
