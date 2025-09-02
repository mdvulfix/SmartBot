from fastapi import FastAPI, APIRouter

from products.routers import product_router
from users.routers import user_router

app = FastAPI()

api_v1_router = APIRouter(prefix="/v1/api")
api_v1_router.include_router(product_router)
api_v1_router.include_router(user_router)
app.include_router(api_v1_router)