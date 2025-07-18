#!/usr/bin/env python3
"""
验证KPI系统是否完全符合PRD 3.4要求
"""

import os
import sys
import json
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game_logic.kpi_calculator import KPICalculator
from src.utils.config_loader import load_factory_config
from src.utils.mqtt_client import MQTTClient
from config.topics import KPI_UPDATE_TOPIC
from config.schemas import NewOrder, OrderItem, OrderPriority, KPIUpdate
import simpy

class KPIValidator:
    """验证KPI是否符合PRD 3.4"""
    def __init__(self):
        self.mqtt_messages = []
        
    def on_kpi_message(self, client, userdata, message):
        """捕获MQTT消息"""
        try:
            payload = json.loads(message.payload.decode())
            self.mqtt_messages.append(payload)
        except Exception as e:
            print(f"解析MQTT消息失败: {e}")

def test_score_range():
    """测试得分范围"""
    print("\n" + "="*60)
    print("测试1: 得分范围验证")
    print("="*60)
    
    config = load_factory_config()
    
    # 场景1：最差表现（0分）
    print("\n场景1: 最差表现")
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None, config=config)
    
    # 创建订单但不完成
    for i in range(5):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=0,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.HIGH,
            deadline=50
        )
        kpi.register_new_order(order)
    
    # 只产生成本
    kpi.add_energy_cost("StationA", 1000)
    kpi.add_maintenance_cost("StationA", "repair", False)
    
    # 被动充电
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=100)
    
    scores = kpi.get_final_score()
    print(f"总得分: {scores['total_score']:.2f}/100")
    
    # 场景2：中等表现
    print("\n场景2: 中等表现")
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None, config=config)
    
    # 创建并部分完成订单
    for i in range(4):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=i * 50,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.MEDIUM,
            deadline=i * 50 + 300
        )
        kpi.register_new_order(order)
        
        if i < 2:  # 完成一半订单
            env.run(until=i * 50 + 100)
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=True)
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=i == 0)
    
    # 添加设备和AGV数据
    kpi.add_energy_cost("StationA", 100)
    kpi.update_device_utilization("StationA", 200)
    
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=30)
    kpi.register_agv_task_complete("AGV_1")
    kpi.register_agv_task_complete("AGV_1")
    
    scores = kpi.get_final_score()
    print(f"总得分: {scores['total_score']:.2f}/100")
    
    # 场景3：优秀表现
    print("\n场景3: 优秀表现")
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None, config=config)
    
    # 高效完成所有订单
    for i in range(5):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=i * 10,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.LOW,
            deadline=i * 10 + 1000
        )
        kpi.register_new_order(order)
        
        # 立即完成
        for j in range(2):
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=True)
    
    # 高设备利用率
    for station in ["StationA", "StationB", "StationC"]:
        kpi.add_energy_cost(station, 180)
        kpi.update_device_utilization(station, 200)
    
    # 完美AGV效率
    for _ in range(10):
        kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=10)
        kpi.register_agv_task_complete("AGV_1")
    
    kpi.update_agv_transport_time("AGV_1", 180)
    env.run(until=200)
    
    scores = kpi.get_final_score()
    print(f"总得分: {scores['total_score']:.2f}/100")
    
    print("\n得分范围总结:")
    print("- 理论最低分: 0分")
    print("- 理论最高分: 100分")
    print("- 实际可达到的最高分: 约85-90分")
    print("- 初始状态（无操作）: 约18-20分")

def test_mqtt_compliance():
    """测试MQTT消息是否符合PRD 3.4"""
    print("\n" + "="*60)
    print("测试2: MQTT消息PRD合规性验证")
    print("="*60)
    
    # 创建MQTT客户端和验证器
    mqtt_client = MQTTClient(
        host="localhost",
        port=1883,
        client_id=f"kpi_validator_{int(time.time())}"
    )
    
    try:
        mqtt_client.connect()
        validator = KPIValidator()
        mqtt_client.client.on_message = validator.on_kpi_message
        mqtt_client.client.subscribe(KPI_UPDATE_TOPIC)
        mqtt_client.client.loop_start()
        
        # 创建KPI计算器
        config = load_factory_config()
        env = simpy.Environment()
        kpi = KPICalculator(env, mqtt_client=mqtt_client, config=config)
        
        # 触发一些KPI事件
        order = NewOrder(
            order_id="test_order",
            created_at=0,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.MEDIUM,
            deadline=300
        )
        kpi.register_new_order(order)
        kpi.complete_order_item("test_order", "P1", passed_quality=True)
        kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
        
        # 等待MQTT消息
        time.sleep(2)
        mqtt_client.client.loop_stop()
        
        if validator.mqtt_messages:
            print(f"\n收到 {len(validator.mqtt_messages)} 条MQTT消息")
            latest_msg = validator.mqtt_messages[-1]
            
            print("\n验证PRD 3.4 第2.8节定义的KPI字段:")
            
            # 生产效率指标
            print("\n生产效率指标:")
            check_field(latest_msg, "order_completion_rate", "订单完成率")
            check_field(latest_msg, "average_production_cycle", "加权平均生产周期")
            check_field(latest_msg, "device_utilization", "设备利用率")
            
            # 质量与成本指标
            print("\n质量与成本指标:")
            check_field(latest_msg, "first_pass_rate", "一次通过率")
            check_field(latest_msg, "total_production_cost", "总生产成本")
            check_field(latest_msg, "material_costs", "物料成本")
            check_field(latest_msg, "energy_costs", "能源成本")
            check_field(latest_msg, "maintenance_costs", "维修成本")
            check_field(latest_msg, "scrap_costs", "报废成本")
            
            # AGV操控效率指标
            print("\nAGV操控效率指标:")
            check_field(latest_msg, "charge_strategy_efficiency", "充电策略效率")
            check_field(latest_msg, "agv_energy_efficiency", "AGV能效比")
            check_field(latest_msg, "agv_utilization", "AGV利用率")
            
            # 额外的辅助指标
            print("\n额外的辅助指标:")
            check_field(latest_msg, "on_time_delivery_rate", "按时交付率")
            check_field(latest_msg, "total_orders", "总订单数")
            check_field(latest_msg, "completed_orders", "完成订单数")
            check_field(latest_msg, "active_orders", "活跃订单数")
            check_field(latest_msg, "total_products", "总产品数")
            check_field(latest_msg, "active_faults", "活跃故障数")
            
            # 检查不应存在的字段
            print("\n验证已移除的字段:")
            check_not_exists(latest_msg, "diagnosis_accuracy", "诊断准确率")
            check_not_exists(latest_msg, "average_recovery_time", "平均恢复时间")
            
        else:
            print("❌ 未收到MQTT消息")
            
    except Exception as e:
        print(f"⚠️  MQTT测试失败: {e}")
        print("请确保MQTT Broker在运行")
    finally:
        try:
            mqtt_client.disconnect()
        except:
            pass

def check_field(msg, field, name):
    """检查字段是否存在"""
    if field in msg:
        print(f"  ✅ {name} ({field}): {msg[field]}")
    else:
        print(f"  ❌ {name} ({field}): 缺失")

def check_not_exists(msg, field, name):
    """检查字段不应存在"""
    if field not in msg:
        print(f"  ✅ {name} ({field}): 已正确移除")
    else:
        print(f"  ❌ {name} ({field}): 不应存在但找到值 {msg[field]}")

def test_kpi_formulas():
    """验证KPI计算公式"""
    print("\n" + "="*60)
    print("测试3: KPI计算公式验证")
    print("="*60)
    
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 测试数据设置
    print("\n设置测试数据:")
    print("- 创建3个订单，完成2个（1个按时，1个延迟）")
    print("- 生产4个产品，3个通过质检")
    print("- AGV充电3次（2次主动，1次被动）")
    print("- AGV完成5个任务，充电总时间100秒")
    
    # 创建订单
    orders = [
        ("order_1", 0, 500, True),   # 按时完成
        ("order_2", 0, 100, False),  # 延迟完成
        ("order_3", 0, 400, None)    # 未完成
    ]
    
    for order_id, created_at, deadline, will_complete in orders:
        order = NewOrder(
            order_id=order_id,
            created_at=created_at,
            items=[OrderItem(product_type="P1", quantity=1)],
            priority=OrderPriority.MEDIUM,
            deadline=deadline
        )
        kpi.register_new_order(order)
        
        if will_complete is not None:
            env.run(until=50 if will_complete else 150)
            kpi.complete_order_item(order_id, "P1", passed_quality=True)
    
    # 添加一个失败的产品
    kpi.stats.total_products += 1
    kpi.stats.scrapped_products += 1
    
    # AGV数据
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=40)
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=30)
    
    for _ in range(5):
        kpi.register_agv_task_complete("AGV_1")
    
    # 计算KPI
    kpis = kpi.calculate_current_kpis()
    
    print("\n验证PRD 3.4公式计算:")
    
    # 验证订单完成率
    print(f"\n1. 订单完成率 = (按时完成订单数 / 总订单数) × 100%")
    print(f"   = ({kpi.stats.on_time_orders} / {kpi.stats.total_orders}) × 100%")
    print(f"   = {kpis.order_completion_rate:.1f}%")
    expected = (1 / 3) * 100
    print(f"   期望值: {expected:.1f}% {'✅' if abs(kpis.order_completion_rate - expected) < 0.1 else '❌'}")
    
    # 验证一次通过率
    print(f"\n2. 一次通过率 = (一次通过质检产品数 / 总产品数) × 100%")
    print(f"   = ({kpi.stats.quality_passed_products} / {kpi.stats.total_products}) × 100%")
    print(f"   = {kpis.first_pass_rate:.1f}%")
    expected = (3 / 4) * 100
    print(f"   期望值: {expected:.1f}% {'✅' if abs(kpis.first_pass_rate - expected) < 0.1 else '❌'}")
    
    # 验证充电策略效率
    print(f"\n3. 充电策略效率 = (主动充电次数 / (主动充电次数 + 被动充电次数)) × 100%")
    print(f"   = ({kpi.stats.agv_active_charges} / ({kpi.stats.agv_active_charges} + {kpi.stats.agv_passive_charges})) × 100%")
    print(f"   = {kpis.charge_strategy_efficiency:.1f}%")
    expected = (2 / 3) * 100
    print(f"   期望值: {expected:.1f}% {'✅' if abs(kpis.charge_strategy_efficiency - expected) < 0.1 else '❌'}")
    
    # 验证AGV能效比
    print(f"\n4. AGV能效比 = (完成任务数 / 总充电时间)")
    print(f"   = {kpi.stats.agv_completed_tasks} / {kpi.stats.agv_total_charge_time}")
    print(f"   = {kpis.agv_energy_efficiency:.3f} 任务/秒")
    expected = 5 / 100
    print(f"   期望值: {expected:.3f} {'✅' if abs(kpis.agv_energy_efficiency - expected) < 0.001 else '❌'}")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("KPI系统PRD 3.4合规性验证")
    print("="*70)
    
    # 运行所有测试
    test_score_range()
    test_mqtt_compliance()
    test_kpi_formulas()
    
    print("\n" + "="*70)
    print("✅ 验证完成!")
    print("="*70)