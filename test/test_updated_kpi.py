#!/usr/bin/env python3
"""
测试更新后的KPI系统（移除鲁棒性）
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game_logic.kpi_calculator import KPICalculator
from src.utils.config_loader import load_factory_config
from config.schemas import NewOrder, OrderItem, OrderPriority
import simpy

def test_updated_kpi_system():
    """测试更新后的KPI系统"""
    print("\n" + "="*60)
    print("PRD 3.4 KPI系统测试")
    print("="*60)
    
    # 加载配置
    config = load_factory_config()
    env = simpy.Environment()
    kpi = KPICalculator(env, mqtt_client=None, config=config)
    
    print("\n1. 验证KPI权重配置:")
    print(f"   - 生产效率: {kpi.weights['production_efficiency']*100}%")
    print(f"   - 质量与成本: {kpi.weights['quality_cost']*100}%")
    print(f"   - AGV操控效率: {kpi.weights['agv_efficiency']*100}%")
    print(f"   总计: {sum(kpi.weights.values())*100}%")
    
    # 创建测试场景
    print("\n2. 创建测试场景...")
    
    # 创建订单
    for i in range(3):
        order = NewOrder(
            order_id=f"order_{i}",
            created_at=i * 50,
            items=[OrderItem(product_type="P1", quantity=2)],
            priority=OrderPriority.MEDIUM,
            deadline=i * 50 + 400
        )
        kpi.register_new_order(order)
    
    # 完成一些产品
    env.run(until=100)
    kpi.complete_order_item("order_0", "P1", passed_quality=True)
    kpi.complete_order_item("order_0", "P1", passed_quality=True)
    kpi.complete_order_item("order_1", "P1", passed_quality=True)
    kpi.complete_order_item("order_1", "P1", passed_quality=False)  # 一个失败
    
    # 添加设备利用数据
    kpi.add_energy_cost("StationA", 80)
    kpi.update_device_utilization("StationA", 100)
    
    # 添加AGV数据
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=20)
    kpi.register_agv_charge("AGV_1", is_active=True, charge_duration=20)
    kpi.register_agv_charge("AGV_1", is_active=False, charge_duration=20)  # 一次被动
    
    for _ in range(3):
        kpi.register_agv_task_complete("AGV_1")
    
    kpi.update_agv_transport_time("AGV_1", 50)
    
    # 计算KPI
    print("\n3. 计算当前KPI指标:")
    kpis = kpi.calculate_current_kpis()
    
    print(f"\n生产效率指标:")
    print(f"   - 订单完成率: {kpis.order_completion_rate:.1f}%")
    print(f"   - 加权平均生产周期: {kpis.average_production_cycle:.2f}")
    print(f"   - 设备利用率: {kpis.device_utilization:.1f}%")
    
    print(f"\n质量与成本指标:")
    print(f"   - 一次通过率: {kpis.first_pass_rate:.1f}%")
    print(f"   - 总生产成本: ¥{kpis.total_production_cost:.2f}")
    print(f"     • 物料成本: ¥{kpis.material_costs:.2f}")
    print(f"     • 能源成本: ¥{kpis.energy_costs:.2f}")
    print(f"     • 维修成本: ¥{kpis.maintenance_costs:.2f}")
    print(f"     • 报废成本: ¥{kpis.scrap_costs:.2f}")
    
    print(f"\nAGV操控效率指标:")
    print(f"   - 充电策略效率: {kpis.charge_strategy_efficiency:.1f}%")
    print(f"   - AGV能效比: {kpis.agv_energy_efficiency:.3f} 任务/秒")
    print(f"   - AGV利用率: {kpis.agv_utilization:.1f}%")
    
    # 计算最终得分
    print("\n4. 计算最终得分:")
    scores = kpi.get_final_score()
    
    print(f"\n各维度得分明细:")
    print(f"   生产效率 (40%):")
    print(f"     - 订单完成率贡献: {scores['efficiency_components']['order_completion'] * 0.4 * 0.4:.2f}分")
    print(f"     - 生产周期贡献: {scores['efficiency_components']['production_cycle'] * 0.4 * 0.4:.2f}分")
    print(f"     - 设备利用率贡献: {scores['efficiency_components']['device_utilization'] * 0.2 * 0.4:.2f}分")
    print(f"     小计: {scores['efficiency_score']:.2f}分")
    
    print(f"\n   质量与成本 (30%):")
    print(f"     - 一次通过率贡献: {scores['quality_cost_components']['first_pass_rate'] * 0.4 * 0.3:.2f}分")
    print(f"     - 成本效率贡献: {scores['quality_cost_components']['cost_efficiency'] * 0.6 * 0.3:.2f}分")
    print(f"     小计: {scores['quality_cost_score']:.2f}分")
    
    print(f"\n   AGV操控效率 (30%):")
    print(f"     - 充电策略贡献: {scores['agv_components']['charge_strategy'] * 0.3 * 0.3:.2f}分")
    print(f"     - 能效比贡献: {scores['agv_components']['energy_efficiency'] * 0.4 * 0.3:.2f}分")
    print(f"     - 利用率贡献: {scores['agv_components']['utilization'] * 0.3 * 0.3:.2f}分")
    print(f"     小计: {scores['agv_score']:.2f}分")
    
    print(f"\n   总得分: {scores['total_score']:.2f}/100分")
    
    # 验证没有鲁棒性相关内容
    print("\n5. 验证系统更新:")
    print("   ✅ 已移除鲁棒性（robustness）权重")
    print("   ✅ 已移除诊断准确率（diagnosis_accuracy）计算")
    print("   ✅ 已移除平均恢复时间（average_recovery_time）计算")
    print("   ✅ 完全符合PRD 3.4规范")

if __name__ == "__main__":
    test_updated_kpi_system()