# simulation/entities/agv.py
import simpy
import math
import random
from typing import Tuple, Dict, Optional, List
from src.simulation.entities.base import Vehicle
from src.simulation.entities.product import Product
from src.simulation.entities.quality_checker import QualityChecker
from src.simulation.entities.station import Station
from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from config.schemas import DeviceStatus, AGVStatus
from config.topics import get_agv_status_topic

class AGV(Vehicle):
    """
    Represents an Automated Guided Vehicle (AGV).

    AGVs are responsible for transporting products between stations.
    
    Attributes:
        battery_level (float): The current battery percentage (0-100).
        payload (List[any]): The list of products currently being carried.
        is_charging (bool): Flag indicating if the AGV is charging.
        low_battery_threshold (float): 电量低于此值时自动返航充电
        charging_point (Tuple[int, int]): 充电点坐标
        charging_speed (float): 充电速度 (%/秒)
        battery_consumption_per_meter (float): 每米移动消耗的电量
        battery_consumption_per_action (float): 每次装卸操作消耗的电量
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        path_points: Dict[str, Tuple[int, int]],
        speed_mps: float,
        payload_capacity: int = 1,
        low_battery_threshold: float = 5.0,  # 低电量阈值
        charging_point: Tuple[int, int] = (10, 10),  # 充电点坐标
        charging_speed: float = 3.33,  # 充电速度(30秒充满)
        battery_consumption_per_meter: float = 0.1,  # 每米消耗0.1%电量
        battery_consumption_per_action: float = 0.5,  # 每次操作消耗0.5%电量
        mqtt_client=None
    ):
        super().__init__(env, id, position, speed_mps, mqtt_client)
        self.battery_level = 100.0
        self.payload_capacity = payload_capacity
        self.payload = simpy.Store(env, capacity=payload_capacity)
        self.path_points = path_points
        # 充电相关属性
        self.is_charging = False
        self.low_battery_threshold = low_battery_threshold
        self.charging_point = charging_point
        self.charging_speed = charging_speed
        self.battery_consumption_per_meter = battery_consumption_per_meter
        self.battery_consumption_per_action = battery_consumption_per_action
        
        # 统计数据
        self.stats = {
            "total_distance": 0.0,
            "total_charge_time": 0.0,
            "forced_charge_count": 0,  # 被迫充电次数（KPI惩罚）
            "voluntary_charge_count": 0,  # 主动充电次数
            "low_battery_interruptions": 0,  # 低电量中断任务次数
            "tasks_completed": 0,
            "tasks_interrupted": 0
        }
        
        # 更新设备特定属性
        self._specific_attributes.update({
            "battery_level": self.battery_level,
            "is_charging": self.is_charging,
            "charging_point": self.charging_point,
            "low_battery_threshold": self.low_battery_threshold
        })

        # Publish initial status upon creation
        self.publish_status()

    def consume_battery(self, amount: float, reason: str = "operation"):
        """消耗电量"""
        if amount <= 0:
            return
            
        old_level = self.battery_level
        self.battery_level = max(0.0, self.battery_level - amount)
        
        # 更新设备属性
        self._specific_attributes["battery_level"] = self.battery_level
        
        if old_level > self.low_battery_threshold and self.battery_level <= self.low_battery_threshold:
            # 电量首次降到阈值以下时告警
            self.report_battery_low(self.battery_level)
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量过低！当前电量: {self.battery_level:.1f}% (原因: {reason})")

    def is_battery_low(self) -> bool:
        """检查电量是否过低"""
        return self.battery_level <= self.low_battery_threshold

    def can_complete_task(self, estimated_distance: float = 0.0, estimated_actions: int = 0) -> bool:
        """预估是否有足够电量完成任务"""
        estimated_consumption = (
            estimated_distance * self.battery_consumption_per_meter +
            estimated_actions * self.battery_consumption_per_action
        )
        
        # 预留回到充电点的电量
        return_distance = math.dist(self.position, self.charging_point)
        return_consumption = return_distance * self.battery_consumption_per_meter
        
        total_needed = estimated_consumption + return_consumption + 2.0  # 2%安全余量
        return self.battery_level >= total_needed

    def move_to(self, target_point: str):
        """
        Move to a specific path point using AGV's independent path system.
        
        Args:
            target_point: Path point name (e.g., "LP1", "UP3")
        """
        if not self.can_operate():
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法移动，设备不可用")
            return
            
        if target_point not in self.path_points:
            print(f"[{self.env.now:.2f}] ❌ {self.id}: 未知路径点 {target_point}")
            return
            
        target_position = self.path_points[target_point]
        
        # 检查电量是否足够
        distance = math.dist(self.position, target_position)
        if not self.can_complete_task(distance, 1):
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量不足，无法移动到 {target_point}")
            self.stats["tasks_interrupted"] += 1
            yield self.env.process(self.emergency_charge())
            return
            
        self.set_status(DeviceStatus.MOVING)
        print(f"[{self.env.now:.2f}] 🚛 {self.id}: 移动到路径点 {target_point} {target_position}")
        
        # 计算移动时间
        travel_time = distance / self.speed_mps
        yield self.env.timeout(travel_time)
        
        # 更新位置和消耗电量
        self.position = target_position
        self.consume_battery(distance * self.battery_consumption_per_meter, f"移动到{target_point}")
        self.consume_battery(self.battery_consumption_per_action, "路径点操作")
        
        # 更新统计
        self.stats["total_distance"] += distance
        self.stats["tasks_completed"] += 1
        
        print(f"[{self.env.now:.2f}] ✅ {self.id}: 到达 {target_point}, 电量: {self.battery_level:.1f}%")
        self.set_status(DeviceStatus.IDLE)
        
    def load_from(self, device, buffer_type=None, product_id=None, action_time_factor=1):
        """AGV从指定设备/缓冲区取货，支持多种设备类型和buffer_type。返回(成功,反馈信息,产品对象)
        """
        # 检查电量
        if self.is_battery_low():
            return False, f"{self.id}电量过低({self.battery_level:.1f}%)，无法执行取货操作", None
            
        product = None
        feedback = ""
        success = False
        
        # 计算超时时间
        time_out = getattr(device, 'processing_time', 10) / 5 * action_time_factor
        
        try:
            # QualityChecker (先检查子类)
            if isinstance(device, QualityChecker):
                # 根据buffer_type选择合适的buffer
                if buffer_type == "buffer":
                    target_buffer = device.buffer
                    buffer_name = "buffer"
                elif buffer_type == "output_buffer" or buffer_type is None:
                    # QualityChecker默认从output_buffer取货
                    target_buffer = device.output_buffer
                    buffer_name = "output_buffer"
                else:
                    feedback = f"QualityChecker不支持的buffer类型: {buffer_type}"
                    return False, feedback, None
                
                if len(target_buffer.items) == 0:
                    feedback = f"{device.id} {buffer_name}为空，无法取货"
                    return False, feedback, None
                    
                if product_id:
                    for item in target_buffer.items:
                        if item.id == product_id:
                            product = item
                            break
                    if not product:
                        feedback = f"产品{product_id}不存在"
                        return False, feedback, None
                else:
                    product = yield target_buffer.get()
                success = True
                
            # Station (父类)
            elif isinstance(device, Station):
                if len(device.buffer.items) == 0:
                    feedback = f"{device.id} buffer为空，无法取货"
                    return False, feedback, None

                if product_id:
                    for item in device.buffer.items:
                        if item.id == product_id:
                            product = item
                            break
                else:
                    product = yield device.buffer.get()
                success = True
                
            # TripleBufferConveyor
            elif isinstance(device, TripleBufferConveyor):
                buffer_name = buffer_type if buffer_type else "main"
                if device.is_empty(buffer_name):
                    feedback = f"{device.id} {buffer_name}缓冲区为空，无法取货"
                    return False, feedback, None
                if product_id:
                    for item in device.get_buffer(buffer_name).items:
                        if item.id == product_id:
                            product = item
                            break
                else:
                    product = yield device.pop(buffer_name)
                success = True
                
            # Conveyor
            elif isinstance(device, Conveyor):
                if device.is_empty():
                    feedback = f"{device.id}缓冲区为空，无法取货"
                    return False, feedback, None

                if product_id:
                    for item in device.buffer.items:
                        if item.id == product_id:
                            product = item
                            break
                else:
                    product = yield device.pop()
                success = True
                
            else:
                feedback = f"不支持的设备类型: {type(device).__name__}"
                return False, feedback, None
                
            # 成功取货后的操作
            if success and product:
                self.set_status(DeviceStatus.INTERACTING)
                yield self.env.timeout(time_out)
                yield self.payload.put(product)
                self.consume_battery(self.battery_consumption_per_action, "取货操作")
                buffer_desc = f" {buffer_type}" if buffer_type else ""
                feedback = f"已从{device.id}{buffer_desc}取出产品{product.id}并装载到AGV，剩余电量: {self.battery_level:.1f}%"
                
        except Exception as e:
            feedback = f"取货异常: {str(e)}"
            success = False
        
        finally:
            self.set_status(DeviceStatus.IDLE)

        return success, feedback, product

    def unload_to(self, device, buffer_type=None, action_time_factor=1):
        """AGV将产品卸载到指定设备/缓冲区，支持多种设备类型和buffer_type。返回(成功,反馈信息,产品对象)"""
        # 检查电量
        if self.is_battery_low():
            return False, f"{self.id}电量过低({self.battery_level:.1f}%)，无法执行卸载操作", None
            
        product = None
        feedback = ""
        success = False
        
        # Calculate process time
        time_out = getattr(device, 'processing_time', 10) / 5 * action_time_factor
        
        try:
            # Check if AGV has products
            if len(self.payload.items) == 0:
                return False, "AGV货物为空，无法卸载", None
            
            self.set_status(DeviceStatus.INTERACTING)
            
            # Get product from AGV
            product = yield self.payload.get()
            
            # Try to unload to device
            # QualityChecker (Check subclass first)
            if isinstance(device, QualityChecker):
                if buffer_type == "output_buffer":
                    # Default use output_buffer
                    success = yield self.env.process(device.add_product_to_outputbuffer(product))
                else:
                    success = yield self.env.process(device.add_product_to_buffer(product))
                        
            # Station (父类)
            elif isinstance(device, Station):
                success = yield self.env.process(device.add_product_to_buffer(product))
                    
            # TripleBufferConveyor (先检查子类)
            elif isinstance(device, TripleBufferConveyor):
                buffer_type = buffer_type if buffer_type else "main"
                # SimPy push()会自动阻塞直到有空间，无需手动检查is_full
                yield device.push(product, buffer_type)
                success = True
                
            # Conveyor (父类)
            elif isinstance(device, Conveyor):
                # SimPy push()会自动阻塞直到有空间，无需手动检查is_full
                yield device.push(product)
                success = True
                
            else:
                feedback = f"不支持的设备类型: {type(device).__name__}"
            
            # 统一处理结果
            if success:
                yield self.env.timeout(time_out)
                self.consume_battery(self.battery_consumption_per_action, "卸载操作")
                buffer_desc = f" {buffer_type}" if buffer_type else ""
                feedback = f"已将产品{product.id}卸载到{device.id}{buffer_desc}，剩余电量: {self.battery_level:.1f}%"
            else:
                # 失败时放回产品
                yield self.payload.put(product)
                
        except Exception as e:
            feedback = f"卸载异常: {str(e)}"
            # 异常时尝试放回产品
            if product and len(self.payload.items) < self.payload_capacity:
                yield self.payload.put(product)
            success = False
            
        finally:
            self.set_status(DeviceStatus.IDLE)
            
        return success, feedback, product

    def charge_battery(self, target_level: float = 100.0):
        """Charge battery to target level."""
        if self.is_charging:
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 已在充电中")
            return
            
        if self.battery_level >= target_level:
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量已足够 ({self.battery_level:.1f}%)")
            return
            
        # 移动到充电点
        if self.position != self.charging_point:
            distance = math.dist(self.position, self.charging_point)
            travel_time = distance / self.speed_mps
            print(f"[{self.env.now:.2f}] 🚛 {self.id}: 前往充电点 {self.charging_point}")
            yield self.env.timeout(travel_time)
            self.position = self.charging_point
            self.consume_battery(distance * self.battery_consumption_per_meter, "前往充电点")
            
        # 开始充电
        self.is_charging = True
        self.set_status(DeviceStatus.CHARGING)
        self._specific_attributes["is_charging"] = True
        
        charge_needed = target_level - self.battery_level
        charge_time = charge_needed / self.charging_speed
        
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 开始充电 ({self.battery_level:.1f}% → {target_level:.1f}%, 预计 {charge_time:.1f}s)")
        
        yield self.env.timeout(charge_time)
        
        # 充电完成
        self.battery_level = target_level
        self.is_charging = False
        self._specific_attributes["battery_level"] = self.battery_level
        self._specific_attributes["is_charging"] = False
        
        # 更新统计
        self.stats["total_charge_time"] += charge_time
        
        print(f"[{self.env.now:.2f}] ✅ {self.id}: 充电完成，当前电量: {self.battery_level:.1f}%")
        self.set_status(DeviceStatus.IDLE)

    def emergency_charge(self):
        """Emergency charging when battery is critically low."""
        print(f"[{self.env.now:.2f}] 🚨 {self.id}: 应急充电启动")
        self.stats["forced_charge_count"] += 1
        self.stats["low_battery_interruptions"] += 1
        
        # 充电到安全水平
        yield self.env.process(self.charge_battery(50.0))

    def voluntary_charge(self, target_level: float = 80.0):
        """Voluntary charging to maintain good battery level."""
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 主动充电")
        self.stats["voluntary_charge_count"] += 1
        
        yield self.env.process(self.charge_battery(target_level))

    def auto_charge_if_needed(self):
        """自动检查并在需要时充电（后台进程）"""
        while True:
            # 每5秒检查一次电量
            yield self.env.timeout(5.0)
            
            # 如果电量过低且未在充电，则自动充电
            if self.is_battery_low() and not self.is_charging:
                print(f"[{self.env.now:.2f}] 🔋 {self.id}: 自动检测到电量过低，启动应急充电")
                yield self.env.process(self.emergency_charge())

    def get_battery_status(self) -> dict:
        """获取电池状态信息"""
        return {
            "battery_level": self.battery_level,
            "is_charging": self.is_charging,
            "is_low_battery": self.is_battery_low(),
            "charging_point": self.charging_point,
            "can_operate": not self.is_battery_low(),
            "stats": self.stats.copy()
        }

    def get_charging_stats(self) -> dict:
        """获取充电相关统计数据（用于KPI计算）"""
        return {
            "total_charge_time": self.stats["total_charge_time"],
            "forced_charge_count": self.stats["forced_charge_count"],
            "voluntary_charge_count": self.stats["voluntary_charge_count"],
            "low_battery_interruptions": self.stats["low_battery_interruptions"],
            "tasks_completed": self.stats["tasks_completed"],
            "tasks_interrupted": self.stats["tasks_interrupted"],
            "charge_efficiency": (
                self.stats["voluntary_charge_count"] / 
                max(1, self.stats["forced_charge_count"] + self.stats["voluntary_charge_count"])
            ) * 100  # 主动充电比例
        }

    def get_current_payload(self) -> List[Product]:
        """获取当前载货列表"""
        return list(self.payload.items)

    def is_payload_full(self) -> bool:
        """检查载货是否已满"""
        return len(self.payload.items) >= self.payload_capacity

    def is_payload_empty(self) -> bool:
        """检查载货是否为空"""
        return len(self.payload.items) == 0

    def get_available_path_points(self) -> List[str]:
        """获取可用的路径点列表"""
        return list(self.path_points.keys())

    def get_path_point_position(self, point_name: str) -> Optional[Tuple[int, int]]:
        """获取路径点的坐标"""
        return self.path_points.get(point_name)

    def estimate_travel_time(self, target_point: str) -> float:
        """估算到目标路径点的移动时间"""
        if target_point not in self.path_points:
            return float('inf')
            
        target_position = self.path_points[target_point]
        distance = math.dist(self.position, target_position)
        return distance / self.speed_mps

    def __repr__(self) -> str:
        return f"AGV(id='{self.id}', battery={self.battery_level:.1f}%, payload={len(self.payload.items)}/{self.payload_capacity})"

    def set_status(self, new_status: DeviceStatus):
        """Overrides the base method to publish status on change."""
        if self.status == new_status:
            return  # Avoid redundant publications
        super().set_status(new_status)
        self.publish_status()

    def publish_status(self):
        """Publishes the current AGV status to the MQTT broker."""
        if not self.mqtt_client:
            return

        status_payload = AGVStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            speed_mps=self.speed_mps,
            payload=[p.id for p in self.payload.items] if self.payload else [],
            position={'x': self.position[0], 'y': self.position[1]},
            battery_level=self.battery_level,
            is_charging=(self.status == DeviceStatus.CHARGING)
        )
        # Assuming model_dump_json() is the correct method for pydantic v2
        self.mqtt_client.publish(get_agv_status_topic(self.id), status_payload.model_dump_json(), retain=True)