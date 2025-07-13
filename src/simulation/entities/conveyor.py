# simulation/entities/conveyor.py
import simpy
from typing import Optional
from src.simulation.entities.base import BaseConveyor
from src.simulation.entities.product import Product
from typing import Tuple

from config.schemas import DeviceStatus, ConveyorStatus
from config.topics import get_conveyor_status_topic

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
        self.resumed = self.env.event() # 恢复信号
        self.resumed.succeed() # 初始状态是“已恢复”
        
        # 传送带默认状态为工作中
        self.status = DeviceStatus.WORKING
        self.publish_status()

    def _determine_status(self):
        """根据当前状态确定传送带状态"""
        if self.is_full():
            # 只有当真正无法继续工作时才算blocked
            if self.downstream_station and not self.downstream_station.can_operate():
                return DeviceStatus.BLOCKED
        return DeviceStatus.WORKING

    def publish_status(self, **kwargs):
        """直接发布传送带状态，不通过set_status"""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return

        # 实时确定状态
        current_status = self._determine_status()
        self.status = current_status

        status_data = ConveyorStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.buffer.items],
            is_full=self.is_full(),
            upper_buffer=None,
            lower_buffer=None
        )
        topic = get_conveyor_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=True)

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer."""
        self.downstream_station = station
        if self._auto_transfer_proc is None:
            self._auto_transfer_proc = self.env.process(self.run())

    def push(self, product):
        """Put a product on the conveyor (may block if full)."""
        result = self.buffer.put(product)
        # 产品添加后发布状态
        self.publish_status()
        return result

    def pop(self):
        """Remove and return a product from the conveyor (may block if empty)."""
        result = self.buffer.get()
        # 产品移除后发布状态
        self.publish_status()
        return result

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
                    # 发布blocked状态
                    self.set_status(DeviceStatus.BLOCKED)
                    yield self.env.timeout(1.0) # wait before retrying
                    continue

                yield self.resumed

                product = yield self.buffer.get()
                self.publish_status()
                try:
                    yield self.env.timeout(self.transfer_time) # 模拟搬运时间
                    
                    yield self.downstream_station.buffer.put(product)
                    print(f"[{self.env.now:.2f}] Conveyor: moved product to {self.downstream_station.id}")

                except simpy.Interrupt as e:
                    print(f"FAULT! Conveyor {self.id} interrupted, product {product.id} returned to start.")
                    yield self.buffer.put(product) # 安全地将产品退回起点
                    self.set_status(DeviceStatus.FAULT)

                    self.resumed = self.env.event()
                    
                finally:
                    self.publish_status()
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
        self.resumed = self.env.event() # 恢复信号
        self.resumed.succeed() # 初始状态是“已恢复”
        
        # 传送带默认状态为工作中
        self.status = DeviceStatus.WORKING
        self.publish_status()

    def _determine_status(self):
        """根据当前状态确定传送带状态"""
        # 只有main_buffer满且下游无法接收时才算blocked
        if (len(self.main_buffer.items) >= self.main_buffer.capacity and 
            self.downstream_station and not self.downstream_station.can_operate()):
            return DeviceStatus.BLOCKED
        elif len(self.upper_buffer.items) >= self.upper_buffer.capacity:
            return DeviceStatus.BLOCKED
        elif len(self.lower_buffer.items) >= self.lower_buffer.capacity:
            return DeviceStatus.BLOCKED
        return DeviceStatus.WORKING

    def publish_status(self, **kwargs):
        """直接发布传送带状态，不通过set_status"""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return

        # 实时确定状态
        current_status = self._determine_status()
        self.status = current_status
        
        # 判断是否满载：所有缓冲区都满
        is_full = (len(self.main_buffer.items) >= self.main_buffer.capacity and
                   len(self.upper_buffer.items) >= self.upper_buffer.capacity and
                   len(self.lower_buffer.items) >= self.lower_buffer.capacity)
        
        status_data = ConveyorStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.main_buffer.items],
            upper_buffer=[p.id for p in self.upper_buffer.items],
            lower_buffer=[p.id for p in self.lower_buffer.items],
            is_full=is_full
        )
        topic = get_conveyor_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=True)

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer from main_buffer."""
        self.downstream_station = station
        if self._auto_transfer_proc is None:
            self._auto_transfer_proc = self.env.process(self.run())

    def push(self, product, buffer_type="main"):
        """Put product into specified buffer. buffer_type: 'main', 'upper', 'lower'."""
        result = self.get_buffer(buffer_type).put(product)
        # 产品添加后发布状态
        self.publish_status()
        return result

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
        result = self.get_buffer(buffer_type).get()
        # 产品移除后发布状态
        self.publish_status()
        return result

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
                    # 发布blocked状态
                    self.set_status(DeviceStatus.BLOCKED)
                    yield self.env.timeout(1.0) # wait before retrying
                    continue

                yield self.resumed

                product = yield self.main_buffer.get()
                self.publish_status()
                try:
                    
                    yield self.env.timeout(self.transfer_time) # 模拟搬运时间
                    
                    yield self.downstream_station.buffer.put(product)
                    print(f"[{self.env.now:.2f}] TripleBufferConveyor: moved product to {self.downstream_station.id}")
                except simpy.Interrupt as e:
                    print(f"FAULT! Conveyor {self.id} interrupted, product {product.id} returned to start.")
                    yield self.main_buffer.put(product) # 安全地将产品退回起点
                    self.set_status(DeviceStatus.FAULT)
                    self.resumed = self.env.event()
                finally:
                    self.publish_status()
            else:
                yield self.env.timeout(1.0)
