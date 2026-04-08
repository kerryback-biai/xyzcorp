from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.auth.dependencies import hash_password
from app.database.user_db import init_db, get_user_by_username, create_user, update_user
from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router

STATIC_DIR = "app/static"


def ensure_admin():
    if not settings.admin_user or not settings.admin_password:
        return
    existing = get_user_by_username(settings.admin_user)
    if existing:
        if not existing["is_admin"]:
            update_user(existing["id"], is_admin=True)
    else:
        create_user(
            username=settings.admin_user,
            password_hash=hash_password(settings.admin_password),
            name="Admin",
            is_admin=True,
        )


SEED_USERS = [
    ("kerry_back", "Kerry Back"),
    ("kelcie_wold", "Kelcie Wold"),
]
SEED_PASSWORD = "jgsbai"


def seed_users():
    pw_hash = hash_password(SEED_PASSWORD)
    for username, name in SEED_USERS:
        if not get_user_by_username(username):
            create_user(username=username, password_hash=pw_hash, name=name,
                        is_admin=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_admin()
    seed_users()
    # Build RAG vector store from documents/
    from app.chat.rag import ingest_documents
    ingest_documents()
    yield


app = FastAPI(title="XYZ Corp Chatbot", lifespan=lifespan)

# API routes first
app.include_router(auth_router)
app.include_router(chat_router)

# Static assets (CSS, JS)
app.mount("/css", StaticFiles(directory=f"{STATIC_DIR}/css"), name="css")
app.mount("/js", StaticFiles(directory=f"{STATIC_DIR}/js"), name="js")


# File downloads for generated documents
@app.get("/api/files/{filename}")
async def download_file(filename: str):
    from app.chat.code_executor import get_file_path
    path = get_file_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/octet-stream",
    )


# HTML pages
@app.get("/")
@app.get("/login.html")
async def login_page():
    return FileResponse(f"{STATIC_DIR}/login.html")


@app.get("/index.html")
async def index_page():
    return FileResponse(f"{STATIC_DIR}/index.html")


