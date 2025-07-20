# src/simulation/line.py
import simpy
from typing import Dict, List, Optional

from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor, BaseConveyor
from src.simulation.entities.warehouse import Warehouse, RawMaterial
from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.simulation.entities.quality_checker import QualityChecker
from src.game_logic.order_generator import OrderGenerator
from src.game_logic.fault_system import FaultSystem
from src.utils.mqtt_client import MQTTClient
from src.utils.topic_manager import TopicManager

class Line:
    """
    Represents a single production line within the factory.
    """
    def __init__(self, env: simpy.Environment, line_name: str, line_config: Dict, 
                 mqtt_client: MQTTClient, topic_manager: TopicManager,
                 warehouse: Warehouse, raw_material: RawMaterial, order_generator: OrderGenerator,
                 no_faults: bool = False):
        self.env = env
        self.name = line_name
        self.config = line_config
        self.mqtt_client = mqtt_client
        self.topic_manager = topic_manager
        self.no_faults_mode = no_faults

        # Shared resources injected from Factory
        self.warehouse = warehouse
        self.raw_material = raw_material
        self.order_generator = order_generator

        self.stations: Dict[str, Station] = {}
        self.agvs: Dict[str, AGV] = {}
        self.conveyors: Dict[str, BaseConveyor] = {}
        
        self.agv_task_queue = simpy.Store(self.env)
        self.all_devices = {}

        self._create_devices()
        
        self.all_devices.update(self.stations)
        self.all_devices.update(self.agvs)
        self.all_devices.update(self.conveyors)

        self._create_game_logic_systems()
        self._bind_conveyors_to_stations()
        self._setup_conveyor_downstreams()

    def _create_devices(self):
        """Instantiates all devices for this line based on its configuration."""
        for station_cfg in self.config.get('stations', []):
            station_id = f"{self.name}_{station_cfg['id']}"
            if station_cfg['id'] == 'QualityCheck':
                station = QualityChecker(env=self.env, mqtt_client=self.mqtt_client, topic_manager=self.topic_manager, line_id=self.name, id=station_id, **station_cfg)
            else:
                station = Station(env=self.env, mqtt_client=self.mqtt_client, topic_manager=self.topic_manager, line_id=self.name, id=station_id, **station_cfg)
            self.stations[station_id] = station

        for agv_cfg in self.config.get('agvs', []):
            agv_id = f"{self.name}_{agv_cfg['id']}"
            agv = AGV(env=self.env, mqtt_client=self.mqtt_client, topic_manager=self.topic_manager, line_id=self.name, id=agv_id, **agv_cfg)
            self.agvs[agv_id] = agv

        for conveyor_cfg in self.config.get('conveyors', []):
            conveyor_id = f"{self.name}_{conveyor_cfg['id']}"
            common_args = {
                "env": self.env, "id": conveyor_id, "position": conveyor_cfg['position'],
                "interacting_points": conveyor_cfg['interacting_points'],
                "transfer_time": conveyor_cfg['transfer_time'], "mqtt_client": self.mqtt_client,
                "topic_manager": self.topic_manager, "line_id": self.name
            }
            if conveyor_cfg['id'] == 'Conveyor_CQ':
                conveyor = TripleBufferConveyor(**common_args, main_capacity=conveyor_cfg['main_capacity'], upper_capacity=conveyor_cfg['upper_capacity'], lower_capacity=conveyor_cfg['lower_capacity'])
            else: # Assuming 'Conveyor_AB', 'Conveyor_BC' or similar
                conveyor = Conveyor(**common_args, capacity=conveyor_cfg['capacity'])
            self.conveyors[conveyor_id] = conveyor

    def _create_game_logic_systems(self):
        """Creates game logic systems like FaultSystem for this line."""
        if 'fault_system' in self.config and not self.no_faults_mode:
            fs_config = self.config['fault_system']
            self.fault_system = FaultSystem(self.env, self.all_devices, self.mqtt_client, self.topic_manager, self.name, **fs_config)

    def _bind_conveyors_to_stations(self):
        """Bind conveyors to stations according to the process flow."""
        station_map = {s.id.split('_', 2)[-1]: s for s in self.stations.values()}
        conveyor_map = {c.id.split('_', 2)[-1]: c for c in self.conveyors.values()}

        if 'StationA' in station_map and 'Conveyor_AB' in conveyor_map:
            station_map['StationA'].downstream_conveyor = conveyor_map['Conveyor_AB']
        if 'StationB' in station_map and 'Conveyor_BC' in conveyor_map:
            station_map['StationB'].downstream_conveyor = conveyor_map['Conveyor_BC']
        if 'StationC' in station_map and 'Conveyor_CQ' in conveyor_map:
            station_map['StationC'].downstream_conveyor = conveyor_map['Conveyor_CQ']

    def _setup_conveyor_downstreams(self):
        """Set downstream stations for conveyors to enable auto-transfer."""
        station_map = {s.id.split('_', 2)[-1]: s for s in self.stations.values()}
        conveyor_map = {c.id.split('_', 2)[-1]: c for c in self.conveyors.values()}

        if 'StationB' in station_map and 'Conveyor_AB' in conveyor_map:
            conveyor_map['Conveyor_AB'].set_downstream_station(station_map['StationB'])
        if 'StationC' in station_map and 'Conveyor_BC' in conveyor_map:
            conveyor_map['Conveyor_BC'].set_downstream_station(station_map['StationC'])
        if 'QualityCheck' in station_map and 'Conveyor_CQ' in conveyor_map:
            conveyor_map['Conveyor_CQ'].set_downstream_station(station_map['QualityCheck'])
