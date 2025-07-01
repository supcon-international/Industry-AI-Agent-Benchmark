# simulation/entities/station.py
import simpy
import random
from typing import Dict, Tuple

from config.schemas import DeviceStatus
from src.simulation.entities.base import Device

class Station(Device):
    """
    Represents a manufacturing station in the factory.

    Stations have a buffer to hold products and take time to process them.
    
    Attributes:
        buffer (simpy.Store): A buffer to hold incoming products.
        buffer_size (int): The maximum capacity of the buffer.
        processing_times (Dict[str, Tuple[int, int]]): A dictionary mapping product types
            to a tuple of (min_time, max_time) for processing.
    """
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        buffer_size: int,
        processing_times: Dict[str, Tuple[int, int]],
    ):
        super().__init__(env, id, position)
        self.buffer_size = buffer_size
        self.buffer = simpy.Store(env, capacity=buffer_size)
        self.processing_times = processing_times
        # Start the main operational process for the station
        self.env.process(self.run())

    def run(self):
        """The main operational loop for the station."""
        while True:
            # Wait for a product to arrive in the buffer
            product = yield self.buffer.get()
            
            # Start processing the product
            yield self.env.process(self.process_product(product))

    def process_product(self, product):
        """Simulates the time taken to process a single product."""
        self.set_status(DeviceStatus.PROCESSING)
        
        # Get processing time based on product type
        min_time, max_time = self.processing_times.get(product.product_type, (10, 20)) # Default time
        processing_time = random.uniform(min_time, max_time)
        
        yield self.env.timeout(processing_time)
        
        # For now, we'll just say the product is done.
        # Later, this will trigger moving the product to the next stage.
        print(f"[{self.env.now:.2f}] {self.id}: Finished processing product {product.id}.")
        self.set_status(DeviceStatus.IDLE) 