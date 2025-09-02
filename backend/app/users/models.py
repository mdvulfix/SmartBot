from pydantic import BaseModel

PERMISSIONS = {
    "view_product": "Can view products",
    "add_product": "Can add products",
    "edit_product": "Can edit products",
    "delete_product": "Can delete products"
}


class User(BaseModel):
    def __init__(self, username, email, is_admin, permissions) -> None:
        self.username = username
        self.email = email
        self.is_admin = is_admin
        self.permissions = permissions

    def get_info(self) -> dict:
        return {
            "username": self.username,
            "email": self.email,
            "is_admin": self.is_admin,
            "permissions": self.permissions
        }

    def __repr__(self) -> str:
        return f"<User(username='{self.username}', email='{self.email}')>"
    

class AdminUser(User):
    def __init__(self, username, email) -> None:
        super().__init__(username, email, True, PERMISSIONS)

class RegularUser(User):
    def __init__(self, username, email, permissions) -> None:
        super().__init__(username, email, False, permissions)