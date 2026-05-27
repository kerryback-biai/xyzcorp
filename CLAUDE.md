# XYZ Corp Data Simulation

* [ ] 

## Stack

- **Backend:** FastAPI + Uvicorn (Python 3.12)
- **AI:** Anthropic Claude API
- **User DB:** PostgreSQL on Koyeb (`biai-db`, shared with admin service)
- **Data DB:** DuckDB (in-process, reads `data/*.parquet` — 10 enterprise systems)
- **Auth:** JWT (HS256, 24h expiry) + bcrypt password hashing
- **Frontend:** Vanilla JS + Bootstrap 5 (Flatly theme)
- **Deployment:** Docker container on Koyeb, auto-deploys on push to `master`

## User Management

Users are managed through a **separate admin service** at `c:\users\kerry\repos\biai-admin` (deployed at `admin-kerryback-biai-2bb62426.koyeb.app`). Both services share the same PostgreSQL database (`biai-db`).

### Admin service capabilities

- **Single user creation:** username, password, display name, spending limit
- **Bulk CSV upload:** columns `username,password,name,spending_limit`
- **Update user:** toggle active/disabled, grant/revoke admin, change spending limit
- **Reset password:** sets bcrypt hash + plaintext `vm_password` (used by AI+Code Lab VM)
- **Delete user:** cascades to `meridian_usage_log` and `meridian_alerts`
- **Usage dashboard:** total cost, token counts, per-user spending vs. limits

### Admin API endpoints (biai-admin)

All require admin JWT auth (`Authorization: Bearer <token>`):

| Method | Endpoint                                 | Description                  |
| ------ | ---------------------------------------- | ---------------------------- |
| GET    | `/api/admin/users`                     | List users with usage totals |
| POST   | `/api/admin/users`                     | Create single user           |
| POST   | `/api/admin/users/bulk`                | Bulk create from CSV         |
| PATCH  | `/api/admin/users/{id}`                | Update user fields           |
| POST   | `/api/admin/users/{id}/reset-password` | Reset password               |
| DELETE | `/api/admin/users/{id}`                | Delete user + usage data     |

### Database schema (shared `biai-db`)

```sql
users (id, username, password_hash, name, is_admin, is_active, spending_limit_cents, vm_password, created_at)
meridian_usage_log (user_id, input_tokens, output_tokens, cache_read_tokens, model, cost_cents, tool_calls, request_type, created_at)
meridian_alerts (user_id, alert_type, message, acknowledged, created_at)
```

### Startup seed users

On every startup, `seed_users()` ensures these accounts exist:

- `kerry_back` (admin)
- `kelcie_wold` (admin)

An admin account is also auto-created from `ADMIN_USER` / `ADMIN_PASSWORD` env vars if set.

## Koyeb Service Management

### Organization & authentication

These services live in the **kerryback-biai** Koyeb organization, not the default personal org. The `KOYEB_TOKEN` in `.env` is a personal access token that grants access to this org. The default `~/.koyeb.yaml` token points to the personal org (kerrybackapps) and will not find these services.

**Always pass the org token** when using the CLI:

```bash
export KOYEB_TOKEN=$(grep KOYEB_TOKEN .env | cut -d= -f2)
```

Or prefix individual commands: `KOYEB_TOKEN=... koyeb <command>`

### Services in kerryback-biai org

| App         | Service     | Domain                                                                      |
| ----------- | ----------- | --------------------------------------------------------------------------- |
| `xyzcorp` | `xyzcorp` | `xyzcorp.rice-business.org`, `xyzcorp.koyeb.app`                        |
| `admin`   | `admin`   | `ai-admin.rice-business.org`, `admin-kerryback-biai-2bb62426.koyeb.app` |
| `biai-db` | —          | Managed PostgreSQL (`biai-db-kerryback-biai-c028876c.koyeb.app`)          |

### Common CLI commands

```bash
# List apps and services
koyeb apps list
koyeb services list

# View service details
koyeb services describe xyzcorp/xyzcorp

# View logs
koyeb services logs xyzcorp/xyzcorp
koyeb services logs xyzcorp/xyzcorp --type build    # build logs
koyeb services logs xyzcorp/xyzcorp --type runtime  # runtime logs

# Redeploy (trigger rebuild from latest commit)
koyeb services redeploy xyzcorp/xyzcorp

# Pause / resume
koyeb services pause xyzcorp/xyzcorp
koyeb services resume xyzcorp/xyzcorp

# View deployments
koyeb deployments list
koyeb deployments describe DEPLOYMENT_ID

# Manage secrets (env vars)
koyeb secrets list
koyeb secrets describe SECRET_NAME
koyeb secrets update SECRET_NAME --value "new-value"
koyeb secrets create SECRET_NAME --value "value"

# Database
koyeb databases list
```

### Environment variables (set as Koyeb secrets)

| Variable              | Purpose                      |
| --------------------- | ---------------------------- |
| `ANTHROPIC_API_KEY` | Claude API key               |
| `DATABASE_URL`      | PostgreSQL connection string |
| `SECRET_KEY`        | JWT signing key              |
| `ADMIN_USER`        | Auto-create admin username   |
| `ADMIN_PASSWORD`    | Auto-create admin password   |

### Deployment flow

1. Push to `master` on GitHub (`kerryback-biai/xyzcorp`)
2. Koyeb webhook triggers Docker build from `Dockerfile`
3. Container starts `uvicorn app.main:app --host 0.0.0.0 --port 8000`
4. `init_db()` runs migrations, `ensure_admin()` and `seed_users()` create accounts
