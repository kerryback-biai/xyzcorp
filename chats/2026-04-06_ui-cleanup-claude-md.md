# Chat: UI cleanup and CLAUDE.md creation
**Date:** 2026-04-06
**Repo:** biai-xyzcorp (master)

## What was done
- Removed welcome title ("XYZ Corp Data Simulation") and subtitle ("Rice Business Executive Education...") from the chat prompt page
- Dropped the em dash in the navbar banner: "XYZ Corp — Data Simulation" → "XYZ Corp Data Simulation"
- Removed `firstname_lastname` placeholder from the login page username input
- Changed "10 enterprise systems" to "10 synthetic enterprise systems" in welcome text
- Created `CLAUDE.md` documenting:
  - User management via the separate biai-admin service (endpoints, DB schema, seed users)
  - Koyeb service management via CLI, including that services are in the **kerryback-biai** org (not the default personal org) and require `KOYEB_TOKEN` from `.env`

## Files changed
- `app/static/index.html` — banner and title tag
- `app/static/js/chat.js` — welcome area title/subtitle removed, synthetic wording
- `app/static/login.html` — username placeholder removed
- `CLAUDE.md` — created

## Next steps
- None identified
