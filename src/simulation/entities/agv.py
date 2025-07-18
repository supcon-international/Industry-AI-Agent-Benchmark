# simulation/entities/agv.py
import simpy
import math
from typing import Tuple, Dict, Optional, List
from src.simulation.entities.base import Vehicle, Device
from src.simulation.entities.product import Product
from src.simulation.entities.quality_checker import QualityChecker
from src.simulation.entities.station import Station
from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from src.simulation.entities.warehouse import RawMaterial, Warehouse
from config.schemas import DeviceStatus, AGVStatus
from config.topics import get_agv_status_topic
from config.path_timing import get_travel_time, is_path_available
import logging

logger = logging.getLogger(__name__)

class AGV(Vehicle):
    """
    Represents an Automated Guided Vehicle (AGV). Must be initialized with a position in path_points!

    AGVs are responsible for transporting products between stations.
    
    Attributes:
        battery_level (float): The current battery percentage (0-100).
        payload (List[any]): The list of products currently being carried.
        low_battery_threshold (float): when battery level is below this value, AGV will return to charging point automatically
        charging_point (str): Charging point name, must be in path_points
        charging_speed (float): charging speed (%/second)
        battery_consumption_per_meter (float): every meter move consumes this much battery
        battery_consumption_per_action (float): every action consumes this much battery
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
        charging_point: str = "P10",  # 充电点坐标(可为路径点名或坐标)
        charging_speed: float = 3.33,  # 充电速度(30秒充满)
        battery_consumption_per_meter: float = 0.1,  # 每米消耗0.1%电量
        battery_consumption_per_action: float = 0.5,  # 每次操作消耗0.5%电量
        fault_system=None, # Injected dependency
        mqtt_client=None,
        kpi_calculator=None  # KPI calculator dependency
    ):
        if position not in path_points.values():
            raise ValueError(f"AGV position {position} not in path_points {path_points}")

        super().__init__(env, id, position, speed_mps, mqtt_client)
        self.battery_level = 40.0
        self.payload_capacity = payload_capacity
        self.payload = simpy.Store(env, capacity=payload_capacity)
        self.fault_system = fault_system
        self.kpi_calculator = kpi_calculator
        self.current_point = list(path_points.keys())[list(path_points.values()).index(position)]
        self.path_points = path_points
        self.target_point = None # current target point if moving
        self.estimated_time = 0.0 # estimated time to complete the task or moving to the target point
        # 充电相关属性
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

        # Publish initial status upon creation
        self.publish_status("initialized")

    def consume_battery(self, amount: float, reason: str = "operation"):
        """消耗电量"""
        if amount <= 0:
            return
            
        old_level = self.battery_level
        self.battery_level = max(0.0, self.battery_level - amount)
        
        if old_level > self.low_battery_threshold and self.battery_level <= self.low_battery_threshold:
            # 电量首次降到阈值以下时告警
            self.report_battery_low(self.battery_level)
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量过低！当前电量: {self.battery_level:.1f}% (原因: {reason})")

    def is_battery_low(self) -> bool:
        """检查电量是否过低"""
        return self.battery_level <= self.low_battery_threshold

    def can_complete_task(self, estimated_travel_time: float = 0.0, estimated_actions: int = 0) -> bool:
        """预估是否有足够电量完成任务"""
        # Convert travel time to estimated distance for battery calculation
        estimated_distance = estimated_travel_time * self.speed_mps
        estimated_consumption = (
            estimated_distance * self.battery_consumption_per_meter +
            estimated_actions * self.battery_consumption_per_action
        )
        
        # 预留回到充电点的电量 (使用路径时间表)
        return_time = get_travel_time(self.current_point, self.charging_point)
        if return_time < 0:
            # If no direct path to charging point, use fallback calculation
            return_distance = math.dist(self.position, self.path_points[self.charging_point])
            return_consumption = return_distance * self.battery_consumption_per_meter
        else:
            return_distance = return_time * self.speed_mps
            return_consumption = return_distance * self.battery_consumption_per_meter
        
        total_needed = estimated_consumption + return_consumption + 2.0  # 2%安全余量
        return self.battery_level >= total_needed

    def move_to(self, target_point: str):
        """
        Move to a specific path point using AGV's independent path system.
        
        Args:
            target_point: Path point name (e.g., "P1", "P2")
            
        Returns:
            (success, feedback_message)
        """
        # Wrap the core logic in a process to make it interruptible
        self.action = self.env.process(self._move_to_process(target_point))
        try:
            result = yield self.action
            return result if result else (True, f"成功移动到{target_point}")
        except simpy.Interrupt as e:
            msg = f"Movement to {target_point} interrupted: {e.cause}"
            logger.error(f"[{self.env.now:.2f}] ⚠️  {self.id}: {msg}")
            return False, msg
            
    def _move_to_process(self, target_point: str):
        """The actual process logic for move_to, to be wrapped by self.action."""
        try:
            if not self.can_operate():
                msg = f"Can not move. AGV {self.id} is not available."
                logger.error(f"[{self.env.now:.2f}] ⚠️  {self.id}: {msg}")
                return False, msg
                
            if target_point not in self.path_points:
                msg = f"Unknown path point {target_point}"
                logger.error(f"[{self.env.now:.2f}] ❌ {self.id}: {msg}")
                return False, msg
                
            self.target_point = target_point
    
            # use path timing to get travel time
            travel_time = get_travel_time(self.current_point, target_point)
            if travel_time < 0:
                msg = f"Can not find path from {self.current_point} to {target_point}"
                print(f"[{self.env.now:.2f}] ❌ {self.id}: {msg}")
                return False, msg
                
            # check if battery is enough
            if not self.can_complete_task(travel_time, 1):
                msg = f"Battery level is too low to move to {target_point}"
                print(f"[{self.env.now:.2f}] 🔋 {self.id}: {msg}")
                self.stats["tasks_interrupted"] += 1
                yield self.env.process(self.emergency_charge())
                return False, f"{msg}, emergency charging"
                
            self.set_status(DeviceStatus.MOVING, f"moving to {target_point} from {self.current_point}, estimated time: {travel_time:.1f}s")
            print(f"[{self.env.now:.2f}] 🚛 {self.id}: move to path point {target_point} {self.path_points[target_point]} (estimated time: {travel_time:.1f}s)")
            
            # wait for move to complete
            self.estimated_time = travel_time
            yield self.env.timeout(travel_time)
            
            # update position and consume battery
            self.position = self.path_points[target_point]
            self.current_point = target_point
            self.target_point = None
            self.estimated_time = 0.0
            
            # calculate battery consumption based on travel time
            distance = travel_time * self.speed_mps
            self.consume_battery(distance * self.battery_consumption_per_meter, f"移动到{target_point}")
            self.consume_battery(self.battery_consumption_per_action, "路径点操作")
            
            # update statistics
            self.stats["total_distance"] += distance
            self.stats["tasks_completed"] += 1
            
            # Report task completion to KPI calculator
            if self.kpi_calculator:
                self.kpi_calculator.register_agv_task_complete(self.id)
            
            print(f"[{self.env.now:.2f}] ✅ {self.id}: 到达 {target_point}, 电量: {self.battery_level:.1f}%")
            
            # Before setting to IDLE, check for pending faults
            if self._check_and_trigger_pending_fault():
                return True, f"Arrived at {target_point}, but triggered fault"

            self.set_status(DeviceStatus.IDLE, f"arrived at {target_point}")
            return True, f"Successfully arrived at path point {target_point}, remaining battery: {self.battery_level:.1f}%"
        
        finally:
            self.action = None

    def load_from(self, device:Device, buffer_type=None, product_id=None, action_time_factor=1) :
        """AGV从指定设备/缓冲区取货，支持多种设备类型和buffer_type。返回(成功,反馈信息,产品对象)
        """
        if not self.can_operate():
                msg = f"Can not load. AGV {self.id} is not available."
                logger.error(f"[{self.env.now:.2f}] ⚠️  {self.id}: {msg}")
                return False, msg, None
        
        if self.current_point not in device.interacting_points:
            msg = f"[{self.env.now:.2f}] ❌ {self.id}: Cannot load. Not at a valid interacting point for {device.id}. Current: {self.current_point}, Valid: {device.interacting_points}"
            logger.error(msg)
            return False, msg, None
        
        # check battery level
        if self.is_battery_low():
            return False, f"{self.id} battery level is too low ({self.battery_level:.1f}%), can not load", None
            
        product = None
        feedback = ""
        success = False
        
        # calculate timeout time
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
            elif isinstance(device, Station) or isinstance(device, RawMaterial):
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
                logger.error(feedback)
                return False, feedback, None
                
            # 成功取货后的操作
            if success and product:
                buffer_desc = f" {buffer_type}" if buffer_type else ""
                product.add_history(self.env.now, f"Loaded onto {self.id} from {device.id}")
                
                self.set_status(DeviceStatus.INTERACTING, f"loading from {device.id}{buffer_desc}")
                yield self.env.timeout(time_out)
                yield self.payload.put(product)
                self.consume_battery(self.battery_consumption_per_action, "取货操作")
                feedback = f"已从{device.id}{buffer_desc}取出产品{product.id}并装载到AGV，剩余电量: {self.battery_level:.1f}%"
                
        except Exception as e:
            feedback = f"取货异常: {str(e)}"
            success = False
        
        finally:
            self.set_status(DeviceStatus.IDLE)

        return success, feedback, product

    def unload_to(self, device, buffer_type=None, action_time_factor=1):
        """AGV将产品卸载到指定设备/缓冲区，支持多种设备类型和buffer_type。返回(成功,反馈信息,产品对象)"""
        # check if agv can operate
        if not self.can_operate():
                msg = f"Can not unload. AGV {self.id} is not available."
                logger.error(f"[{self.env.now:.2f}] ⚠️  {self.id}: {msg}")
                return False, msg, None
        
        if self.current_point not in device.interacting_points:
            msg = f"[{self.env.now:.2f}] ❌ {self.id}: Cannot unload. Not at a valid interacting point for {device.id}. Current: {self.current_point}, Valid: {device.interacting_points}"
            logger.error(msg)
            return False, msg, None

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
            
            self.set_status(DeviceStatus.INTERACTING, f"unloading to {device.id}")
            
            # Get product from AGV
            product = yield self.payload.get()
            
            # 检查产品移动是否符合工艺路线
            if hasattr(product, 'next_move_checker') and hasattr(product, 'update_location'):
                # 检查移动是否合法
                can_move, move_reason = product.next_move_checker(self.env.now, device.id)
                if not can_move:
                    feedback = f"产品移动违反工艺路线: {move_reason}"
                    yield self.payload.put(product)  # 放回产品
                    return False, feedback, product
            
            # Try to unload to device
            # QualityChecker (Check subclass first)
            if isinstance(device, QualityChecker):
                if buffer_type == "output_buffer":
                    # Default use output_buffer
                    success = yield self.env.process(device.add_product_to_outputbuffer(product))
                else:
                    success = yield self.env.process(device.add_product_to_buffer(product))
                        
            # Station (父类)
            elif isinstance(device, Station) or isinstance(device, Warehouse):
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
                # 更新产品位置
                if hasattr(product, 'update_location'):
                    location_updated = product.update_location(device.id, self.env.now)
                    if not location_updated:
                        print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 产品位置更新失败，但卸载成功")
                
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

    def charge_battery(self, target_level: float = 100.0, message: Optional[str] = None):
        """Charge battery to target level. Returns (success, feedback_message)"""
        if self.status == DeviceStatus.CHARGING:
            msg = f"already charging"
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: {msg}")
            return True, msg
            
        if self.battery_level >= target_level:
            msg = f"battery level is enough ({self.battery_level:.1f}%)"
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: {msg}")
            return True, msg
            
        # move to charging point
        if self.current_point != self.charging_point:
            yield self.env.process(self.move_to(self.charging_point))
            
        # start charging
        self.set_status(DeviceStatus.CHARGING, message)
        
        charge_needed = target_level - self.battery_level
        charge_time = charge_needed / self.charging_speed
        
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: start charging ({self.battery_level:.1f}% → {target_level:.1f}%, estimated {charge_time:.1f}s)")
        
        yield self.env.timeout(charge_time)
        
        # charging completed
        self.battery_level = target_level
        
        # update statistics
        self.stats["total_charge_time"] += charge_time
        
        # Report charge event with duration to KPI calculator
        if self.kpi_calculator and hasattr(self, '_charge_start_time'):
            actual_charge_duration = self.env.now - self._charge_start_time
            is_active = getattr(self, '_is_active_charge', False)
            self.kpi_calculator.register_agv_charge(self.id, is_active, actual_charge_duration)
            # Clean up temporary attributes
            if hasattr(self, '_charge_start_time'):
                del self._charge_start_time
            if hasattr(self, '_is_active_charge'):
                del self._is_active_charge
        
        print(f"[{self.env.now:.2f}] ✅ {self.id}: 充电完成，当前电量: {self.battery_level:.1f}%")

        # Before setting to IDLE, check for pending faults
        if self._check_and_trigger_pending_fault():
            return True, f"充电完成到 {target_level:.1f}%，但触发了故障"

        self.set_status(DeviceStatus.IDLE, f"charged to {target_level:.1f}%")
        return True, f"充电完成，当前电量: {self.battery_level:.1f}%"

    def emergency_charge(self):
        """Emergency charging when battery is critically low."""
        print(f"[{self.env.now:.2f}] 🚨 {self.id}: emergency charging started")
        self.stats["forced_charge_count"] += 1
        self.stats["low_battery_interruptions"] += 1
        
        # Report to KPI calculator
        if self.kpi_calculator:
            # Note: charge_duration will be calculated and reported after charging completes
            self._charge_start_time = self.env.now
        
        # charge to safe level
        yield self.env.process(self.charge_battery(50.0, "emergency charging to 50%"))

    def voluntary_charge(self, target_level: float = 80.0):
        """Voluntary charging to maintain good battery level. Returns (success, feedback_message)"""
        target_level = float(target_level)
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: voluntary charging")
        self.stats["voluntary_charge_count"] += 1
        
        # Report to KPI calculator
        if self.kpi_calculator:
            # Note: charge_duration will be calculated and reported after charging completes
            self._charge_start_time = self.env.now
            self._is_active_charge = True
        
        self.action = self.env.process(self.charge_battery(target_level, f"voluntary charging to {target_level:.1f}%"))
        try:
            result = yield self.action
            return result if result else (True, f"充电完成到 {target_level:.1f}%")
        except simpy.Interrupt as e:
            msg = f"Charging interrupted: {e.cause}"
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: {msg}")
            return False, msg
        finally:
            self.action = None

    def auto_charge_if_needed(self):
        """auto check and charge if needed (background process)"""
        while True:
            # check every 5 seconds
            yield self.env.timeout(5.0)
            
            # Update transport time for KPI if moving
            if self.status == DeviceStatus.MOVING and self.kpi_calculator:
                self.kpi_calculator.update_agv_transport_time(self.id, 5.0)
            
            # if battery is low and not charging, start emergency charging
            if self.is_battery_low() and self.status != DeviceStatus.CHARGING:
                print(f"[{self.env.now:.2f}] 🔋 {self.id}: battery is low, start emergency charging")
                yield self.env.process(self.emergency_charge())

    def get_battery_status(self) -> dict:
        """获取电池状态信息"""
        return {
            "battery_level": self.battery_level,
            "is_charging": self.status == DeviceStatus.CHARGING,
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

    def _check_and_trigger_pending_fault(self) -> bool:
        """
        Checks if a fault is pending for this AGV and triggers it.
        This is called internally just before the AGV becomes IDLE.
        Returns True if a fault was triggered, False otherwise.
        """
        if self.fault_system and self.id in self.fault_system.pending_agv_faults:
            fault_type = self.fault_system.pending_agv_faults.pop(self.id)
            print(f"[{self.env.now:.2f}] 💥 AGV {self.id} is idle, triggering pending fault: {fault_type.value}")
            self.fault_system._inject_fault_now(self.id, fault_type)
            return True
        return False

    def __repr__(self) -> str:
        return f"AGV(id='{self.id}', battery={self.battery_level:.1f}%, payload={len(self.payload.items)}/{self.payload_capacity})"

    def set_status(self, new_status: DeviceStatus, message: Optional[str] = None):
        """Overrides the base method to publish status on change."""
        if self.status == new_status:
            return  # Avoid redundant publications
        super().set_status(new_status)
        self.publish_status(message)

    def report_battery_low(self, battery_level: float):
        """report battery low"""
        self._publish_fault_event("battery_low", {
            "device_id": self.id,
            "battery_level": battery_level,
            "timestamp": self.env.now,
            "severity": "warning"
        })
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: Battery low warning ({battery_level:.1f}%)")

    def publish_status(self, message: Optional[str] = None):
        """Publishes the current AGV status to the MQTT broker."""
        if not self.mqtt_client:
            return

        status_payload = AGVStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            speed_mps=self.speed_mps,
            current_point=self.current_point,
            target_point=self.target_point,
            estimated_time=self.estimated_time,
            position={'x': self.position[0], 'y': self.position[1]},
            payload=[p.id for p in self.payload.items] if self.payload else [],
            battery_level=self.battery_level,
            message=message
        )
        # Assuming model_dump_json() is the correct method for pydantic v2
        self.mqtt_client.publish(get_agv_status_topic(self.id), status_payload.model_dump_json(), retain=False)