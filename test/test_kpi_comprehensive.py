#!/usr/bin/env python3
"""
综合测试KPI系统功能
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.factory import Factory
from src.utils.config_loader import load_factory_config
from src.utils.mqtt_client import MQTTClient
from config.topics import KPI_UPDATE_TOPIC
from config.schemas import NewOrder, OrderItem, OrderPriority
import simpy
import json
import time
from datetime import datetime

class KPITestCollector:
    """收集KPI更新用于验证"""
    def __init__(self):
        self.kpi_updates = []
        self.last_update = None
        
    def on_kpi_update(self, client, userdata, message):
        """处理KPI更新消息"""
        try:
            payload = json.loads(message.payload.decode())
            self.kpi_updates.append(payload)
            self.last_update = payload
            print(f"\n📊 收到KPI更新 #{len(self.kpi_updates)}:")
            print(f"  - 订单完成率: {payload.get('order_completion_rate', 0):.1f}%")
            print(f"  - 生产周期效率: {payload.get('average_production_cycle', 1):.2f}")
            print(f"  - 设备利用率: {payload.get('device_utilization', 0):.1f}%")
            print(f"  - AGV充电策略效率: {payload.get('charge_strategy_efficiency', 0):.1f}%")
            print(f"  - 总生产成本: {payload.get('total_production_cost', 0):.2f}")
        except Exception as e:
            print(f"❌ 解析KPI更新失败: {e}")

def test_kpi_event_driven():
    """测试事件驱动的KPI更新"""
    print("\n" + "="*60)
    print("测试1: 事件驱动KPI更新")
    print("="*60)
    
    # 创建MQTT客户端和KPI收集器
    mqtt_client = MQTTClient(
        host="localhost",
        port=1883,
        client_id=f"kpi_test_{int(time.time())}"
    )
    mqtt_client.connect()
    
    collector = KPITestCollector()
    mqtt_client.client.on_message = collector.on_kpi_update
    mqtt_client.client.subscribe(KPI_UPDATE_TOPIC)
    
    # 创建工厂
    config = load_factory_config()
    factory = Factory(config, mqtt_client=mqtt_client, no_faults=True)
    
    print("\n✅ 初始化完成，开始测试事件驱动更新...")
    
    # 让MQTT有时间处理消息
    mqtt_client.client.loop_start()
    time.sleep(1)
    
    # 记录初始更新数
    initial_updates = len(collector.kpi_updates)
    print(f"初始KPI更新数: {initial_updates}")
    
    # 场景1: 运行10秒，不应有新的KPI更新（无事件）
    print("\n场景1: 静默运行10秒...")
    factory.run(until=10)
    time.sleep(0.5)
    
    if len(collector.kpi_updates) == initial_updates:
        print("✅ 正确：无事件时没有KPI更新")
    else:
        print(f"❌ 错误：无事件时产生了 {len(collector.kpi_updates) - initial_updates} 个更新")
    
    # 场景2: 手动触发订单事件
    print("\n场景2: 添加新订单...")
    order = NewOrder(
        order_id="test_order_1",
        created_at=factory.env.now,
        items=[OrderItem(product_type="P1", quantity=2)],
        priority=OrderPriority.HIGH,
        deadline=factory.env.now + 240
    )
    factory.kpi_calculator.register_new_order(order)
    time.sleep(0.5)
    
    if len(collector.kpi_updates) > initial_updates:
        print(f"✅ 正确：新订单触发了KPI更新（共 {len(collector.kpi_updates)} 次）")
    else:
        print("❌ 错误：新订单未触发KPI更新")
    
    # 场景3: 完成产品
    print("\n场景3: 完成产品...")
    updates_before_complete = len(collector.kpi_updates)
    factory.kpi_calculator.complete_order_item("test_order_1", "P1", passed_quality=True)
    time.sleep(0.5)
    
    if len(collector.kpi_updates) > updates_before_complete:
        print(f"✅ 正确：产品完成触发了KPI更新（共 {len(collector.kpi_updates)} 次）")
    else:
        print("❌ 错误：产品完成未触发KPI更新")
    
    # 场景4: AGV事件
    print("\n场景4: AGV充电事件...")
    updates_before_agv = len(collector.kpi_updates)
    factory.kpi_calculator.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
    time.sleep(0.5)
    
    if len(collector.kpi_updates) > updates_before_agv:
        print(f"✅ 正确：AGV充电触发了KPI更新（共 {len(collector.kpi_updates)} 次）")
    else:
        print("❌ 错误：AGV充电未触发KPI更新")
    
    mqtt_client.client.loop_stop()
    mqtt_client.disconnect()
    
    return collector.kpi_updates

def test_kpi_formulas():
    """测试KPI计算公式的准确性"""
    print("\n" + "="*60)
    print("测试2: KPI计算公式验证")
    print("="*60)
    
    config = load_factory_config()
    factory = Factory(config, mqtt_client=None, no_faults=True)
    kpi = factory.kpi_calculator
    
    # 测试场景：创建多个订单并部分完成
    print("\n创建测试数据...")
    
    # 订单1：按时完成
    order1 = NewOrder(
        order_id="order_1",
        created_at=0,
        items=[OrderItem(product_type="P1", quantity=2)],
        priority=OrderPriority.LOW,
        deadline=500  # 充足的时间
    )
    kpi.register_new_order(order1)
    
    # 订单2：延迟完成
    order2 = NewOrder(
        order_id="order_2", 
        created_at=0,
        items=[OrderItem(product_type="P2", quantity=1)],
        priority=OrderPriority.HIGH,
        deadline=100  # 很短的期限
    )
    kpi.register_new_order(order2)
    
    # 订单3：未完成
    order3 = NewOrder(
        order_id="order_3",
        created_at=0,
        items=[OrderItem(product_type="P3", quantity=1)],
        priority=OrderPriority.MEDIUM,
        deadline=400
    )
    kpi.register_new_order(order3)
    
    # 模拟生产过程
    print("\n模拟生产过程...")
    
    # 完成订单1的产品（按时）
    factory.env.run(until=50)
    kpi.complete_order_item("order_1", "P1", passed_quality=True)
    kpi.complete_order_item("order_1", "P1", passed_quality=True)
    
    # 完成订单2的产品（延迟）
    factory.env.run(until=150)  # 超过deadline
    kpi.complete_order_item("order_2", "P2", passed_quality=False)  # 第一个报废
    kpi.stats.total_products += 1  # 手动增加总产品数
    kpi.complete_order_item("order_2", "P2", passed_quality=True)   # 第二个通过
    
    # 订单3不完成
    
    # 添加一些设备和AGV数据
    kpi.add_energy_cost("StationA", 100)
    kpi.update_device_utilization("StationA", 200)
    kpi.update_device_utilization("StationB", 200)
    
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=20)
    kpi.register_agv_task_complete("AGV_1")
    kpi.register_agv_task_complete("AGV_1")
    
    # 计算最终KPI
    print("\n计算KPI指标...")
    kpis = kpi.calculate_current_kpis()
    
    # 验证计算结果
    print("\n验证计算公式:")
    print(f"\n1. 订单完成率 = 按时完成订单数 / 总订单数")
    print(f"   = {kpi.stats.on_time_orders} / {kpi.stats.total_orders}")
    print(f"   = {kpis.order_completion_rate:.1f}%")
    expected_rate = (1 / 3) * 100  # 只有订单1按时完成
    if abs(kpis.order_completion_rate - expected_rate) < 0.1:
        print("   ✅ 计算正确")
    else:
        print(f"   ❌ 计算错误，期望值: {expected_rate:.1f}%")
    
    print(f"\n2. 一次通过率 = 一次通过产品数 / 总产品数")
    print(f"   = {kpi.stats.quality_passed_products} / {kpi.stats.total_products}")
    print(f"   = {kpis.first_pass_rate:.1f}%")
    expected_pass_rate = (3 / 4) * 100  # 4个产品，3个通过
    if abs(kpis.first_pass_rate - expected_pass_rate) < 0.1:
        print("   ✅ 计算正确")
    else:
        print(f"   ❌ 计算错误，期望值: {expected_pass_rate:.1f}%")
    
    print(f"\n3. 充电策略效率 = 主动充电次数 / 总充电次数")
    print(f"   = {kpi.stats.agv_active_charges} / {kpi.stats.agv_active_charges + kpi.stats.agv_passive_charges}")
    print(f"   = {kpis.charge_strategy_efficiency:.1f}%")
    expected_charge_eff = (1 / 2) * 100  # 1次主动，1次被动
    if abs(kpis.charge_strategy_efficiency - expected_charge_eff) < 0.1:
        print("   ✅ 计算正确")
    else:
        print(f"   ❌ 计算错误，期望值: {expected_charge_eff:.1f}%")
    
    print(f"\n4. AGV能效比 = 完成任务数 / 总充电时间")
    print(f"   = {kpi.stats.agv_completed_tasks} / {kpi.stats.agv_total_charge_time}")
    print(f"   = {kpis.agv_energy_efficiency:.3f} 任务/秒")
    expected_energy_eff = 2 / 50  # 2个任务，50秒充电
    if abs(kpis.agv_energy_efficiency - expected_energy_eff) < 0.001:
        print("   ✅ 计算正确")
    else:
        print(f"   ❌ 计算错误，期望值: {expected_energy_eff:.3f}")

def test_kpi_scoring():
    """测试最终得分计算"""
    print("\n" + "="*60)
    print("测试3: 最终得分计算")
    print("="*60)
    
    config = load_factory_config()
    factory = Factory(config, mqtt_client=None, no_faults=True)
    kpi = factory.kpi_calculator
    
    # 创建一个高效生产场景
    print("\n创建高效生产场景...")
    
    # 创建并完成多个订单
    for i in range(5):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=i * 10,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.MEDIUM,
            deadline=i * 10 + 300
        )
        kpi.register_new_order(order)
        
        # 模拟生产
        for j in range(2):
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=True)
    
    # 添加设备利用率
    for station in ["StationA", "StationB", "StationC"]:
        kpi.add_energy_cost(station, 150)
        kpi.update_device_utilization(station, 200)
    
    # 添加AGV数据
    for _ in range(10):
        kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=10)
        kpi.register_agv_task_complete("AGV_1")
    
    # 计算最终得分
    scores = kpi.get_final_score()
    
    print("\n最终得分明细:")
    print(f"\n配置的权重:")
    print(f"  - 主权重: {kpi.weights}")
    print(f"  - 效率子权重: {kpi.efficiency_weights}")
    print(f"  - 质量成本子权重: {kpi.quality_cost_weights}")
    print(f"  - AGV子权重: {kpi.agv_weights}")
    
    print(f"\n各项得分:")
    print(f"  - 生产效率得分 ({kpi.weights['production_efficiency']*100}%): {scores['efficiency_score']:.2f}")
    print(f"    - 订单完成率: {scores['efficiency_components']['order_completion']:.1f}")
    print(f"    - 生产周期: {scores['efficiency_components']['production_cycle']:.1f}")
    print(f"    - 设备利用率: {scores['efficiency_components']['device_utilization']:.1f}")
    
    print(f"  - 质量成本得分 ({kpi.weights['cost_control']*100}%): {scores['quality_cost_score']:.2f}")
    print(f"    - 一次通过率: {scores['quality_cost_components']['first_pass_rate']:.1f}")
    print(f"    - 成本效率: {scores['quality_cost_components']['cost_efficiency']:.1f}")
    
    print(f"  - AGV效率得分 ({kpi.weights.get('robustness', 0.3)*100}%): {scores['agv_score']:.2f}")
    print(f"    - 充电策略: {scores['agv_components']['charge_strategy']:.1f}")
    print(f"    - 能效比: {scores['agv_components']['energy_efficiency']:.1f}")
    print(f"    - 利用率: {scores['agv_components']['utilization']:.1f}")
    
    print(f"\n总得分: {scores['total_score']:.2f}/100")
    
    # 验证得分计算
    expected_total = scores['efficiency_score'] + scores['quality_cost_score'] + scores['agv_score']
    if abs(scores['total_score'] - expected_total) < 0.01:
        print("✅ 总分计算正确")
    else:
        print(f"❌ 总分计算错误，期望值: {expected_total:.2f}")

def test_config_loading():
    """测试配置加载功能"""
    print("\n" + "="*60)
    print("测试4: 配置加载验证")
    print("="*60)
    
    config = load_factory_config()
    factory = Factory(config, mqtt_client=None, no_faults=True)
    kpi = factory.kpi_calculator
    
    print("\n验证加载的配置:")
    
    # 验证主权重
    print("\n1. 主权重:")
    for key, value in kpi.weights.items():
        expected = config['kpi_weights'][key]
        status = "✅" if value == expected else "❌"
        print(f"   {status} {key}: {value} (配置值: {expected})")
    
    # 验证子权重
    print("\n2. 效率子权重:")
    for key, value in kpi.efficiency_weights.items():
        expected = config['kpi_weights']['efficiency_components'][key]
        status = "✅" if value == expected else "❌"
        print(f"   {status} {key}: {value} (配置值: {expected})")
    
    # 验证成本参数
    print("\n3. 成本参数:")
    for product, cost in kpi.cost_parameters['material_cost_per_product'].items():
        expected = config['kpi_costs']['material_cost_per_product'][product]
        status = "✅" if cost == expected else "❌"
        print(f"   {status} {product} 材料成本: {cost} (配置值: {expected})")
    
    # 验证理论生产时间
    print("\n4. 理论生产时间:")
    for product, time in kpi.theoretical_production_times.items():
        expected = config['order_generator']['theoretical_production_times'][product]
        status = "✅" if time == expected else "❌"
        print(f"   {status} {product}: {time}秒 (配置值: {expected})")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("KPI系统综合测试")
    print("="*70)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 检查是否需要MQTT
        import socket
        try:
            # 测试MQTT连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 1883))
            sock.close()
            mqtt_available = result == 0
        except:
            mqtt_available = False
            
        if mqtt_available:
            print("\n✅ MQTT Broker可用，运行所有测试...")
            test_kpi_event_driven()
        else:
            print("\n⚠️  MQTT Broker不可用，跳过事件驱动测试...")
            
        # 运行不需要MQTT的测试
        test_kpi_formulas()
        test_kpi_scoring()
        test_config_loading()
        
        print("\n" + "="*70)
        print("✅ 所有测试完成!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()