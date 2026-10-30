# Deployment

## Local (Windows)
1. `backend\setup.bat` - creates the venv, installs hash-checked packages, writes `.env`
   (choose 1 for a SQLite test, 2 for your Supabase URLs).
2. `backend\start.bat` - API on http://127.0.0.1:8000
3. `backend\test.bat` - runs the test suite.
4. App in a desktop browser: `cd app`, `npm install`, `npm run dev`.

## Render
1. Push the repo, then Render -> New -> Blueprint -> select it (uses `render.yaml`).
2. Fill the secret variables: `DATABASE_URL`, `CHAT_DATABASE_URL`, `SMTP_*`.
3. Upload `supabase-ca.crt` as a Secret File and use `sslrootcert=/etc/secrets/supabase-ca.crt`
   in both URLs (`sslmode=verify-full` is required in production). Use the Supabase pooler
   host if Render cannot reach the IPv6-only direct host.
4. `EMAIL_CODE_PEPPER` is generated once by Render; do not change it afterwards.
5. The service's `*.onrender.com` name is allowed automatically. Add a custom domain to `ALLOWED_HOSTS` if you use one.

`run.py` trusts the proxy's X-Forwarded-For on Render so per-IP rate limits see real clients.
The free plan sleeps when idle and the process restarts after 20,000 requests by design.

## APK
Install Node 18+, JDK 17 and the Android SDK, set `ANDROID_HOME`, then run `app\build-apk.bat`.
It asks for your Render URL, builds the web code, creates the Android project, adds the native
plugins and produces `Wire.apk` (debug-signed; sideload it). For a release build open `app/android`
in Android Studio and use Build > Generate Signed App Bundle / APK.
