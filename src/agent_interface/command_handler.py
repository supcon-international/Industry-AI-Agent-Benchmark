# src/agent_interface/command_handler.py
import json
import logging
from typing import Dict, Any

from config.schemas import AgentCommand
from config.topics import AGENT_COMMANDS_TOPIC
from src.utils.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

class CommandHandler:
    """
    Handles MQTT commands received from agents and translates them 
    into method calls on the factory simulation.
    
    This is the bridge between the external MQTT interface and the internal simulation.
    """
    
    def __init__(self, factory, mqtt_client: MQTTClient):
        """
        Args:
            factory: The Factory instance to send commands to.
            mqtt_client: The MQTT client to subscribe to agent commands.
        """
        self.factory = factory
        self.mqtt_client = mqtt_client
        
        # Subscribe to agent commands
        self.mqtt_client.subscribe(AGENT_COMMANDS_TOPIC, self._handle_command_message)
        logger.info(f"CommandHandler initialized and subscribed to {AGENT_COMMANDS_TOPIC}")

    def _handle_command_message(self, topic: str, payload: bytes):
        """
        Callback for incoming MQTT command messages.
        Parses the JSON and validates it against the AgentCommand schema.
        """
        try:
            # Parse JSON payload
            command_data = json.loads(payload.decode('utf-8'))
            
            # Validate using Pydantic schema
            command = AgentCommand.model_validate(command_data)
            
            logger.info(f"Received valid command: {command.action} for {command.target}")
            
            # Route the command to the appropriate handler
            self._execute_command(command)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON command: {e}")
        except Exception as e:
            logger.error(f"Failed to process command: {e}")

    def _execute_command(self, command: AgentCommand):
        """
        Executes a validated command by calling the appropriate factory method.
        """
        action = command.action
        target = command.target
        params = command.params
        
        try:
            if action == "move_agv":
                self._handle_move_agv(target, params)
            elif action == "request_maintenance":
                self._handle_request_maintenance(target, params)
            elif action == "emergency_stop":
                self._handle_emergency_stop(target, params)
            elif action == "adjust_priority":
                self._handle_adjust_priority(target, params)
            elif action == "reroute_order":
                self._handle_reroute_order(target, params)
            else:
                logger.warning(f"Unknown action: {action}")
                
        except Exception as e:
            logger.error(f"Failed to execute command {action} on {target}: {e}")

    def _handle_move_agv(self, agv_id: str, params: Dict[str, Any]):
        """Handle AGV movement commands."""
        destination_id = params.get("destination_id")
        if not destination_id:
            logger.error("move_agv command missing 'destination_id' parameter")
            return
            
        if agv_id not in self.factory.agvs:
            logger.error(f"AGV {agv_id} not found in factory")
            return
            
        # For now, we assume the AGV is already at a known path point.
        # In a complete implementation, we'd need to determine the AGV's current path point.
        agv = self.factory.agvs[agv_id]
        current_pos = agv.position
        
        # Find the closest path point to current position
        closest_point = self._find_closest_path_point(current_pos)
        
        logger.info(f"Moving {agv_id} from {closest_point} to {destination_id}")
        
        # Schedule the movement in the simulation
        self.factory.env.process(self.factory.move_agv(agv_id, closest_point, destination_id))

    def _handle_request_maintenance(self, device_id: str, params: Dict[str, Any]):
        """Handle maintenance request commands."""
        maintenance_type = params.get("maintenance_type")
        if not maintenance_type:
            logger.error("request_maintenance command missing 'maintenance_type' parameter")
            return
            
        logger.info(f"Requesting {maintenance_type} maintenance for {device_id}")
        
        # Use the factory's maintenance handling system
        success, repair_time = self.factory.handle_maintenance_request(device_id, maintenance_type)
        
        if success:
            logger.info(f"✅ Maintenance request accepted for {device_id}, repair time: {repair_time:.1f}s")
        else:
            logger.warning(f"❌ Maintenance request failed for {device_id} (wrong diagnosis)")
        
        return success, repair_time
        
    def _handle_emergency_stop(self, device_id: str, params: Dict[str, Any]):
        """Handle emergency stop commands."""
        logger.info(f"Emergency stop requested for {device_id}")
        # TODO: Implement emergency stop logic
        
    def _handle_adjust_priority(self, order_id: str, params: Dict[str, Any]):
        """Handle order priority adjustment commands."""
        new_priority = params.get("priority")
        logger.info(f"Adjusting priority of order {order_id} to {new_priority}")
        # TODO: Implement order priority logic
        
    def _handle_reroute_order(self, order_id: str, params: Dict[str, Any]):
        """Handle order rerouting commands."""
        target_station_id = params.get("target_station_id")
        logger.info(f"Rerouting order {order_id} to {target_station_id}")
        # TODO: Implement order rerouting logic

    def _find_closest_path_point(self, position: tuple) -> str:
        """
        Finds the closest path point to a given position.
        This is a helper method for AGV movement commands.
        """
        min_distance = float('inf')
        closest_point = None
        
        for point_id, point_pos in self.factory.path_points.items():
            distance = ((position[0] - point_pos[0])**2 + (position[1] - point_pos[1])**2)**0.5
            if distance < min_distance:
                min_distance = distance
                closest_point = point_id
                
        return closest_point or "P0"  # fallback to P0 if something goes wrong 