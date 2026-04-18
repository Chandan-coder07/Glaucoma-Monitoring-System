"""
Auth router — /api/auth/login  /api/auth/register  /api/auth/me
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends, Header

from models.database import RegisterRequest, LoginRequest, TokenResponse
from services.auth_service import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
)

router = APIRouter()


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> dict:
    """JWT dependency — raises 401 on missing/invalid token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token   = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token is invalid or expired")
    return payload


@router.post("/register", response_model=TokenResponse)
async def register(request: Request, body: RegisterRequest):
    db = request.app.state.db

    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    doc = {
        "name":             body.name,
        "email":            body.email,
        "hashed_password":  hash_password(body.password),
        "role":             body.role,
        "age":              body.age,
        "cornea_thickness": body.cornea_thickness,
        "created_at":       datetime.utcnow(),
        "is_active":        True,
    }
    result  = await db.users.insert_one(doc)
    user_id = str(result.inserted_id)
    token   = create_access_token({"sub": user_id, "role": body.role, "email": body.email})

    return TokenResponse(access_token=token, role=body.role, user_id=user_id, name=body.name)


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest):
    db   = request.app.state.db
    user = await db.users.find_one({"email": body.email})

    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    user_id = str(user["_id"])
    token   = create_access_token({"sub": user_id, "role": user["role"], "email": user["email"]})
    return TokenResponse(access_token=token, role=user["role"], user_id=user_id, name=user["name"])


@router.get("/me")
async def get_me(request: Request, current_user: dict = Depends(get_current_user)):
    from bson import ObjectId
    db   = request.app.state.db
    user = await db.users.find_one({"_id": ObjectId(current_user["sub"])})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id":               str(user["_id"]),
        "name":             user["name"],
        "email":            user["email"],
        "role":             user["role"],
        "age":              user.get("age"),
        "cornea_thickness": user.get("cornea_thickness"),
    }
