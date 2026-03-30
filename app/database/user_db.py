import psycopg2
import psycopg2.extras
from contextlib import contextmanager

from app.config import settings

APP_NAME = settings.app_name


def get_connection():
    conn = psycopg2.connect(settings.database_url)
    conn.autocommit = False
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS app_access (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    app_name TEXT NOT NULL,
                    spending_limit_cents INTEGER DEFAULT 1000,
                    granted_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (user_id, app_name)
                );

                CREATE TABLE IF NOT EXISTS meridian_usage_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cache_read_tokens INTEGER DEFAULT 0,
                    model TEXT,
                    cost_cents REAL DEFAULT 0,
                    tool_calls INTEGER DEFAULT 0,
                    request_type TEXT DEFAULT 'chat'
                );

                CREATE TABLE IF NOT EXISTS meridian_alerts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    alert_type TEXT,
                    message TEXT,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_app_access_app ON app_access(app_name);
                CREATE INDEX IF NOT EXISTS idx_meridian_usage_user ON meridian_usage_log(user_id);
                CREATE INDEX IF NOT EXISTS idx_meridian_usage_time ON meridian_usage_log(created_at);
            """)


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def create_user(email: str, password_hash: str, name: str = "",
                is_admin: bool = False, spending_limit_cents: int | None = None) -> int:
    limit = spending_limit_cents or settings.default_spending_limit_cents
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (email, password_hash, name, is_admin)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (email, password_hash, name, is_admin)
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO app_access (user_id, app_name, spending_limit_cents)
                   VALUES (%s, %s, %s)""",
                (user_id, APP_NAME, limit)
            )
            return user_id


def grant_app_access(user_id: int, app_name: str,
                     spending_limit_cents: int | None = None) -> None:
    limit = spending_limit_cents or settings.default_spending_limit_cents
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app_access (user_id, app_name, spending_limit_cents)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id, app_name) DO NOTHING""",
                (user_id, app_name, limit)
            )


def list_users() -> list[dict]:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.email, u.name, u.is_admin, u.is_active,
                       COALESCE(a.spending_limit_cents, %s) as spending_limit_cents,
                       u.created_at,
                       COALESCE(SUM(l.cost_cents), 0) as total_cost_cents
                FROM users u
                LEFT JOIN app_access a ON u.id = a.user_id AND a.app_name = %s
                LEFT JOIN meridian_usage_log l ON u.id = l.user_id
                WHERE a.id IS NOT NULL OR u.is_admin = TRUE
                GROUP BY u.id, a.spending_limit_cents
                ORDER BY u.created_at DESC
            """, (settings.default_spending_limit_cents, APP_NAME))
            return [dict(r) for r in cur.fetchall()]


def update_user(user_id: int, **kwargs) -> None:
    user_fields = {"name", "is_active", "is_admin"}
    access_fields = {"spending_limit_cents"}

    user_updates = {k: v for k, v in kwargs.items() if k in user_fields}
    access_updates = {k: v for k, v in kwargs.items() if k in access_fields}

    with get_db() as conn:
        with conn.cursor() as cur:
            if user_updates:
                set_clause = ", ".join(f"{k} = %s" for k in user_updates)
                values = list(user_updates.values()) + [user_id]
                cur.execute(f"UPDATE users SET {set_clause} WHERE id = %s", values)
            if access_updates:
                set_clause = ", ".join(f"{k} = %s" for k in access_updates)
                values = list(access_updates.values()) + [user_id, APP_NAME]
                cur.execute(
                    f"UPDATE app_access SET {set_clause} WHERE user_id = %s AND app_name = %s",
                    values
                )


def log_usage(user_id: int, input_tokens: int, output_tokens: int,
              cache_read_tokens: int, model: str, cost_cents: float,
              tool_calls: int = 0, request_type: str = "chat") -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meridian_usage_log
                   (user_id, input_tokens, output_tokens, cache_read_tokens,
                    model, cost_cents, tool_calls, request_type)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, input_tokens, output_tokens, cache_read_tokens,
                 model, cost_cents, tool_calls, request_type)
            )


def get_user_total_cost(user_id: int) -> float:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT COALESCE(SUM(cost_cents), 0) as total FROM meridian_usage_log WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()["total"]


def get_usage_summary(user_id: int | None = None) -> list[dict]:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if user_id:
                cur.execute(
                    """SELECT * FROM meridian_usage_log WHERE user_id = %s
                       ORDER BY created_at DESC LIMIT 200""",
                    (user_id,)
                )
            else:
                cur.execute(
                    """SELECT l.*, u.email, u.name
                       FROM meridian_usage_log l JOIN users u ON l.user_id = u.id
                       ORDER BY l.created_at DESC LIMIT 500"""
                )
            return [dict(r) for r in cur.fetchall()]
