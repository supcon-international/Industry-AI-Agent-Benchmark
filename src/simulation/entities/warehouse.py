# simulation/entities/warehouse.py
import simpy
import random
from typing import Dict, Tuple, Optional

from src.simulation.entities.base import Device
from src.simulation.entities.product import Product
from config.schemas import WarehouseStatus
from config.topics import get_warehouse_status_topic

class BaseWarehouse(Device):
    """Base class for all warehouse types, inheriting from Device."""

    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        mqtt_client=None,
        interacting_points: list = [],
        **kwargs # Absorb other config values
    ):
        super().__init__(env, id, position, device_type="warehouse", mqtt_client=mqtt_client)
        self.buffer = simpy.Store(env)
        self.interacting_points = interacting_points
        self.stats = {}  # To be overridden by subclasses

    def publish_status(self, message: str = "Warehouse is ready"):
        """Publishes the current status of the warehouse to MQTT."""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
        status_data = WarehouseStatus(
            timestamp=self.env.now,
            source_id=self.id,
            message=message,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats
        )
        self.mqtt_client.publish(get_warehouse_status_topic(self.id), status_data.model_dump_json(), retain=False)

    def get_buffer_level(self) -> int:
        """Return the current number of items in the buffer."""
        return len(self.buffer.items)

    def run(self):
        """Warehouses don't process products, just idle loop."""
        while True:
            yield self.env.timeout(60)  # Check every minute

class RawMaterial(BaseWarehouse):
    """Raw material warehouse - the starting point of the production line"""

    def __init__(
        self,
        env: simpy.Environment,
        mqtt_client=None,
        **config
    ):
        super().__init__(env=env, mqtt_client=mqtt_client, **config)
        self.device_type = "raw_material"  # Override device type
        self.stats = {
            "total_materials_supplied": 0,
            "product_type_summary": {"P1": 0, "P2": 0, "P3": 0}
        }
        print(f"[{self.env.now:.2f}] 🏭 {self.id}: Raw material warehouse is ready")
        self.publish_status("Raw material warehouse is ready")

    def create_raw_material(self, product_type: str, order_id: str) -> Product:
        """Create raw material product"""
        product = Product(product_type, order_id)
        self.stats["total_materials_supplied"] += 1
        self.stats["product_type_summary"][product_type] += 1
        product.add_history(self.env.now, f"Raw material created at {self.id}")
        print(f"[{self.env.now:.2f}] 🔧 {self.id}: Create raw material {product.id} (type: {product_type})")
        self.buffer.put(product)
        self.publish_status(f"Supply raw material {product.id} (type: {product_type}) since order {order_id} is created")
        return product

    def is_full(self) -> bool:
        # return self.get_buffer_level() >= self.buffer_size
        return False

class Warehouse(BaseWarehouse):
    """Finished product warehouse - the ending point of the production line"""

    def __init__(
        self,
        env: simpy.Environment,
        mqtt_client=None,
        **config
    ):
        super().__init__(env=env, mqtt_client=mqtt_client, **config)
        self.stats = {
            "total_products_received": 0,
            "product_type_summary": {"P1": 0, "P2": 0, "P3": 0},
        }
        print(f"[{self.env.now:.2f}] 🏪 {self.id}: Finished product warehouse is ready")
        self.publish_status("Warehouse is ready")

    def add_product_to_buffer(self, product: Product):
        """AGV put product to warehouse"""
        yield self.buffer.put(product)
        self.publish_status(f"Store finished product {product.id} (type: {product.product_type})")
        self.stats["total_products_received"] += 1
        self.stats["product_type_summary"][product.product_type] += 1
        product.add_history(self.env.now, f"Stored in warehouse {self.id}")
        print(f"[{self.env.now:.2f}] 📦 {self.id}: Store finished product {product.id} (type: {product.product_type})")
        return True
