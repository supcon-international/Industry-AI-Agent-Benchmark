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
from src.unity_interface.real_time_publisher import RealTimePublisher

# Import configuration loader
from src.utils.config_loader import get_legacy_layout_config

# Load configuration from YAML file instead of hardcoding
def get_layout_config():
    """Get factory layout configuration from YAML file."""
    try:
        return get_legacy_layout_config()
    except Exception as e:
        print(f"Warning: Failed to load configuration from YAML, using fallback: {e}")
        # Fallback to original hardcoded config if YAML loading fails
        return {
    'path_points': {
        'P0': (5, 20), 'P1': (12, 20), 'P2': (18, 20), 'P3': (32, 20),
        'P4': (38, 20), 'P5': (58, 20), 'P6': (72, 20), 'P7': (78, 20),
        'P8': (85, 20), 'P9': (10, 10)
    },
            'path_segments': [ 
        ('P0', 'P1'), ('P1', 'P2'), ('P2', 'P3'), ('P3', 'P4'), ('P4', 'P5'),
        ('P5', 'P6'), ('P6', 'P7'), ('P7', 'P8'),
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

# For backward compatibility, provide the same interface
MOCK_LAYOUT_CONFIG = get_layout_config()

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
        
        # Create devices first
        self._create_devices()
        self._create_path_resources()
        
        # Create a combined devices dictionary for fault system
        self.all_devices = {}
        self.all_devices.update(self.stations)
        self.all_devices.update(self.agvs)
        
        # Game logic components (fault system needs device references)
        self.order_generator = OrderGenerator(self.env, self.mqtt_client)
        self.fault_system = FaultSystem(self.env, self.all_devices)  # 传递设备引用
        self.kpi_calculator = KPICalculator(self.env, self.mqtt_client)
        self.state_space_manager = ComplexStateSpaceManager(self.env, self, self.fault_system)
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Start device status publishing
        self._start_status_publishing()
        
        # Start Unity real-time publishing (high frequency updates)
        self.unity_publisher = RealTimePublisher(self.env, self.mqtt_client, self)
        print(f"[{self.env.now:.2f}] 🎮 Unity real-time publisher initialized (100ms AGV updates)")

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

    def handle_maintenance_request(self, device_id: str, maintenance_type: str, agent_id: str = "unknown"):
        """Handle maintenance requests from agents using new diagnosis system."""
        # Use the enhanced fault system's maintenance handling
        diagnosis_result = self.fault_system.handle_maintenance_request(device_id, maintenance_type, agent_id)
        
        # Update KPI tracking with the new result structure
        self.kpi_calculator.add_maintenance_cost(device_id, maintenance_type, diagnosis_result.is_correct)
        self.kpi_calculator.add_fault_recovery_time(diagnosis_result.repair_time)
        
        # Track diagnosis accuracy for KPI (could be extended later)
        # TODO: Add diagnosis result tracking to KPI calculator if needed
        
        return diagnosis_result

    def inspect_device(self, device_id: str):
        """
        Inspect a device to get detailed status information.
        This delegates to the fault system and returns current device state.
        """
        return self.fault_system.inspect_device(device_id)

    def skip_repair_time(self, device_id: str) -> bool:
        """
        Skip the repair/penalty time for a device.
        This allows players to continue operating other devices.
        """
        return self.fault_system.skip_repair_time(device_id)

    def get_available_devices(self) -> List[str]:
        """
        Get list of devices that can currently be operated (not frozen).
        """
        return self.fault_system.get_available_devices()

    def get_device_status(self, device_id: str) -> Dict:
        """Get comprehensive device status including faults."""
        if device_id in self.all_devices:
            device = self.all_devices[device_id]
            detailed_status = device.get_detailed_status()
            
            # Convert to simplified status format for compatibility
            status_dict = {
                'device_id': device_id,
                'device_type': detailed_status.device_type,
                'status': detailed_status.current_status.value,
                'has_fault': detailed_status.has_fault,
                'symptom': detailed_status.fault_symptom,
                'temperature': detailed_status.temperature,
                'efficiency_rate': detailed_status.efficiency_rate,
                'can_operate': device.can_operate(),
                'frozen_until': detailed_status.frozen_until
            }
            
            # Add device-specific information
            if device_id in self.stations:
                status_dict.update({
                    'buffer_level': self.stations[device_id].get_buffer_level(),
                    'precision_level': detailed_status.precision_level,
                    'tool_wear_level': detailed_status.tool_wear_level
                })
            elif device_id in self.agvs:
                agv = self.agvs[device_id]
                status_dict.update({
                    'position': {'x': agv.position[0], 'y': agv.position[1]},
                    'battery_level': detailed_status.battery_level,
                    'position_accuracy': detailed_status.position_accuracy,
                    'payload': agv.payload if hasattr(agv, 'payload') else []
                })
            
            return status_dict
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
            device_status = self.get_device_status(station_id)
            
            # Create status message
            from config.schemas import StationStatus
            from config.topics import get_station_status_topic
            
            status = StationStatus(
                timestamp=self.env.now,
                source_id=station_id,
                status=station.status,
                utilization=device_status.get('efficiency_rate', 75.0) / 100.0,  # Convert to 0-1 range
                buffer_level=device_status.get('buffer_level', 0),
                symptom=device_status.get('symptom')
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
            device_status = self.get_device_status(agv_id)
            
            # Create status message
            from config.schemas import AGVStatus
            from config.topics import get_agv_status_topic
            
            status = AGVStatus(
                timestamp=self.env.now,
                source_id=agv_id,
                position=device_status.get('position', {'x': agv.position[0], 'y': agv.position[1]}),
                battery_level=device_status.get('battery_level', 80.0),
                payload=device_status.get('payload', []),
                is_charging=getattr(agv, 'is_charging', False)
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
                # Create a detailed fault alert message
                device_status = self.get_device_status(device_id)
                
                fault_alert = {
                    "device_id": device_id,
                    "fault_type": fault.fault_type.value,
                    "symptom": fault.symptom,
                    "duration_seconds": self.env.now - fault.start_time,
                    "device_status": device_status.get('status'),
                    "can_operate": device_status.get('can_operate', False),
                    "frozen_until": device_status.get('frozen_until'),
                    "timestamp": self.env.now
                }
                
                try:
                    import json
                    self.mqtt_client.publish(f"factory/alerts/{device_id}", json.dumps(fault_alert))
                    print(f"[{self.env.now:.2f}] 🚨 Enhanced fault alert published for {device_id}: {fault.symptom}")
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
        print(f"--- Available devices: {', '.join(self.all_devices.keys())} ---")
        print(f"--- Use 'inspect_device', 'skip_repair_time', 'request_maintenance' commands ---")
        
        # Core simulation processes are already started in __init__:
        # - Order generation: self.order_generator.run() (auto-started)
        # - Fault injection: self.fault_system.run_fault_injection() (auto-started) 
        # - KPI updates: self.kpi_calculator.run_kpi_updates() (auto-started)
        # - MQTT publishing: self._start_status_publishing() (started in __init__)
        # - State evolution: self.state_space_manager._evolve_states() (auto-started)
        
        print(f"--- Active processes: Order Gen, Fault Injection, KPI Updates, MQTT Publishing ---")
        self.env.run(until=until)
        print("--- Factory simulation finished ---")


# Example of how to run the factory simulation
if __name__ == '__main__':
    from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
    mqtt_client = MQTTClient(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT,
        client_id="factory_test"
    )
    # 连接MQTT broker
    mqtt_client.connect()
    print(f"✅ Connected to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    
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