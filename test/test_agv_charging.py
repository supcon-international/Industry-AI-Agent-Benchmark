#!/usr/bin/env python3
"""
AGV充电机制测试脚本
测试AGV的电量消耗、主动充电、被动充电、告警等功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simpy
from src.simulation.entities.agv import AGV
from src.game_logic.fault_system import FaultSystem
from src.utils.mqtt_client import MQTTClient

def test_battery_consumption():
    """测试电量消耗机制"""
    print("=== 测试 AGV 电量消耗机制 ===")
    
    env = simpy.Environment()
    
    # 创建AGV（较低的阈值便于测试）
    agv = AGV(
        env=env,
        id="AGV_TEST",
        position=(0, 0),
        speed_mps=2.0,
        path_points={
            "LP0": (0, 0),
            "LP1": (20, 20),
            "LC1": (10, 10)
        },
        low_battery_threshold=20.0,  # 提高阈值便于测试
        charging_point=(10, 10),
        battery_consumption_per_meter=2.0,  # 增加消耗便于测试
        battery_consumption_per_action=5.0
    )
    
    def test_process():
        print(f"[{env.now:.2f}] 初始电量: {agv.battery_level:.1f}%")
        
        # 测试移动消耗
        print("\n--- 测试移动电量消耗 ---")
        yield env.process(agv.move_to("LP1"))  # 移动约28.3米，消耗约56.6%
        print(f"[{env.now:.2f}] 移动后电量: {agv.battery_level:.1f}%")
        
        # 测试装卸消耗
        print("\n--- 测试装卸操作电量消耗 ---")
        from src.simulation.entities.product import Product
        product = Product("P1", "order_001")
        
        yield env.process(agv.load_product(product))
        print(f"[{env.now:.2f}] 装载后电量: {agv.battery_level:.1f}%")
        
        yield env.process(agv.unload_product("prod_001"))
        print(f"[{env.now:.2f}] 卸载后电量: {agv.battery_level:.1f}%")
        
        # 测试电量预估
        print("\n--- 测试电量预估功能 ---")
        can_complete = agv.can_complete_task(estimated_distance=50.0, estimated_actions=2)
        print(f"是否能完成50m移动+2次操作: {can_complete}")
        
        battery_status = agv.get_battery_status()
        print(f"电池状态: {battery_status}")
        
    env.process(test_process())
    env.run(until=200)
    print("电量消耗测试完成\n")

def test_voluntary_charging():
    """测试主动充电机制"""
    print("=== 测试主动充电机制 ===")
    
    env = simpy.Environment()
    
    agv = AGV(
        env=env,
        id="AGV_CHARGE_TEST",
        position=(50, 50),
        speed_mps=5.0,  # 加快移动速度便于测试
        low_battery_threshold=5.0,
        charging_point=(10, 10),
        charging_speed=10.0,  # 加快充电速度便于测试
        path_points={
            "LP0": (50, 50),
            "LP1": (10, 10),
            "LC1": (10, 10)
        }
    )
    
    # 手动设置较低电量
    agv.battery_level = 30.0
    
    def test_process():
        print(f"[{env.now:.2f}] 开始测试，当前电量: {agv.battery_level:.1f}%")
        
        # 测试主动充电
        yield env.process(agv.voluntary_charge(target_level=80.0))
        
        print(f"[{env.now:.2f}] 充电完成，当前电量: {agv.battery_level:.1f}%")
        
        charging_stats = agv.get_charging_stats()
        print(f"充电统计: {charging_stats}")
        
    env.process(test_process())
    env.run(until=200)
    print("主动充电测试完成\n")

def test_emergency_charging():
    """测试被动/紧急充电机制"""
    print("=== 测试被动/紧急充电机制 ===")
    
    env = simpy.Environment()
    
    # 创建模拟的故障系统（用于告警测试）
    mock_fault_system = type('MockFaultSystem', (), {
        'report_battery_low': lambda self, agv_id, level: print(f"[FAULT_SYSTEM] {agv_id} 电量告警: {level:.1f}%")
    })()
    
    agv = AGV(
        env=env,
        id="AGV_EMERGENCY_TEST",
        position=(80, 80),
        speed_mps=2.0,
        low_battery_threshold=5.0,
        charging_point=(10, 10),
        path_points={
            "LP0": (0, 0),
            "LP1": (80, 80),
            "LC1": (10, 10)
        }
    )
    
    # 手动设置低电量
    agv.battery_level = 6.0
    
    def test_process():
        print(f"[{env.now:.2f}] 开始测试，当前电量: {agv.battery_level:.1f}%")
        
        # 尝试移动，触发紧急充电
        print("\n--- 尝试长距离移动触发紧急充电 ---")
        yield env.process(agv.move_to("LP0"))  # 长距离移动
        
        print(f"[{env.now:.2f}] 处理完成，当前电量: {agv.battery_level:.1f}%")
        
        charging_stats = agv.get_charging_stats()
        print(f"充电统计: {charging_stats}")
        
    env.process(test_process())
    env.run(until=300)
    print("紧急充电测试完成\n")

def test_low_battery_operations():
    """测试低电量时的操作限制"""
    print("=== 测试低电量操作限制 ===")
    
    env = simpy.Environment()
    
    agv = AGV(
        env=env,
        id="AGV_LOW_BATTERY_TEST",
        position=(20, 20),
        speed_mps=2.0,
        low_battery_threshold=10.0,
        path_points={
            "LP0": (20, 20),
            "LP1": (0, 0),
            "LC1": (10, 10)
        }
    )
    
    # 设置低电量
    agv.battery_level = 3.0  # 低于阈值
    
    def test_process():
        print(f"[{env.now:.2f}] 当前电量: {agv.battery_level:.1f}% (低于阈值)")
        
        # 测试装载操作
        from src.simulation.entities.product import Product
        product = Product("P1", "order_001")
        
        result = yield env.process(agv.load_product(product))
        print(f"低电量装载结果: {result}")
        
        # 测试卸载操作
        result = yield env.process(agv.unload_product("test_product"))
        print(f"低电量卸载结果: {result}")
        
        # 测试load_from/unload_to操作
        from src.simulation.entities.station import Station
        
        mock_station = type('MockStation', (), {
            'id': 'MockStation',
            'buffer': type('MockBuffer', (), {'items': [product]})()
        })()
        
        success, feedback, prod = yield env.process(agv.load_from(mock_station))
        print(f"低电量取货结果: {success}, 反馈: {feedback}")
        
    env.process(test_process())
    env.run(until=100)
    print("低电量操作限制测试完成\n")

def test_battery_status_monitoring():
    """测试电池状态监控"""
    print("=== 测试电池状态监控 ===")
    
    env = simpy.Environment()
    
    agv = AGV(
        env=env,
        id="AGV_MONITOR_TEST",
        position=(0, 0),
        speed_mps=2.0,
        low_battery_threshold=15.0,
        path_points={
            "LP0": (0, 0),
            "LP1": (20, 20),
            "LC1": (10, 10)
        }
    )
    
    def test_process():
        # 测试各种电量状态
        test_levels = [100.0, 50.0, 20.0, 10.0, 3.0]
        
        for level in test_levels:
            agv.battery_level = level
            agv._specific_attributes["battery_level"] = level
            
            print(f"\n--- 电量 {level}% 状态检查 ---")
            print(f"是否低电量: {agv.is_battery_low()}")
            print(f"能否完成30m移动: {agv.can_complete_task(30.0, 1)}")
            
            status = agv.get_battery_status()
            print(f"电池状态: {status}")
            
            yield env.timeout(1)  # 小延时
        
    env.process(test_process())
    env.run(until=20)
    print("电池状态监控测试完成\n")

if __name__ == "__main__":
    print("开始 AGV 充电机制完整测试\n")
    
    try:
        test_battery_consumption()
        test_voluntary_charging()
        test_emergency_charging()
        test_low_battery_operations()
        test_battery_status_monitoring()
        
        print("🎉 所有 AGV 充电机制测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc() 