# src/simulation/line.py
import simpy
from typing import Dict, List, Optional

from src.simulation.entities.conveyor import Conveyor, TripleBufferConveyor, BaseConveyor
from src.simulation.entities.station import Station
from src.simulation.entities.agv import AGV
from src.simulation.entities.quality_checker import QualityChecker
from src.game_logic.fault_system import FaultSystem
from src.utils.mqtt_client import MQTTClient

class Line:
    """
    Represents a single production line within the factory.
    It contains all the devices and logic for one line.
    """
    def __init__(self, env: simpy.Environment, line_name: str, line_config: Dict, mqtt_client: MQTTClient, no_faults: bool = False):
        self.env = env
        self.name = line_name
        self.config = line_config
        self.mqtt_client = mqtt_client
        self.no_faults_mode = no_faults

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
        # Create stations
        for station_cfg in self.config.get('stations', []):
            if station_cfg['id'] == 'QualityCheck':
                station = QualityChecker(env=self.env, mqtt_client=self.mqtt_client, **station_cfg)
            else:
                station = Station(env=self.env, mqtt_client=self.mqtt_client, **station_cfg)
            self.stations[station_cfg['id']] = station

        # Create AGVs
        for agv_cfg in self.config.get('agvs', []):
            agv = AGV(env=self.env, mqtt_client=self.mqtt_client, **agv_cfg)
            self.agvs[agv_cfg['id']] = agv

        # Create Conveyors
        for conveyor_cfg in self.config.get('conveyors', []):
            conveyor_id = f"{self.name}_{conveyor_cfg['id']}"
            common_args = {
                "env": self.env, "id": conveyor_id, "position": conveyor_cfg['position'],
                "interacting_points": conveyor_cfg['interacting_points'],
                "transfer_time": conveyor_cfg['transfer_time'], "mqtt_client": self.mqtt_client
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
            self.fault_system = FaultSystem(self.env, self.all_devices, self.mqtt_client, **fs_config)

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