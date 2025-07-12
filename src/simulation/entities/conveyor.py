# simulation/entities/conveyor.py
import simpy
from typing import Optional
from src.simulation.entities.base import BaseConveyor
from src.simulation.entities.product import Product
from typing import Tuple

class Conveyor(BaseConveyor):
    """
    Conveyor with limited capacity, simulating a production line conveyor belt.
    Now uses simpy.Store for event-driven simulation and supports auto-transfer.
    """
    def __init__(self, env, id, capacity, position: Tuple[int, int], mqtt_client=None):
        super().__init__(env, id, position, mqtt_client)
        self.capacity = capacity
        self.buffer = simpy.Store(env, capacity=capacity)
        self.downstream_station = None  # 下游工站引用
        self._auto_transfer_proc = None
        self.transfer_time = 5.0 # 模拟搬运时间

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer."""
        self.downstream_station = station
        if self._auto_transfer_proc is None:
            self._auto_transfer_proc = self.env.process(self.run())

    def push(self, product):
        """Put a product on the conveyor (may block if full)."""
        return self.buffer.put(product)

    def pop(self):
        """Remove and return a product from the conveyor (may block if empty)."""
        return self.buffer.get()

    def get_buffer(self):
        return self.buffer

    def is_full(self):
        return len(self.buffer.items) >= self.capacity

    def is_empty(self):
        return len(self.buffer.items) == 0

    def peek(self):
        if self.buffer.items:
            return self.buffer.items[0]
        return None

    def run(self):
        """Auto-transfer products to downstream station's buffer if possible."""
        while True:
            if self.downstream_station is not None:
                # Before putting, check if the station can operate
                if not self.downstream_station.can_operate():
                    yield self.env.timeout(1.0) # wait before retrying
                    continue

                product = yield self.buffer.get()
                yield self.env.timeout(self.transfer_time) # 模拟搬运时间
                yield self.downstream_station.buffer.put(product)
                print(f"[{self.env.now:.2f}] Conveyor: moved product to {self.downstream_station.id}")
            else:
                yield self.env.timeout(1.0)

class TripleBufferConveyor(BaseConveyor):
    """
    Conveyor with three buffers:
    - main_buffer: for direct transfer to QualityCheck (auto-transfer)
    - upper_buffer: for P3 products, AGV pickup
    - lower_buffer: for P3 products, AGV pickup
    All buffers use simpy.Store for event-driven simulation.
    """
    def __init__(self, env, id, main_capacity, upper_capacity, lower_capacity, position: Tuple[int, int], mqtt_client=None):
        super().__init__(env, id, position, mqtt_client)
        self.main_buffer = simpy.Store(env, capacity=main_capacity)
        self.upper_buffer = simpy.Store(env, capacity=upper_capacity)
        self.lower_buffer = simpy.Store(env, capacity=lower_capacity)
        self.downstream_station = None  # QualityCheck
        self._auto_transfer_proc = None
        self.transfer_time = 5.0 # 模拟搬运时间

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer from main_buffer."""
        self.downstream_station = station
        if self._auto_transfer_proc is None:
            self._auto_transfer_proc = self.env.process(self.run())

    def push(self, product, buffer_type="main"):
        """Put product into specified buffer. buffer_type: 'main', 'upper', 'lower'."""
        return self.get_buffer(buffer_type).put(product)

    def get_buffer(self, buffer_type="main"):
        if buffer_type == "main":
            return self.main_buffer
        elif buffer_type == "upper":
            return self.upper_buffer
        elif buffer_type == "lower":
            return self.lower_buffer
        else:
            raise ValueError("buffer_type must be 'main', 'upper', or 'lower'")

    def pop(self, buffer_type="main"):
        """Get product from specified buffer."""
        return self.get_buffer(buffer_type).get()

    def is_full(self, buffer_type="main"):
        if buffer_type == "main":
            return len(self.main_buffer.items) >= self.main_buffer.capacity
        elif buffer_type == "upper":
            return len(self.upper_buffer.items) >= self.upper_buffer.capacity
        elif buffer_type == "lower":
            return len(self.lower_buffer.items) >= self.lower_buffer.capacity
        else:
            raise ValueError("buffer_type must be 'main', 'upper', or 'lower'")

    def is_empty(self, buffer_type="main"):
        if buffer_type == "main":
            return len(self.main_buffer.items) == 0
        elif buffer_type == "upper":
            return len(self.upper_buffer.items) == 0
        elif buffer_type == "lower":
            return len(self.lower_buffer.items) == 0
        else:
            raise ValueError("buffer_type must be 'main', 'upper', or 'lower'")

    def run(self):
        """Auto-transfer products from main_buffer to downstream station if possible."""
        while True:
            if self.downstream_station is not None:
                # Before putting, check if the station can operate
                if not self.downstream_station.can_operate():
                    yield self.env.timeout(1.0) # wait before retrying
                    continue
                
                product = yield self.main_buffer.get()
                yield self.env.timeout(self.transfer_time) # 模拟搬运时间
                yield self.downstream_station.buffer.put(product)
                print(f"[{self.env.now:.2f}] TripleBufferConveyor: moved product to {self.downstream_station.id}")
            else:
                yield self.env.timeout(1.0)
