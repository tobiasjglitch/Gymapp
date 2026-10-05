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

V5 aktiverar RLS, stänger publik läsning av träningsdata, lägger till autosparade
utkast och gör sparning av träningspass idempotent.

## Streamlit Secrets

Lägg bara hemligheter i Streamlit Cloud, aldrig i GitHub-repot:

```toml
APP_PIN = "din-pin"

[supabase]
url = "https://ditt-projekt.supabase.co"
service_role_key = "din-servernyckel"
```

Servernyckeln får aldrig placeras i webbläsarkod eller delas publikt. Lyftlogg
kör all databaskod på Streamlit-servern och blockerar uppstart om nyckeln eller
`APP_PIN` saknas.

## Kontroll efter deploy

1. Lås upp appen med PIN.
2. Byt mellan profiler och kontrollera att rätt program visas.
3. Ändra en vikt, ladda om sidan och kontrollera att utkastet återställs.
4. Spara ett testpass och kontrollera PB, Trend och Historik.
