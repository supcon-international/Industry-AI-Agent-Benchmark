# src/simulation/factory_multi.py
import os
import simpy
from typing import Dict, List, Optional

from src.simulation.line import Line
from src.game_logic.kpi_calculator import KPICalculator
from src.utils.mqtt_client import MQTTClient
from src.simulation.entities.warehouse import Warehouse, RawMaterial
from src.game_logic.order_generator import OrderGenerator
from src.utils.topic_manager import TopicManager

class Factory:
    """
    The main class that orchestrates the entire factory simulation with multiple production lines.
    """
    def __init__(self, layout_config: Dict, mqtt_client: MQTTClient, no_faults: bool = False):
        self.env = simpy.Environment()
        self.layout = layout_config
        self.mqtt_client = mqtt_client
        self.no_faults_mode = no_faults
        
        # Read player name from environment variable
        player_name = os.getenv("TOPIC_ROOT", "NLDF_DEFAULT")
        self.topic_manager = TopicManager(player_name)

        self.lines: Dict[str, Line] = {}
        self.warehouse: Warehouse
        self.order_generator: OrderGenerator
        self.kpi_calculator = KPICalculator(self.env, self.mqtt_client, self.topic_manager)

        self.all_devices = {}
        self._create_warehouse_order_generator()
        self._create_production_lines()


    def _create_production_lines(self):
        """Creates all production lines based on the layout configuration."""
        for line_config in self.layout.get('production_lines', []):
            line_name = line_config['name']
            line = Line(
                env=self.env,
                line_name=line_name,
                line_config=line_config,
                mqtt_client=self.mqtt_client,
                topic_manager=self.topic_manager,
                warehouse=self.warehouse,
                raw_material=self.raw_material,
                order_generator=self.order_generator,
                no_faults=self.no_faults_mode,
                kpi_calculator=self.kpi_calculator
            )
            self.lines[line_name] = line
            self.all_devices.update(line.all_devices)
            print(f"[{self.env.now:.2f}] 🏭 Created Production Line: {line_name}")

    def _create_warehouse_order_generator(self):
        """Creates the warehouse for the factory."""
        for warehouse_cfg in self.layout.get('warehouses', []):
            common_args = {"env": self.env, "mqtt_client": self.mqtt_client, **warehouse_cfg}
            if warehouse_cfg['id'] == 'RawMaterial':
                self.raw_material = RawMaterial(**common_args)
            elif warehouse_cfg['id'] == 'Warehouse':
                self.warehouse = Warehouse(**common_args)

        self.order_generator = OrderGenerator(
            env=self.env,
            raw_material=self.raw_material,
            mqtt_client=self.mqtt_client,
            topic_manager=self.topic_manager
        )

    def get_device_status(self, device_id: str) -> Dict:
        """Get comprehensive device status including faults."""
        for line in self.lines.values():
            if device_id in line.all_devices:
                # This part can be enhanced to call a method on the line object
                # which in turn calls the device. For now, direct access for simplicity.
                device = line.all_devices[device_id]
                return device.get_detailed_status() # Simplified for now
        return {}


    def run(self, until: int):
        """Runs the simulation for a given duration."""
        self.env.run(until=until)