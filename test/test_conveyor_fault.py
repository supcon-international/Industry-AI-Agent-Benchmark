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

def monitor_conveyor_status(env, conveyor, interval=2):
    """监控传送带状态的进程"""
    while True:
        yield env.timeout(interval)
        print(f"[{env.now:.2f}] 📊 {conveyor.id} - 状态: {conveyor.status.value}, "
              f"Buffer产品数: {len(conveyor.buffer.items)}, "
              f"活跃进程数: {len(conveyor.active_processes)}")

def test_conveyor_fault_simple():
    """简单测试传送带故障功能"""
    env = simpy.Environment()
    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT,
        client_id="conveyor_fault_test"
    )
    
    # 连接MQTT
    mqtt_client.connect()
    time.sleep(1)  # 等待连接
    
    # 创建设备
    station_a = Station(
        env, "StationA", (0, 0), buffer_size=5,
        processing_times={"P1": (2, 3)},
        mqtt_client=mqtt_client
    )
    
    station_b = Station(
        env, "StationB", (1, 0), buffer_size=5,
        processing_times={"P1": (5, 10)},
        mqtt_client=mqtt_client
    )
    
    conveyor = Conveyor(
        env, id="Conveyor_AB", capacity=3, 
        position=(0, 0), transfer_time=15,
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
    
    # 产品生成进程
    def generate_products():
        for i in range(10):
            p = Product("P1", f"test_order_{i}")
            print(f"\n[{env.now:.2f}] 🏭 生成产品: {p.id}")
            yield station_a.buffer.put(p)
            yield env.timeout(3)
    
    # 故障注入进程
    def inject_faults():
        # 等待一些产品进入传送带
        yield env.timeout(10)
        
        print(f"\n{'='*60}")
        print(f"[{env.now:.2f}] 🔴 注入传送带故障（持续10秒）")
        print(f"{'='*60}")
        
        # 注入故障前的状态
        print(f"[{env.now:.2f}] 故障前 - Buffer产品: {[p.id for p in conveyor.buffer.items]}")
        print(f"[{env.now:.2f}] 故障前 - 活跃进程: {list(conveyor.active_processes.keys())}")
        
        # 注入故障
        fault_system._inject_fault_now("Conveyor_AB", FaultType.CONVEYOR_FAULT, 10)
        
        # 故障期间监控
        yield env.timeout(2)
        print(f"[{env.now:.2f}] 故障中 - Buffer产品: {[p.id for p in conveyor.buffer.items]}")
        print(f"[{env.now:.2f}] 故障中 - 活跃进程: {list(conveyor.active_processes.keys())}")
        
        # 等待故障恢复
        yield env.timeout(10)
        print(f"\n[{env.now:.2f}] ✅ 故障已恢复")
        print(f"[{env.now:.2f}] 恢复后 - Buffer产品: {[p.id for p in conveyor.buffer.items]}")
        print(f"[{env.now:.2f}] 恢复后 - 活跃进程: {list(conveyor.active_processes.keys())}")
    
    # 启动进程
    env.process(generate_products())
    env.process(inject_faults())
    env.process(monitor_conveyor_status(env, conveyor))
    
    # 运行仿真
    print("\n🚀 开始传送带故障测试...\n")
    for i in range(50):
        env.run(until=env.now + 1.0)
        time.sleep(0.1)
    
    print(f"\n✅ 测试完成，总时间: {env.now:.2f}秒")
    
    # 断开MQTT连接
    mqtt_client.disconnect()

if __name__ == '__main__':
    test_conveyor_fault_simple()