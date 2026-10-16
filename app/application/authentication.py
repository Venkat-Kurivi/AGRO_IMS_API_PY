from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.domain.entities import AuthenticatedUser
from app.domain.repositories import UserRepository


password_hash = PasswordHash.recommended()


class InvalidCredentialsError(Exception):
    pass


class AuthenticateUser:
    def __init__(self, users: UserRepository):
        self.users = users

    def execute(self, username: str, password: str) -> tuple[str, AuthenticatedUser]:
        user = self.users.get_by_username(username)
        if user is None or not user.active or not password_hash.verify(password, user.password_hash):
            raise InvalidCredentialsError("Incorrect username or password")

        identity = AuthenticatedUser(user.id, user.username, user.role, user.branch_id)
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
        token = jwt.encode(
            {
                "sub": user.id,
                "username": user.username,
                "role": user.role.value,
                "branch_id": user.branch_id,
                "exp": expires_at,
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        return token, identity