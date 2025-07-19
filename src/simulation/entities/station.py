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

        # For fault system to record the current product for resume processing
        current_product_id (str): The ID of the current product being processed.
        current_product_start_time (float): The time when the current product started processing.
        current_product_total_time (float): The total time required to process the current product.
        current_product_elapsed_time (float): The elapsed time before the current product was interrupted.
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        buffer_size: int = 1,  # 默认容量为1
        processing_times: Dict[str, Tuple[int, int]] = {},
        downstream_conveyor=None,
        mqtt_client=None,
        interacting_points: list = []
    ):
        # TODO: Add a Processing Area(simpy.Store) to hold products that are being processed
        super().__init__(env, id, position, device_type="station", mqtt_client=mqtt_client, interacting_points=interacting_points)
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
        # 产品处理时间跟踪（站点一次只处理一个产品）
        self.current_product_id = None  # 当前正在处理的产品ID
        self.current_product_start_time = None  # 当前产品开始处理的时间
        self.current_product_total_time = None  # 当前产品需要的总处理时间
        self.current_product_elapsed_time = None  # 中断前已经处理的累计时间
        
        # Start the main operational process for the station
        self.env.process(self.run())
        
        # Publish initial status
        self.publish_status("Station initialized")

    def publish_status(self, message: Optional[str] = None):
        """Publishes the current status of the station to MQTT."""
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
            
        status_data = StationStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            message=message,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats,
            output_buffer=[]  # 普通工站没有 output_buffer
        )
        topic = get_station_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=False)

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
                msg = f"[{self.env.now:.2f}] ⚠️  {self.id}: can not process product, device is not available"
                print(msg)
                self.publish_status(msg)
                return

            self.set_status(DeviceStatus.PROCESSING)
            self.publish_status()

            # Record processing start and get processing time
            min_time, max_time = self.processing_times.get(product.product_type, (10, 20))
            processing_time = random.uniform(min_time, max_time)
            
            # 处理中断恢复的逻辑
            if (self.current_product_id == product.id and 
                self.current_product_elapsed_time is not None and
                self.current_product_total_time is not None):
                # 恢复处理：使用之前记录的已处理时间
                elapsed_time = self.current_product_elapsed_time
                remaining_time = max(0, self.current_product_total_time - elapsed_time)
                msg = f"[{self.env.now:.2f}] {self.id}: {product.id} resume processing, elapsed {elapsed_time:.1f}s, remaining {remaining_time:.1f}s"
                print(msg)
                self.publish_status(msg)
                # 重新记录开始时间，但保留累计时间和总时间
                self.current_product_start_time = self.env.now
            else:
                # 第一次开始处理
                self.current_product_id = product.id
                self.current_product_start_time = self.env.now
                self.current_product_total_time = processing_time
                self.current_product_elapsed_time = 0  # 初始化累计时间
                remaining_time = processing_time
                msg = f"[{self.env.now:.2f}] {self.id}: {product.id} start processing, need {processing_time:.1f}s"
                print(msg)
                self.publish_status(msg)
            
            # The actual processing work
            yield self.env.timeout(remaining_time)
            product = yield self.buffer.get()
            product.process_at_station(self.id, self.env.now)

            # Update statistics upon successful completion
            self.stats["products_processed"] += 1
            self.stats["total_processing_time"] += processing_time
            self.stats["average_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["products_processed"]
            )
            
            # Set to IDLE now, as core processing is done.
            # The subsequent transfer is a separate action performed while IDLE.
            self.set_status(DeviceStatus.IDLE)
            # Processing finished successfully
            msg = f"[{self.env.now:.2f}] {self.id}: {product.id} finished processing, actual processing time {processing_time:.1f}s"
            print(msg)
            self.publish_status(msg)
            
            # Trigger moving the product to the next stage
            yield self.env.process(self._transfer_product_to_next_stage(product))

        except simpy.Interrupt as e:
            message = f"Processing of product {product.id} was interrupted: {e.cause}"
            print(f"[{self.env.now:.2f}] ⚠️ {self.id}: {message}")
            
            # 记录中断时已经处理的时间
            if self.current_product_start_time is not None:
                elapsed_before_interrupt = self.env.now - self.current_product_start_time
                self.current_product_elapsed_time = (self.current_product_elapsed_time or 0) + elapsed_before_interrupt
                print(f"[{self.env.now:.2f}] 💾 {self.id}: 产品 {product.id} 中断前已处理 {elapsed_before_interrupt:.1f}s，累计 {self.current_product_elapsed_time:.1f}s")
                # 清理开始时间，但保留其他记录
                self.current_product_start_time = None
            
            if product not in self.buffer.items:
                # 产品已取出，说明处理时间已经完成，应该继续流转
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: 产品 {product.id} 已处理完成，继续流转到下游")
                yield self.env.process(self._transfer_product_to_next_stage(product))
                # 清理所有时间记录
                self.current_product_id = None
                self.current_product_start_time = None
                self.current_product_total_time = None
                self.current_product_elapsed_time = None
            else:
                # 产品还在buffer中，说明在timeout期间被中断，等待下次处理
                print(f"[{self.env.now:.2f}] ⏸️  {self.id}: 产品 {product.id} 处理被中断，留在buffer中")
        finally:
            # Clear the action handle once the process is complete or interrupted
            self.action = None
            # 如果产品成功完成处理并转移，清理时间记录
            if self.current_product_id == product.id and product not in self.buffer.items:
                self.current_product_id = None
                self.current_product_start_time = None
                self.current_product_total_time = None
                self.current_product_elapsed_time = None

    def _transfer_product_to_next_stage(self, product):
        """Transfer the processed product to the next station or conveyor."""

        if self.downstream_conveyor is None:
            # No downstream, end of process
            return
        
        # Set status to INTERACTING before the potentially blocking push operation
        self.set_status(DeviceStatus.INTERACTING)
        self.publish_status()

        # normal conveyor - SimPy push()会自动阻塞直到有空间
        yield self.downstream_conveyor.push(product)
        
        # Set status back to IDLE after the push operation is complete
        self.set_status(DeviceStatus.IDLE)
        self.publish_status()
        return

    def add_product_to_buffer(self, product: Product):
        """Add a product to the station's buffer, wrapped in INTERACTING state."""
        success = False
        self.set_status(DeviceStatus.INTERACTING)
        self.publish_status()
        try:
            yield self.buffer.put(product)
            print(f"[{self.env.now:.2f}] 📥 {self.id}: Product {product.id} added to buffer.")
            success = True
        except simpy.Interrupt:
            print(f"[{self.env.now:.2f}] ⚠️ {self.id}: add_product_to_buffer interrupted.")
            success = False
        finally:
            self.set_status(DeviceStatus.IDLE)
            self.publish_status()
        return success

    def get_buffer_level(self) -> int:
        """获取当前缓冲区产品数量"""
        return len(self.buffer.items)

    def is_full(self):
        return len(self.buffer.items) >= self.buffer_size
    
    def is_empty(self):
        return len(self.buffer.items) == 0
    
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
    
    def recover(self):
        """Custom recovery logic for the station."""
        # 清理不在buffer中的产品的时间记录
        if self.current_product_id:
            products_in_buffer = {p.id for p in self.buffer.items}
            if self.current_product_id not in products_in_buffer:
                print(f"[{self.env.now:.2f}] 🗑️ Station {self.id}: 清理过期产品 {self.current_product_id} 的时间记录")
                self.current_product_id = None
                self.current_product_start_time = None
                self.current_product_total_time = None
                self.current_product_elapsed_time = None
        
        # 恢复后，设置为IDLE状态
        self.set_status(DeviceStatus.IDLE)
        msg = f"[{self.env.now:.2f}] ✅ Station {self.id} is recovered."
        print(msg)
        self.publish_status(msg)

