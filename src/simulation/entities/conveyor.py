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
    def __init__(self, env, id, capacity, position: Tuple[int, int],transfer_time: float =5.0, mqtt_client=None):
        super().__init__(env, id, position, mqtt_client)
        self.capacity = capacity
        self.buffer = simpy.Store(env, capacity=capacity)
        self.downstream_station = None  # 下游工站引用
        self.action = None  # 保留但不使用，兼容 fault system 接口
        self.transfer_time = transfer_time # 模拟搬运时间
        self.main_process = None  # 主运行进程
        self.active_processes = {}  # Track active transfer processes per product
        
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
            upper_buffer=None,
            lower_buffer=None
        )
        topic = get_conveyor_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=True)

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer."""
        self.downstream_station = station
        if self.main_process is None:
            self.main_process = self.env.process(self.run())

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
        """Main operational loop for the conveyor. This should NOT be interrupted by faults."""
        
        while True:
            # 等待设备可操作且buffer有产品
            yield self.env.process(self._wait_for_ready_state())
            
            # 检查buffer中的每个产品，如果还没有处理进程就启动一个
            for item in list(self.buffer.items):  # 使用list避免迭代时修改
                if item.id not in self.active_processes:
                    # 为这个产品启动一个处理进程
                    process = self.env.process(self.process_single_item(item))
                    self.active_processes[item.id] = process
            
            # 清理已完成的进程
            completed_ids = []
            for product_id, process in self.active_processes.items():
                if not process.is_alive:
                    completed_ids.append(product_id)
            for product_id in completed_ids:
                del self.active_processes[product_id]
            
            yield self.env.timeout(0.1)  # 短暂等待后再检查
    
    def _wait_for_ready_state(self):
        """等待设备处于可操作状态且buffer有产品"""
        while True:
            # 如果设备不可操作，等待
            if not self.can_operate():
                yield self.env.timeout(1)
                continue
            
            # 如果没有下游站点，等待
            if self.downstream_station is None:
                yield self.env.timeout(1)
                continue
            
            # 如果buffer为空，等待
            if len(self.buffer.items) == 0:
                yield self.env.timeout(0.1)
                continue
            
            # 设备可操作且有产品，返回
            return
        
    def process_single_item(self, product):
        """Process a single item with timeout-get-put pattern. This CAN be interrupted by faults."""
        actual_product = None
        try:
            # 检查下游站点是否存在
            if self.downstream_station is None:
                return
                
            # 先等待下游站点可操作
            while not self.downstream_station.can_operate():
                # 发布blocked状态
                self.set_status(DeviceStatus.BLOCKED)
                yield self.env.timeout(1.0)  # wait before retrying
            
            # 恢复工作状态
            self.set_status(DeviceStatus.WORKING)
            
            # 先进行timeout（模拟搬运时间）
            yield self.env.timeout(self.transfer_time)
            
            # 然后从buffer获取产品（get）
            actual_product = yield self.buffer.get()
            # 确保获取的是正确的产品
            if actual_product.id != product.id:
                # 如果不是预期的产品，放回去
                yield self.buffer.put(actual_product)
                print(f"[{self.env.now:.2f}] Conveyor {self.id}: unexpected product order, retrying")
                return
            
            self.publish_status()
            
            # 最后将产品放入下游（put）
            yield self.downstream_station.buffer.put(actual_product)
            print(f"[{self.env.now:.2f}] Conveyor {self.id}: moved product {actual_product.id} to {self.downstream_station.id}")
                
        except simpy.Interrupt as e:
            print(f"[{self.env.now:.2f}] ⚠️ Conveyor {self.id}: Processing of product {product.id} was interrupted")
            # 如果产品已经取出，放回buffer
            if actual_product and actual_product not in self.buffer.items:
                yield self.downstream_station.buffer.put(actual_product) if self.downstream_station else self.buffer.put(actual_product)
                print(f"[{self.env.now:.2f}] 🔄 Conveyor {self.id}: Product {actual_product.id} returned to downstream station")
            self.set_status(DeviceStatus.FAULT)
                
        finally:
            self.publish_status()

    def recover(self):
        """Custom recovery logic for the conveyor."""
        print(f"[{self.env.now:.2f}] ✅ Conveyor {self.id} is recovering.")
        # 恢复后，它应该继续工作，而不是空闲
        self.set_status(DeviceStatus.WORKING)
        
    def interrupt_all_processing(self):
        """Interrupt all active product processing. Called by fault system."""
        interrupted_count = 0
        for product_id, process in list(self.active_processes.items()):
            if process.is_alive:
                process.interrupt("Fault injected")
                interrupted_count += 1
        print(f"[{self.env.now:.2f}] 🚫 Conveyor {self.id}: Interrupted {interrupted_count} product processes")
        return interrupted_count

class TripleBufferConveyor(BaseConveyor):
    """
    Conveyor with three buffers:
    - main_buffer: for direct transfer to QualityCheck (auto-transfer)
    - upper_buffer: for P3 products, AGV pickup
    - lower_buffer: for P3 products, AGV pickup
    All buffers use simpy.Store for event-driven simulation.
    """
    def __init__(self, env, id, main_capacity, upper_capacity, lower_capacity, position: Tuple[int, int], transfer_time: float =5.0, mqtt_client=None):
        super().__init__(env, id, position, mqtt_client)
        self.main_buffer = simpy.Store(env, capacity=main_capacity)
        self.upper_buffer = simpy.Store(env, capacity=upper_capacity)
        self.lower_buffer = simpy.Store(env, capacity=lower_capacity)
        self.downstream_station = None  # QualityCheck
        self.action = None  # 保留但不使用，兼容 fault system 接口
        self.transfer_time = transfer_time # 模拟搬运时间
        self.main_process = None  # 主运行进程
        self.active_processes = {}  # Track active transfer processes per product
        
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
        )
        topic = get_conveyor_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=True)

    def set_downstream_station(self, station):
        """Set the downstream station for auto-transfer from main_buffer."""
        self.downstream_station = station
        if self.main_process is None:
            self.main_process = self.env.process(self.run())

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
        """Main operational loop for the triple buffer conveyor. This should NOT be interrupted by faults."""
        
        while True:
            # 等待设备可操作且buffer有产品
            yield self.env.process(self._wait_for_ready_state())
            
            # 检查main_buffer中的每个产品，如果还没有处理进程就启动一个
            for item in list(self.main_buffer.items):  # 使用list避免迭代时修改
                if item.id not in self.active_processes:
                    # 为这个产品启动一个处理进程
                    process = self.env.process(self.process_single_item(item))
                    self.active_processes[item.id] = process
            
            # 清理已完成的进程
            completed_ids = []
            for product_id, process in self.active_processes.items():
                if not process.is_alive:
                    completed_ids.append(product_id)
            for product_id in completed_ids:
                del self.active_processes[product_id]
            
            yield self.env.timeout(0.1)  # 短暂等待后再检查
    
    def _wait_for_ready_state(self):
        """等待设备处于可操作状态且buffer有产品"""
        while True:
            # 如果设备不可操作，等待
            if not self.can_operate():
                yield self.env.timeout(1)
                continue
            
            # 如果没有下游站点，等待
            if self.downstream_station is None:
                yield self.env.timeout(1)
                continue
            
            # 如果main_buffer为空，等待
            if len(self.main_buffer.items) == 0:
                yield self.env.timeout(0.1)
                continue
            
            # 设备可操作且有产品，返回
            return
    
    def process_single_item(self, product):
        """Process a single item from main_buffer with timeout-get-put pattern. This CAN be interrupted by faults."""
        actual_product = None
        try:
            # 检查下游站点是否存在
            if self.downstream_station is None:
                return
                
            # Before putting, check if the station can operate
            while not self.downstream_station.can_operate():
                # 发布blocked状态
                self.set_status(DeviceStatus.BLOCKED)
                yield self.env.timeout(1.0)  # wait before retrying
            
            # 恢复工作状态
            self.set_status(DeviceStatus.WORKING)
            
            # 先进行timeout（模拟搬运时间）
            yield self.env.timeout(self.transfer_time)
            
            # 获取产品
            actual_product = yield self.main_buffer.get()
            
            # 确保获取的是正确的产品
            if actual_product.id != product.id:
                # 如果不是预期的产品，放回去
                yield self.main_buffer.put(actual_product)
                print(f"[{self.env.now:.2f}] TripleBufferConveyor {self.id}: unexpected product order, retrying")
                return
            
            self.publish_status()
            
            # 将产品放入下游（put）
            yield self.downstream_station.buffer.put(actual_product)
            print(f"[{self.env.now:.2f}] TripleBufferConveyor {self.id}: moved product {actual_product.id} to {self.downstream_station.id}")
                
        except simpy.Interrupt as e:
            print(f"[{self.env.now:.2f}] ⚠️ TripleBufferConveyor {self.id}: Processing of product {product.id} was interrupted")
            # 如果产品已经取出，安全地将产品退回起点
            if actual_product and actual_product not in self.main_buffer.items:
                yield self.downstream_station.buffer.put(actual_product) if self.downstream_station else self.main_buffer.put(actual_product)
                print(f"[{self.env.now:.2f}] 🔄 TripleBufferConveyor {self.id}: Product {actual_product.id} returned to downstream station")
            self.set_status(DeviceStatus.FAULT)
                
        finally:
            self.publish_status()

    def recover(self):
        """Custom recovery logic for the TripleBufferConveyor."""
        print(f"[{self.env.now:.2f}] ✅ TripleBufferConveyor {self.id} is recovering.")
        # 恢复后，它应该继续工作，而不是空闲
        self.set_status(DeviceStatus.WORKING)
        
    def interrupt_all_processing(self):
        """Interrupt all active product processing. Called by fault system."""
        interrupted_count = 0
        for product_id, process in list(self.active_processes.items()):
            if process.is_alive:
                process.interrupt("Fault injected")
                interrupted_count += 1
        print(f"[{self.env.now:.2f}] 🚫 TripleBufferConveyor {self.id}: Interrupted {interrupted_count} product processes")
        return interrupted_count
