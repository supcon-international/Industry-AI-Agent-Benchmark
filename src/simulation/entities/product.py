# src/simulation/entities/product.py
import uuid
from typing import List, Tuple

class Product:
    """
    Represents a single product unit being manufactured in the factory.
    
    Attributes:
        id (str): A unique identifier for the product instance.
        product_type (str): The type of the product (e.g., 'P1', 'P2').
        order_id (str): The ID of the order this product belongs to.
        history (List[Tuple[float, str]]): A log of events for this product,
            e.g., [(10.5, "Arrived at StationA"), (45.2, "Finished processing at StationA")].
    """
    def __init__(self, product_type: str, order_id: str):
        self.id: str = f"prod_{uuid.uuid4().hex[:8]}"
        self.product_type: str = product_type
        self.order_id: str = order_id
        self.history: List[Tuple[float, str]] = []

    def __repr__(self) -> str:
        return f"Product(id='{self.id}', type='{self.product_type}')"

    def add_history(self, timestamp: float, event: str):
        """Adds a new event to the product's history log."""
        self.history.append((timestamp, event)) 