import simpy
from src.simulation.entities.station import Station
from src.simulation.entities.quality_checker import QualityChecker
from src.simulation.entities.conveyor import TripleBufferConveyor, Conveyor
from src.game_logic.fault_system import FaultSystem
from src.simulation.entities.product import Product

class DummyMqttClient:
    def publish(self, topic, payload):
        print(f"[MQTT] {topic}: {payload}")

def agv_pickup_q_output(env, qc, interval=15):
    """模拟AGV定时搬运QualityChecker output buffer"""
    while True:
        if len(qc.output_buffer.items) > 0:
            product = yield qc.output_buffer.get()
            print(f"[{env.now:.2f}] 🚚 AGV搬运出厂产品: {product.id}")
        yield env.timeout(interval)

def test_buffer_full_alert():
    env = simpy.Environment()
    mqtt_client = DummyMqttClient()
    factory_devices = {}
    fault_system = FaultSystem(env, factory_devices, mqtt_client)

    # StationC
    station_a = Station(
        env, "StationA", (2, 0), buffer_size=1,
        processing_times={"P1": (20, 30), "P2": (20, 30), "P3": (25, 35)},
        fault_system=fault_system
    )
    station_b = Station(
        env, "StationB", (2, 0), buffer_size=1,
        processing_times={"P1": (20, 30), "P2": (20, 30), "P3": (25, 35)},
        fault_system=fault_system
    )
    station_c = Station(
        env, "StationC", (2, 0), buffer_size=1,
        processing_times={"P1": (20, 30), "P2": (20, 30), "P3": (25, 35)},
        fault_system=fault_system
    )
    # TripleBufferConveyor
    conveyor_1 = Conveyor(env, id="conveyor_1", capacity=3)
    conveyor_2 = Conveyor(env, id="conveyor_2", capacity=3)
    conveyor_3 = TripleBufferConveyor(env, id="conveyor_3", main_capacity=2, upper_capacity=1, lower_capacity=1)
    # conveyor.set_downstream_station = lambda x: None  # 不自动流转
    station_a.downstream_conveyor = conveyor_1
    station_b.downstream_conveyor = conveyor_2
    station_c.downstream_conveyor = conveyor_3

    # QualityChecker
    qc = QualityChecker(
        env, "QualityCheck", (3, 0), buffer_size=1,
        processing_times={"P1": (2, 3), "P2": (2, 3), "P3": (2, 3)},
        output_buffer_capacity=2,
        fault_system=fault_system
    )
    conveyor_1.set_downstream_station(station_b)
    conveyor_2.set_downstream_station(station_c)
    conveyor_3.set_downstream_station(qc)


    # 绑定到factory_devices便于fault_system管理
    factory_devices["StationA"] = station_a
    factory_devices["StationB"] = station_b
    factory_devices["StationC"] = station_c
    factory_devices["QualityCheck"] = qc

    # 产品流转流程
    def product_flow(env):
        for i in range(6):
            p = Product("P3", f"order_{i}")
            print(f"[{env.now:.2f}] 订单生成: {p.id}")
            # 放入StationC
            yield station_a.buffer.put(p)
            yield env.timeout(1)

    # 启动AGV搬运进程
    env.process(agv_pickup_q_output(env, qc, interval=10))
    # 启动产品流转
    env.process(product_flow(env))

    # 运行仿真
    env.run(until=100)

if __name__ == '__main__':
    test_buffer_full_alert()