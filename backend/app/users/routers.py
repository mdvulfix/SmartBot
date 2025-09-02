from fastapi import APIRouter

from users.models import User
from users.managers import UserManager

user_manager = UserManager()
user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.post("")
async def add_user(username: str, email: str, is_admin: bool, permissions: list[str]) -> User:
    return user_manager.add_user(username, email, is_admin, permissions)

@user_router.get("")
async def get_all_users() -> list[User]:
    return user_manager.get_all_users()

@user_router.get("/{username}")
async def get_user(username: str) -> User:
    return user_manager.get_user(username)

@user_router.delete("/{username}")
async def remove_user(username: str):
    return user_manager.remove_user(username)