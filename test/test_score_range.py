#!/usr/bin/env python3
"""
测试KPI得分范围
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game_logic.kpi_calculator import KPICalculator
from config.schemas import NewOrder, OrderItem, OrderPriority
import simpy

def test_minimum_score():
    """测试最低得分场景"""
    print("\n" + "="*60)
    print("最低得分场景")
    print("="*60)
    
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 创建订单但不完成任何
    for i in range(5):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=0,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.HIGH,
            deadline=50  # 很短的期限
        )
        kpi.register_new_order(order)
    
    # 添加一些成本但没有产出
    kpi.add_energy_cost("StationA", 1000)
    kpi.add_maintenance_cost("StationA", "repair", False)  # 错误诊断
    
    # 被动充电（效率低）
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=100)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=100)
    
    # 计算得分
    scores = kpi.get_final_score()
    print_scores(scores)
    
    return scores

def test_maximum_score():
    """测试最高得分场景"""
    print("\n" + "="*60)
    print("最高得分场景")
    print("="*60)
    
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 创建并按时完成所有订单
    for i in range(5):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=i * 10,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.LOW,
            deadline=i * 10 + 1000  # 充足的时间
        )
        kpi.register_new_order(order)
        
        # 立即完成（理论时间内）
        for j in range(2):
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=True)
    
    # 高设备利用率
    for station in ["StationA", "StationB", "StationC"]:
        kpi.add_energy_cost(station, 180)  # 3分钟工作时间
        kpi.update_device_utilization(station, 200)  # 总时间200秒
    
    # 完美的AGV效率
    # 全部主动充电
    for _ in range(5):
        kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=10)
        kpi.register_agv_task_complete("AGV_1")
    
    # 高AGV利用率
    kpi.update_agv_transport_time("AGV_1", 180)
    env.run(until=200)
    
    # 计算得分
    scores = kpi.get_final_score()
    print_scores(scores)
    
    return scores

def test_average_score():
    """测试平均得分场景"""
    print("\n" + "="*60)
    print("平均得分场景")
    print("="*60)
    
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None)
    
    # 创建订单，部分完成
    for i in range(4):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=i * 50,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.MEDIUM,
            deadline=i * 50 + 300
        )
        kpi.register_new_order(order)
        
        # 完成前两个订单
        if i < 2:
            env.run(until=i * 50 + 100)
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=True)
            kpi.complete_order_item(f"order_{i}", "P1", passed_quality=i == 0)  # 第二个订单有一个失败
    
    # 中等设备利用率
    kpi.add_energy_cost("StationA", 100)
    kpi.update_device_utilization("StationA", 200)
    
    # 混合充电策略
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=30)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=30)
    kpi.register_agv_task_complete("AGV_1")
    kpi.register_agv_task_complete("AGV_1")
    
    env.run(until=300)
    
    # 计算得分
    scores = kpi.get_final_score()
    print_scores(scores)
    
    return scores

def print_scores(scores):
    """打印得分详情"""
    print(f"\n各维度得分:")
    print(f"  生产效率 (40%): {scores['efficiency_score']:.2f}/40")
    print(f"    - 订单完成率: {scores['efficiency_components']['order_completion']:.1f}/100")
    print(f"    - 生产周期: {scores['efficiency_components']['production_cycle']:.1f}/100")
    print(f"    - 设备利用率: {scores['efficiency_components']['device_utilization']:.1f}/100")
    
    print(f"  质量成本 (30%): {scores['quality_cost_score']:.2f}/30")
    print(f"    - 一次通过率: {scores['quality_cost_components']['first_pass_rate']:.1f}/100")
    print(f"    - 成本效率: {scores['quality_cost_components']['cost_efficiency']:.1f}/100")
    
    print(f"  AGV效率 (30%): {scores['agv_score']:.2f}/30")
    print(f"    - 充电策略: {scores['agv_components']['charge_strategy']:.1f}/100")
    print(f"    - 能效比: {scores['agv_components']['energy_efficiency']:.1f}/100")
    print(f"    - 利用率: {scores['agv_components']['utilization']:.1f}/100")
    
    print(f"\n总得分: {scores['total_score']:.2f}/100")

def analyze_score_range():
    """分析得分范围"""
    print("\n" + "="*60)
    print("得分范围分析")
    print("="*60)
    
    print("\n理论得分范围: 0-100分")
    print("\n各维度满分:")
    print("  - 生产效率: 40分 (40%)")
    print("  - 质量成本: 30分 (30%)")
    print("  - AGV效率: 30分 (30%)")
    
    print("\n实际得分分布:")
    print("  - 极差表现: 0-20分")
    print("    * 无订单完成")
    print("    * 高成本无产出")
    print("    * 全被动充电")
    
    print("  - 较差表现: 20-40分")
    print("    * 少量订单完成")
    print("    * 成本控制差")
    print("    * 充电策略不佳")
    
    print("  - 中等表现: 40-60分")
    print("    * 部分订单按时完成")
    print("    * 成本控制一般")
    print("    * 混合充电策略")
    
    print("  - 良好表现: 60-80分")
    print("    * 大部分订单按时完成")
    print("    * 成本控制良好")
    print("    * 主动充电为主")
    
    print("  - 优秀表现: 80-100分")
    print("    * 几乎全部订单按时完成")
    print("    * 成本效率高")
    print("    * 完美充电策略")
    
    print("\n特殊情况:")
    print("  - 初始状态（无操作）: 约18分")
    print("    * 成本效率给基础分50分")
    print("    * 充电策略100分（无充电时默认）")
    print("  - 有成本无产出: 0-10分")
    print("    * 所有效率指标为0")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("KPI得分范围测试")
    print("="*70)
    
    # 测试不同场景
    min_scores = test_minimum_score()
    avg_scores = test_average_score()
    max_scores = test_maximum_score()
    
    # 分析得分范围
    analyze_score_range()
    
    # 总结
    print("\n" + "="*70)
    print("测试结果总结")
    print("="*70)
    print(f"最低得分: {min_scores['total_score']:.2f}分")
    print(f"平均得分: {avg_scores['total_score']:.2f}分")
    print(f"最高得分: {max_scores['total_score']:.2f}分")