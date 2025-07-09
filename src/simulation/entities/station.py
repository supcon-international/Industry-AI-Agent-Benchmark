# simulation/entities/station.py
import simpy
import random
from typing import Dict, Tuple, Optional, Callable

from config.schemas import DeviceStatus
from src.simulation.entities.base import Device

class Station(Device):
    """
    Represents a manufacturing station in the factory.

    Stations have a buffer to hold products and take time to process them.
    Default input buffer capacity is 1 (single-piece flow).
    
    Attributes:
        buffer (simpy.Store): A buffer to hold incoming products.
        buffer_size (int): The maximum capacity of the buffer（default 1）。
        processing_times (Dict[str, Tuple[int, int]]): A dictionary mapping product types
            to a tuple of (min_time, max_time) for processing.
        product_transfer_callback (Callable): Callback function to transfer products to next station
        product_scrap_callback (Callable): Callback function to handle scrapped products
        downstream_conveyor (Conveyor): The conveyor downstream from this station
    """
    
    # 默认工艺路线定义 - 产品在各工站间的流转顺序
    DEFAULT_PROCESS_ROUTE = {
        "P1": ["StationA", "StationB", "StationC", "QualityCheck"],
        "P2": ["StationA", "StationB", "StationC", "QualityCheck"],  
        "P3": ["StationA", "StationB", "StationC", "StationB", "StationC", "QualityCheck"]
    }
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        buffer_size: int = 1,  # 默认容量为1
        processing_times: Dict[str, Tuple[int, int]] = {},
        product_transfer_callback: Optional[Callable] = None,
        product_scrap_callback: Optional[Callable] = None,
        downstream_conveyor=None,
        fault_system=None
    ):
        super().__init__(env, id, position, device_type="station")
        self.buffer_size = buffer_size
        self.buffer = simpy.Store(env, capacity=buffer_size)
        self.processing_times = processing_times
        
        # 产品流转回调函数
        self.product_transfer_callback = product_transfer_callback
        self.product_scrap_callback = product_scrap_callback
        
        # 工站特定属性初始化
        self._specific_attributes.update({
            "precision_level": random.uniform(95.0, 100.0),  # 加工精度水平
            "tool_wear_level": random.uniform(0.0, 20.0),    # 刀具磨损程度
            "lubricant_level": random.uniform(80.0, 100.0)   # 润滑油水平
        })
        
        # 统计数据
        self.stats = {
            "products_processed": 0,
            "products_scrapped": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0
        }
        
        self.downstream_conveyor = downstream_conveyor
        self.fault_system = fault_system
        # Start the main operational process for the station
        self.env.process(self.run())

    def run(self):
        """The main operational loop for the station."""
        while True:
            # 检查设备是否可以操作
            if not self.can_operate():
                # 设备无法操作时等待
                yield self.env.timeout(1)  # 每1秒检查一次
                continue
                
            # Wait for a product to arrive in the buffer
            product = yield self.buffer.get()
            print(f"[{self.env.now:.2f}] 📦 {self.id}: 从缓冲区获取产品 {product.id}开始自动加工")
            # Start processing the product
            yield self.env.process(self.process_product(product))

    def process_product(self, product):
        """Simulates the time taken to process a single product."""
        # Check if the device can operate
        if not self.can_operate():
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法处理产品，设备不可用")
            # Put the product back into the buffer
            yield self.buffer.put(product)
            return
            
        self.set_status(DeviceStatus.PROCESSING)
        
        # Record processing start
        product.process_at_station(self.id, self.env.now)
        
        # Get processing time based on product type
        min_time, max_time = self.processing_times.get(product.product_type, (10, 20)) # Default time
        processing_time = random.uniform(min_time, max_time)
        
        # Apply efficiency impact
        efficiency_factor = self.performance_metrics.efficiency_rate / 100.0
        actual_processing_time = processing_time / efficiency_factor
        
        # If there is a fault, it may affect the processing time
        if self.has_fault:
            actual_processing_time *= random.uniform(1.2, 2.0)  # The processing time increases when there is a fault
        
        yield self.env.timeout(actual_processing_time)
        
        # Update statistics
        self.stats["products_processed"] += 1
        self.stats["total_processing_time"] += actual_processing_time
        self.stats["average_processing_time"] = (
            self.stats["total_processing_time"] / self.stats["products_processed"]
        )
        
        # Check if the product is defective due to precision problem
        precision_level = self._specific_attributes.get("precision_level", 100.0)
        if precision_level < 80.0:
            # Precision is too low, which may cause the product to be scrapped
            scrap_chance = (80.0 - precision_level) / 80.0
            if random.random() < scrap_chance:
                yield self.env.process(self._handle_product_scrap(product, "precision_issue"))
                self.set_status(DeviceStatus.IDLE)
                return
        
        # Product processing completed successfully
        print(f"[{self.env.now:.2f}] {self.id}: Finished processing product {product.id} (实际耗时: {actual_processing_time:.1f}s)")
        
        # Trigger moving the product to the next stage
        yield self.env.process(self._transfer_product_to_next_stage(product))
        
        self.set_status(DeviceStatus.IDLE) 

    def _handle_product_scrap(self, product, reason: str):
        """Handle product scrapping due to quality issues"""
        from src.simulation.entities.product import QualityStatus, QualityDefect, DefectType
        
        # Set product status to scrapped
        product.quality_status = QualityStatus.SCRAP
        
        # Add defect record
        defect = QualityDefect(
            defect_type=DefectType.DIMENSIONAL,  # Use DIMENSIONAL for precision issues
            severity=90.0,  # High severity for scrapped products
            description=f"Product scrapped at {self.id} due to {reason}",
            station_id=self.id,
            detected_at=self.env.now
        )
        product.add_defect(defect)
        
        # Update statistics
        self.stats["products_scrapped"] += 1
        
        print(f"[{self.env.now:.2f}] ❌ {self.id}: 产品 {product.id} 因{reason}报废")
        
        # Notify factory about scrapped product (for KPI tracking)
        if self.product_scrap_callback:
            yield self.env.process(self.product_scrap_callback(product, self.id, reason))
        
        # Simulate scrap handling time
        yield self.env.timeout(2.0)

    def _transfer_product_to_next_stage(self, product):
        """Transfer the processed product to the next station or conveyor."""
        from src.simulation.entities.conveyor import TripleBufferConveyor

        if self.downstream_conveyor is None:
        # No downstream, end of process
            return
        
        # TripleBufferConveyor special handling (only StationC)
        if isinstance(self.downstream_conveyor, TripleBufferConveyor):
            if product.product_type == "P3":
                # P3 product to the least full buffer (upper/lower)
                while self.downstream_conveyor.is_full("upper") and self.downstream_conveyor.is_full("lower"):
                    print(f"[{self.env.now:.2f}] ⏸️  {self.id}: Both AGV buffers of downstream conveyor full, waiting...")
                    if self.fault_system:
                        self.fault_system.report_buffer_full(self.id, "downstream_conveyor_2_branch_buffer")
                    yield self.env.timeout(1.0)

                if self.downstream_conveyor.is_full("upper"):
                    chosen_buffer = "lower"
                elif self.downstream_conveyor.is_full("lower"):
                    chosen_buffer = "upper"
                else:
                    if len(self.downstream_conveyor.upper_buffer.items) <= len(self.downstream_conveyor.lower_buffer.items):
                        chosen_buffer = "upper"
                    else:
                        chosen_buffer = "lower"
                yield self.downstream_conveyor.push(product, buffer_type=chosen_buffer)
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: Product {product.id} (P3) moved to downstream {chosen_buffer} buffer")
                return
            else:
                # not P3 product, move to main buffer
                while self.downstream_conveyor.is_full("main"):
                    print(f"[{self.env.now:.2f}] ⏸️  {self.id}: Main buffer of downstream conveyor full, waiting...")
                    yield self.env.timeout(1.0)
                yield self.downstream_conveyor.push(product, buffer_type="main")
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: Product {product.id} moved to downstream main buffer")
                return
        else:
            # normal conveyor
            while self.downstream_conveyor.is_full():
                yield self.env.timeout(1.0)
            yield self.downstream_conveyor.push(product)
            return

    def add_product_to_buffer(self, product):
        """Add a product to the station's buffer (used by AGV for delivery)"""
        if len(self.buffer.items) >= self.buffer_size:
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 缓冲区已满，无法接收产品 {product.id}")
            return False
        
        self.buffer.put(product)
        print(f"[{self.env.now:.2f}] 📦 {self.id}: 接收产品 {product.id} 到缓冲区")
        return True

    def get_buffer_level(self) -> int:
        """获取当前缓冲区产品数量"""
        return len(self.buffer.items)

    def get_processing_stats(self) -> Dict:
        """获取工站处理统计信息"""
        return {
            **self.stats,
            "buffer_level": self.get_buffer_level(),
            "buffer_utilization": self.get_buffer_level() / self.buffer_size,
            "precision_level": self._specific_attributes.get("precision_level", 100.0),
            "tool_wear_level": self._specific_attributes.get("tool_wear_level", 0.0),
            "can_operate": self.can_operate()
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            "products_processed": 0,
            "products_scrapped": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0
        }
    