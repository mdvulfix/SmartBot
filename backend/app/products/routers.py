from fastapi import APIRouter

from products.models import Product
from products.managers import ProductManager

product_manager = ProductManager()
product_router = APIRouter(prefix="/products", tags=["products"])


@product_router.get("")
async def get_all_products() -> tuple[bool, list[Product]]:
    return True, product_manager.get_all_products()

@product_router.get("/{product_id}")
async def get_product(product_id: int) -> tuple[bool, Product]:
    return True, product_manager.get_product(item_id=product_id)

@product_router.post("")
async def add_product(product: Product):
    return product_manager.add_product(product)

@product_router.put("/{product_id}")
async def edit_product(product_id: int, product: Product):
    return product_manager.edit_product(item_id=product_id, new_item=product)

@product_router.delete("/{product_id}")
async def delete_product(product_id: int):
    return product_manager.delete_product(item_id=product_id)