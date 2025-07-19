#!/usr/bin/env python3
"""
简单的KPI系统测试 - 不启动OrderGenerator
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game_logic.kpi_calculator import KPICalculator
from config.schemas import NewOrder, OrderItem, OrderPriority
import simpy

def test_kpi_calculations():
    """测试KPI计算的准确性"""
    print("\n" + "="*60)
    print("KPI计算测试（无OrderGenerator干扰）")
    print("="*60)
    
    # 直接创建KPI计算器，不通过Factory
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 测试1: 订单完成率
    print("\n测试1: 订单完成率计算")
    print("-" * 40)
    
    # 创建3个订单
    order1 = NewOrder(
        order_id="order_1",
        created_at=0,
        items=[OrderItem(product_type="P1", quantity=2)],
        priority=OrderPriority.LOW,
        deadline=500
    )
    kpi.register_new_order(order1)
    
    order2 = NewOrder(
        order_id="order_2",
        created_at=0,
        items=[OrderItem(product_type="P2", quantity=1)],
        priority=OrderPriority.HIGH,
        deadline=100
    )
    kpi.register_new_order(order2)
    
    order3 = NewOrder(
        order_id="order_3",
        created_at=0,
        items=[OrderItem(product_type="P3", quantity=1)],
        priority=OrderPriority.MEDIUM,
        deadline=400
    )
    kpi.register_new_order(order3)
    
    print(f"创建了 {kpi.stats.total_orders} 个订单")
    
    # 完成订单1（按时）
    env.run(until=50)
    kpi.complete_order_item("order_1", "P1", passed_quality=True)
    kpi.complete_order_item("order_1", "P1", passed_quality=True)
    print(f"时间 {env.now}: 完成订单1")
    
    # 完成订单2（延迟）
    env.run(until=150)  # 超过deadline
    kpi.complete_order_item("order_2", "P2", passed_quality=True)
    print(f"时间 {env.now}: 完成订单2（延迟）")
    
    # 订单3不完成
    
    # 计算KPI
    kpis = kpi.calculate_current_kpis()
    
    print(f"\n结果:")
    print(f"  总订单数: {kpi.stats.total_orders}")
    print(f"  完成订单数: {kpi.stats.completed_orders}")
    print(f"  按时完成订单数: {kpi.stats.on_time_orders}")
    print(f"  订单完成率: {kpis.order_completion_rate:.1f}%")
    
    expected_rate = (1 / 3) * 100  # 1个按时完成，3个总订单
    print(f"  期望值: {expected_rate:.1f}%")
    
    if abs(kpis.order_completion_rate - expected_rate) < 0.1:
        print("  ✅ 计算正确")
    else:
        print("  ❌ 计算错误")
    
    # 测试2: 一次通过率
    print("\n测试2: 一次通过率计算")
    print("-" * 40)
    
    # 清空并重新开始
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 创建订单
    order = NewOrder(
        order_id="test_order",
        created_at=0,
        items=[OrderItem(product_type="P1", quantity=4)],
        priority=OrderPriority.MEDIUM,
        deadline=1000
    )
    kpi.register_new_order(order)
    
    # 完成产品：3个通过，1个失败
    kpi.complete_order_item("test_order", "P1", passed_quality=True)
    kpi.complete_order_item("test_order", "P1", passed_quality=True)
    kpi.complete_order_item("test_order", "P1", passed_quality=False)  # 失败
    kpi.complete_order_item("test_order", "P1", passed_quality=True)
    
    kpis = kpi.calculate_current_kpis()
    
    print(f"\n结果:")
    print(f"  总产品数: {kpi.stats.total_products}")
    print(f"  通过产品数: {kpi.stats.quality_passed_products}")
    print(f"  报废产品数: {kpi.stats.scrapped_products}")
    print(f"  一次通过率: {kpis.first_pass_rate:.1f}%")
    
    expected_pass_rate = (3 / 4) * 100
    print(f"  期望值: {expected_pass_rate:.1f}%")
    
    if abs(kpis.first_pass_rate - expected_pass_rate) < 0.1:
        print("  ✅ 计算正确")
    else:
        print("  ❌ 计算错误")
    
    # 测试3: AGV效率指标
    print("\n测试3: AGV效率指标计算")
    print("-" * 40)
    
    # 清空并重新开始
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 添加AGV数据
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=20)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=50)  # 被动充电
    
    for _ in range(5):
        kpi.register_agv_task_complete("AGV_1")
    
    kpi.update_agv_transport_time("AGV_1", 100)
    kpi.update_agv_transport_time("AGV_2", 80)
    
    # 运行一段时间
    env.run(until=200)
    
    kpis = kpi.calculate_current_kpis()
    
    print(f"\n结果:")
    print(f"  主动充电次数: {kpi.stats.agv_active_charges}")
    print(f"  被动充电次数: {kpi.stats.agv_passive_charges}")
    print(f"  总充电时间: {kpi.stats.agv_total_charge_time}秒")
    print(f"  完成任务数: {kpi.stats.agv_completed_tasks}")
    print(f"  充电策略效率: {kpis.charge_strategy_efficiency:.1f}%")
    print(f"  AGV能效比: {kpis.agv_energy_efficiency:.3f} 任务/秒")
    
    expected_charge_eff = (2 / 3) * 100  # 2次主动，1次被动
    expected_energy_eff = 5 / 100  # 5个任务，100秒充电
    
    print(f"\n期望值:")
    print(f"  充电策略效率: {expected_charge_eff:.1f}%")
    print(f"  AGV能效比: {expected_energy_eff:.3f} 任务/秒")
    
    if abs(kpis.charge_strategy_efficiency - expected_charge_eff) < 0.1:
        print("  ✅ 充电策略效率计算正确")
    else:
        print("  ❌ 充电策略效率计算错误")
        
    if abs(kpis.agv_energy_efficiency - expected_energy_eff) < 0.001:
        print("  ✅ AGV能效比计算正确")
    else:
        print("  ❌ AGV能效比计算错误")
    
    # 测试4: 最终得分计算
    print("\n测试4: 最终得分计算")
    print("-" * 40)
    
    scores = kpi.get_final_score()
    
    print(f"\n得分明细:")
    print(f"  生产效率得分: {scores['efficiency_score']:.2f}")
    print(f"  质量成本得分: {scores['quality_cost_score']:.2f}")
    print(f"  AGV效率得分: {scores['agv_score']:.2f}")
    print(f"  总得分: {scores['total_score']:.2f}")
    
    # 验证总分
    expected_total = scores['efficiency_score'] + scores['quality_cost_score'] + scores['agv_score']
    if abs(scores['total_score'] - expected_total) < 0.01:
        print("  ✅ 总分计算正确")
    else:
        print(f"  ❌ 总分计算错误，期望值: {expected_total:.2f}")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("KPI系统简单测试")
    print("="*70)
    
    test_kpi_calculations()
    
    print("\n" + "="*70)
    print("✅ 测试完成!")
    print("="*70)