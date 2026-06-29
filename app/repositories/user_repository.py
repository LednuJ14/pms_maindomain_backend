"""
User repository: encapsulates DB access for User model
"""
from typing import Optional
from app import db
from app.models.user import User


class UserRepository:
    def get_by_id(self, user_id: int) -> Optional[User]:
        return User.query.get(user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        return User.query.filter_by(email=email.lower().strip()).first()

    def create(self, user: User) -> User:
        db.session.add(user)
        return user

    def save(self, user: User) -> User:
        # user is already tracked; just return it for consistency
        return user

    def commit(self):
        db.session.commit()

    def flush(self):
        db.session.flush()

    def rollback(self):
        db.session.rollback()