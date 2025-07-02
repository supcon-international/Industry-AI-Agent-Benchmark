#!/usr/bin/env python3
"""
工厂仿真基础测试
验证所有核心系统功能
"""

import sys
import os
import time
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
from src.utils.mqtt_client import MQTTClient
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT

def test_basic_factory_initialization():
    """测试基础工厂初始化"""
    print("🏭 测试1: 基础工厂初始化")
    print("-" * 50)
    
    try:
        mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 验证设备数量
        assert len(factory.stations) == 4, f"预期4个Station，实际{len(factory.stations)}"
        assert len(factory.agvs) == 2, f"预期2个AGV，实际{len(factory.agvs)}"
        assert len(factory.path_points) == 10, f"预期10个路径点，实际{len(factory.path_points)}"
        
        print("✅ 工厂初始化成功")
        print(f"   - Stations: {list(factory.stations.keys())}")
        print(f"   - AGVs: {list(factory.agvs.keys())}")
        print(f"   - Path points: {len(factory.path_points)}")
        return True
        
    except Exception as e:
        print(f"❌ 工厂初始化失败: {e}")
        return False

def test_order_generation():
    """测试订单生成系统"""
    print("\n📋 测试2: 订单生成系统")
    print("-" * 50)
    
    try:
        mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 运行30秒查看订单生成
        print("🚀 运行30秒观察订单生成...")
        factory.run(until=30)
        
        # 检查订单统计
        stats = factory.kpi_calculator.stats
        print(f"✅ 订单生成测试完成")
        print(f"   - 总订单数: {stats.total_orders}")
        print(f"   - 活跃订单数: {len(factory.kpi_calculator.active_orders)}")
        
        # 显示订单详情
        for order_id, order in list(factory.kpi_calculator.active_orders.items())[:3]:
            print(f"   - {order_id}: {order.items_total}件订单")
            
        return stats.total_orders > 0
        
    except Exception as e:
        print(f"❌ 订单生成测试失败: {e}")
        return False

def test_fault_injection():
    """测试故障注入系统"""
    print("\n⚠️ 测试3: 故障注入系统")
    print("-" * 50)
    
    try:
        mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 手动注入一个故障进行测试
        print("💥 手动注入故障进行测试...")
        factory.fault_system.inject_random_fault("StationA", None)
        
        # 检查故障状态
        fault_stats = factory.fault_system.get_fault_stats()
        print(f"✅ 故障注入测试完成")
        print(f"   - 活跃故障数: {fault_stats['active_faults']}")
        print(f"   - 故障设备: {fault_stats['fault_devices']}")
        
        # 显示故障详情
        for device_id, fault in factory.fault_system.active_faults.items():
            print(f"   - {device_id}: {fault.symptom}")
            print(f"     隐藏原因: {fault.actual_root_cause}")
            print(f"     正确修复命令: {fault.correct_repair_command}")
            
        return fault_stats['active_faults'] > 0
        
    except Exception as e:
        print(f"❌ 故障注入测试失败: {e}")
        return False

def test_command_handling():
    """测试命令处理系统"""
    print("\n🎮 测试4: 命令处理系统")
    print("-" * 50)
    
    try:
        mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 先注入一个故障
        factory.fault_system.inject_random_fault("StationB", None)
        fault = list(factory.fault_system.active_faults.values())[0]
        
        print(f"💉 注入故障: {fault.symptom}")
        print(f"🔍 正确诊断应该是: {fault.correct_repair_command}")
        
        # 测试正确的维修命令
        print("\n🔧 测试正确的维修命令...")
        result = factory.fault_system.handle_maintenance_request(
            "StationB", fault.correct_repair_command
        )
        
        print(f"✅ 命令处理测试完成")
        print(f"   - 诊断正确: {result.is_correct}")
        print(f"   - 修复时间: {result.repair_time:.1f}秒")
        print(f"   - 可跳过等待: {result.can_skip}")
        
        # 测试错误的维修命令
        factory.fault_system.inject_random_fault("StationC", None)
        print("\n❌ 测试错误的维修命令...")
        result2 = factory.fault_system.handle_maintenance_request(
            "StationC", "wrong_command"
        )
        
        print(f"   - 诊断正确: {result2.is_correct}")
        print(f"   - 惩罚修复时间: {result2.repair_time:.1f}秒")
        print(f"   - 受影响设备: {len(result2.affected_devices)}个")
        
        return True
        
    except Exception as e:
        print(f"❌ 命令处理测试失败: {e}")
        return False

def test_kpi_calculation():
    """测试KPI计算系统"""
    print("\n📊 测试5: KPI计算系统")
    print("-" * 50)
    
    try:
        mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 运行一段时间生成数据
        print("📈 运行60秒生成KPI数据...")
        factory.run(until=60)
        
        # 获取KPI数据
        kpi_data = factory.kpi_calculator.get_final_score()
        
        print(f"✅ KPI计算测试完成")
        print(f"   - 生产效率得分: {kpi_data['efficiency_score']:.2f}")
        print(f"   - 成本控制得分: {kpi_data['cost_score']:.2f}")
        print(f"   - 鲁棒性得分: {kpi_data['robustness_score']:.2f}")
        print(f"   - 总分: {kpi_data['total_score']:.2f}")
        
        # 显示详细指标
        stats = factory.kpi_calculator.stats
        print(f"\n📋 详细统计:")
        print(f"   - 总订单: {stats.total_orders}")
        print(f"   - 完成订单: {stats.completed_orders}")
        print(f"   - 活跃订单: {len(factory.kpi_calculator.active_orders)}")
        print(f"   - 总成本: ¥{stats.material_costs + stats.energy_costs + stats.maintenance_costs + stats.scrap_costs:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ KPI计算测试失败: {e}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("🧪 SUPCON 工厂仿真系统 - 完整测试套件")
    print("=" * 60)
    
    tests = [
        test_basic_factory_initialization,
        test_order_generation,
        test_fault_injection,
        test_command_handling,
        test_kpi_calculation
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            time.sleep(0.5)  # 短暂延迟，便于观察
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    print("\n" + "=" * 60)
    print(f"🏆 测试完成: {passed}/{total} 通过")
    
    if passed == total:
        print("✅ 所有测试通过！系统运行正常！")
    else:
        print("⚠️ 有测试失败，请检查系统配置")
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1) 