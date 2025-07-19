import simpy
import time
import logging
from src.simulation.entities.station import Station
from src.simulation.entities.conveyor import Conveyor
from src.simulation.entities.product import Product
from src.utils.mqtt_client import MQTTClient
from src.game_logic.fault_system import FaultSystem, FaultType
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def monitor_station_status(env, station, interval=2):
    """监控站点状态的进程"""
    while True:
        yield env.timeout(interval)
        print(f"[{env.now:.2f}] 📊 {station.id} - 状态: {station.status.value}, "
              f"Buffer产品数: {len(station.buffer.items)}, "
              f"当前处理产品: {station.current_product_id}")

def test_station_fault_multiple_interrupts():
    """测试站点的多次故障中断和恢复"""
    env = simpy.Environment()
    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT,
        client_id="station_fault_test"
    )
    
    # 连接MQTT
    mqtt_client.connect()
    time.sleep(1)
    
    # 创建设备
    station_a = Station(
        env, "StationA", (0, 0), buffer_size=5,
        processing_times={"P1": (20, 20)},  # 固定20秒处理时间，便于测试
        mqtt_client=mqtt_client
    )
    
    station_b = Station(
        env, "StationB", (1, 0), buffer_size=5,
        processing_times={"P1": (10, 10)},
        mqtt_client=mqtt_client
    )
    
    conveyor = Conveyor(
        env, id="Conveyor_AB", capacity=3,
        position=(0.5, 0), transfer_time=5,
        mqtt_client=mqtt_client
    )
    
    # 设置连接
    station_a.downstream_conveyor = conveyor
    conveyor.set_downstream_station(station_b)
    
    # 创建故障系统
    factory_devices = {
        "StationA": station_a,
        "StationB": station_b,
        "Conveyor_AB": conveyor
    }
    fault_system = FaultSystem(env, factory_devices, mqtt_client)
    
    # 产品生成和多次故障注入
    def test_scenario():
        # 生成一个产品
        p = Product("P1", "test_product_multi_interrupt")
        print(f"\n[{env.now:.2f}] 🏭 生成产品: {p.id}")
        yield station_a.buffer.put(p)
        
        # 等待产品开始处理
        yield env.timeout(2)
        
        # 第一次故障注入（5秒后）
        print(f"\n{'='*60}")
        print(f"[{env.now:.2f}] 🔴 第一次注入站点故障（持续5秒）")
        print(f"{'='*60}")
        fault_system._inject_fault_now("StationA", FaultType.STATION_FAULT, 5)
        
        # 等待故障恢复
        yield env.timeout(6)
        print(f"[{env.now:.2f}] ✅ 第一次故障已恢复")
        
        # 等待继续处理
        yield env.timeout(3)
        
        # 第二次故障注入
        print(f"\n{'='*60}")
        print(f"[{env.now:.2f}] 🔴 第二次注入站点故障（持续4秒）")
        print(f"{'='*60}")
        fault_system._inject_fault_now("StationA", FaultType.STATION_FAULT, 4)
        
        # 等待故障恢复
        yield env.timeout(5)
        print(f"[{env.now:.2f}] ✅ 第二次故障已恢复")
        
        # 等待产品处理完成
        yield env.timeout(15)
        
        # 检查最终状态
        print(f"\n[{env.now:.2f}] 🎯 最终状态:")
        print(f"  - StationA buffer: {[p.id for p in station_a.buffer.items]}")
        print(f"  - Conveyor buffer: {[p.id for p in conveyor.buffer.items]}")
        print(f"  - StationB buffer: {[p.id for p in station_b.buffer.items]}")
    
    # 启动进程
    env.process(test_scenario())
    env.process(monitor_station_status(env, station_a))
    
    # 运行仿真
    print("\n🚀 开始站点多次故障测试...\n")
    for i in range(50):
        env.run(until=env.now + 1.0)
        time.sleep(0.1)
    
    print(f"\n✅ 测试完成，总时间: {env.now:.2f}秒")
    mqtt_client.disconnect()

def test_station_vs_conveyor_fault():
    """对比测试站点和传送带的故障处理"""
    env = simpy.Environment()
    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT,
        client_id="comparison_test"
    )
    
    # 连接MQTT
    mqtt_client.connect()
    time.sleep(1)
    
    # 创建设备
    station_a = Station(
        env, "StationA", (0, 0), buffer_size=5,
        processing_times={"P1": (10, 10)},  # 10秒处理时间
        mqtt_client=mqtt_client
    )
    
    station_b = Station(
        env, "StationB", (1, 0), buffer_size=5,
        processing_times={"P1": (10, 10)},
        mqtt_client=mqtt_client
    )
    
    conveyor = Conveyor(
        env, id="Conveyor_AB", capacity=3,
        position=(0.5, 0), transfer_time=10,  # 10秒传输时间
        mqtt_client=mqtt_client
    )
    
    # 设置连接
    station_a.downstream_conveyor = conveyor
    conveyor.set_downstream_station(station_b)
    
    # 创建故障系统
    factory_devices = {
        "StationA": station_a,
        "StationB": station_b,
        "Conveyor_AB": conveyor
    }
    fault_system = FaultSystem(env, factory_devices, mqtt_client)
    
    # 测试场景
    def comparison_scenario():
        # 生成两个产品
        p1 = Product("P1", "product_for_station")
        p2 = Product("P1", "product_for_conveyor")
        
        print(f"\n[{env.now:.2f}] 🏭 生成产品: {p1.id} 和 {p2.id}")
        yield station_a.buffer.put(p1)
        yield station_a.buffer.put(p2)
        
        # 等待第一个产品进入站点处理，第二个产品进入传送带
        yield env.timeout(12)
        
        # 同时注入两个故障
        print(f"\n{'='*60}")
        print(f"[{env.now:.2f}] 🔴 同时注入站点和传送带故障（持续8秒）")
        print(f"{'='*60}")
        
        fault_system._inject_fault_now("StationA", FaultType.STATION_FAULT, 8)
        fault_system._inject_fault_now("Conveyor_AB", FaultType.CONVEYOR_FAULT, 8)
        
        # 监控故障期间状态
        for i in range(4):
            yield env.timeout(2)
            print(f"\n[{env.now:.2f}] 📊 故障期间状态检查 {i+1}:")
            print(f"  - StationA: 状态={station_a.status.value}, 处理产品={station_a.current_product_id}")
            print(f"  - Conveyor: 状态={conveyor.status.value}, 活跃进程={list(conveyor.active_processes.keys())}")
        
        # 等待故障恢复
        yield env.timeout(2)
        print(f"\n[{env.now:.2f}] ✅ 故障已恢复")
        
        # 等待处理完成
        yield env.timeout(20)
    
    # 启动进程
    env.process(comparison_scenario())
    
    # 运行仿真
    print("\n🚀 开始站点与传送带故障对比测试...\n")
    for i in range(60):
        env.run(until=env.now + 1.0)
        time.sleep(0.1)
    
    print(f"\n✅ 测试完成，总时间: {env.now:.2f}秒")
    mqtt_client.disconnect()

if __name__ == '__main__':
    print("选择测试场景:")
    print("1. 测试站点多次故障中断")
    print("2. 对比站点和传送带故障处理")
    
    choice = input("请输入选择 (1 或 2): ")
    
    if choice == "1":
        test_station_fault_multiple_interrupts()
    elif choice == "2":
        test_station_vs_conveyor_fault()
    else:
        print("无效选择，运行默认测试")
        test_station_fault_multiple_interrupts()