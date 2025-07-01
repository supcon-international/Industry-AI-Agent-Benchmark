# src/simulation/factory.py
import simpy
import random
from typing import Dict, List, Tuple

from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.game_logic.kpi_calculator import KPICalculator
from src.game_logic.state_space_manager import ComplexStateSpaceManager
from src.utils.mqtt_client import MQTTClient

# This mock config will be replaced by a YAML loader later.
MOCK_LAYOUT_CONFIG = {
    'path_points': {
        'P0': (5, 20), 'P1': (12, 20), 'P2': (18, 20), 'P3': (32, 20),
        'P4': (38, 20), 'P5': (58, 20), 'P6': (72, 20), 'P7': (78, 20),
        'P8': (85, 20), 'P9': (10, 10)
    },
    'path_segments': [ # Defines one-way paths between points
        ('P0', 'P1'), ('P1', 'P2'), ('P2', 'P3'), ('P3', 'P4'), ('P4', 'P5'),
        ('P5', 'P6'), ('P6', 'P7'), ('P7', 'P8'),
        # Return paths (example)
        ('P2', 'P1'), ('P1', 'P0'),
    ],
    'stations': [
        {'id': 'StationA', 'position': (15, 20), 'buffer_size': 3, 'processing_times': {'P1': (30, 45), 'P2': (40, 60), 'P3': (35, 50)}},
        {'id': 'StationB', 'position': (35, 20), 'buffer_size': 3, 'processing_times': {'P1': (45, 60), 'P2': (60, 80), 'P3': (50, 70)}},
        {'id': 'StationC', 'position': (55, 20), 'buffer_size': 3, 'processing_times': {'P1': (20, 30), 'P2': (30, 40), 'P3': (25, 35)}},
        {'id': 'QualityCheck', 'position': (75, 20), 'buffer_size': 2, 'processing_times': {'P1': (15, 25), 'P2': (20, 30), 'P3': (20, 30)}},
    ],
    'agvs': [
        {'id': 'AGV_1', 'position': (10, 15), 'speed_mps': 2.0, 'battery_capacity': 100},
        {'id': 'AGV_2', 'position': (10, 25), 'speed_mps': 2.0, 'battery_capacity': 100},
    ]
}

class Factory:
    """
    The main class that orchestrates the entire factory simulation.
    """
    def __init__(self, layout_config: Dict, mqtt_client: MQTTClient):
        self.env = simpy.Environment()
        self.layout = layout_config
        self.mqtt_client = mqtt_client
        
        self.stations: Dict[str, Station] = {}
        self.agvs: Dict[str, AGV] = {}
        
        # Resources for AGV path collision avoidance
        self.path_points = self.layout['path_points']
        self.path_resources: Dict[str, simpy.Resource] = {}
        
        # Game logic components
        self.order_generator = OrderGenerator(self.env, self.mqtt_client)
        self.fault_system = FaultSystem(self.env)
        self.kpi_calculator = KPICalculator(self.env, self.mqtt_client)
        self.state_space_manager = ComplexStateSpaceManager(self.env, self, self.fault_system)
        
        self._create_devices()
        self._create_path_resources()
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Start device status publishing
        self._start_status_publishing()

    def _create_devices(self):
        """Instantiates all devices based on the layout configuration."""
        for station_cfg in self.layout['stations']:
            station = Station(self.env, **station_cfg)
            self.stations[station.id] = station
            
        for agv_cfg in self.layout['agvs']:
            # Set initial position based on a path point if not explicitly defined
            if 'position_id' in agv_cfg:
                agv_cfg['position'] = self.path_points[agv_cfg['position_id']]
            
            agv = AGV(self.env, **agv_cfg)
            self.agvs[agv.id] = agv

    def _create_path_resources(self):
        """Creates a SimPy resource for each path segment to manage access."""
        for start, end in self.layout['path_segments']:
            path_key = f"{start}_{end}"
            self.path_resources[path_key] = simpy.Resource(self.env, capacity=1)

    def move_agv(self, agv_id: str, start_point_id: str, end_point_id: str):
        """
        Manages the movement of an AGV along a single path segment,
        ensuring no collisions by using path resources.
        """
        agv = self.agvs[agv_id]
        path_key = f"{start_point_id}_{end_point_id}"
        
        if path_key not in self.path_resources:
            raise ValueError(f"Path segment {path_key} does not exist.")
            
        path_resource = self.path_resources[path_key]
        target_pos = self.path_points[end_point_id]

        print(f"[{self.env.now:.2f}] {agv_id}: Requesting path {path_key}")
        with path_resource.request() as req:
            yield req
            print(f"[{self.env.now:.2f}] {agv_id}: Acquired path {path_key}. Starting move.")
            
            # Use the AGV's own move_to method to perform the actual movement
            yield self.env.process(agv.move_to(target_pos, self.path_points))
        
        print(f"[{self.env.now:.2f}] {agv_id}: Released path {path_key}")

    def _setup_event_handlers(self):
        """Setup event handlers for order processing and fault handling."""
        # Register callback for new orders
        def on_new_order(order):
            self.kpi_calculator.register_new_order(order)
            print(f"[{self.env.now:.2f}] 📝 Registered order {order.order_id} for KPI tracking")
        
        # This would be called when orders are generated
        self.order_generator._publish_order = self._wrap_order_publisher(self.order_generator._publish_order, on_new_order)

    def _wrap_order_publisher(self, original_publish, callback):
        """Wrap the order publisher to trigger callbacks."""
        def wrapped_publisher(order):
            original_publish(order)
            callback(order)
        return wrapped_publisher

    def handle_maintenance_request(self, device_id: str, maintenance_type: str):
        """Handle maintenance requests from agents."""
        success, repair_time = self.fault_system.handle_maintenance_request(device_id, maintenance_type)
        self.kpi_calculator.add_maintenance_cost(device_id, maintenance_type, success)
        self.kpi_calculator.add_fault_recovery_time(repair_time)
        return success, repair_time

    def get_device_status(self, device_id: str) -> Dict:
        """Get comprehensive device status including faults."""
        if device_id in self.stations:
            station = self.stations[device_id]
            symptom = self.fault_system.get_device_symptom(device_id)
            return {
                'device_id': device_id,
                'status': 'error' if symptom else 'idle',  # Simplified
                'symptom': symptom,
                'buffer_level': len(station.buffer.items),
                'utilization': 0.75  # Mock value
            }
        elif device_id in self.agvs:
            agv = self.agvs[device_id]
            symptom = self.fault_system.get_device_symptom(device_id)
            return {
                'device_id': device_id,
                'status': 'error' if symptom else 'idle',
                'symptom': symptom,
                'position': agv.position,
                'battery_level': agv.battery_level,
                'payload': agv.payload
            }
        return {}

    def _start_status_publishing(self):
        """Start processes to publish device status to MQTT."""
        # Start station status publishing
        for station_id in self.stations:
            self.env.process(self._publish_station_status(station_id))
        
        # Start AGV status publishing  
        for agv_id in self.agvs:
            self.env.process(self._publish_agv_status(agv_id))
        
        # Start factory overall status publishing
        self.env.process(self._publish_factory_status())
        
        # Start enhanced fault events publishing  
        self.env.process(self._publish_enhanced_fault_events())
    
    def _publish_station_status(self, station_id: str):
        """Publish station status every 10 seconds."""
        while True:
            yield self.env.timeout(10.0)  # Publish every 10 seconds
            
            station = self.stations[station_id]
            symptom = self.fault_system.get_device_symptom(station_id)
            
            # Create status message
            from config.schemas import StationStatus
            from config.topics import get_station_status_topic
            
            status = StationStatus(
                timestamp=self.env.now,
                source_id=station_id,
                status=station.status,
                utilization=0.75,  # Mock utilization
                buffer_level=len(station.buffer.items),
                symptom=symptom
            )
            
            topic = get_station_status_topic(station_id)
            try:
                self.mqtt_client.publish(topic, status)
                print(f"[{self.env.now:.2f}] 📡 Published {station_id} status: {station.status.value}")
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Failed to publish {station_id} status: {e}")
    
    def _publish_agv_status(self, agv_id: str):
        """Publish AGV status every 10 seconds."""
        while True:
            yield self.env.timeout(10.0)  # Publish every 10 seconds
            
            agv = self.agvs[agv_id]
            
            # Create status message
            from config.schemas import AGVStatus
            from config.topics import get_agv_status_topic
            
            status = AGVStatus(
                timestamp=self.env.now,
                source_id=agv_id,
                position={'x': agv.position[0], 'y': agv.position[1]},
                battery_level=agv.battery_level,
                payload=[],  # Mock empty payload for now
                is_charging=agv.is_charging
            )
            
            topic = get_agv_status_topic(agv_id)
            try:
                self.mqtt_client.publish(topic, status)
                print(f"[{self.env.now:.2f}] 📡 Published {agv_id} status: {agv.status.value}, pos: {agv.position}")
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Failed to publish {agv_id} status: {e}")

    def _publish_factory_status(self):
        """Publish factory overall status every 30 seconds."""
        while True:
            yield self.env.timeout(30.0)  # Publish every 30 seconds
            
            # Create factory status summary
            from config.topics import FACTORY_STATUS_TOPIC
            from config.schemas import FactoryStatus
            
            factory_status = FactoryStatus(
                timestamp=self.env.now,
                total_stations=len(self.stations),
                total_agvs=len(self.agvs),
                active_orders=len(self.kpi_calculator.active_orders),
                total_orders=self.kpi_calculator.stats.total_orders,
                completed_orders=self.kpi_calculator.stats.completed_orders,
                active_faults=len(self.fault_system.active_faults),
                unique_states_observed=self.state_space_manager.get_state_space_statistics()['unique_states_observed'],
                simulation_time=self.env.now
            )
            
            try:
                self.mqtt_client.publish(FACTORY_STATUS_TOPIC, factory_status)
                print(f"[{self.env.now:.2f}] 📊 Published factory status: {factory_status.active_orders} active orders, {factory_status.active_faults} faults")
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Failed to publish factory status: {e}")

    def _publish_enhanced_fault_events(self):
        """Publish enhanced fault events to make them more visible."""
        while True:
            yield self.env.timeout(5.0)  # Check for faults every 5 seconds
            
            # If there are active faults, publish them more frequently
            for device_id, fault in self.fault_system.active_faults.items():
                # Create a simple fault alert message
                fault_alert = f"FAULT_ALERT:{device_id}:{fault.symptom}:duration_{self.env.now - fault.start_time:.1f}s"
                
                try:
                    self.mqtt_client.publish(f"factory/alerts/{device_id}", fault_alert)
                    print(f"[{self.env.now:.2f}] 🚨 Fault alert published for {device_id}: {fault.symptom}")
                except Exception as e:
                    print(f"[{self.env.now:.2f}] ❌ Failed to publish fault alert: {e}")

    def get_state_space_statistics(self) -> Dict:
        """Get comprehensive state space statistics."""
        return self.state_space_manager.get_state_space_statistics()

    def get_current_state_vector(self):
        """Get the current state vector for analysis."""
        return self.state_space_manager.get_state_vector()

    def run(self, until: int):
        """Runs the simulation for a given duration."""
        print(f"--- Factory simulation starting for {until} seconds ---")
        # Here we will later add processes for order generation, MQTT publishing etc.
        self.env.run(until=until)
        print("--- Factory simulation finished ---")


# Example of how to run the factory simulation
if __name__ == '__main__':
    from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT
    )
    factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
    
    # Example usage: create a dummy process to test AGV movement
    def test_agv_movement(factory_env):
        # Move AGV_1 from P0 to P1
        p0 = factory.path_points['P0']
        factory.agvs['AGV_1'].position = p0
        yield factory_env.process(factory.move_agv('AGV_1', 'P0', 'P1'))

        # Try to move AGV_2 on the same path, it should wait if AGV_1 is slow
        # (for this test, we just start it right after)
        p0_agv2 = factory.path_points['P0']
        factory.agvs['AGV_2'].position = p0_agv2
        factory_env.process(factory.move_agv('AGV_2', 'P0', 'P1'))

    factory.env.process(test_agv_movement(factory.env))
    factory.run(until=100) 