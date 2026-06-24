"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenResponse, UserCreate, UserLogin, UserOut
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.rag.database import session_scope
from app.rag.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/register", response_model=TokenResponse)
async def register_user(payload: UserCreate) -> TokenResponse:
    if not get_settings().allow_register:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is closed")

    normalized_username = payload.username.strip().lower()
    display_name = payload.display_name.strip() or normalized_username
    with session_scope() as session:
        existing = session.scalar(select(User).where(User.username == normalized_username))
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        user = User(
            username=normalized_username,
            password_hash=hash_password(payload.password),
            display_name=display_name,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        user_out = _user_out(user)

    return TokenResponse(access_token=create_access_token(user_out.id), user=user_out)


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin) -> TokenResponse:
    normalized_username = payload.username.strip().lower()
    with session_scope() as session:
        user = session.scalar(select(User).where(User.username == normalized_username))
        if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_out = _user_out(user)

    return TokenResponse(access_token=create_access_token(user_out.id), user=user_out)


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(current_user)
