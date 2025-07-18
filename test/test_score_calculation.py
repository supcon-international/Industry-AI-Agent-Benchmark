#!/usr/bin/env python3
"""
测试得分计算逻辑
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.factory import Factory
from src.utils.config_loader import load_factory_config
from config.schemas import NewOrder, OrderItem, OrderPriority
import simpy

def test_score_details():
    """测试得分计算细节"""
    print("\n" + "="*60)
    print("得分计算详细测试")
    print("="*60)
    
    # 加载配置并创建工厂
    config = load_factory_config()
    factory = Factory(config, mqtt_client=None, no_faults=True)
    kpi = factory.kpi_calculator
    
    # 场景1：初始状态（无任何活动）
    print("\n场景1：初始状态")
    print("-" * 40)
    scores = kpi.get_final_score()
    print_score_details(scores)
    
    # 场景2：添加一些订单但不完成
    print("\n场景2：添加订单但不完成")
    print("-" * 40)
    
    # 手动创建订单
    order1 = NewOrder(
        order_id="test_order_1",
        created_at=factory.env.now,
        items=[OrderItem(product_type="P1", quantity=2)],
        priority=OrderPriority.MEDIUM,
        deadline=factory.env.now + 400
    )
    kpi.register_new_order(order1)
    
    # 运行一小段时间
    factory.run(until=10)
    
    scores = kpi.get_final_score()
    print_score_details(scores)
    
    # 场景3：完成一些产品
    print("\n场景3：完成一些产品")
    print("-" * 40)
    
    # 模拟完成产品
    kpi.complete_order_item("test_order_1", "P1", passed_quality=True)
    kpi.complete_order_item("test_order_1", "P1", passed_quality=True)
    
    # 添加一些设备利用时间
    kpi.add_energy_cost("StationA", 100)
    kpi.update_device_utilization("StationA", 200)
    
    scores = kpi.get_final_score()
    print_score_details(scores)
    
    # 场景4：检查AGV效率
    print("\n场景4：检查AGV效率得分")
    print("-" * 40)
    print(f"主动充电次数: {kpi.stats.agv_active_charges}")
    print(f"被动充电次数: {kpi.stats.agv_passive_charges}")
    print(f"AGV完成任务数: {kpi.stats.agv_completed_tasks}")
    print(f"AGV总充电时间: {kpi.stats.agv_total_charge_time}")
    print(f"AGV效率得分: {scores['agv_score']:.2f}")
    print(f"AGV效率组件: {scores['agv_components']}")

def print_score_details(scores):
    """打印得分详情"""
    print(f"\n原始KPI值:")
    for key, value in scores['raw_kpis'].items():
        print(f"  - {key}: {value:.2f}")
    
    print(f"\n效率组件:")
    for key, value in scores.get('efficiency_components', {}).items():
        print(f"  - {key}: {value:.2f}")
    
    print(f"\n成本效率: {scores.get('cost_efficiency', 0):.2f}")
    
    print(f"\n质量与成本组件:")
    for key, value in scores.get('quality_cost_components', {}).items():
        print(f"  - {key}: {value:.2f}")
    
    print(f"\nAGV效率组件:")
    for key, value in scores.get('agv_components', {}).items():
        print(f"  - {key}: {value:.2f}")
    
    print(f"\n最终得分:")
    print(f"  - 生产效率得分 (40%): {scores['efficiency_score']:.2f}")
    print(f"  - 质量与成本得分 (30%): {scores['quality_cost_score']:.2f}")
    print(f"  - AGV效率得分 (30%): {scores['agv_score']:.2f}")
    print(f"  - 总得分: {scores['total_score']:.2f}")

if __name__ == "__main__":
    test_score_details()