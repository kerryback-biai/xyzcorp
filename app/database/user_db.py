import psycopg2
import psycopg2.extras
from contextlib import contextmanager

from app.config import settings


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
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    spending_limit_cents INTEGER DEFAULT 1000,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                DO $$ BEGIN
                    ALTER TABLE users RENAME COLUMN email TO username;
                EXCEPTION WHEN undefined_column THEN NULL;
                END $$;

                ALTER TABLE users ADD COLUMN IF NOT EXISTS spending_limit_cents INTEGER DEFAULT 1000;

                DROP TABLE IF EXISTS app_access;

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

                CREATE INDEX IF NOT EXISTS idx_meridian_usage_user ON meridian_usage_log(user_id);
                CREATE INDEX IF NOT EXISTS idx_meridian_usage_time ON meridian_usage_log(created_at);
            """)


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def create_user(username: str, password_hash: str, name: str = "",
                is_admin: bool = False, spending_limit_cents: int | None = None) -> int:
    limit = spending_limit_cents or settings.default_spending_limit_cents
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (username, password_hash, name, is_admin, spending_limit_cents)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (username, password_hash, name, is_admin, limit)
            )
            return cur.fetchone()[0]


def list_users() -> list[dict]:
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.username, u.name, u.is_admin, u.is_active,
                       u.spending_limit_cents,
                       u.created_at,
                       COALESCE(SUM(l.cost_cents), 0) as total_cost_cents
                FROM users u
                LEFT JOIN meridian_usage_log l ON u.id = l.user_id
                GROUP BY u.id
                ORDER BY u.created_at DESC
            """)
            return [dict(r) for r in cur.fetchall()]


def update_user(user_id: int, **kwargs) -> None:
    allowed = {"name", "is_active", "is_admin", "password_hash", "spending_limit_cents"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [user_id]
            cur.execute(f"UPDATE users SET {set_clause} WHERE id = %s", values)


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
                    """SELECT l.*, u.username, u.name
                       FROM meridian_usage_log l JOIN users u ON l.user_id = u.id
                       ORDER BY l.created_at DESC LIMIT 500"""
                )
            return [dict(r) for r in cur.fetchall()]
