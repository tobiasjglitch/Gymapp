# Deploy av Lyftlogg

## Kod

`app.py` är den enda riktiga appfilen. `app_v2.py` och `app_v3.py` är små
kompatibilitetsfiler så den befintliga Streamlit-deployen fortsätter fungera.

## Supabase

Kör SQL-filerna i den här ordningen i Supabase SQL Editor:

1. `supabase_schema_v2.sql` för en helt ny databas.
2. `supabase_migration_profiles_v3.sql`.
3. `supabase_migration_start_values_v4.sql`.
4. `supabase_migration_hardening_v5.sql`.
5. `supabase_program_tobias_chest_v6.sql` för Tobias nuvarande grundprogram.
6. `supabase_program_tobias_upper_body_v7.sql` för mer övre rygg och axlar.
7. `supabase_program_tobias_glutes_v8.sql` för det nya sätesfokuset.

V5 aktiverar RLS, stänger publik läsning av träningsdata, lägger till autosparade
utkast och gör sparning av träningspass idempotent.

## Streamlit Secrets

Lägg bara hemligheter i Streamlit Cloud, aldrig i GitHub-repot:

```toml
[supabase]
url = "https://ditt-projekt.supabase.co"
service_role_key = "din-servernyckel"
```

Servernyckeln får aldrig placeras i webbläsarkod eller delas publikt. Lyftlogg
kör all databaskod på Streamlit-servern och blockerar uppstart om nyckeln saknas.
Appen har ingen PIN-inloggning, så den som har webbadressen kan använda profilerna.

## Kontroll efter deploy

1. Byt mellan profiler och kontrollera att rätt program visas.
2. Ändra en vikt, ladda om sidan och kontrollera att utkastet återställs.
3. Spara ett testpass och kontrollera PB, Trend och Historik.
