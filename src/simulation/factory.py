# src/simulation/factory.py
import simpy
import random
from typing import Dict, List, Tuple, Optional

from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.simulation.entities.quality_checker import QualityChecker
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.game_logic.kpi_calculator import KPICalculator
from src.game_logic.state_space_manager import ComplexStateSpaceManager
from src.utils.mqtt_client import MQTTClient
from src.unity_interface.real_time_publisher import RealTimePublisher
from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor

# Import configuration loader
from src.utils.config_loader import get_legacy_layout_config

# Load configuration from YAML file instead of hardcoding
def get_layout_config():
    """Get factory layout configuration from YAML file."""
    try:
        return get_legacy_layout_config()
    except Exception as e:
        print(f"Warning: Failed to load configuration from YAML, using fallback: {e}")

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
        
        # AGV task queue for product transportation
        self.agv_task_queue = simpy.Store(self.env)
        
        # Statistics for scrapped products
        self.scrap_stats = {
            "total_scrapped": 0,
            "scrap_by_station": {},
            "scrap_reasons": {}
        }
        
        self.conveyor_ab = Conveyor(self.env, capacity=5)  # A→B
        self.conveyor_bc = Conveyor(self.env, capacity=5)  # B→C
        self.conveyor_cq = TripleBufferConveyor(self.env, main_capacity=5, upper_capacity=3, lower_capacity=3)  # C→QualityCheck
        
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
        
        # Start AGV dispatcher
        self.env.process(self._agv_dispatcher())
        
        self._bind_conveyors_to_stations()
        self._setup_conveyor_downstreams()

    def _create_devices(self):
        """Instantiates all devices based on the layout configuration."""
        for station_cfg in self.layout['stations']:
            # 🔍 特殊处理QualityCheck工站，使用QualityChecker类
            if station_cfg['id'] == 'QualityCheck':
                station = QualityChecker(
                    env=self.env,
                    id=station_cfg['id'],
                    position=station_cfg['position'],
                    buffer_size=station_cfg['buffer_size'],
                    processing_times=station_cfg['processing_times']
                )
                print(f"[{self.env.now:.2f}] 🔍 Created QualityChecker: {station_cfg['id']}")
            else:
                # 创建普通工站，传入回调函数
                station = Station(
                    env=self.env,
                    product_transfer_callback=self._handle_product_transfer,
                    product_scrap_callback=self._handle_product_scrap,
                    **station_cfg
                )
                print(f"[{self.env.now:.2f}] 🏭 Created Station: {station_cfg['id']}")
                
            self.stations[station.id] = station
            
        for agv_cfg in self.layout['agvs']:
            # Set initial position based on a path point if not explicitly defined
            if 'position_id' in agv_cfg:
                agv_cfg['position'] = self.path_points[agv_cfg['position_id']]
            
            agv = AGV(self.env, **agv_cfg)
            self.agvs[agv.id] = agv
            print(f"[{self.env.now:.2f}] 🚛 Created AGV: {agv_cfg['id']}")

    def _handle_product_transfer(self, product, from_station_id: str, to_station_id: str):
        """Handle product transfer request from station - schedule AGV transport"""
        try:
            # Create transport task
            transport_task = {
                "type": "transport",
                "product": product,
                "from_station": from_station_id,
                "to_station": to_station_id,
                "timestamp": self.env.now,
                "priority": self._get_transport_priority(product, to_station_id)
            }
            
            # Add to AGV task queue
            yield self.agv_task_queue.put(transport_task)
            print(f"[{self.env.now:.2f}] 📋 Factory: 已安排AGV运输任务 - {product.id} 从 {from_station_id} 到 {to_station_id}")
            
        except Exception as e:
            print(f"[{self.env.now:.2f}] ❌ Factory: 产品转移任务创建失败: {e}")

    def _handle_product_scrap(self, product, station_id: str, reason: str):
        """Handle product scrapping notification - update statistics and KPIs"""
        try:
            # Update scrap statistics
            self.scrap_stats["total_scrapped"] += 1
            
            if station_id not in self.scrap_stats["scrap_by_station"]:
                self.scrap_stats["scrap_by_station"][station_id] = 0
            self.scrap_stats["scrap_by_station"][station_id] += 1
            
            if reason not in self.scrap_stats["scrap_reasons"]:
                self.scrap_stats["scrap_reasons"][reason] = 0
            self.scrap_stats["scrap_reasons"][reason] += 1
            
            # Notify KPI calculator about scrapped product (if method exists)
            # Note: register_scrapped_product method may not be implemented yet
            # if hasattr(self.kpi_calculator, 'register_scrapped_product'):
            #     self.kpi_calculator.register_scrapped_product(product, station_id, reason)
            
            # Publish scrap event to MQTT for Unity visualization
            scrap_event = {
                "timestamp": self.env.now,
                "product_id": product.id,
                "product_type": product.product_type,
                "station_id": station_id,
                "reason": reason,
                "total_scrapped": self.scrap_stats["total_scrapped"]
            }
            
            import json
            topic = f"factory/events/product_scrapped"
            self.mqtt_client.publish(topic, json.dumps(scrap_event))
            
            print(f"[{self.env.now:.2f}] 📊 Factory: 产品报废统计已更新 - 总计: {self.scrap_stats['total_scrapped']}")
            
        except Exception as e:
            print(f"[{self.env.now:.2f}] ❌ Factory: 产品报废处理失败: {e}")
        
        # Simulate scrap processing time
        yield self.env.timeout(1.0)

    def _get_transport_priority(self, product, to_station_id: str) -> int:
        """Calculate transport priority based on product and destination"""
        priority = 5  # Default priority
        
        # Higher priority for quality check station
        if to_station_id == "QualityCheck":
            priority = 3
        
        # Higher priority for rework products
        if product.rework_count > 0:
            priority = 2
        
        # Highest priority for urgent orders (if implemented)
        # if hasattr(product, 'urgent') and product.urgent:
        #     priority = 1
        
        return priority

    def _agv_dispatcher(self):
        """AGV dispatcher that assigns transport tasks to available AGVs"""
        while True:
            try:
                # Wait for a transport task
                task = yield self.agv_task_queue.get()
                
                # Find an available AGV
                available_agv = self._find_available_agv()
                
                if available_agv:
                    # Assign the task to the AGV
                    self.env.process(self._execute_transport_task(available_agv, task))
                else:
                    # No AGV available, put task back in queue
                    print(f"[{self.env.now:.2f}] ⏳ AGV Dispatcher: 无可用AGV，任务重新排队")
                    yield self.agv_task_queue.put(task)
                    yield self.env.timeout(5.0)  # Wait before retrying
                    
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ AGV Dispatcher: 调度失败: {e}")
                yield self.env.timeout(1.0)

    def _find_available_agv(self) -> Optional[str]:
        """Find an available AGV for transport task"""
        for agv_id, agv in self.agvs.items():
            if agv.status.value == "idle" and len(agv.payload) == 0:
                return agv_id
        return None

    def _execute_transport_task(self, agv_id: str, task: Dict):
        """Execute a product transport task with the assigned AGV"""
        try:
            agv = self.agvs[agv_id]
            product = task["product"]
            from_station_id = task["from_station"]
            to_station_id = task["to_station"]
            
            from_station = self.stations[from_station_id]
            to_station = self.stations[to_station_id]
            
            print(f"[{self.env.now:.2f}] 🚛 {agv_id}: 开始执行运输任务 - {product.id}")
            
            # Step 1: Move AGV to pickup station
            pickup_point = self._get_station_pickup_point(from_station_id)
            if agv.position != pickup_point:
                yield self.env.process(self._move_agv_to_position(agv_id, pickup_point))
            
            # Step 2: Load product from station
            agv.load_product(product)
            product.add_history(self.env.now, f"Loaded onto {agv_id} at {from_station_id}")
            yield self.env.timeout(3.0)  # Loading time
            
            # Step 3: Move AGV to destination station
            delivery_point = self._get_station_pickup_point(to_station_id)
            yield self.env.process(self._move_agv_to_position(agv_id, delivery_point))
            
            # Step 4: Unload product to destination station
            unloaded_product = agv.unload_product(product.id)
            if unloaded_product and to_station.add_product_to_buffer(unloaded_product):
                product.add_history(self.env.now, f"Delivered to {to_station_id} by {agv_id}")
                print(f"[{self.env.now:.2f}] ✅ {agv_id}: 成功运输产品 {product.id} 到 {to_station_id}")
            else:
                print(f"[{self.env.now:.2f}] ❌ {agv_id}: 无法将产品 {product.id} 交付到 {to_station_id}")
            
            yield self.env.timeout(2.0)  # Unloading time
            
        except Exception as e:
            print(f"[{self.env.now:.2f}] ❌ {agv_id}: 运输任务执行失败: {e}")

    def _get_station_pickup_point(self, station_id: str) -> Tuple[int, int]:
        """Get the pickup/delivery point for a station"""
        # For now, use station position directly
        # In a more complex system, this would return nearby path points
        station = self.stations.get(station_id)
        if station:
            return station.position
        return (0, 0)

    def _move_agv_to_position(self, agv_id: str, target_position: Tuple[int, int]):
        """Move AGV to a specific position using the path system"""
        agv = self.agvs[agv_id]
        
        # For now, move directly to position
        # In a more complex system, this would use pathfinding
        yield self.env.process(agv.move_to(target_position, self.path_points))

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
        # print(f"--- Factory simulation starting for {until} seconds ---")
        # print(f"--- Available devices: {', '.join(self.all_devices.keys())} ---")
        # print(f"--- Use 'inspect_device', 'skip_repair_time', 'request_maintenance' commands ---")
        """
        # Core simulation processes are already started in __init__:
        # - Order generation: self.order_generator.run() (auto-started)
        # - Fault injection: self.fault_system.run_fault_injection() (auto-started) 
        # - KPI updates: self.kpi_calculator.run_kpi_updates() (auto-started)
        # - MQTT publishing: self._start_status_publishing() (started in __init__)
        # - State evolution: self.state_space_manager._evolve_states() (auto-started)
        """
        # print(f"--- Active processes: Order Gen, Fault Injection, KPI Updates, MQTT Publishing ---")
        self.env.run(until=until)
        # print("--- Factory simulation finished ---")

    def get_factory_stats(self) -> Dict:
        """Get comprehensive factory statistics"""
        station_stats = {}
        for station_id, station in self.stations.items():
            if hasattr(station, 'get_processing_stats'):
                station_stats[station_id] = station.get_processing_stats()
        
        agv_stats = {}
        for agv_id, agv in self.agvs.items():
            agv_stats[agv_id] = {
                "status": agv.status.value,
                "position": agv.position,
                "battery_level": getattr(agv, 'battery_level', 100.0),
                "payload_count": len(agv.payload)
            }
        
        return {
            "timestamp": self.env.now,
            "stations": station_stats,
            "agvs": agv_stats,
            "scrap_stats": self.scrap_stats,
            "total_devices": len(self.all_devices),
            "active_transport_tasks": len(self.agv_task_queue.items)
        }

    def _bind_conveyors_to_stations(self):
        """Bind conveyors to stations according to the process flow."""
        # StationA → conveyor_ab
        if 'StationA' in self.stations:
            self.stations['StationA'].downstream_conveyor = self.conveyor_ab
        # StationB → conveyor_bc
        if 'StationB' in self.stations:
            self.stations['StationB'].downstream_conveyor = self.conveyor_bc
        # StationC → conveyor_cq (TripleBufferConveyor)
        if 'StationC' in self.stations:
            self.stations['StationC'].downstream_conveyor = self.conveyor_cq

    def _setup_conveyor_downstreams(self):
        """Set downstream stations for conveyors to enable auto-transfer."""
        # conveyor_ab → StationB
        if 'StationB' in self.stations:
            self.conveyor_ab.set_downstream_station(self.stations['StationB'])
        # conveyor_bc → StationC
        if 'StationC' in self.stations:
            self.conveyor_bc.set_downstream_station(self.stations['StationC'])
        # conveyor_cq → QualityCheck
        if 'QualityCheck' in self.stations:
            self.conveyor_cq.set_downstream_station(self.stations['QualityCheck'])


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