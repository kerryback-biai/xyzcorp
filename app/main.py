from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.auth.dependencies import hash_password
from app.database.user_db import init_db, get_user_by_email, create_user, update_user, grant_app_access
from app.auth.routes import router as auth_router
from app.admin.routes import router as admin_router
from app.chat.routes import router as chat_router

STATIC_DIR = "app/static"


def ensure_admin():
    if not settings.admin_user or not settings.admin_password:
        return
    existing = get_user_by_email(settings.admin_user)
    if existing:
        if not existing["is_admin"]:
            update_user(existing["id"], is_admin=True)
        user_id = existing["id"]
    else:
        user_id = create_user(
            email=settings.admin_user,
            password_hash=hash_password(settings.admin_password),
            name="Admin",
            is_admin=True,
        )
    grant_app_access(user_id, "vm", vm_password=settings.admin_password)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_admin()
    yield


app = FastAPI(title="AI Data Assistant", lifespan=lifespan)

# API routes first
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)

# Static assets (CSS, JS)
app.mount("/css", StaticFiles(directory=f"{STATIC_DIR}/css"), name="css")
app.mount("/js", StaticFiles(directory=f"{STATIC_DIR}/js"), name="js")


# HTML pages
@app.get("/")
@app.get("/login.html")
async def login_page():
    return FileResponse(f"{STATIC_DIR}/login.html")


@app.get("/index.html")
async def index_page():
    return FileResponse(f"{STATIC_DIR}/index.html")


@app.get("/admin.html")
async def admin_page():
    return FileResponse(f"{STATIC_DIR}/admin.html")
