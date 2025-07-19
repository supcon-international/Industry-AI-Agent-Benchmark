import simpy
import time
from src.simulation.entities.station import Station
from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from src.simulation.entities.quality_checker import QualityChecker
from src.simulation.entities.product import Product
from src.utils.mqtt_client import MQTTClient
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from config.schemas import DeviceStatus

def test_conveyor_blocking():
    """测试传送带阻塞逻辑"""
    env = simpy.Environment()
    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT,
        client_id="blocking_test"
    )
    mqtt_client.connect()
    time.sleep(0.5)
    
    # 创建设备
    station_a = Station(
        env, "StationA", (0, 0), buffer_size=5,
        processing_times={"P1": (1, 1)},  # 快速处理
        mqtt_client=mqtt_client
    )
    
    station_b = Station(
        env, "StationB", (1, 0), buffer_size=1,  # 小容量，容易满
        processing_times={"P1": (30, 30)},  # 慢速处理
        mqtt_client=mqtt_client
    )
    
    conveyor = Conveyor(
        env, id="Conveyor_AB", capacity=5,  # 可以容纳多个产品
        position=(5, 0), transfer_time=5,  # 5秒传输时间
        mqtt_client=mqtt_client
    )

    station_c = Station(
        env, id="StationC", buffer_size=1,  # 可以容纳多个产品
        position=(5, 0), processing_times={"P1": (1, 1)}, 
        mqtt_client=mqtt_client
    )

    conveyor_cq = TripleBufferConveyor(
        env, id="Conveyor_CQ", main_capacity=4, upper_capacity=2, lower_capacity=2,  # 可以容纳多个产品
        position=(5, 0), transfer_time=5,  # 5秒传输时间
        mqtt_client=mqtt_client
    )

    qualtity_check = QualityChecker(
        env, id="QualityCheckStation", buffer_size=1,  # 可以容纳多个产品
        position=(5, 0), processing_times={"P1": (30, 30)}, 
        mqtt_client=mqtt_client
    )
    
    # 设置连接
    station_a.downstream_conveyor = conveyor
    conveyor.set_downstream_station(station_b)

    station_c.downstream_conveyor = conveyor_cq
    conveyor_cq.set_downstream_station(qualtity_check)
    
    # 监控进程
    def monitor():
        while True:
            yield env.timeout(2)
            print(f"\n[{env.now:.2f}] 📊 系统状态:")
            print(f"  - StationA: {station_a.status.value}, Buffer: {len(station_a.buffer.items)}")
            print(f"  - Conveyor_CQ: {conveyor_cq.status.value}, Buffer: {[p.id for p in conveyor_cq.main_buffer.items]}, 活跃: {len(conveyor_cq.active_processes)}")
            print(f"  - StationB: {station_b.status.value}, Buffer: {len(station_b.buffer.items)}")
            print(f"  - StationC: {station_c.status.value}, Buffer: {len(station_c.buffer.items)}")
            print(f"  - QualityCheckStation: {qualtity_check.status.value}, Buffer: {len(qualtity_check.buffer.items)}")
            print(f"  - 传送带阻塞状态: {'是' if conveyor_cq.status == DeviceStatus.BLOCKED else '否'}")
    
    # 测试场景
    def test_scenario():
        # 快速生成多个产品
        products = []
        for i in range(6):
            p = Product("P1", f"blocking_test_{i}")
            products.append(p)
            print(f"\n[{env.now:.2f}] 🏭 生成产品: {p.id}")
            yield station_c.buffer.put(p)
            yield env.timeout(1)  # 间隔1秒
        
        # 等待观察阻塞效果
        yield env.timeout(30)
        
        print(f"\n[{env.now:.2f}] 🎯 测试完成")
        print(f"最终状态:")
        print(f"  - 产品位置分布:")
        for p in products:
            if hasattr(p, 'current_location'):
                print(f"    - {p.id}: {p.current_location}")
    
    # 启动进程
    env.process(monitor())
    env.process(test_scenario())
    
    # 运行仿真
    print("\n🚀 开始传送带阻塞测试...\n")
    env.run(until=60)
    
    print(f"\n✅ 测试完成，总时间: {env.now:.2f}秒")
    mqtt_client.disconnect()

if __name__ == '__main__':
    test_conveyor_blocking()