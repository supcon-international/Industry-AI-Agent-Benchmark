# simulation/entities/base.py
import simpy
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional
from dataclasses import dataclass

from config.schemas import DeviceStatus, DeviceDetailedStatus
from src.utils.topic_manager import TopicManager

class Device:
    """
    Base class for all simulated devices in the factory.
    Simplified for a basic fault model.
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], device_type: str = "generic", mqtt_client=None, interacting_points: list = []):
        if not isinstance(env, simpy.Environment):
            raise ValueError("env must be a valid simpy.Environment object.")
        
        self.env = env
        self.id = id
        self.device_type = device_type
        self.position = position
        self.mqtt_client = mqtt_client
        self.interacting_points = interacting_points if interacting_points is not None else []
        
        # 设备状态和故障相关属性
        self.status = DeviceStatus.IDLE
        self.fault_symptom = None
        self.action: Optional[simpy.Process] = None # Stores the current action process
        
        # 性能指标
        self.performance_metrics = type('PerformanceMetrics', (), {
            'efficiency_rate': 100.0,
            'error_rate': 0.0,
            'uptime': 100.0
        })()
        
        # 设备特定属性（可被子类扩展）
        self._specific_attributes = {
            'temperature': random.uniform(20.0, 25.0),
            'vibration_level': random.uniform(0.0, 5.0),
            'power_consumption': random.uniform(80.0, 120.0)
        }

    def set_status(self, new_status: DeviceStatus, message: Optional[str] = None):
        """设置设备状态"""
        if self.status != new_status:
            old_status = self.status
            self.status = new_status
            log_message = f"[{self.env.now:.2f}] 🔄 {self.id}: 状态变更 {old_status.value} → {new_status.value}"
            if message:
                log_message += f" ({message})"
            print(log_message)

    def can_operate(self) -> bool:
        """检查设备是否可以操作"""
        # 检查冻结状态
        return self.status not in [DeviceStatus.FAULT, DeviceStatus.MAINTENANCE, DeviceStatus.BLOCKED]

    def get_detailed_status(self) -> DeviceDetailedStatus:
        """获取设备详细状态"""
        return DeviceDetailedStatus(
            device_id=self.id,
            device_type=self.device_type,
            current_status=self.status,
            temperature=self._specific_attributes.get('temperature', 25.0),
            vibration_level=self._specific_attributes.get('vibration_level', 0.0),
            power_consumption=self._specific_attributes.get('power_consumption', 100.0),
            efficiency_rate=getattr(self.performance_metrics, 'efficiency_rate', 100.0),
            cycle_count=0,  # 简化实现
            last_maintenance_time=0.0,  # 简化实现
            operating_hours=self.env.now / 3600.0,  # 转换为小时
            fault_symptom=self.fault_symptom,
            frozen_until=None,  # 简化故障系统不使用冻结机制
            precision_level=self._specific_attributes.get('precision_level', 100.0),
            tool_wear_level=self._specific_attributes.get('tool_wear_level', 0.0),
            lubricant_level=self._specific_attributes.get('lubricant_level', 100.0),
            battery_level=self._specific_attributes.get('battery_level', 100.0),
            position_accuracy=self._specific_attributes.get('position_accuracy', 100.0),
            load_weight=self._specific_attributes.get('load_weight', 0.0)
        )
    
    def report_buffer_full(self, buffer_name: str):
        """报告缓冲区满"""
        self._publish_fault_event("buffer_full", {
            "device_id": self.id,
            "buffer_name": buffer_name,
            "timestamp": self.env.now,
            "severity": "warning"
        })
        print(f"[{self.env.now:.2f}] 📦 {self.id}: 缓冲区满告警 ({buffer_name})")


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

    def recover(self):
        """Default recovery logic."""
        self.set_status(DeviceStatus.IDLE)

class Vehicle(Device):
    """
    Base class for mobile entities like AGVs.
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], speed_mps: float, mqtt_client=None):
        super().__init__(env, id, position, "vehicle", mqtt_client)
        self.speed_mps = speed_mps

class BaseConveyor(Device, ABC):
    """
    Abstract base class for different types of conveyors.
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], transfer_time: float, line_id: str,interacting_points: list = [], topic_manager= None, mqtt_client=None):
        super().__init__(env, id, position, "conveyor", mqtt_client, interacting_points)

    @abstractmethod
    def push(self, product):
        """Add a product to the conveyor."""
        pass

    @abstractmethod
    def pop(self):
        """Remove a product from the conveyor."""
        pass

    @abstractmethod
    def is_full(self):
        """Check if the conveyor is full."""
        pass

    @abstractmethod
    def is_empty(self):
        """Check if the conveyor is empty."""
        pass

    @abstractmethod
    def get_buffer(self):
        """Get the internal buffer of the conveyor."""
        pass

    @abstractmethod
    def set_downstream_station(self, station):
        """Set the station that receives products from this conveyor."""
        pass