import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from app.admin.dependencies import require_admin
from app.auth.dependencies import hash_password
from app.database.user_db import (
    list_users, create_user, update_user, get_user_by_username, get_usage_summary,
    grant_app_access,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    name: str = ""
    is_admin: bool = False
    spending_limit_cents: int | None = None
    apps: list[str] = ["meridian"]


class UpdateUserRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    spending_limit_cents: int | None = None


@router.get("/users")
def admin_list_users(_admin: dict = Depends(require_admin)):
    return list_users()


@router.post("/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(req: CreateUserRequest, _admin: dict = Depends(require_admin)):
    if get_user_by_username(req.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    user_id = create_user(
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name,
        is_admin=req.is_admin,
        spending_limit_cents=req.spending_limit_cents,
    )
    for app_name in req.apps:
        grant_app_access(
            user_id, app_name,
            spending_limit_cents=req.spending_limit_cents,
            vm_password=req.password if app_name == "vm" else None,
        )
    return {"id": user_id, "username": req.username}


@router.patch("/users/{user_id}")
def admin_update_user(user_id: int, req: UpdateUserRequest,
                      _admin: dict = Depends(require_admin)):
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_user(user_id, **updates)
    return {"ok": True}


@router.post("/users/bulk")
async def admin_bulk_create(file: UploadFile = File(...),
                            _admin: dict = Depends(require_admin)):
    """Upload a CSV with columns: username, password, name (optional),
    spending_limit (optional, in dollars), apps (optional, comma-separated e.g. 'meridian,vm')."""
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    created = []
    skipped = []
    for row in reader:
        username = row.get("username", "").strip()
        password = row.get("password", "").strip()
        if not username or not password:
            continue
        if get_user_by_username(username):
            skipped.append(username)
            continue
        name = row.get("name", "").strip()
        limit = row.get("spending_limit", "")
        limit_cents = int(float(limit) * 100) if limit.strip() else None
        apps_str = row.get("apps", "").strip()
        apps = [a.strip() for a in apps_str.split(",") if a.strip()] if apps_str else ["meridian"]
        user_id = create_user(
            username=username,
            password_hash=hash_password(password),
            name=name,
            spending_limit_cents=limit_cents,
        )
        for app_name in apps:
            if app_name != "meridian":
                grant_app_access(
                    user_id, app_name,
                    spending_limit_cents=limit_cents,
                    vm_password=password if app_name == "vm" else None,
                )
        created.append(username)
    return {"created": created, "skipped": skipped}


@router.get("/usage")
def admin_usage(user_id: int | None = None, _admin: dict = Depends(require_admin)):
    return get_usage_summary(user_id)
