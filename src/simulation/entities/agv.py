# simulation/entities/agv.py
import simpy
import math
from typing import Tuple, List, Dict

from config.schemas import DeviceStatus
from src.simulation.entities.base import Vehicle
from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from src.simulation.entities.station import Station
from src.simulation.entities.quality_checker import QualityChecker

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
        speed_mps: float,
        payload_capacity: int = 1,
        low_battery_threshold: float = 5.0,  # 低电量阈值
        charging_point: Tuple[int, int] = (10, 10),  # 充电点坐标
        charging_speed: float = 3.33,  # 充电速度(30秒充满)
        battery_consumption_per_meter: float = 0.1,  # 每米消耗0.1%电量
        battery_consumption_per_action: float = 0.5,  # 每次操作消耗0.5%电量
        fault_system=None  # 故障系统引用，用于告警
    ):
        super().__init__(env, id, position, speed_mps)
        self.battery_level = 100.0
        self.payload_capacity = payload_capacity
        self.payload = simpy.Store(env, capacity=payload_capacity)
        
        # 充电相关属性
        self.is_charging = False
        self.low_battery_threshold = low_battery_threshold
        self.charging_point = charging_point
        self.charging_speed = charging_speed
        self.battery_consumption_per_meter = battery_consumption_per_meter
        self.battery_consumption_per_action = battery_consumption_per_action
        self.fault_system = fault_system
        
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
            if self.fault_system:
                self.fault_system.report_battery_low(self.id, self.battery_level)
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

    def move_to(self, target_pos: Tuple[int, int], path_points: Dict[str, Tuple[int, int]] = {}):
        """
        Moves the AGV to a new target position.
        This is a generator function that yields a timeout event.
        """
        # 检查电量是否足够移动
        distance = math.dist(self.position, target_pos)
        if not self.can_complete_task(distance, 0):
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量不足以完成移动，自动返航充电")
            yield self.env.process(self.emergency_charge())
            return
        
        self.set_status(DeviceStatus.PROCESSING) # Use 'processing' for 'moving'
        
        travel_time = distance / self.speed_mps
        
        print(f"[{self.env.now:.2f}] {self.id}: Starting move from {self.position} to {target_pos}. Duration: {travel_time:.2f}s")
        
        yield self.env.timeout(travel_time)
        
        # 消耗电量
        battery_consumed = distance * self.battery_consumption_per_meter
        self.consume_battery(battery_consumed, f"移动{distance:.1f}m")
        self.stats["total_distance"] += distance
        
        self.position = target_pos
        print(f"[{self.env.now:.2f}] {self.id}: Arrived at {self.position}. 剩余电量: {self.battery_level:.1f}%")
        self.set_status(DeviceStatus.IDLE)

    def load_product(self, product):
        """Adds a product to the AGV's payload."""
        # 检查电量
        if self.is_battery_low():
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量过低，无法执行装载操作")
            return False
            
        if len(self.payload.items) < self.payload_capacity:
            yield self.payload.put(product)
            yield self.env.timeout(1)
            self.consume_battery(self.battery_consumption_per_action, "装载产品")
            print(f"[{self.env.now:.2f}] {self.id}: Loaded product {product.id}. 剩余电量: {self.battery_level:.1f}%")
            return True
        else:
            print(f"[{self.env.now:.2f}] {self.id}: Error - Payload capacity reached.")
            return False

    def unload_product(self, product_id: str):
        """Removes a product from the AGV's payload."""
        # 检查电量
        if self.is_battery_low():
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量过低，无法执行卸载操作")
            return None
            
        if self.payload.items:
            product_to_remove = yield self.payload.get()
            yield self.env.timeout(1)
            self.consume_battery(self.battery_consumption_per_action, "卸载产品")
            print(f"[{self.env.now:.2f}] {self.id}: Unloaded product {product_to_remove.id}. 剩余电量: {self.battery_level:.1f}%")
            return product_to_remove
        else:
            print(f"[{self.env.now:.2f}] {self.id}: Error - Product {product_id} not in payload.")
            return None
        
    def load_from(self, device, buffer_type=None, action_time_factor=1):
        """AGV从指定设备/缓冲区取货，支持多种设备类型和buffer_type。返回(成功,反馈信息,产品对象)"""
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
                    
                product = yield target_buffer.get()
                success = True
                
            # Station (父类)
            elif isinstance(device, Station):
                if len(device.buffer.items) == 0:
                    feedback = f"{device.id} buffer为空，无法取货"
                    return False, feedback, None
                    
                product = yield device.buffer.get()
                success = True
                
            # TripleBufferConveyor
            elif isinstance(device, TripleBufferConveyor):
                buffer_name = buffer_type if buffer_type else "main"
                if device.is_empty(buffer_name):
                    feedback = f"{device.id} {buffer_name}缓冲区为空，无法取货"
                    return False, feedback, None
                    
                product = yield device.pop(buffer_name)
                success = True
                
            # Conveyor
            elif isinstance(device, Conveyor):
                if device.is_empty():
                    feedback = f"{device.id}缓冲区为空，无法取货"
                    return False, feedback, None
                    
                product = yield device.pop()
                success = True
                
            else:
                feedback = f"不支持的设备类型: {type(device).__name__}"
                return False, feedback, None
                
            # 成功取货后的操作
            if success and product:
                yield self.env.timeout(time_out)
                yield self.payload.put(product)
                self.consume_battery(self.battery_consumption_per_action, "取货操作")
                buffer_desc = f" {buffer_type}" if buffer_type else ""
                feedback = f"已从{device.id}{buffer_desc}取出产品{product.id}并装载到AGV，剩余电量: {self.battery_level:.1f}%"
                
        except Exception as e:
            feedback = f"取货异常: {str(e)}"
            success = False

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
                
            # Get product from AGV
            product = yield self.payload.get()
            
            # Try to unload to device
            # QualityChecker (Check subclass first)
            if isinstance(device, QualityChecker):
                if buffer_type == "output_buffer":
                    # Default use output_buffer
                    success = device.add_product_to_outputbuffer(product)
                else:
                    success = device.add_product_to_buffer(product)
                        
            # Station (父类)
            elif isinstance(device, Station):
                success = device.add_product_to_buffer(product)
                    
            # TripleBufferConveyor (先检查子类)
            elif isinstance(device, TripleBufferConveyor):
                buffer_type = buffer_type if buffer_type else "main"
                if not device.is_full(buffer_type):
                    yield device.push(product, buffer_type)
                    success = True
                else:
                    feedback = f"{device.id} {buffer_type}缓冲区已满，卸载失败"
                
            # Conveyor (父类)
            elif isinstance(device, Conveyor):
                if not device.is_full():
                    yield device.push(product)
                    success = True
                else:
                    feedback = f"{device.id}缓冲区已满，卸载失败"
                
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
            
        return success, feedback, product

    def request_charge(self):
        """主动请求充电（选手调用）"""
        if self.is_charging:
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 已在充电中")
            return
            
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 收到主动充电请求，当前电量: {self.battery_level:.1f}%")
        self.stats["voluntary_charge_count"] += 1
        
        # 移动到充电点并充电
        yield self.env.process(self.go_to_charging_point())
        yield self.env.process(self.charge())

    def emergency_charge(self):
        """紧急充电（电量过低自动触发）"""
        if self.is_charging:
            return
            
        print(f"[{self.env.now:.2f}] 🚨 {self.id}: 电量过低，强制返航充电！当前电量: {self.battery_level:.1f}%")
        self.stats["forced_charge_count"] += 1
        self.stats["tasks_interrupted"] += 1
        
        # 如果有载货，需要考虑是否继续任务还是返航
        if len(self.payload.items) > 0:
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 载有{len(self.payload.items)}件货物时电量不足！")
            self.stats["low_battery_interruptions"] += 1
            
        # 移动到充电点并充电
        yield self.env.process(self.go_to_charging_point())
        yield self.env.process(self.charge())

    def go_to_charging_point(self):
        """移动到充电点"""
        if self.position == self.charging_point:
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 已在充电点")
            return
            
        distance = math.dist(self.position, self.charging_point)
        travel_time = distance / self.speed_mps
        
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 前往充电点 {self.charging_point}，距离: {distance:.1f}m")
        
        self.set_status(DeviceStatus.PROCESSING)  # 移动状态
        yield self.env.timeout(travel_time)
        
        # 移动到充电点的电量消耗（即使电量很低也要能到达）
        battery_consumed = distance * self.battery_consumption_per_meter
        self.consume_battery(battery_consumed, f"前往充电点{distance:.1f}m")
        self.stats["total_distance"] += distance
        
        self.position = self.charging_point
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 到达充电点，剩余电量: {self.battery_level:.1f}%")

    def charge(self):
        """充电过程"""
        if self.battery_level >= 100.0:
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电量已满，无需充电")
            return
            
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 开始充电，当前电量: {self.battery_level:.1f}%")
        self.is_charging = True
        self._specific_attributes["is_charging"] = True
        self.set_status(DeviceStatus.MAINTENANCE)  # 充电状态用维护表示
        
        charge_start_time = self.env.now
        
        # 充电到满
        while self.battery_level < 100.0:
            yield self.env.timeout(1.0)  # 每秒检查一次
            
            charge_amount = min(self.charging_speed, 100.0 - self.battery_level)
            self.battery_level += charge_amount
            self._specific_attributes["battery_level"] = self.battery_level
            
            # 每10%电量打印一次进度
            if int(self.battery_level) % 10 == 0 and charge_amount > 0:
                print(f"[{self.env.now:.2f}] 🔋 {self.id}: 充电中... {self.battery_level:.0f}%")
        
        charge_time = self.env.now - charge_start_time
        self.stats["total_charge_time"] += charge_time
        
        self.is_charging = False
        self._specific_attributes["is_charging"] = False
        self.set_status(DeviceStatus.IDLE)
        
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 充电完成！电量: {self.battery_level:.1f}%，耗时: {charge_time:.1f}秒")

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