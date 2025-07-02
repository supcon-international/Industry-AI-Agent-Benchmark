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
            elif action == "inspect_device":
                self._handle_inspect_device(target, params)
            elif action == "skip_repair_time":
                self._handle_skip_repair_time(target, params)
            elif action == "get_available_devices":
                self._handle_get_available_devices(target, params)
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
        diagnosis_result = self.factory.handle_maintenance_request(device_id, maintenance_type)
        
        if diagnosis_result.is_correct:
            logger.info(f"✅ Correct diagnosis for {device_id}, repair time: {diagnosis_result.repair_time:.1f}s")
        else:
            logger.warning(f"❌ Incorrect diagnosis for {device_id}, penalty time: {diagnosis_result.repair_time:.1f}s")
            if diagnosis_result.affected_devices:
                logger.warning(f"   Affected devices: {', '.join(diagnosis_result.affected_devices)}")
        
        return diagnosis_result

    def _handle_inspect_device(self, device_id: str, params: Dict[str, Any]):
        """Handle device inspection commands."""
        logger.info(f"Inspecting device {device_id}")
        
        if not hasattr(self.factory, 'fault_system'):
            logger.error("Factory does not have fault system available")
            return None
            
        # Use the fault system's inspect function
        detailed_status = self.factory.fault_system.inspect_device(device_id)
        
        if detailed_status:
            logger.info(f"✅ Device {device_id} inspection completed")
            # 发布检查结果供agent使用
            self._publish_inspection_result(device_id, detailed_status)
        else:
            logger.warning(f"❌ Device {device_id} inspection failed")
        
        return detailed_status

    def _handle_skip_repair_time(self, device_id: str, params: Dict[str, Any]):
        """Handle skip repair time commands."""
        logger.info(f"Attempting to skip repair time for {device_id}")
        
        if not hasattr(self.factory, 'fault_system'):
            logger.error("Factory does not have fault system available")
            return False
            
        # Use the fault system's skip function
        success = self.factory.fault_system.skip_repair_time(device_id)
        
        if success:
            logger.info(f"✅ Successfully skipped repair time for {device_id}")
        else:
            logger.warning(f"❌ Failed to skip repair time for {device_id}")
        
        return success

    def _handle_get_available_devices(self, target: str, params: Dict[str, Any]):
        """Handle get available devices commands."""
        logger.info("Retrieving available devices list")
        
        if not hasattr(self.factory, 'fault_system'):
            logger.error("Factory does not have fault system available")
            return []
            
        # Get available devices from fault system
        available_devices = self.factory.fault_system.get_available_devices()
        
        logger.info(f"✅ Available devices: {', '.join(available_devices)}")
        
        # Publish available devices via MQTT
        self._publish_available_devices(available_devices)
        
        return available_devices
        
    def _handle_emergency_stop(self, device_id: str, params: Dict[str, Any]):
        """Handle emergency stop commands."""
        logger.info(f"Emergency stop requested for {device_id}")
        
        success = False
        
        # Handle station emergency stop
        if device_id in self.factory.stations:
            station = self.factory.stations[device_id]
            if hasattr(station, 'emergency_stop'):
                station.emergency_stop()
                success = True
            else:
                # Fallback: force station to idle state
                from src.simulation.entities.base import DeviceStatus
                station.status = DeviceStatus.MAINTENANCE
                logger.info(f"✅ Station {device_id} emergency stopped (forced to maintenance mode)")
                success = True
        
        # Handle AGV emergency stop
        elif device_id in self.factory.agvs:
            agv = self.factory.agvs[device_id]
            if hasattr(agv, 'emergency_stop'):
                agv.emergency_stop()
                success = True
            else:
                # Fallback: force AGV to stop
                agv.is_moving = False
                logger.info(f"✅ AGV {device_id} emergency stopped")
                success = True
        
        # Handle factory-wide emergency stop
        elif device_id == "factory":
            logger.info("🚨 Factory-wide emergency stop initiated")
            # Stop all stations
            for station_id, station in self.factory.stations.items():
                if hasattr(station, 'emergency_stop'):
                    station.emergency_stop()
                else:
                    from src.simulation.entities.base import DeviceStatus
                    station.status = DeviceStatus.MAINTENANCE
            
            # Stop all AGVs
            for agv_id, agv in self.factory.agvs.items():
                if hasattr(agv, 'emergency_stop'):
                    agv.emergency_stop()
                else:
                    agv.is_moving = False
            
            success = True
        
        else:
            logger.error(f"❌ Unknown device for emergency stop: {device_id}")
            
        if success:
            logger.info(f"✅ Emergency stop completed for {device_id}")
        else:
            logger.error(f"❌ Emergency stop failed for {device_id}")
        
        return success
        
    def _handle_adjust_priority(self, order_id: str, params: Dict[str, Any]):
        """Handle order priority adjustment commands."""
        new_priority = params.get("priority")
        if not new_priority:
            logger.error("adjust_priority command missing 'priority' parameter")
            return False
            
        logger.info(f"Adjusting priority of order {order_id} to {new_priority}")
        
        # Validate priority value
        valid_priorities = ["low", "medium", "high"]
        if new_priority not in valid_priorities:
            logger.error(f"Invalid priority '{new_priority}'. Valid priorities: {valid_priorities}")
            return False
        
        success = False
        
        # Try to find and update the order in the order generator
        if hasattr(self.factory, 'order_generator'):
            order_generator = self.factory.order_generator
            
            # Look for the order in active orders
            if hasattr(order_generator, 'active_orders'):
                for order in order_generator.active_orders:
                    if order.order_id == order_id:
                        old_priority = order.priority
                        order.priority = new_priority
                        
                        # Recalculate deadline based on new priority
                        if hasattr(order_generator, '_calculate_deadline'):
                            order.deadline = order_generator._calculate_deadline(new_priority, order.quantity)
                        
                        logger.info(f"✅ Order {order_id} priority changed from {old_priority} to {new_priority}")
                        success = True
                        break
            
            # If not found in active orders, check pending orders
            if not success and hasattr(order_generator, 'pending_orders'):
                for order in order_generator.pending_orders:
                    if order.order_id == order_id:
                        old_priority = order.priority
                        order.priority = new_priority
                        
                        # Recalculate deadline
                        if hasattr(order_generator, '_calculate_deadline'):
                            order.deadline = order_generator._calculate_deadline(new_priority, order.quantity)
                        
                        logger.info(f"✅ Order {order_id} priority changed from {old_priority} to {new_priority}")
                        success = True
                        break
        
        # Also try to update in KPI calculator if it tracks orders
        if hasattr(self.factory, 'kpi_calculator'):
            kpi_calculator = self.factory.kpi_calculator
            if hasattr(kpi_calculator, 'update_order_priority'):
                kpi_calculator.update_order_priority(order_id, new_priority)
        
        if not success:
            logger.error(f"❌ Order {order_id} not found or could not be updated")
        
        return success
        
    def _handle_reroute_order(self, order_id: str, params: Dict[str, Any]):
        """Handle order rerouting commands."""
        target_station_id = params.get("target_station_id")
        if not target_station_id:
            logger.error("reroute_order command missing 'target_station_id' parameter")
            return False
            
        logger.info(f"Rerouting order {order_id} to {target_station_id}")
        
        # Validate target station exists
        if target_station_id not in self.factory.stations:
            logger.error(f"Target station '{target_station_id}' does not exist")
            return False
        
        success = False
        
        # Try to find the order and reroute it
        if hasattr(self.factory, 'order_generator'):
            order_generator = self.factory.order_generator
            
            # Look for the order in active orders
            if hasattr(order_generator, 'active_orders'):
                for order in order_generator.active_orders:
                    if order.order_id == order_id:
                        # Check if the order has a route or current station
                        if hasattr(order, 'current_station'):
                            old_station = order.current_station
                            order.current_station = target_station_id
                            logger.info(f"✅ Order {order_id} rerouted from {old_station} to {target_station_id}")
                            success = True
                        elif hasattr(order, 'route'):
                            # Modify the route to include the target station
                            if isinstance(order.route, list):
                                # Insert target station at the beginning of remaining route
                                order.route.insert(0, target_station_id)
                            else:
                                # Simple case: set route to target station
                                order.route = [target_station_id]
                            logger.info(f"✅ Order {order_id} route updated to include {target_station_id}")
                            success = True
                        else:
                            # Create a new route attribute if it doesn't exist
                            order.next_station = target_station_id
                            logger.info(f"✅ Order {order_id} next station set to {target_station_id}")
                            success = True
                        break
        
        # If the order is currently being processed at a station, we might need to stop it
        if success:
            target_station = self.factory.stations[target_station_id]
            
            # Check if target station has capacity
            if hasattr(target_station, 'buffer') and hasattr(target_station.buffer, 'items'):
                if len(target_station.buffer.items) >= target_station.buffer.capacity:
                    logger.warning(f"⚠️ Target station {target_station_id} buffer is full, rerouting may be delayed")
            
            # Notify the target station about incoming order (if supported)
            if hasattr(target_station, 'notify_incoming_order'):
                target_station.notify_incoming_order(order_id)
            
            # Update KPI calculator if it tracks order routing
            if hasattr(self.factory, 'kpi_calculator'):
                kpi_calculator = self.factory.kpi_calculator
                if hasattr(kpi_calculator, 'update_order_route'):
                    kpi_calculator.update_order_route(order_id, target_station_id)
        
        if not success:
            logger.error(f"❌ Order {order_id} not found or could not be rerouted")
        
        return success

    def _publish_inspection_result(self, device_id: str, detailed_status):
        """Publish device inspection result via MQTT."""
        topic = f"factory/inspection/{device_id}/result"
        message = {
            "device_id": device_id,
            "timestamp": self.factory.env.now,
            "status": detailed_status.dict()
        }
        
        try:
            self.mqtt_client.publish(topic, json.dumps(message))
            logger.debug(f"Published inspection result for {device_id}")
        except Exception as e:
            logger.error(f"Failed to publish inspection result: {e}")

    def _publish_available_devices(self, available_devices):
        """Publish available devices list via MQTT."""
        topic = "factory/devices/available"
        message = {
            "timestamp": self.factory.env.now,
            "available_devices": available_devices
        }
        
        try:
            self.mqtt_client.publish(topic, json.dumps(message))
            logger.debug("Published available devices list")
        except Exception as e:
            logger.error(f"Failed to publish available devices: {e}")

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