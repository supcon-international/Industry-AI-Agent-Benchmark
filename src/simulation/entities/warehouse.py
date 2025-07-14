# simulation/entities/warehouse.py
import simpy
import random
from typing import Dict, Tuple, Optional

from src.simulation.entities.station import Station
from src.simulation.entities.product import Product
from config.schemas import WarehouseStatus
from config.topics import get_warehouse_status_topic

class RawMaterial(Station):
    """
    Raw material warehouse - the starting point of the production line
    Function:
    1. Unlimited(large enough) raw material supply (according to order generation)
    2. Create various types of raw materials/semi-finished products
    3. Supply raw materials to AGV for transportation to stations
    4. Do not process any products
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str = "RawMaterial",
        position: Tuple[int, int] = (5, 20),
        buffer_size: int = 1000,  # large enough buffer
        mqtt_client=None
    ):
        # dont need processing time for raw material warehouse
        super().__init__(
            env=env,
            id=id,
            position=position,
            buffer_size=buffer_size,
            processing_times={},  # no processing time
            mqtt_client=mqtt_client
        )
        
        # override device type
        self.device_type = "raw_material"
        
        # statistics data
        self.stats = {
            "total_materials_supplied": 0,
            "product_type_summary": {"P1": 0, "P2": 0, "P3": 0}
        }
        
        print(f"[{self.env.now:.2f}] 🏭 {self.id}: Raw material warehouse is ready, buffer size: {buffer_size}")
        # Ensure status is published after initialization
        self.publish_status()

    def publish_status(self, message: str = "Raw material warehouse is ready"):
        """Publishes the current status of the raw material warehouse to MQTT."""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
        status_data = WarehouseStatus(
            timestamp=self.env.now,
            source_id=self.id,
            message=message,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats
        )
        self.mqtt_client.publish(get_warehouse_status_topic(self.id), status_data.model_dump_json(), retain=True)

    def run(self):
        """raw material warehouse dont process product, only wait for AGV to take product"""
        # empty loop, dont process product, avoid auto processing behavior from Station
        while True:
            yield self.env.timeout(60)  # check every minute

    def create_raw_material(self, product_type: str, order_id: str) -> Product:
        """Create raw material product"""
        product = Product(product_type, order_id)
        
        # record statistics
        self.stats["total_materials_supplied"] += 1
        self.stats["product_type_summary"][product_type] += 1
        
        # record history
        product.add_history(self.env.now, f"Raw material created at {self.id}")
        
        print(f"[{self.env.now:.2f}] 🔧 {self.id}: Create raw material {product.id} (type: {product_type})")
        # raw material warehouse has large capacity, so put will not block, keep simple
        self.buffer.put(product)
        self.publish_status(f"Supply raw material {product.id} (type: {product_type}) since order {order_id} is created")
        return product

    def is_full(self) -> bool:
        return self.get_buffer_level() >= self.buffer_size

class Warehouse(Station):
    """
    Finished product warehouse - the ending point of the production line
    Function:
    1. Unlimited storage of finished products
    2. Receive products transported by AGV
    3. Statistics of finished product information and quality data
    4. Do not process any products
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str = "Warehouse",
        position: Tuple[int, int] = (85, 20),
        mqtt_client=None
    ):
        # finished product warehouse dont need processing time
        super().__init__(
            env=env,
            id=id,
            position=position,
            processing_times={},  # no processing time
            mqtt_client=mqtt_client
        )
        self.buffer = simpy.Store(env)
        # override device type
        self.device_type = "warehouse"
        
        # statistics data
        self.stats = {
            "total_products_received": 0,
            "product_type_summary": {"P1": 0, "P2": 0, "P3": 0},
        }
        
        print(f"[{self.env.now:.2f}] 🏪 {self.id}: Finished product warehouse is ready")
        # Ensure status is published after buffer reassignment
        self.publish_status()

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
        self.mqtt_client.publish(get_warehouse_status_topic(self.id), status_data.model_dump_json(), retain=True)

    def run(self):
        """warehouse dont process product, only receive product"""
        # empty loop, dont process product, avoid auto processing behavior from Station
        while True:
            yield self.env.timeout(60)  # check every minute

    def add_product_to_buffer(self, product: Product):
        """AGV put product to warehouse"""

        yield self.buffer.put(product)
        self.publish_status(f"Store finished product {product.id} (type: {product.product_type})")
        # record finished product statistics
        self.stats["total_products_received"] += 1
        self.stats["product_type_summary"][product.product_type] += 1
        
        # record product completion history
        product.add_history(self.env.now, f"Stored in warehouse {self.id}")
        print(f"[{self.env.now:.2f}] 📦 {self.id}: Store finished product {product.id} (type: {product.product_type})")

        return True