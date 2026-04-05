# Chat: Koyeb deployment with shared Postgres and XYZ rebrand
**Date:** 2026-03-30
**Repo:** biai-meridian (master)

## What was done
- Deployed biai-meridian as a Koyeb service with Dockerfile, uvicorn on port 8000
- Created shared Koyeb managed Postgres (`biai-db`) for cross-app user management
- Migrated from ephemeral SQLite to Postgres with shared schema: `users`, `app_access`, `meridian_usage_log`
- Added bulk CSV user upload (`POST /api/admin/users/bulk`) with `apps` column for multi-app access
- Auto-creates admin account on startup from `ADMIN_USER`/`ADMIN_PASSWORD` env vars
- Updated biai-vm to read student accounts from shared Postgres via `fetch-students.py`
- Renamed `email` to `username` throughout auth (login form, API, DB column with migration)
- Added show/hide password toggle on login page
- Rebranded: Meridian Corp -> XYZ Corp across biai-meridian, biai-course (349+ occurrences)
- Updated login page with BI to AI branding (Rice Business Executive Education)
- Flattened data directory: removed unused datasets, elevated meridian/ contents to data/
- Fixed admin password corruption caused by bash `!` escaping in env vars
- Set DNS CNAME for meridian.kerryback.com (user configured separately)

## Files changed
- `Dockerfile`, `.dockerignore`, `.gitignore`, `requirements.txt`
- `app/config.py`, `app/main.py`, `app/database/user_db.py`, `app/database/duckdb_manager.py`
- `app/auth/routes.py`, `app/admin/routes.py`
- `app/static/login.html`, `app/static/admin.html`, `app/static/index.html`
- `app/static/js/admin.js`, `app/static/js/chat.js`
- `app/system_prompts/base.txt`, `app/system_prompts/database_schemas/meridian.txt`
- `data/` — 41 parquet files across 10 enterprise systems
- biai-vm: `entrypoint.sh`, `Dockerfile`, `fetch-students.py`
- biai-course: 48 files (slides, demos, planning, docs)

## Next steps
- Verify data queries work after latest deployment finishes building
- Test bulk CSV upload with real student list (columns: username, password, name, apps)
- VM service needs redeployment after next DB-seeded user creation to pick up new accounts
- Consider storing `ADMIN_PASSWORD` as a Koyeb secret to avoid bash escaping issues
