#!/usr/bin/env python3
"""
测试简化故障系统的功能
包括Station、Conveyor和AGV的故障注入和恢复
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import simpy
import pytest
from unittest.mock import Mock

from src.game_logic.fault_system import FaultSystem, FaultType
from src.simulation.entities.station import Station
from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from src.simulation.entities.agv import AGV
from src.simulation.entities.product import Product
from config.schemas import DeviceStatus


# ==================== Base Test Setup ====================
class BaseTestSetup:
    """基础测试设置类"""
    
    def create_mock_mqtt(self):
        """创建模拟的MQTT客户端"""
        mqtt_client = Mock()
        mqtt_client.is_connected.return_value = True
        return mqtt_client
    
    def create_fault_system(self, env, devices):
        """创建故障系统"""
        return FaultSystem(
            env=env,
            factory_devices=devices,
            mqtt_client=self.create_mock_mqtt()
        )


# ==================== Basic Fault System Tests ====================
class TestSimplifiedFaultSystem(BaseTestSetup):
    """测试简化故障系统基础功能"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        self.env = simpy.Environment()
        self.mqtt_client = self.create_mock_mqtt()
        
        # 创建测试设备
        self.factory_devices = {}
        
        # 创建测试Station
        self.station = Station(
            env=self.env,
            id="TestStation",
            position=(0, 0),
            processing_times={"P1": (5, 10)},
            mqtt_client=self.mqtt_client
        )
        self.factory_devices["TestStation"] = self.station
        
        # 创建测试Conveyor
        self.conveyor = Conveyor(
            env=self.env,
            id="TestConveyor",
            capacity=5,
            position=(10, 0),
            mqtt_client=self.mqtt_client
        )
        self.factory_devices["TestConveyor"] = self.conveyor
        
        # 创建测试AGV
        self.path_points = {
            "P1": (0, 0),
            "P2": (10, 10),
            "P3": (20, 20),
            "P10": (100, 100)  # Charging point
        }
        self.agv = AGV(
            env=self.env,
            id="TestAGV",
            position=(0, 0),
            path_points=self.path_points,
            speed_mps=2.0,
            mqtt_client=self.mqtt_client
        )
        self.factory_devices["TestAGV"] = self.agv
        
        # 创建故障系统
        self.fault_system = self.create_fault_system(self.env, self.factory_devices)
        # Link fault system to AGV for pending fault checks
        self.agv.fault_system = self.fault_system
    
    def test_station_fault_injection(self):
        """测试Station故障注入"""
        # 验证设备初始状态
        assert self.station.status == DeviceStatus.IDLE
        assert self.station.can_operate() == True
        
        # 手动注入Station故障
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=30.0
        )
        
        assert self.station.status == DeviceStatus.FAULT
        assert self.station.can_operate() == False
        assert self.fault_system.is_device_faulty("TestStation") == True
        
        # 验证故障信息
        fault_info = self.fault_system.get_fault_info("TestStation")
        assert fault_info is not None
        assert fault_info["fault_type"] == FaultType.STATION_FAULT.value
        assert fault_info["duration"] == 30.0
        
        # 运行仿真直到故障恢复
        self.env.run(until=35.0)
        
        # 验证设备已恢复
        assert self.station.status == DeviceStatus.IDLE
        assert self.station.can_operate() == True
        assert self.fault_system.is_device_faulty("TestStation") == False
    
    def test_conveyor_fault_injection(self):
        """测试Conveyor故障注入"""
        # 验证设备初始状态
        assert self.conveyor.status == DeviceStatus.WORKING  # Conveyor starts as WORKING
        assert self.conveyor.can_operate() == True
        
        # 手动注入Conveyor故障
        self.fault_system._inject_fault_now(
            device_id="TestConveyor",
            fault_type=FaultType.CONVEYOR_FAULT,
            duration=20.0
        )
        
        assert self.conveyor.status == DeviceStatus.FAULT
        assert self.conveyor.can_operate() == False
        assert self.fault_system.is_device_faulty("TestConveyor") == True
        
        # 验证故障信息
        fault_info = self.fault_system.get_fault_info("TestConveyor")
        assert fault_info is not None
        assert fault_info["fault_type"] == FaultType.CONVEYOR_FAULT.value
        assert fault_info["duration"] == 20.0
        
        # 运行仿真直到故障恢复
        self.env.run(until=25.0)
        
        # 验证设备已恢复 (故障恢复后Conveyor状态为IDLE)
        assert self.conveyor.status == DeviceStatus.WORKING
        assert self.conveyor.can_operate() == True
        assert self.fault_system.is_device_faulty("TestConveyor") == False
    
    def test_agv_fault_injection(self):
        """测试AGV故障注入"""
        # 验证设备初始状态
        assert self.agv.status == DeviceStatus.IDLE
        assert self.agv.can_operate() == True
        
        # 手动注入AGV故障
        self.fault_system._inject_fault_now(
            device_id="TestAGV",
            fault_type=FaultType.AGV_FAULT,
            duration=15.0
        )
        
        assert self.agv.status == DeviceStatus.FAULT
        assert self.agv.can_operate() == False
        assert self.fault_system.is_device_faulty("TestAGV") == True
        
        # 验证故障信息
        fault_info = self.fault_system.get_fault_info("TestAGV")
        assert fault_info is not None
        assert fault_info["fault_type"] == FaultType.AGV_FAULT.value
        assert fault_info["duration"] == 15.0
        
        # 运行仿真直到故障恢复
        self.env.run(until=20.0)
        
        # 验证设备已恢复
        assert self.agv.status == DeviceStatus.IDLE
        assert self.agv.can_operate() == True
        assert self.fault_system.is_device_faulty("TestAGV") == False
    
    def test_multiple_device_faults(self):
        """测试多设备同时故障"""
        # 同时注入多个设备故障
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=25.0
        )
        
        self.fault_system._inject_fault_now(
            device_id="TestConveyor",
            fault_type=FaultType.CONVEYOR_FAULT,
            duration=30.0
        )
        
        self.fault_system._inject_fault_now(
            device_id="TestAGV",
            fault_type=FaultType.AGV_FAULT,
            duration=20.0
        )
        
        # 验证所有设备都处于故障状态
        assert self.station.status == DeviceStatus.FAULT
        assert self.conveyor.status == DeviceStatus.FAULT
        assert self.agv.status == DeviceStatus.FAULT
        
        # 验证故障统计
        fault_stats = self.fault_system.get_fault_stats()
        assert fault_stats["active_faults"] == 3
        assert set(fault_stats["fault_devices"]) == {"TestStation", "TestConveyor", "TestAGV"}
        assert fault_stats["available_devices"] == 0
        assert fault_stats["total_devices"] == 3
        
        # 运行仿真，等待部分设备恢复
        self.env.run(until=22.0)
        
        # TestAGV应该已恢复（duration=20.0）
        assert self.agv.status == DeviceStatus.IDLE
        assert self.agv.can_operate() == True
        assert self.fault_system.is_device_faulty("TestAGV") == False
        
        # 其他设备仍有故障
        assert self.station.status == DeviceStatus.FAULT
        assert self.conveyor.status == DeviceStatus.FAULT
        
        # 运行仿真直到所有设备恢复
        self.env.run(until=35.0)
        
        # 验证所有设备都已恢复
        assert self.station.status == DeviceStatus.IDLE
        assert self.conveyor.status == DeviceStatus.WORKING
        assert self.agv.status == DeviceStatus.IDLE
        
        # 验证故障统计
        fault_stats = self.fault_system.get_fault_stats()
        assert fault_stats["active_faults"] == 0
        assert fault_stats["available_devices"] == 3
    
    def test_duplicate_fault_injection(self):
        """测试重复故障注入（应该被忽略）"""
        # 先注入一个故障
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=30.0
        )
        assert self.fault_system.is_device_faulty("TestStation")
        original_fault_info = self.fault_system.get_fault_info("TestStation")
        
        # 尝试再次注入故障到同一设备（应该被忽略）
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=20.0  # different duration
        )
        
        # 验证原故障仍然存在，并且没有被新故障覆盖
        assert self.fault_system.is_device_faulty("TestStation")
        new_fault_info = self.fault_system.get_fault_info("TestStation")
        assert new_fault_info["duration"] == 30.0  # check that duration is from the first fault
        assert new_fault_info["start_time"] == original_fault_info["start_time"]
        assert new_fault_info["fault_type"] == FaultType.STATION_FAULT.value
    
    def test_force_clear_fault(self):
        """测试强制清除故障"""
        # 注入故障
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=60.0
        )
        assert self.station.status == DeviceStatus.FAULT
        
        # 强制清除故障
        clear_success = self.fault_system.force_clear_fault("TestStation")
        assert clear_success == True
        assert self.station.status == DeviceStatus.IDLE
        assert self.fault_system.is_device_faulty("TestStation") == False
    
    def test_get_available_devices(self):
        """测试获取可用设备列表"""
        # 初始状态：所有设备都可用
        available = self.fault_system.get_available_devices()
        assert len(available) == 3
        assert set(available) == {"TestStation", "TestConveyor", "TestAGV"}
        
        # 注入故障到部分设备
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=30.0
        )
        
        self.fault_system._inject_fault_now(
            device_id="TestAGV",
            fault_type=FaultType.AGV_FAULT,
            duration=25.0
        )
        
        # 验证可用设备列表
        available = self.fault_system.get_available_devices()
        assert len(available) == 1
        assert available == ["TestConveyor"]
    
    def test_fault_symptom_handling(self):
        """测试故障症状处理"""
        # 注入故障
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=20.0
        )
        
        # 验证故障症状
        symptom = self.fault_system.get_device_symptom("TestStation")
        assert symptom == "Station Vibration"
        
        # 验证设备的故障症状属性
        if hasattr(self.station, 'fault_symptom'):
            assert self.station.fault_symptom == "Station Vibration"
        
        # 运行仿真直到故障恢复
        self.env.run(until=25.0)
        
        # 验证症状已清除
        symptom = self.fault_system.get_device_symptom("TestStation")
        assert symptom is None
        
        if hasattr(self.station, 'fault_symptom'):
            assert self.station.fault_symptom is None
    
    def test_timeout_handling(self):
        """测试超时处理逻辑（Broken Time）"""
        # 记录开始时间
        start_time = self.env.now
        
        # 注入具有特定持续时间的故障
        duration = 40.0
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=duration
        )
        
        # 验证故障信息中的剩余时间
        fault_info = self.fault_system.get_fault_info("TestStation")
        assert fault_info is not None
        assert fault_info["remaining_time"] == duration
        
        # 推进仿真时间
        self.env.run(until=15.0)
        
        # 验证剩余时间减少
        fault_info = self.fault_system.get_fault_info("TestStation")
        assert fault_info is not None
        assert fault_info["remaining_time"] == duration - 15.0
        
        # 验证设备仍处于故障状态
        assert self.station.status == DeviceStatus.FAULT
        assert self.fault_system.is_device_faulty("TestStation") == True
        
        # 运行到超时时间
        self.env.run(until=start_time + duration + 1.0)
        
        # 验证设备已自动恢复
        assert self.station.status == DeviceStatus.IDLE
        assert self.fault_system.is_device_faulty("TestStation") == False
    
    def test_all_fault_info(self):
        """测试获取所有故障信息"""
        # 注入多个故障
        self.fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=30.0
        )
        
        self.fault_system._inject_fault_now(
            device_id="TestConveyor",
            fault_type=FaultType.CONVEYOR_FAULT,
            duration=25.0
        )
        
        # 获取所有故障信息
        all_faults = self.fault_system.get_all_fault_info()
        assert len(all_faults) == 2
        
        # 验证故障信息内容
        fault_devices = [fault["device_id"] for fault in all_faults]
        assert set(fault_devices) == {"TestStation", "TestConveyor"}
        
        # 验证故障类型
        fault_types = [fault["fault_type"] for fault in all_faults]
        assert FaultType.STATION_FAULT.value in fault_types
        assert FaultType.CONVEYOR_FAULT.value in fault_types


# ==================== Station Fault Tests ====================
class TestStationFaultScenarios(BaseTestSetup):
    """测试Station在各种故障场景下的行为"""
    
    def create_station_with_downstream(self, env, processing_time=(5, 5), buffer_size=1):
        """创建带有下游传送带的Station"""
        mqtt_client = self.create_mock_mqtt()
        
        # 创建下游传送带
        downstream_conveyor = Conveyor(
            env=env,
            id="DownstreamConveyor",
            capacity=5,
            position=(10, 0),
            mqtt_client=mqtt_client
        )
        
        # 创建Station
        station = Station(
            env=env,
            id="TestStation",
            position=(0, 0),
            buffer_size=buffer_size,
            processing_times={"P1": processing_time},
            downstream_conveyor=downstream_conveyor,
            mqtt_client=mqtt_client
        )
        
        return station, downstream_conveyor
    
    def test_station_fault_during_wait_for_product(self):
        """测试Station在等待产品时发生故障"""
        env = simpy.Environment()
        station, downstream = self.create_station_with_downstream(env)
        fault_system = self.create_fault_system(env, {"TestStation": station})
        
        # 让Station运行一段时间（此时buffer为空）
        env.run(until=2.0)
        assert station.status == DeviceStatus.IDLE
        
        # 注入故障
        fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=5.0
        )
        
        # 添加产品
        product = Product(product_type="P1", order_id="TestOrder")
        def add_product():
            yield station.buffer.put(product)
        env.process(add_product())
        
        env.run(until=3.0)
        
        # 验证产品在buffer中，Station无法处理
        assert len(station.buffer.items) == 1
        assert station.status == DeviceStatus.FAULT
        
        # 等待故障恢复
        env.run(until=8.0)
        
        # Station应该开始处理产品
        env.run(until=15.0)
        
        # 验证产品被处理并转移
        assert len(station.buffer.items) == 0
        assert len(downstream.buffer.items) == 1
    
    def test_station_fault_during_timeout(self):
        """测试Station在timeout期间发生故障，产品应留在buffer"""
        env = simpy.Environment()
        station, downstream = self.create_station_with_downstream(env, processing_time=(10, 10))
        fault_system = self.create_fault_system(env, {"TestStation": station, "DownstreamConveyor": downstream})
        
        # 创建产品并放入buffer
        product = Product(product_type="P1", order_id="TestOrder")
        def add_product():
            yield station.buffer.put(product)
        env.process(add_product())
        env.run(until=0.1)
        
        # 验证产品在buffer中
        assert len(station.buffer.items) == 1
        assert product in station.buffer.items
        
        # 等待Station开始处理（进入timeout）
        env.run(until=2.0)
        assert station.status == DeviceStatus.PROCESSING
        
        # 在timeout期间注入故障（处理时间10秒，在第2秒注入）
        fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=5.0
        )
        
        # 验证Station进入故障状态
        assert station.status == DeviceStatus.FAULT
        
        # 运行一段时间
        env.run(until=3.0)
        
        # 验证产品仍在buffer中（因为在timeout期间被中断）
        assert len(station.buffer.items) == 1
        assert product in station.buffer.items
        assert len(downstream.buffer.items) == 0
        
        # 等待故障恢复
        env.run(until=8.0)
        # Station可能立即重新开始处理产品，所以状态可能是PROCESSING或IDLE
        assert station.can_operate() == True
        assert fault_system.is_device_faulty("TestStation") == False
        
        # 继续运行，让Station重新处理产品
        env.run(until=20.0)
        
        # 验证产品最终被处理并转移到下游
        assert len(station.buffer.items) == 0
        assert len(downstream.buffer.items) == 1
        assert product in downstream.buffer.items
    
    def test_station_fault_after_buffer_get(self):
        """测试Station在buffer.get()后发生故障，产品应继续流转"""
        env = simpy.Environment()
        station, downstream = self.create_station_with_downstream(env, processing_time=(5, 5))
        fault_system = self.create_fault_system(env, {"TestStation": station, "DownstreamConveyor": downstream})
        
        # 创建产品并放入buffer
        product = Product(product_type="P1", order_id="TestOrder")
        def add_product():
            yield station.buffer.put(product)
        env.process(add_product())
        env.run(until=0.1)
        
        # 验证初始状态
        assert len(station.buffer.items) == 1
        assert product in station.buffer.items
        
        # 运行足够长时间，让Station完成timeout并执行buffer.get()
        env.run(until=6.0)  # 处理时间5秒 + 1秒余量
        
        # 此时产品应该已经从buffer取出，正在或已经完成处理
        # 在这个时刻注入故障
        fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=5.0
        )
        
        # 立即检查状态
        env.run(until=6.1)
        
        # 验证产品不在buffer中（已被取出）
        assert len(station.buffer.items) == 0
        assert product not in station.buffer.items
        
        # 验证产品应该继续流转到下游
        env.run(until=7.0)
        assert len(downstream.buffer.items) == 1
        assert product in downstream.buffer.items
    
    def test_station_multiple_products_with_fault(self):
        """测试Station处理多个产品时的故障场景"""
        env = simpy.Environment()
        station, downstream = self.create_station_with_downstream(env, processing_time=(5, 5), buffer_size=3)
        fault_system = self.create_fault_system(env, {"TestStation": station, "DownstreamConveyor": downstream})
        
        # 创建3个产品并放入buffer
        products = []
        for i in range(3):
            product = Product(product_type="P1", order_id=f"Order{i}")
            products.append(product)
            def add_product(p):
                yield station.buffer.put(p)
            env.process(add_product(product))
        
        env.run(until=0.1)
        assert len(station.buffer.items) == 3
        
        # 让Station开始处理第一个产品
        env.run(until=2.0)
        assert station.status == DeviceStatus.PROCESSING
        
        # 在处理第一个产品时注入故障
        fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=10.0
        )
        
        # 验证故障状态
        assert station.status == DeviceStatus.FAULT
        
        # 运行一段时间
        env.run(until=5.0)
        
        # 验证buffer中仍有3个产品（第一个产品处理被中断，留在buffer）
        assert len(station.buffer.items) == 3
        assert len(downstream.buffer.items) == 0
        
        # 等待故障恢复
        env.run(until=13.0)
        assert station.can_operate() == True
        
        # 继续运行，让Station处理所有产品
        env.run(until=30.0)
        
        # 验证所有产品都被处理并转移到下游
        assert len(station.buffer.items) == 0
        assert len(downstream.buffer.items) == 3
    
    def test_station_fault_with_downstream_blocked(self):
        """测试下游阻塞时Station发生故障的场景"""
        env = simpy.Environment()
        mqtt_client = self.create_mock_mqtt()
        
        # 创建容量为1的下游传送带（容易阻塞）
        downstream = Conveyor(
            env=env,
            id="DownstreamConveyor",
            capacity=1,
            position=(10, 0),
            mqtt_client=mqtt_client
        )
        
        # 先填满下游传送带
        blocker_product = Product(product_type="P1", order_id="Blocker")
        def block_downstream():
            yield downstream.push(blocker_product)
        env.process(block_downstream())
        env.run(until=0.1)
        
        # 创建Station
        station = Station(
            env=env,
            id="TestStation",
            position=(0, 0),
            processing_times={"P1": (3, 3)},  # 3秒处理时间
            downstream_conveyor=downstream,
            mqtt_client=mqtt_client
        )
        
        fault_system = self.create_fault_system(env, {"TestStation": station, "DownstreamConveyor": downstream})
        
        # 创建产品并放入Station的buffer
        product = Product(product_type="P1", order_id="TestOrder")
        def add_product():
            yield station.buffer.put(product)
        env.process(add_product())
        env.run(until=0.2)
        
        # 让Station处理产品
        env.run(until=4.0)  # 处理完成，尝试转移到下游
        
        # 此时Station应该在INTERACTING状态（等待下游空间）
        assert station.status == DeviceStatus.INTERACTING
        assert len(station.buffer.items) == 0  # 产品已取出
        
        # 在等待下游期间注入故障
        fault_system._inject_fault_now(
            device_id="TestStation",
            fault_type=FaultType.STATION_FAULT,
            duration=5.0
        )
        
        # 验证故障状态
        assert station.status == DeviceStatus.FAULT
        
        # 清除下游阻塞
        def clear_downstream():
            yield downstream.pop()
        env.process(clear_downstream())
        env.run(until=5.0)
        
        # 等待故障恢复
        env.run(until=10.0)
        
        # 验证产品最终被转移到下游
        assert len(downstream.buffer.items) == 1
        assert product in downstream.buffer.items


# ==================== Conveyor Fault Tests ====================
class TestConveyorFaultScenarios(BaseTestSetup):
    """测试Conveyor在各种故障场景下的行为"""
    
    def test_conveyor_basic_fault(self):
        """测试Conveyor基本故障场景"""
        env = simpy.Environment()
        mqtt_client = self.create_mock_mqtt()
        
        # 创建Conveyor
        conveyor = Conveyor(
            env=env,
            id="TestConveyor",
            capacity=3,
            position=(0, 0),
            mqtt_client=mqtt_client
        )
        
        fault_system = self.create_fault_system(env, {"TestConveyor": conveyor})
        
        # 创建产品
        product = Product(product_type="P1", order_id="TestOrder")
        
        # 添加产品到Conveyor
        def add_product():
            yield conveyor.push(product)
        env.process(add_product())
        
        # 注入故障
        fault_system._inject_fault_now(
            device_id="TestConveyor",
            fault_type=FaultType.CONVEYOR_FAULT,
            duration=15.0
        )
        
        # 运行仿真
        env.run(until=10.0)
        
        # 验证Conveyor故障状态
        assert fault_system.is_device_faulty("TestConveyor") == True
        
        # 等待故障恢复
        env.run(until=20.0)
        
        # 验证Conveyor恢复正常
        assert fault_system.is_device_faulty("TestConveyor") == False
    
    # TODO: 添加更多Conveyor相关的测试场景
    # - 测试TripleBufferConveyor的故障处理
    # - 测试Conveyor在传输过程中的故障
    # - 测试多个产品在Conveyor上的故障场景


# ==================== AGV Fault Tests ====================
class TestAGVFaultScenarios(BaseTestSetup):
    """测试AGV在各种故障场景下的行为"""
    
    def setup_method(self):
        """设置AGV测试环境"""
        self.env = simpy.Environment()
        self.mqtt_client = self.create_mock_mqtt()
        
        self.path_points = {
            "P1": (0, 0),
            "P2": (10, 10),
            "P3": (20, 20),
            "P10": (100, 100)  # Charging point
        }
        
        self.agv = AGV(
            env=self.env,
            id="TestAGV",
            position=(0, 0),
            path_points=self.path_points,
            speed_mps=2.0,
            mqtt_client=self.mqtt_client
        )
        
        self.fault_system = self.create_fault_system(self.env, {"TestAGV": self.agv})
        self.agv.fault_system = self.fault_system
    
    def test_agv_pending_fault_injection_while_moving(self):
        """测试AGV在移动时接收到故障注入，故障应在移动结束后触发"""
        # 让AGV开始移动
        self.env.process(self.agv.move_to("P2"))
        
        # 运行一小段时间，确保AGV处于MOVING状态
        self.env.run(until=1.0)
        assert self.agv.status == DeviceStatus.MOVING
        
        # 在AGV移动时注入故障
        self.fault_system.inject_random_fault(target_device="TestAGV", fault_type=FaultType.AGV_FAULT)
        
        # 验证故障已被挂起，AGV仍在移动
        assert "TestAGV" in self.fault_system.pending_agv_faults
        assert not self.fault_system.is_device_faulty("TestAGV")
        assert self.agv.status == DeviceStatus.MOVING
        
        # 运行直到AGV完成移动 (travel_time约为11.9s)
        self.env.run(until=13.0)
        
        # 验证移动完成后，挂起的故障被触发
        assert "TestAGV" not in self.fault_system.pending_agv_faults
        assert self.fault_system.is_device_faulty("TestAGV")
        assert self.agv.status == DeviceStatus.FAULT
        
        # 验证AGV无法执行新命令
        self.env.process(self.agv.move_to("P3"))
        self.env.run(until=14.0)
        # AGV should still be at P2 and in FAULT state
        assert self.agv.current_point == "P2"
        assert self.agv.status == DeviceStatus.FAULT
    
    def test_agv_fault_injection_while_charging(self):
        """测试AGV在充电时注入故障"""
        # 让AGV移动到充电点并开始充电
        self.agv.battery_level = 20.0
        self.env.process(self.agv.voluntary_charge(100.0))
        
        # 运行足够长的时间，确保AGV到达充电点并开始充电 (travel_time约为11.9s)
        self.env.run(until=12.5)
        assert self.agv.status == DeviceStatus.CHARGING
        
        # 在AGV充电时注入故障
        self.fault_system._inject_fault_now(
            device_id="TestAGV",
            fault_type=FaultType.AGV_FAULT,
            duration=15.0
        )
        
        # 验证充电过程被中断，AGV进入故障状态
        assert self.agv.status == DeviceStatus.FAULT
        assert self.fault_system.is_device_faulty("TestAGV")
        
        # 运行直到故障自动恢复之后
        self.env.run(until=28.0)  # 12.5 + 15 + 0.5
        
        # 验证AGV恢复到IDLE状态
        assert self.agv.status == DeviceStatus.IDLE
        assert not self.fault_system.is_device_faulty("TestAGV")
        
        # 验证AGV可以接收新指令
        self.env.process(self.agv.move_to("P3"))
        self.env.run(until=50.0)
        assert self.agv.current_point == "P3"
    
    def test_command_conflict_after_fault(self):
        """测试设备故障后立即接收新指令的行为"""
        # 注入AGV故障
        self.fault_system._inject_fault_now(
            device_id="TestAGV",
            fault_type=FaultType.AGV_FAULT,
            duration=30.0
        )
        self.env.run(until=1.0)
        assert self.agv.status == DeviceStatus.FAULT
        
        # 尝试移动故障的AGV
        self.env.process(self.agv.move_to("P3"))
        self.env.run(until=2.0)
        
        # AGV不应该移动
        assert self.agv.current_point == "P1"
        assert self.agv.status == DeviceStatus.FAULT
        
        # 清除故障
        self.fault_system.force_clear_fault("TestAGV")
        self.env.run(until=3.0)
        assert self.agv.status == DeviceStatus.IDLE
        
        # 再次尝试移动
        self.env.process(self.agv.move_to("P2"))
        # travel_time约为11.9s
        self.env.run(until=16.0)
        
        # AGV现在应该已经移动
        assert self.agv.current_point == "P2"
        assert self.agv.status == DeviceStatus.IDLE
    
    def test_pending_fault_is_not_overwritten(self):
        """测试挂起的故障不会被新的挂起故障覆盖"""
        # 让AGV开始移动
        self.env.process(self.agv.move_to("P2"))
        self.env.run(until=1.0)
        assert self.agv.status == DeviceStatus.MOVING
        
        # 注入第一个挂起的故障
        self.fault_system.inject_random_fault(target_device="TestAGV", fault_type=FaultType.AGV_FAULT)
        assert "TestAGV" in self.fault_system.pending_agv_faults
        first_fault_type = self.fault_system.pending_agv_faults["TestAGV"]
        
        # 注入第二个挂起的故障
        self.fault_system.inject_random_fault(target_device="TestAGV", fault_type=FaultType.AGV_FAULT)
        
        # 验证第一个故障没有被覆盖
        assert self.fault_system.pending_agv_faults["TestAGV"] == first_fault_type
        
        # 运行直到AGV完成移动
        self.env.run(until=13.0)
        
        # 验证故障已触发
        assert self.agv.status == DeviceStatus.FAULT
        assert self.fault_system.is_device_faulty("TestAGV")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])