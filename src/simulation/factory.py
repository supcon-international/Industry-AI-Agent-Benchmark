# src/simulation/factory.py
import simpy
import random
from typing import Dict, List, Tuple, Optional

from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor
from src.simulation.entities.base import BaseConveyor
from src.simulation.entities.warehouse import Warehouse, RawMaterial
from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.simulation.entities.quality_checker import QualityChecker
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.game_logic.kpi_calculator import KPICalculator
from src.utils.mqtt_client import MQTTClient

# Import configuration loader
from src.utils.config_loader import load_factory_config

class Factory:
    """
    The main class that orchestrates the entire factory simulation.
    """
    def __init__(self, layout_config: Dict, mqtt_client: MQTTClient, no_faults: bool = False):
        self.env = simpy.Environment()
        self.layout = layout_config
        self.mqtt_client = mqtt_client
        self.no_faults_mode = no_faults # Store the flag
        
        self.stations: Dict[str, Station] = {}
        self.agvs: Dict[str, AGV] = {}
        self.conveyors: Dict[str, BaseConveyor] = {}
        
        # Warehouse attributes - will be set during device creation
        self.warehouse: Optional[Warehouse] = None
        self.raw_material: Optional[RawMaterial] = None
        
        # AGV task queue for product transportation
        self.agv_task_queue = simpy.Store(self.env)
        
        # Statistics for scrapped products
        self.scrap_stats = {
            "total_scrapped": 0,
            "scrap_by_station": {},
            "scrap_reasons": {}
        }
        
        # Initialize all_devices dictionary first
        self.all_devices = {}
        
        # Create devices first
        self._create_devices()
        
        # Update all_devices with created devices
        self.all_devices.update(self.stations)
        self.all_devices.update(self.agvs)
        self.all_devices.update(self.conveyors)

        if self.warehouse is not None:
            self.all_devices[self.warehouse.id] = self.warehouse

        if self.raw_material is not None:
            self.all_devices[self.raw_material.id] = self.raw_material
            self.order_generator = OrderGenerator(self.env, self.mqtt_client, self.raw_material)
        else:
            raise ValueError("RawMaterial device not found in configuration")

        # Game logic components (fault system needs device references)
        # Conditionally initialize FaultSystem
        if not self.no_faults_mode:
            self.fault_system = FaultSystem(self.env, self.all_devices, self.mqtt_client)
            print("🔧 Fault System Initialized.")
        else:
            self.fault_system = None # Explicitly set to None if not enabled
            print("🚫 Fault System Disabled (no-faults mode).")
        
        self.kpi_calculator = KPICalculator(self.env, self.mqtt_client)
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Start device status publishing
        self._start_status_publishing()
           
        self._bind_conveyors_to_stations()
        self._setup_conveyor_downstreams()

    def _create_devices(self):
        """Instantiates all devices based on the layout configuration."""
        
        for station_cfg in self.layout['stations']:
            # Quality checker station
            if station_cfg['id'] == 'QualityCheck':
                station = QualityChecker(
                    env=self.env,
                    mqtt_client=self.mqtt_client,
                    **station_cfg
                )
                print(f"[{self.env.now:.2f}] 🔍 Created QualityChecker: {station_cfg['id']}")
            else:
                # create normal station
                station = Station(
                    env=self.env,
                    mqtt_client=self.mqtt_client,
                    **station_cfg
                )
                print(f"[{self.env.now:.2f}] 🏭 Created Station: {station_cfg['id']}")
            
            self.stations[station.id] = station
        
        # create AGV
        for agv_cfg in self.layout['agvs']:
            agv = AGV(
                env=self.env,
                mqtt_client=self.mqtt_client,
                **agv_cfg
            )
            self.agvs[agv.id] = agv
            print(f"[{self.env.now:.2f}] 🚛 Created AGV: {agv_cfg['id']}")
        
        # create conveyor
        for conveyor_cfg in self.layout['conveyors']:
            conveyor_id = conveyor_cfg['id']
            # Common arguments for all conveyors
            common_args = {
                "env": self.env,
                "id": conveyor_id,
                "position": conveyor_cfg['position'],
                "mqtt_client": self.mqtt_client
            }
            if conveyor_id == 'Conveyor_CQ':
                conveyor = TripleBufferConveyor(
                    main_capacity=conveyor_cfg['main_capacity'],
                    upper_capacity=conveyor_cfg['upper_capacity'],
                    lower_capacity=conveyor_cfg['lower_capacity'],
                    **common_args
                )
            elif conveyor_id in ['Conveyor_AB', 'Conveyor_BC']:
                conveyor = Conveyor(
                    capacity=conveyor_cfg['capacity'],
                    **common_args
                )
            else:
                raise ValueError(f"Unknown conveyor type: {conveyor_id}")
            
            self.conveyors[conveyor.id] = conveyor
            print(f"[{self.env.now:.2f}] 🚛 Created Conveyor: {conveyor_id}")
        
        # create warehouse
        for warehouse_cfg in self.layout['warehouses']:
            # Common arguments for all warehouses
            common_args = {
                "env": self.env,
                "mqtt_client": self.mqtt_client,
                **warehouse_cfg
            }
            if warehouse_cfg['id'] == 'RawMaterial':
                warehouse = RawMaterial(**common_args)
                self.raw_material = warehouse  # Store dedicated reference
            elif warehouse_cfg['id'] == 'Warehouse':
                warehouse = Warehouse(**common_args)
                self.warehouse = warehouse  # Store dedicated reference
            else:
                raise ValueError(f"Unknown warehouse type: {warehouse_cfg['id']}")
            
            print(f"[{self.env.now:.2f}] 🏪 Created Warehouse: {warehouse_cfg['id']}")

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
        if self.fault_system is None:
            # Handle case where fault system is disabled
            print(f"[{self.env.now:.2f}] 🚫 Fault System is disabled. Cannot handle maintenance request for {device_id}.")
            # Return a default/empty diagnosis result or raise an error
            # Assuming DiagnosisResult has a default constructor or can be mocked
            from src.game_logic.fault_system import DiagnosisResult
            return DiagnosisResult(is_correct=False, repair_time=0.0, affected_devices=[], device_id=device_id, diagnosis_command=maintenance_type, penalty_applied=False, can_skip=False)

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
        if self.fault_system is None:
            print(f"[{self.env.now:.2f}] 🚫 Fault System is disabled. Cannot inspect device {device_id}.")
            return None
        return self.fault_system.inspect_device(device_id)

    def skip_repair_time(self, device_id: str) -> bool:
        """
        Skip the repair/penalty time for a device.
        This allows players to continue operating other devices.
        """
        if self.fault_system is None:
            print(f"[{self.env.now:.2f}] 🚫 Fault System is disabled. Cannot skip repair time for {device_id}.")
            return False
        return self.fault_system.skip_repair_time(device_id)

    def get_available_devices(self) -> List[str]:
        """
        Get list of devices that can currently be operated (not frozen).
        """
        if self.fault_system is None:
            print(f"[{self.env.now:.2f}] 🚫 Fault System is disabled. No available devices from fault system.")
            return []
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
                    'payload': [p.id for p in agv.payload.items] if hasattr(agv, 'payload') else []
                })
            
            return status_dict
        return {}

    def _start_status_publishing(self):
        """Start processes to publish device status to MQTT."""        
        # Start factory overall status publishing
        self.env.process(self._publish_factory_status())
        
        # Start enhanced fault events publishing  
        self.env.process(self._publish_fault_events())
    
    
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
                active_faults=len(self.fault_system.active_faults) if self.fault_system else 0,
                simulation_time=self.env.now
            )
            
            try:
                self.mqtt_client.publish(FACTORY_STATUS_TOPIC, factory_status)
                print(f"[{self.env.now:.2f}] 📊 Published factory status: {factory_status.active_orders} active orders, {factory_status.active_faults} faults")
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Failed to publish factory status: {e}")

    def _publish_fault_events(self):
        """Publish enhanced fault events to make them more visible."""
        while True:
            yield self.env.timeout(1.0)  # Check for faults every 1 seconds
            
            # If there are active faults, publish them more frequently
            if self.fault_system and self.fault_system.active_faults:
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
                "payload_count": len(agv.payload.items)  # Use .items for SimPy Store
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
        if 'StationA' in self.stations and 'Conveyor_AB' in self.conveyors:
            self.stations['StationA'].downstream_conveyor = self.conveyors['Conveyor_AB']
        # StationB → conveyor_bc
        if 'StationB' in self.stations and 'Conveyor_BC' in self.conveyors:
            self.stations['StationB'].downstream_conveyor = self.conveyors['Conveyor_BC']
        # StationC → conveyor_cq (TripleBufferConveyor)
        if 'StationC' in self.stations and 'Conveyor_CQ' in self.conveyors:
            self.stations['StationC'].downstream_conveyor = self.conveyors['Conveyor_CQ']

    def _setup_conveyor_downstreams(self):
        """Set downstream stations for conveyors to enable auto-transfer."""
        # conveyor_ab → StationB
        if 'StationB' in self.stations and 'Conveyor_AB' in self.conveyors:
            self.conveyors['Conveyor_AB'].set_downstream_station(self.stations['StationB'])
        # conveyor_bc → StationC
        if 'StationC' in self.stations and 'Conveyor_BC' in self.conveyors:
            self.conveyors['Conveyor_BC'].set_downstream_station(self.stations['StationC'])
        # conveyor_cq → QualityCheck
        if 'QualityCheck' in self.stations and 'Conveyor_CQ' in self.conveyors:
            self.conveyors['Conveyor_CQ'].set_downstream_station(self.stations['QualityCheck'])


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
    
    # 加载配置
    try:
        from src.utils.config_loader import load_factory_config
        layout_config = load_factory_config()
    except Exception as e:
        print(f"❌ Failed to load factory configuration: {e}")
        raise e
    
    factory = Factory(layout_config, mqtt_client)
    
    # Simple test - just create the factory and run briefly
    print(f"[{factory.env.now:.2f}] 🎉 Factory created successfully!")
    print(f"[{factory.env.now:.2f}] 📊 Stations: {list(factory.stations.keys())}")
    print(f"[{factory.env.now:.2f}] 🚛 AGVs: {list(factory.agvs.keys())}")
    agv1 = factory.agvs['AGV_1']
    factory.env.process(agv1.move_to('LP1'))

    print(f"[{factory.env.now:.2f}] 🛤️  Conveyors: {list(factory.conveyors.keys())}")
    print(f"[{factory.env.now:.2f}] 🏪 Warehouses: RawMaterial={factory.raw_material.id if factory.raw_material else None}, Warehouse={factory.warehouse.id if factory.warehouse else None}")
    
    # Test simple simulation for 30 seconds
    factory.run(until=20)