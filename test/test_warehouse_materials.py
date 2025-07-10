#!/usr/bin/env python3
"""
原料仓库和成品仓库测试脚本
测试RawMaterial和Warehouse类的基本功能和AGV交互
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simpy
from src.simulation.entities.warehouse import RawMaterial, Warehouse
from src.simulation.entities.agv import AGV
from src.simulation.entities.product import Product

def test_raw_material_basic():
    """测试原料仓库基本功能"""
    print("=== 测试原料仓库基本功能 ===")
    
    env = simpy.Environment()
    
    # 创建原料仓库
    raw_material = RawMaterial(
        env=env,
        id="RawMaterial_Test",
        position=(5, 20),
        buffer_size=20
    )
    
    def test_process():
        print(f"[{env.now:.2f}] 开始测试原料仓库")
        
        # 测试创建原料
        products = []
        for i in range(3):
            product_type = ["P1", "P2", "P3"][i]
            product = raw_material.create_raw_material(product_type, f"order_{i+1}")
            products.append(product)
            
            # 将产品放入buffer
            raw_material.add_product_to_buffer(product)
            
        print(f"\n--- 原料仓库状态 ---")
        stats = raw_material.get_material_stats()
        print(f"统计信息: {stats}")
        
        # 测试库存检查
        yield env.timeout(50)  # 等待库存检查
        
        stats_after = raw_material.get_material_stats()
        print(f"50秒后统计信息: {stats_after}")
        
    env.process(test_process())
    env.run(until=100)
    print("原料仓库基本功能测试完成\n")

def test_warehouse_basic():
    """测试成品仓库基本功能"""
    print("=== 测试成品仓库基本功能 ===")
    
    env = simpy.Environment()
    
    # 创建成品仓库
    warehouse = Warehouse(
        env=env,
        id="Warehouse_Test",
        position=(85, 20),
        buffer_size=10  # 小容量便于测试
    )
    
    def test_process():
        print(f"[{env.now:.2f}] 开始测试成品仓库")
        
        # 创建一些成品并存入仓库
        for i in range(5):
            product_type = ["P1", "P2", "P3"][i % 3]
            product = Product(product_type, f"order_{i+1}")
            
            success = warehouse.add_product_to_buffer(product)
            print(f"存储产品 {product.id}: {success}")
            
        print(f"\n--- 成品仓库状态 ---")
        stats = warehouse.get_warehouse_stats()
        print(f"仓库统计: {stats}")
        
        quality_summary = warehouse.get_quality_summary()
        print(f"质量汇总: {quality_summary}")
        
        # 等待一段时间观察发货
        yield env.timeout(350)  # 等待发货过程
        
        print(f"\n--- 发货后仓库状态 ---")
        stats_after = warehouse.get_warehouse_stats()
        print(f"发货后统计: {stats_after}")
        
    env.process(test_process())
    env.run(until=400)
    print("成品仓库基本功能测试完成\n")

def test_agv_integration():
    """测试AGV与仓库的集成"""
    print("=== 测试AGV与仓库集成 ===")
    
    env = simpy.Environment()
    
    # 创建原料仓库、成品仓库和AGV
    raw_material = RawMaterial(env, "RawMaterial", (5, 20), buffer_size=20)
    warehouse = Warehouse(env, "Warehouse", (85, 20), buffer_size=20)
    agv = AGV(
        env=env,
        id="AGV_Test",
        position=(10, 20),
        speed_mps=5.0,  # 加快速度便于测试
        low_battery_threshold=5.0
    )
    
    def test_process():
        print(f"[{env.now:.2f}] 开始测试AGV与仓库集成")
        
        # 1. 向原料仓库添加一些产品
        products = []
        for i in range(3):
            product = raw_material.create_raw_material("P1", f"order_{i+1}")
            raw_material.add_product_to_buffer(product)
            products.append(product)
        
        print(f"\n--- 原料仓库准备完成，产品数: {len(raw_material.buffer.items)} ---")
        
        # 2. AGV从原料仓库取货
        agv_pos_before = agv.position
        yield env.process(agv.move_to(raw_material.position))
        print(f"AGV移动: {agv_pos_before} -> {agv.position}")
        
        success, feedback, product = yield env.process(agv.load_from(raw_material))
        print(f"AGV取货结果: {success}, {feedback}")
        
        # 3. AGV运输到成品仓库
        yield env.process(agv.move_to(warehouse.position))
        print(f"AGV到达成品仓库: {agv.position}")
        
        success, feedback, product = yield env.process(agv.unload_to(warehouse))
        print(f"AGV卸货结果: {success}, {feedback}")
        
        # 4. 查看最终状态
        print(f"\n--- 最终状态 ---")
        print(f"原料仓库缓冲区: {len(raw_material.buffer.items)} 个产品")
        print(f"成品仓库缓冲区: {len(warehouse.buffer.items)} 个产品")
        print(f"AGV载货: {len(agv.payload.items)} 个产品")
        print(f"AGV电量: {agv.battery_level:.1f}%")
        
        raw_stats = raw_material.get_material_stats()
        warehouse_stats = warehouse.get_warehouse_stats()
        print(f"原料仓库统计: 供应{raw_stats['materials_supplied']}个, 库存{raw_stats['stock_level']:.1f}%")
        print(f"成品仓库统计: 接收{warehouse_stats['products_received']}个, 利用率{warehouse_stats['buffer_utilization']*100:.1f}%")
        
    env.process(test_process())
    env.run(until=200)
    print("AGV与仓库集成测试完成\n")

def test_buffer_full_scenarios():
    """测试缓冲区满载场景"""
    print("=== 测试缓冲区满载场景 ===")
    
    env = simpy.Environment()
    
    # 创建模拟故障系统
    class MockFaultSystem:
        def report_buffer_full(self, device_id, buffer_type):
            print(f"[ALERT] {device_id} 的 {buffer_type} 已满！")
    
    fault_system = MockFaultSystem()
    
    # 创建小容量仓库
    warehouse = Warehouse(
        env=env,
        id="SmallWarehouse",
        position=(85, 20),
        buffer_size=3,  # 很小的容量
        fault_system=fault_system
    )
    
    def test_process():
        print(f"[{env.now:.2f}] 测试仓库满载情况")
        
        # 尝试存储超过容量的产品
        for i in range(5):
            product = Product("P1", f"order_{i+1}")
            success = warehouse.add_product_to_buffer(product)
            print(f"存储产品 {i+1}: {success}, 当前容量: {len(warehouse.buffer.items)}/{warehouse.buffer_size}")
            
            if not success:
                print(f"仓库已满，无法存储更多产品")
                
        # 检查告警触发
        stats = warehouse.get_warehouse_stats()
        print(f"仓库状态: 接近满载={stats['is_near_full']}, 可接收={stats['can_receive']}")
        
        # 需要yield来使其成为生成器
        yield env.timeout(0)
        
    env.process(test_process())
    env.run(until=50)
    print("缓冲区满载场景测试完成\n")

def test_production_flow_simulation():
    """模拟完整的生产流程"""
    print("=== 模拟完整生产流程 ===")
    
    env = simpy.Environment()
    
    # 创建完整系统
    raw_material = RawMaterial(env, "RawMaterial", (5, 20))
    warehouse = Warehouse(env, "Warehouse", (85, 20))
    agv = AGV(env, "AGV", (40, 20), speed_mps=3.0)
    
    def production_simulation():
        print(f"[{env.now:.2f}] 开始生产流程模拟")
        
        # 生产循环
        for cycle in range(3):
            print(f"\n--- 生产周期 {cycle + 1} ---")
            
            # 1. 创建原料
            product = raw_material.create_raw_material("P1", f"order_cycle_{cycle+1}")
            raw_material.add_product_to_buffer(product)
            
            # 2. AGV取原料
            yield env.process(agv.move_to(raw_material.position))
            success, feedback, _ = yield env.process(agv.load_from(raw_material))
            print(f"取原料: {success}")
            
            # 3. AGV运输到成品仓库
            yield env.process(agv.move_to(warehouse.position))
            success, feedback, _ = yield env.process(agv.unload_to(warehouse))
            print(f"存成品: {success}")
            
            # 4. 短暂休息
            yield env.timeout(20)
            
        # 最终统计
        print(f"\n--- 生产完成统计 ---")
        raw_stats = raw_material.get_material_stats()
        warehouse_stats = warehouse.get_warehouse_stats()
        agv_stats = agv.get_battery_status()
        
        print(f"原料供应: {raw_stats['materials_supplied']} 个")
        print(f"成品收货: {warehouse_stats['products_received']} 个")
        print(f"AGV总里程: {agv_stats['stats']['total_distance']:.1f}m")
        print(f"AGV最终电量: {agv_stats['battery_level']:.1f}%")
        
    env.process(production_simulation())
    env.run(until=500)
    print("完整生产流程模拟完成\n")

if __name__ == "__main__":
    print("开始原料仓库和成品仓库测试\n")
    
    try:
        test_raw_material_basic()
        test_warehouse_basic()
        test_agv_integration()
        test_buffer_full_scenarios()
        test_production_flow_simulation()
        
        print("🎉 所有仓库功能测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc() 