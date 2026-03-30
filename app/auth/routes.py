from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.database.user_db import get_user_by_username
from app.auth.dependencies import verify_password, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    name: str
    is_admin: bool


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_token(user["id"])
    return LoginResponse(token=token, name=user["name"], is_admin=bool(user["is_admin"]))
