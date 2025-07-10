#!/usr/bin/env python3
"""
整条生产线仿真测试
测试order_generator、warehouse、agv的完整集成
"""

import simpy
import sys
import os
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.entities.warehouse import RawMaterial, Warehouse
from src.simulation.entities.agv import AGV
from src.simulation.entities.station import Station
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.utils.mqtt_client import MQTTClient

def test_whole_line_simulation():
    """测试完整生产线仿真"""
    print("=" * 60)
    print("🏭 整条生产线仿真测试")
    print("=" * 60)
    
    # 创建仿真环境
    env = simpy.Environment()
    # 创建MQTT客户端（模拟）
    mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
    fault_system = FaultSystem(env, factory_devices={}, mqtt_client=mqtt_client)
    
    # 创建原料仓库和成品仓库
    raw_material = RawMaterial(env, "RAW_001", (5, 20))
    warehouse = Warehouse(env, "WAREHOUSE_001", (85, 20))
    
    # 创建一个简单的工站用于测试
    station_a = Station(
        env=env,
        id="STATION_A",
        position=(30, 20),
        buffer_size=5,
        processing_times={"P1": (30, 30), "P2": (40, 40), "P3": (35, 35)},
        fault_system=fault_system
    )
    
    # 创建AGV
    agv = AGV(
        env=env,
        id="AGV_001",
        position=(10, 10),
        speed_mps=2.0,
        payload_capacity=1,
        fault_system=fault_system
    )
    
    # 创建订单生成器
    order_generator = OrderGenerator(
        env=env,
        mqtt_client=mqtt_client,
        raw_material=raw_material
    )
    
    # 启动所有设备的运行进程
    env.process(raw_material.run())
    env.process(warehouse.run())
    env.process(station_a.run())
    env.process(agv.auto_charge_if_needed())  # AGV自动充电检查
    
    # 添加一个简单的AGV工作流程
    def agv_simple_workflow():
        """简单的AGV工作流程：从原料仓库取货 → 送到工站 → 等待加工 → 送到成品仓库"""
        while True:
            try:
                # 等待原料仓库有货
                while raw_material.get_buffer_level() == 0:
                    yield env.timeout(5)
                
                print(f"\n[{env.now:.2f}] 🚛 {agv.id}: 开始新的工作流程")
                
                # 1. 移动到原料仓库
                yield env.process(agv.move_to(raw_material.position))
                
                # 2. 从原料仓库取货
                success, feedback, product = yield env.process(agv.load_from(raw_material))
                if not success:
                    print(f"[{env.now:.2f}] ❌ {feedback}")
                    yield env.timeout(10)
                    continue
                print(f"[{env.now:.2f}] ✅ {feedback}")
                
                # 3. 移动到工站
                yield env.process(agv.move_to(station_a.position))
                
                # 4. 将产品卸载到工站
                success, feedback, product = yield env.process(agv.unload_to(station_a))
                if not success:
                    print(f"[{env.now:.2f}] ❌ {feedback}")
                    yield env.timeout(10)
                    continue
                print(f"[{env.now:.2f}] ✅ {feedback}")
                
                # 5. 等待工站处理完成（检查output buffer）
                processed_product = None
                wait_time = 0
                while processed_product is None and wait_time < 300:  # 最多等5分钟
                    yield env.timeout(10)
                    wait_time += 10
                    if station_a.get_buffer_level() > 0:
                        # 6. 从工站取走处理好的产品
                        success, feedback, processed_product = yield env.process(agv.load_from(station_a))
                        if success:
                            print(f"[{env.now:.2f}] ✅ {feedback}")
                            break
                
                if processed_product is None:
                    print(f"[{env.now:.2f}] ⏰ 等待工站处理超时")
                    continue
                
                # 7. 移动到成品仓库
                yield env.process(agv.move_to(warehouse.position))
                
                # 8. 将成品卸载到仓库
                success, feedback, final_product = yield env.process(agv.unload_to(warehouse))
                if success:
                    print(f"[{env.now:.2f}] ✅ {feedback}")
                    print(f"[{env.now:.2f}] 🎉 完成一个完整的生产流程！")
                else:
                    print(f"[{env.now:.2f}] ❌ {feedback}")
                
                # 休息一下
                yield env.timeout(5)
                
            except Exception as e:
                print(f"[{env.now:.2f}] 💥 AGV工作流程出错: {e}")
                yield env.timeout(30)
    
    # 启动AGV工作流程
    env.process(agv_simple_workflow())
    
    # 运行仿真
    print(f"[{env.now:.2f}] 🚀 开始仿真...")
    try:
        env.run(until=600)  # 运行10分钟
    except Exception as e:
        print(f"仿真运行出错: {e}")
    
    # 打印最终统计
    print("\n" + "=" * 60)
    print("📊 最终统计结果")
    print("=" * 60)
    
    print(f"\n🏭 原料仓库统计:")
    raw_stats = raw_material.get_material_stats()
    for key, value in raw_stats.items():
        print(f"  {key}: {value}")
    
    print(f"\n🏪 成品仓库统计:")
    warehouse_stats = warehouse.get_warehouse_stats()
    for key, value in warehouse_stats.items():
        print(f"  {key}: {value}")
    
    quality_summary = warehouse.get_quality_summary()
    print(f"\n📈 质量汇总:")
    for key, value in quality_summary.items():
        print(f"  {key}: {value}")
    
    print(f"\n🏭 工站A统计:")
    station_stats = station_a.get_processing_stats()
    for key, value in station_stats.items():
        print(f"  {key}: {value}")
    
    print(f"\n🚛 AGV统计:")
    agv_stats = agv.get_battery_status()
    for key, value in agv_stats.items():
        if key != "stats":
            print(f"  {key}: {value}")
    
    agv_charge_stats = agv.get_charging_stats()
    print(f"\n🔋 AGV充电统计:")
    for key, value in agv_charge_stats.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    test_whole_line_simulation() 