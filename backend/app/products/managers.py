from fastapi import HTTPException

from products.models import Product

class ProductManager:
    def __init__(self) -> None:
        self.products = {}

    def add_product(self, item: Product) -> None:
        if self._is_product_exist(item.id):
            raise HTTPException(status_code=400, detail="Product with this ID already exists.")
        self.products[item.id] = item
        

    def get_product(self, item_id: int) -> Product:
        if not self._is_product_exist(item_id):
            raise HTTPException(status_code=404, detail="Product not found.")
        return self.products[item_id]
    
    
    def edit_product(self, item_id: int, new_item: Product) -> None:
        if not self._is_product_exist(item_id):
            raise HTTPException(status_code=404, detail="Product not found.")
        self.products[item_id] = new_item


    def delete_product(self, item_id: int) -> None:
        if not self._is_product_exist(item_id):
            raise HTTPException(status_code=404, detail="Product not found.")
        del self.products[item_id]


    def get_all_products(self) -> list[Product]:
        return list(self.products.values())

    def _is_product_exist(self, item_id: int) -> bool:
        return item_id in self.products

