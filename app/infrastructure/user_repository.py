from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import User, UserRole
from app.infrastructure.database import UserRecord


class SqlAlchemyUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_username(self, username: str) -> User | None:
        record = self.session.scalar(select(UserRecord).where(UserRecord.username == username))
        if record is None:
            return None
        return User(
            id=record.id,
            name=record.name,
            username=record.username,
            password_hash=record.password_hash,
            role=UserRole(record.role),
            branch_id=record.branch_id,
            active=record.active,
        )