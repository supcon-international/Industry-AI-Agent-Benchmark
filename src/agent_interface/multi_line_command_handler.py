# src/agent_interface/multi_line_command_handler.py
import json
import logging
from typing import Dict, Any, Optional

from config.schemas import AgentCommand, SystemResponse
from src.utils.mqtt_client import MQTTClient
from src.utils.topic_manager import TopicManager

logger = logging.getLogger(__name__)

class MultiLineCommandHandler:
    """
    Handles MQTT commands for a multi-line factory environment.
    It subscribes to a wildcard topic and parses the line_id from the topic.
    """
    
    def __init__(self, factory, mqtt_client: MQTTClient, topic_manager: TopicManager):
        """
        Args:
            factory: The multi-line Factory instance.
            mqtt_client: The MQTT client to subscribe to commands.
            topic_manager: The TopicManager to generate and parse topics.
        """
        self.factory = factory
        self.mqtt_client = mqtt_client
        self.topic_manager = topic_manager
        
        # Subscribe to a wildcard topic for all lines
        command_topic = self.topic_manager.get_agent_command_topic_wildcard()
        self.mqtt_client.subscribe(command_topic, self._handle_command_message)
        logger.info(f"MultiLineCommandHandler initialized and subscribed to {command_topic}")

    def _handle_command_message(self, topic: str, payload: bytes):
        """
        Callback for incoming MQTT command messages.
        Parses the topic to get line_id and device_id, then validates the payload.
        """
        try:
            # Parse the topic to extract line_id and device_id
            parsed_topic = self.topic_manager.parse_agent_command_topic(topic)
            if not parsed_topic:
                logger.error(f"Could not parse command topic: {topic}")
                return

            line_id = parsed_topic['line_id']
            # device_id is now expected in the command payload's target field
            
            # Parse JSON payload
            command_data = json.loads(payload.decode('utf-8'))
            
            try:
                # Validate using Pydantic schema
                command = AgentCommand.model_validate(command_data)
            except Exception as e:
                msg = f"Failed to validate command: {e}"    
                logger.error(msg)
                self._publish_response(line_id, command_data.get("command_id"), msg)
                return
            
            # No need to check command.target against topic-derived device_id anymore

            logger.debug(f"Received valid command for line '{line_id}': {command.action} for {command.target}")
            
            # Route the command to the appropriate handler
            self._execute_command(line_id, command)
            
        except Exception as e:
            msg = f"Failed to process command: {e}"
            logger.error(msg)
            # We might not have line_id if topic parsing fails, so publish to a general error topic
            self._publish_response(None, command_data.get("command_id"), msg)

    def _execute_command(self, line_id: str, command: AgentCommand):
        """
        Executes a validated command by calling the appropriate method on the correct line.
        """
        action = command.action
        params = command.params
        target_device_id = command.target
        command_id = command.command_id

        # Get the correct production line from the factory
        line = self.factory.lines.get(line_id)
        if not line:
            msg = f"Production line '{line_id}' not found."
            logger.error(msg)
            self._publish_response(line_id, command_id, msg)
            return

        try:
            if action == "move":
                self._handle_move_agv(line, target_device_id, params, command_id)
            elif action == "load":
                self._handle_load_agv(line, target_device_id, params, command_id)
            elif action == "unload":
                self._handle_unload_agv(line, target_device_id, params, command_id)
            elif action == "charge":
                self._handle_charge_agv(line, target_device_id, params, command_id)
            else:
                msg = f"Unknown action: {action}"
                logger.warning(msg)
                self._publish_response(line_id, command_id, msg)
                
        except Exception as e:
            msg = f"Failed to execute command {action}: {e}"
            logger.error(msg)
            self._publish_response(line_id, command_id, msg)

    def _handle_move_agv(self, line, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None):
        target_point = params.get("target_point")
        if not target_point:
            self._publish_response(line.name, command_id, "'target_point' missing in move command.")
            return
            
        agv = line.agvs.get(agv_id)
        if not agv:
            self._publish_response(line.name, command_id, f"AGV '{agv_id}' not found in line '{line.name}'.")
            return
            
        def move_process():
            success, message = yield from agv.move_to(target_point)
            self._publish_response(line.name, command_id, message)
        
        self.factory.env.process(move_process())

    def _handle_load_agv(self, line, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None):
        device_id = params.get("device_id")
        buffer_type = params.get("buffer_type")

        if not device_id:
            self._publish_response(line.name, command_id, "'device_id' missing in load command.")
            return

        agv = line.agvs.get(agv_id)
        if not agv:
            self._publish_response(line.name, command_id, f"AGV '{agv_id}' not found in line '{line.name}'.")
            return

        device = self._find_device(line, device_id)
        if not device:
            self._publish_response(line.name, command_id, f"Device '{device_id}' not found in line '{line.name}' or factory.")
            return

        def load_process():
            success, message, _ = yield from agv.load_from(device, buffer_type)
            self._publish_response(line.name, command_id, message)
        
        self.factory.env.process(load_process())

    def _handle_unload_agv(self, line, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None):
        device_id = params.get("device_id")
        buffer_type = params.get("buffer_type")

        if not device_id:
            self._publish_response(line.name, command_id, "'device_id' missing in unload command.")
            return

        agv = line.agvs.get(agv_id)
        if not agv:
            self._publish_response(line.name, command_id, f"AGV '{agv_id}' not found in line '{line.name}'.")
            return

        device = self._find_device(line, device_id)
        if not device:
            self._publish_response(line.name, command_id, f"Device '{device_id}' not found in line '{line.name}' or factory.")
            return

        def unload_process():
            success, message, _ = yield from agv.unload_to(device, buffer_type)
            self._publish_response(line.name, command_id, message)
        
        self.factory.env.process(unload_process())

    def _handle_charge_agv(self, line, agv_id: str, params: Dict[str, Any], command_id: Optional[str] = None):
        target_level = params.get("target_level")
        if not target_level:
            self._publish_response(line.name, command_id, "'target_level' missing in charge command.")
            return

        agv = line.agvs.get(agv_id)
        if not agv:
            self._publish_response(line.name, command_id, f"AGV '{agv_id}' not found in line '{line.name}'.")
            return
            
        def charge_process():
            success, message = yield from agv.voluntary_charge(target_level)
            self._publish_response(line.name, command_id, message)
        
        self.factory.env.process(charge_process())

    def _find_device(self, line, device_id: str):
        """
        Find a device first in the line, then in factory global devices.
        Returns the device if found, None otherwise.
        """
        # First try to find in the current line
        device = line.all_devices.get(device_id)
        if device:
            return device
        
        # If not found in line, search in factory global devices (warehouse, raw_material)
        device = self.factory.all_devices.get(device_id)
        return device

    def _publish_response(self, line_id: Optional[str], command_id: Optional[str], response_message: str):
        """Publishes a response to the appropriate MQTT topic."""
        response_topic = self.topic_manager.get_agent_response_topic(line_id)
        response_payload = SystemResponse(
            timestamp=self.factory.env.now,
            command_id=command_id,
            response=response_message
        ).model_dump_json()
        self.mqtt_client.publish(response_topic, response_payload)
