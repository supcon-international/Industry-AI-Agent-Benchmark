# simulation/entities/agv.py
import simpy
import math
from typing import Tuple, List, Dict

from config.schemas import DeviceStatus
from src.simulation.entities.base import Vehicle

class AGV(Vehicle):
    """
    Represents an Automated Guided Vehicle (AGV).

    AGVs are responsible for transporting products between stations.
    
    Attributes:
        battery_level (float): The current battery percentage (0-100).
        payload (List[any]): The list of products currently being carried.
        is_charging (bool): Flag indicating if the AGV is charging.
    """
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        speed_mps: float,
        battery_capacity: float,
    ):
        super().__init__(env, id, position, speed_mps)
        self.battery_level = 100.0
        self.battery_capacity = battery_capacity # Not used yet, for future extension
        self.payload = []
        self.is_charging = False

    def move_to(self, target_pos: Tuple[int, int], path_points: Dict[str, Tuple[int, int]]):
        """
        Moves the AGV to a new target position.
        This is a generator function that yields a timeout event.
        """
        self.set_status(DeviceStatus.PROCESSING) # Use 'processing' for 'moving'
        
        distance = math.dist(self.position, target_pos)
        travel_time = distance / self.speed_mps
        
        print(f"[{self.env.now:.2f}] {self.id}: Starting move from {self.position} to {target_pos}. Duration: {travel_time:.2f}s")
        
        yield self.env.timeout(travel_time)
        
        self.position = target_pos
        print(f"[{self.env.now:.2f}] {self.id}: Arrived at {self.position}.")
        self.set_status(DeviceStatus.IDLE)

    def load_product(self, product):
        """Adds a product to the AGV's payload."""
        self.payload.append(product)
        print(f"[{self.env.now:.2f}] {self.id}: Loaded product {product.id}.")

    def unload_product(self, product_id: str):
        """Removes a product from the AGV's payload."""
        product_to_remove = next((p for p in self.payload if p.id == product_id), None)
        if product_to_remove:
            self.payload.remove(product_to_remove)
            print(f"[{self.env.now:.2f}] {self.id}: Unloaded product {product_id}.")
            return product_to_remove
        else:
            print(f"[{self.env.now:.2f}] {self.id}: Error - Product {product_id} not in payload.")
            return None 