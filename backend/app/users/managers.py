from fastapi import HTTPException

from users.models import User, AdminUser, RegularUser

class UserManager:
    def __init__(self) -> None:
        self.users = {}
    
    def add_user(self, username: str, email: str, is_admin: bool, permissions: list[str]) -> User:
        if username in self.users:
            raise HTTPException(status_code=400, detail="User with this username already exists.")
        
        if is_admin:
            user = AdminUser(username=username, email=email)
        else:
            user = RegularUser(username=username, email=email, permissions=permissions)
        
        self.users[username] = user
        return user

    def remove_user(self, username: str) -> None:
        if username not in self.users:
            raise HTTPException(status_code=404, detail="User not found.")
        del self.users[username]


    def get_user(self, username: str) -> User:
        if username not in self.users:
            raise HTTPException(status_code=404, detail="User not found.")
        return self.users[username]
    
    def get_all_users(self) -> list[User]:
        return [user.get_info() for user in self.users.values()]