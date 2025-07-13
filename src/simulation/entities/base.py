# simulation/entities/base.py
import simpy
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional
from dataclasses import dataclass

from config.schemas import DeviceStatus, DeviceDetailedStatus

@dataclass
class DevicePerformanceMetrics:
    """设备性能指标"""
    temperature: float = 25.0  # 基准温度
    vibration_level: float = 0.5  # 基准振动水平
    power_consumption: float = 100.0  # 基准功耗
    efficiency_rate: float = 100.0  # 基准效率
    cycle_count: int = 0
    operating_hours: float = 0.0

class Device:
    """
    Base class for all simulated devices in the factory.

    This class provides common attributes and methods that all devices,
    such as stations, AGVs, and conveyors, will inherit.

    Attributes:
        env (simpy.Environment): The simulation environment.
        id (str): The unique identifier for the device.
        status (DeviceStatus): The current operational status of the device.
        position (Tuple[int, int]): The (x, y) coordinates of the device in the factory layout.
        mqtt_client: MQTT client for publishing fault events
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], device_type: str = "generic", mqtt_client=None):
        if not isinstance(env, simpy.Environment):
            raise ValueError("env must be a valid simpy.Environment object.")
        
        self.env = env
        self.id = id
        self.device_type = device_type
        self.status = DeviceStatus.IDLE
        self.position = position
        self.mqtt_client = mqtt_client
        
        # 详细状态信息
        self.performance_metrics = DevicePerformanceMetrics()
        self.last_maintenance_time = 0.0
        
        # 故障相关状态
        self.has_fault = False
        self.fault_symptom: Optional[str] = None
        self.frozen_until: Optional[float] = None
        
        # 设备特定属性（子类可以覆盖）
        self._specific_attributes = {}
        
        # 启动状态更新过程
        self.env.process(self._update_performance_metrics())

    def _update_performance_metrics(self):
        """定期更新设备性能指标"""
        while True:
            # 模拟正常的性能波动
            if self.status == DeviceStatus.PROCESSING:
                self.performance_metrics.operating_hours += 1.0
                self.performance_metrics.cycle_count += 1
                
                # 模拟温度和功耗随使用而变化
                self.performance_metrics.temperature += random.uniform(-0.5, 1.0)
                self.performance_metrics.power_consumption += random.uniform(-5, 10)
                
                # 模拟设备老化
                age_factor = self.performance_metrics.operating_hours / 1000.0
                self.performance_metrics.efficiency_rate = max(50.0, 100.0 - age_factor * 5)
                
            elif self.status == DeviceStatus.IDLE:
                # 闲置时温度下降，功耗降低
                self.performance_metrics.temperature = max(20.0, self.performance_metrics.temperature - 0.2)
                self.performance_metrics.power_consumption = max(50.0, self.performance_metrics.power_consumption - 2)
            
            # 每分钟更新一次
            yield self.env.timeout(60)

    def get_detailed_status(self) -> DeviceDetailedStatus:
        """获取设备详细状态信息（inspect功能）"""
        # 基础状态
        status_data = {
            "device_id": self.id,
            "device_type": self.device_type,
            "current_status": self.status,
            "temperature": round(self.performance_metrics.temperature, 1),
            "vibration_level": round(self.performance_metrics.vibration_level, 2),
            "power_consumption": round(self.performance_metrics.power_consumption, 1),
            "efficiency_rate": round(self.performance_metrics.efficiency_rate, 1),
            "cycle_count": self.performance_metrics.cycle_count,
            "last_maintenance_time": self.last_maintenance_time,
            "operating_hours": round(self.performance_metrics.operating_hours, 1),
            "has_fault": self.has_fault,
            "fault_symptom": self.fault_symptom,
            "frozen_until": self.frozen_until
        }
        
        # 添加设备特定属性
        status_data.update(self._specific_attributes)
        
        return DeviceDetailedStatus(**status_data)

    def apply_fault_effects(self, fault_type: str):
        """应用故障对设备状态的影响"""
        self.has_fault = True
        
        if fault_type == "station_vibration":
            self.performance_metrics.vibration_level *= random.uniform(2.0, 4.0)
            self.performance_metrics.temperature += random.uniform(5, 15)
            self._specific_attributes["precision_level"] = random.uniform(60.0, 80.0)  # 精度下降
            
        elif fault_type == "precision_degradation":
            self._specific_attributes["precision_level"] = random.uniform(40.0, 70.0)
            self._specific_attributes["tool_wear_level"] = random.uniform(70.0, 95.0)
            
        elif fault_type == "efficiency_anomaly":
            self.performance_metrics.efficiency_rate *= random.uniform(0.3, 0.7)
            self.performance_metrics.temperature += random.uniform(10, 25)
            self._specific_attributes["lubricant_level"] = random.uniform(10.0, 30.0)
            
        elif fault_type == "agv_battery_drain":
            if "battery_level" in self._specific_attributes:
                self._specific_attributes["battery_level"] = random.uniform(5.0, 25.0)
                
        elif fault_type == "agv_path_blocked":
            if "position_accuracy" in self._specific_attributes:
                self._specific_attributes["position_accuracy"] = random.uniform(50.0, 80.0)

    def clear_fault_effects(self):
        """清除故障影响，恢复正常状态"""
        self.has_fault = False
        self.fault_symptom = None
        self.frozen_until = None
        
        # 恢复正常的性能指标
        self.performance_metrics.vibration_level = random.uniform(0.3, 0.8)
        self.performance_metrics.temperature = random.uniform(20.0, 30.0)
        
        # 恢复设备特定属性
        if self.device_type == "station":
            self._specific_attributes.update({
                "precision_level": random.uniform(95.0, 100.0),
                "tool_wear_level": random.uniform(0.0, 20.0),
                "lubricant_level": random.uniform(80.0, 100.0)
            })
        elif self.device_type == "agv":
            self._specific_attributes.update({
                "battery_level": random.uniform(80.0, 100.0),
                "position_accuracy": random.uniform(95.0, 100.0),
                "load_weight": random.uniform(0.0, 50.0)
            })

    def freeze_device(self, duration: float):
        """冻结设备指定时间"""
        self.frozen_until = self.env.now + duration
        self.set_status(DeviceStatus.FROZEN)
        print(f"[{self.env.now:.2f}] 🧊 {self.id} 被冻结 {duration:.1f} 秒")

    def is_frozen(self) -> bool:
        """检查设备是否处于冻结状态"""
        if self.frozen_until and self.env.now < self.frozen_until:
            return True
        elif self.frozen_until and self.env.now >= self.frozen_until:
            # 冻结时间结束，自动解冻
            self.unfreeze_device()
        return False

    def unfreeze_device(self):
        """解冻设备"""
        self.frozen_until = None
        if self.status == DeviceStatus.FROZEN:
            # 解冻后恢复为空闲状态（如果没有其他问题）
            if self.has_fault:
                self.set_status(DeviceStatus.ERROR)
            else:
                self.set_status(DeviceStatus.IDLE)
            print(f"[{self.env.now:.2f}] ❄️  {self.id} 解冻完成")

    def can_operate(self) -> bool:
        """检查设备是否可以操作"""
        # 检查冻结状态
        if self.is_frozen():
            return False
            
        # 维修状态下无法操作
        if self.has_fault and self.status in [DeviceStatus.ERROR, DeviceStatus.MAINTENANCE, DeviceStatus.FROZEN]:
            return False
            
        return True

    # ========== 故障报告功能 ==========
    def report_battery_low(self, battery_level: float):
        """报告电池电量过低"""
        self._publish_fault_event("battery_low", {
            "device_id": self.id,
            "battery_level": battery_level,
            "timestamp": self.env.now,
            "severity": "warning"
        })
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: 电池电量过低告警 ({battery_level:.1f}%)")

    def report_buffer_full(self, buffer_name: str):
        """报告缓冲区满"""
        self._publish_fault_event("buffer_full", {
            "device_id": self.id,
            "buffer_name": buffer_name,
            "timestamp": self.env.now,
            "severity": "warning"
        })
        print(f"[{self.env.now:.2f}] 📦 {self.id}: 缓冲区满告警 ({buffer_name})")

    def report_performance_degradation(self, metric_name: str, current_value: float, threshold: float):
        """报告性能下降"""
        self._publish_fault_event("performance_degradation", {
            "device_id": self.id,
            "metric_name": metric_name,
            "current_value": current_value,
            "threshold": threshold,
            "timestamp": self.env.now,
            "severity": "warning"
        })
        print(f"[{self.env.now:.2f}] 📉 {self.id}: 性能下降告警 ({metric_name}: {current_value:.1f})")

    def report_device_error(self, error_type: str, description: str):
        """报告设备错误"""
        self._publish_fault_event("device_error", {
            "device_id": self.id,
            "error_type": error_type,
            "description": description,
            "timestamp": self.env.now,
            "severity": "error"
        })
        print(f"[{self.env.now:.2f}] ❌ {self.id}: 设备错误 ({error_type}: {description})")

    def _publish_fault_event(self, event_type: str, event_data: dict):
        """发布故障事件到MQTT"""
        if self.mqtt_client:
            topic = f"factory/faults/{self.id}"
            message = {
                "event_type": event_type,
                "data": event_data
            }
            self.mqtt_client.publish(topic, message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.id}', status='{self.status.value}')"

    def set_status(self, new_status: DeviceStatus):
        """
        Updates the device's status and logs the change.
        """
        if self.status != new_status:
            # In a real implementation, we would use the logger here.
            print(f"[{self.env.now:.2f}] {self.id}: Status changed from {self.status.value} to {new_status.value}")
            self.status = new_status

# Example of a more specific base class that could inherit from Device
class Vehicle(Device):
    """
    Base class for all mobile entities, like AGVs.
    It can be extended with attributes like speed, battery, etc.
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], speed_mps: float, mqtt_client=None):
        super().__init__(env, id, position, device_type="agv", mqtt_client=mqtt_client)
        self.speed_mps = speed_mps # meters per second 
        
        # AGV特定属性
        self._specific_attributes.update({
            "battery_level": random.uniform(80.0, 100.0),
            "position_accuracy": random.uniform(95.0, 100.0),
            "load_weight": 0.0
        }) 

class BaseConveyor(Device, ABC):
    """
    Conveyor的抽象基类，定义所有Conveyor必须实现的接口
    
    所有Conveyor子类都应该实现这些方法，确保一致的接口
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], mqtt_client=None):
        super().__init__(env, id, position, device_type="conveyor", mqtt_client=mqtt_client)
    
    @abstractmethod
    def push(self, product):
        """将产品放入传送带，满时自动阻塞"""
        pass

    @abstractmethod
    def pop(self):
        """从传送带取出产品，空时自动阻塞"""
        pass

    @abstractmethod
    def is_full(self):
        """检查传送带是否已满（用于状态查询，不用于流控）"""
        pass

    @abstractmethod
    def is_empty(self):
        """检查传送带是否为空"""
        pass

    @abstractmethod
    def get_buffer(self):
        """获取buffer对象"""
        pass 

    @abstractmethod
    def set_downstream_station(self, station):
        """设置下游工站"""
        pass