# Deploy av Gymapp v2

## 1. Supabase

1. Öppna Supabase.
2. Skapa ett nytt projekt, eller använd ett befintligt.
3. Gå till SQL Editor.
4. Klistra in innehållet från `supabase_schema_v2.sql`.
5. Kör SQL.
6. Gå till Project Settings -> API.
7. Kopiera `Project URL` och `anon public` key.

## 2. Streamlit Community Cloud

1. Öppna https://share.streamlit.io
2. Skapa en app från GitHub-repot.
3. Entry point ska vara `app.py`.
4. Lägg in Secrets:

```toml
APP_PIN = "välj-en-pin"

[supabase]
url = "din-supabase-url"
anon_key = "din-supabase-anon-key"
```

## 3. Efter deploy

Appen skapar startprogrammet själv första gången den startar, om programtabellen är tom.
