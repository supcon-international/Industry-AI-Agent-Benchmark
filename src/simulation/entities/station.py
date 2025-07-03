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
        super().__init__(env, id, position, device_type="station")
        self.buffer_size = buffer_size
        self.buffer = simpy.Store(env, capacity=buffer_size)
        self.processing_times = processing_times
        
        # 工站特定属性初始化
        self._specific_attributes.update({
            "precision_level": random.uniform(95.0, 100.0),  # 加工精度水平
            "tool_wear_level": random.uniform(0.0, 20.0),    # 刀具磨损程度
            "lubricant_level": random.uniform(80.0, 100.0)   # 润滑油水平
        })
        
        # Start the main operational process for the station
        self.env.process(self.run())

    def run(self):
        """The main operational loop for the station."""
        while True:
            # 检查设备是否可以操作
            if not self.can_operate():
                # 设备无法操作时等待
                yield self.env.timeout(10)  # 每10秒检查一次
                continue
                
            # Wait for a product to arrive in the buffer
            product = yield self.buffer.get()
            
            # Start processing the product
            yield self.env.process(self.process_product(product))

    def process_product(self, product):
        """Simulates the time taken to process a single product."""
        # 检查设备状态
        if not self.can_operate():
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法处理产品，设备不可用")
            # 将产品放回缓冲区
            yield self.buffer.put(product)
            return
            
        self.set_status(DeviceStatus.PROCESSING)
        
        # Get processing time based on product type
        min_time, max_time = self.processing_times.get(product.product_type, (10, 20)) # Default time
        processing_time = random.uniform(min_time, max_time)
        
        # 应用效率影响
        efficiency_factor = self.performance_metrics.efficiency_rate / 100.0
        actual_processing_time = processing_time / efficiency_factor
        
        # 如果有故障，可能影响处理时间
        if self.has_fault:
            actual_processing_time *= random.uniform(1.2, 2.0)  # 故障时处理时间增加
        
        yield self.env.timeout(actual_processing_time)
        
        # 检查是否因精度问题导致产品质量问题
        precision_level = self._specific_attributes.get("precision_level", 100.0)
        if precision_level < 80.0:
            # 精度过低，可能导致产品报废
            scrap_chance = (80.0 - precision_level) / 80.0
            if random.random() < scrap_chance:
                print(f"[{self.env.now:.2f}] ❌ {self.id}: 产品 {product.id} 因精度问题报废")
                # 产品报废，不传递到下一步
                self.set_status(DeviceStatus.IDLE)
                return
        
        # For now, we'll just say the product is done.
        # Later, this will trigger moving the product to the next stage.
        print(f"[{self.env.now:.2f}] {self.id}: Finished processing product {product.id} (实际耗时: {actual_processing_time:.1f}s)")
        self.set_status(DeviceStatus.IDLE) 
        
    def get_buffer_level(self) -> int:
        """获取当前缓冲区产品数量"""
        return len(self.buffer.items) 