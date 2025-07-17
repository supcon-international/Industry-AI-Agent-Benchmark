# simulation/entities/station.py
import simpy
import random
from typing import Dict, Tuple, Optional, Callable

from config.schemas import DeviceStatus, StationStatus
from src.simulation.entities.base import Device
from src.simulation.entities.product import Product
from config.topics import get_station_status_topic

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
        downstream_conveyor=None,
        mqtt_client=None
    ):
        # TODO: Add a Processing Area(simpy.Store) to hold products that are being processed
        super().__init__(env, id, position, device_type="station", mqtt_client=mqtt_client)
        self.buffer_size = buffer_size
        self.buffer = simpy.Store(env, capacity=buffer_size)
        self.processing_times = processing_times
        
        # # 工站特定属性初始化
        # self._specific_attributes.update({
        #     "precision_level": random.uniform(95.0, 100.0),  # 加工精度水平
        #     "tool_wear_level": random.uniform(0.0, 20.0),    # 刀具磨损程度
        #     "lubricant_level": random.uniform(80.0, 100.0)   # 润滑油水平
        # })
        
        # 统计数据
        self.stats = {
            "products_processed": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0
        }
        
        self.downstream_conveyor = downstream_conveyor
        # Start the main operational process for the station
        self.env.process(self.run())
        
        # Publish initial status
        self.publish_status()

    def set_status(self, new_status: DeviceStatus, message: Optional[str] = None):
        """Overrides the base method to publish status on change."""
        if self.status == new_status:
            return
        super().set_status(new_status, message)
        self.publish_status(message)

    def publish_status(self, message: Optional[str] = None):
        """Publishes the current status of the station to MQTT."""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
            
        status_data = StationStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats,
            output_buffer=[]  # 普通工站没有 output_buffer
        )
        topic = get_station_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=True)

    def run(self):
        """The main operational loop for the station."""
        while True:
            try:
                # 等待设备可操作且buffer有产品
                yield self.env.process(self._wait_for_ready_state())
                
                # 如果能到这里，说明设备可操作且有产品
                if len(self.buffer.items) > 0:
                    product = self.buffer.items[0]
                    self.action = self.env.process(self.process_product(product))
                    yield self.action
                    
            except simpy.Interrupt:
                # 被中断（通常是故障），继续循环
                continue
    
    def _wait_for_ready_state(self):
        """等待设备处于可操作状态且buffer有产品"""
        while True:
            # 如果设备不可操作，等待
            if not self.can_operate():
                yield self.env.timeout(1)
                continue
            
            # 如果buffer为空，等待
            if len(self.buffer.items) == 0:
                yield self.env.timeout(0.1)
                continue
            
            # 设备可操作且有产品，返回
            return

    def process_product(self, product: Product):
        """
        Simulates the entire lifecycle of processing a single product,
        from waiting for it to processing and transferring it.
        Includes robust error handling for interruptions.
        """
        try:
            # Check if the device can operate
            if not self.can_operate():
                print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法处理产品，设备不可用")
                return

            self.set_status(DeviceStatus.PROCESSING)

            # Record processing start and get processing time
            min_time, max_time = self.processing_times.get(product.product_type, (10, 20))
            processing_time = random.uniform(min_time, max_time)
            
            # Apply efficiency and fault impacts
            efficiency_factor = getattr(self.performance_metrics, 'efficiency_rate', 100.0) / 100.0
            actual_processing_time = processing_time / efficiency_factor
            
            # The actual processing work
            yield self.env.timeout(actual_processing_time)
            product = yield self.buffer.get()
            product.process_at_station(self.id, self.env.now)

            # Update statistics upon successful completion
            self.stats["products_processed"] += 1
            self.stats["total_processing_time"] += actual_processing_time
            self.stats["average_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["products_processed"]
            )
            
            # Processing finished successfully
            print(f"[{self.env.now:.2f}] {self.id}: Finished processing product {product.id} (实际耗时: {actual_processing_time:.1f}s)")
            
            # Set to IDLE now, as core processing is done.
            # The subsequent transfer is a separate action performed while IDLE.
            self.set_status(DeviceStatus.IDLE)
            
            # Trigger moving the product to the next stage
            yield self.env.process(self._transfer_product_to_next_stage(product))

        except simpy.Interrupt as e:
            message = f"Processing of product {product.id} was interrupted: {e.cause}"
            print(f"[{self.env.now:.2f}] ⚠️ {self.id}: {message}")
            if product not in self.buffer.items:
          # 产品已取出，说明处理时间已经完成，应该继续流转
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: 产品 {product.id} 已处理完成，继续流转到下游")
                yield self.env.process(self._transfer_product_to_next_stage(product))
            else:
          # 产品还在buffer中，说明在timeout期间被中断，等待下次处理
                product.rework_count += 1
                print(f"[{self.env.now:.2f}] ⏸️  {self.id}: 产品 {product.id} 处理被中断，留在buffer中")
        finally:
            # Clear the action handle once the process is complete or interrupted
            self.action = None

    def _transfer_product_to_next_stage(self, product):
        """Transfer the processed product to the next station or conveyor."""
        from src.simulation.entities.conveyor import TripleBufferConveyor

        if self.downstream_conveyor is None:
            # No downstream, end of process
            return
        
        # Set status to INTERACTING before the potentially blocking push operation
        self.set_status(DeviceStatus.INTERACTING)

        # TripleBufferConveyor special handling (only StationC)
        if isinstance(self.downstream_conveyor, TripleBufferConveyor):
            # 使用Product的智能路由决策
            target_buffer = self._determine_target_buffer_for_product(product)
            
            if target_buffer in ["upper", "lower"]:
                # P3产品返工路径：选择最优的side buffer
                chosen_buffer = self._choose_optimal_side_buffer(target_buffer)
                yield self.downstream_conveyor.push(product, buffer_type=chosen_buffer)
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: Product {product.id} (P3-返工) moved to downstream {chosen_buffer} buffer")
            else:
                # 主流程路径：直接到main buffer
                yield self.downstream_conveyor.push(product, buffer_type="main")
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: Product {product.id} moved to downstream main buffer")
        else:
            # normal conveyor - SimPy push()会自动阻塞直到有空间
            yield self.downstream_conveyor.push(product)
        
        # Set status back to IDLE after the push operation is complete
        self.set_status(DeviceStatus.IDLE)
        return

    def _determine_target_buffer_for_product(self, product):
        """根据产品类型和工艺状态确定目标buffer"""
        if product.product_type != "P3":
            return "main"
        
        # P3产品的特殊逻辑：基于访问次数判断
        stationc_visits = product.visit_count.get("StationC", 0)
        
        if stationc_visits == 1:  # 第一次完成StationC处理
            return "upper"  # 返工到side buffer
        elif stationc_visits >= 2:  # 第二次及以后完成StationC处理
            return "main"   # 进入主流程
        else:
            return "main"   # 默认主流程

    def _choose_optimal_side_buffer(self, preferred_buffer):
        """选择最优的side buffer（upper或lower）"""
        if self.downstream_conveyor is None:
            return "upper"  # 默认返回upper
            
        # 检查优选buffer是否可用
        if preferred_buffer == "upper" and not self.downstream_conveyor.is_full("upper"):
            return "upper"
        elif preferred_buffer == "lower" and not self.downstream_conveyor.is_full("lower"):
            return "lower"
        
        # 优选buffer满，检查另一个
        if preferred_buffer == "upper":
            if not self.downstream_conveyor.is_full("lower"):
                return "lower"
        else:  # preferred_buffer == "lower"
            if not self.downstream_conveyor.is_full("upper"):
                return "upper"
        
        # 两个都满的情况下，选择较空的那个（会阻塞直到有空间）
        if len(self.downstream_conveyor.upper_buffer.items) <= len(self.downstream_conveyor.lower_buffer.items):
            if self.downstream_conveyor.is_full("upper") and self.downstream_conveyor.is_full("lower"):
                self.report_buffer_full("downstream_conveyor_all_side_buffer")
            return "upper"
        else:
            if self.downstream_conveyor.is_full("upper") and self.downstream_conveyor.is_full("lower"):
                self.report_buffer_full("downstream_conveyor_all_side_buffer")
            return "lower"

    def add_product_to_buffer(self, product: Product):
        """Add a product to the station's buffer, wrapped in INTERACTING state."""
        success = False
        self.set_status(DeviceStatus.INTERACTING)
        try:
            yield self.buffer.put(product)
            print(f"[{self.env.now:.2f}] 📥 {self.id}: Product {product.id} added to buffer.")
            success = True
        except simpy.Interrupt:
            print(f"[{self.env.now:.2f}] ⚠️ {self.id}: add_product_to_buffer interrupted.")
            success = False
        finally:
            self.set_status(DeviceStatus.IDLE)
        return success

    def get_buffer_level(self) -> int:
        """获取当前缓冲区产品数量"""
        return len(self.buffer.items)

    def get_processing_stats(self) -> Dict:
        """获取工站处理统计信息"""
        return {
            **self.stats,
            "buffer_level": self.get_buffer_level(),
            "buffer_utilization": self.get_buffer_level() / self.buffer_size,
            "can_operate": self.can_operate()
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            "products_processed": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0
        }

