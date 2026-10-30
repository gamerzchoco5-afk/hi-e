# Wire

One backend + one hybrid Android app.

| Folder | What |
|---|---|
| `backend/` | Single FastAPI server. `setup.bat` then `start.bat`. |
| `app/` | HTML/CSS/JS app packaged as an APK with Capacitor. `build-apk.bat`. |
| `supabase/schema.sql` | Database definition (unchanged). |
| `render.yaml` | One-click Render blueprint. |

Start with `docs/DEPLOYMENT.md`. Design notes: `docs/ARCHITECTURE.md`, `docs/SECURITY.md`.
Read `docs/VALIDATION.md` first: it lists what has and has not been run.
