# Architecture

One backend, one app.

```
Wire/
  backend/            ONE FastAPI service (accounts, posts, people, chat)
    app/core          settings, DB engines, rate limiter, boundary middleware
    app/models        tables: identity, social, chat
    app/schemas       request bodies
    app/services      response builders, session issuing
    app/api           routers: health, auth, account, me, users, posts, chat
    run.py            starts the server
    setup.bat / start.bat / test.bat
  app/                hybrid app (HTML/CSS/JS + Capacitor -> APK)
    src               web code (js/pages = screens)
    native            two small Android plugins: Keystore vault, screenshot guard
    build-apk.bat
  supabase/schema.sql unchanged database definition
  render.yaml         Render blueprint
```

## Database logins stay separate
Least privilege is unchanged. Account/social endpoints use `DATABASE_URL`
(role `wire_main_backend`); chat endpoints use `CHAT_DATABASE_URL`
(role `wire_chat_backend`), via separate SQLAlchemy engines. Rate-limit counters use
the main login. Each process opens up to about 16 connections; check your Supabase limit.

## App
Screens in `app/src/js/pages` map one-to-one to the old native screens. API calls go
through native HTTP (no CORS), HTTPS only, to the origin baked in at build time.
