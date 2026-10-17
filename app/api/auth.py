from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.authentication import AuthenticateUser, InvalidCredentialsError
from app.core.config import settings
from app.domain.entities import AuthenticatedUser, UserRole
from app.infrastructure.database import SessionLocal
from app.infrastructure.user_repository import SqlAlchemyUserRepository


router = APIRouter(prefix="/api/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, str | None]


def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Function scope commits before the response is sent; the default request scope commits afterwards,
# so clients could read stale data and commit failures would never reach them.
SessionDep = Annotated[Session, Depends(get_session, scope="function")]


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, session: SessionDep) -> TokenResponse:
    try:
        token, user = AuthenticateUser(SqlAlchemyUserRepository(session)).execute(
            request.username, request.password
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "username": user.username, "role": user.role.value, "branch_id": user.branch_id},
    )


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]) -> AuthenticatedUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return AuthenticatedUser(
            id=payload["sub"],
            username=payload["username"],
            role=UserRole(payload["role"]),
            branch_id=payload.get("branch_id"),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as error:
        raise unauthorized from error