import secrets
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBUser
from src.db.operations import get_db_session
from src.routes.v1.users.schema import UserLoginInput
from src.routes.v1.users.service import UserService
from src.utils.redis import redis_client

security = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


async def authenticate_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db_session: AsyncSession = Depends(get_db_session),
):
    token = credentials.credentials
    session_key = f"user_session:{token}"
    user_id = await redis_client.get(session_key)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user_service = UserService(db_session=db_session)
    user = await user_service.retrieve(user_id=UUID(user_id))

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return user


async def require_admin(current_user: DBUser = Depends(authenticate_user)) -> DBUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def authenticate_user_login(login_input: UserLoginInput, db_session: AsyncSession = Depends(get_db_session)):
    user_service = UserService(db_session=db_session)

    try:
        user = await user_service.retrieve_by_email(email=login_input.email)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(login_input.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return user
