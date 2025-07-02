# src/unity_interface/real_time_publisher.py
import simpy
import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from src.utils.mqtt_client import MQTTClient
from config.schemas import AGVStatus, StationStatus

@dataclass
class RealTimePosition:
    """Real-time position data for Unity visualization."""
    device_id: str
    timestamp: float
    x: float
    y: float
    z: float = 0.0  # For 3D Unity scenes
    rotation_y: float = 0.0  # Rotation around Y-axis
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    is_moving: bool = False

@dataclass
class DeviceAnimationEvent:
    """Animation event for Unity visualization."""
    device_id: str
    timestamp: float
    animation_type: str  # "start_processing", "fault_alarm", "repair_complete", etc.
    duration: float = 0.0
    parameters: Optional[Dict[str, Any]] = None

class RealTimePublisher:
    """
    High-frequency publisher for Unity visualization.
    Provides real-time updates for AGV positions and device status changes.
    """
    
    def __init__(self, env: simpy.Environment, mqtt_client: MQTTClient, factory):
        self.env = env
        self.mqtt_client = mqtt_client
        self.factory = factory
        
        # Update intervals (in simulation seconds)
        self.agv_position_interval = 0.1  # 100ms for smooth movement
        self.device_status_interval = 0.5  # 500ms for status changes
        self.animation_events_queue = []
        
        # Previous states for diff detection
        self.previous_agv_positions = {}
        self.previous_device_states = {}
        
        # Unity coordinate system conversion (optional)
        self.unity_scale = 1.0  # Scale factor for Unity world
        self.unity_origin_offset = (0, 0)  # Offset for Unity coordinates
        
        # Start real-time publishing processes
        self.env.process(self._publish_agv_positions())
        self.env.process(self._publish_device_status())
        self.env.process(self._publish_animation_events())

    def _convert_to_unity_coordinates(self, x: float, y: float) -> tuple[float, float, float]:
        """Convert simulation coordinates to Unity 3D coordinates."""
        # Apply scale and offset
        unity_x = (x + self.unity_origin_offset[0]) * self.unity_scale
        unity_z = (y + self.unity_origin_offset[1]) * self.unity_scale  # Y becomes Z in Unity
        unity_y = 0.0  # Ground level
        
        return unity_x, unity_y, unity_z

    def _calculate_rotation(self, current_pos: tuple, previous_pos: tuple) -> float:
        """Calculate rotation angle based on movement direction."""
        if current_pos == previous_pos:
            return 0.0
        
        import math
        dx = current_pos[0] - previous_pos[0]
        dy = current_pos[1] - previous_pos[1]
        
        # Calculate angle in degrees (0 = facing right, positive = counterclockwise)
        angle = math.degrees(math.atan2(dy, dx))
        return angle

    def _publish_agv_positions(self):
        """Publish AGV positions at high frequency for smooth Unity animation."""
        while True:
            try:
                for agv_id, agv in self.factory.agvs.items():
                    current_pos = agv.position
                    previous_pos = self.previous_agv_positions.get(agv_id, current_pos)
                    
                    # Convert to Unity coordinates
                    unity_x, unity_y, unity_z = self._convert_to_unity_coordinates(
                        current_pos[0], current_pos[1]
                    )
                    
                    # Calculate movement and rotation
                    is_moving = current_pos != previous_pos
                    rotation_y = self._calculate_rotation(current_pos, previous_pos) if is_moving else 0.0
                    
                    # Calculate velocity
                    time_delta = self.agv_position_interval
                    velocity_x = (current_pos[0] - previous_pos[0]) / time_delta if time_delta > 0 else 0.0
                    velocity_y = (current_pos[1] - previous_pos[1]) / time_delta if time_delta > 0 else 0.0
                    
                    # Create real-time position data
                    position_data = RealTimePosition(
                        device_id=agv_id,
                        timestamp=self.env.now,
                        x=unity_x,
                        y=unity_y,
                        z=unity_z,
                        rotation_y=rotation_y,
                        velocity_x=velocity_x,
                        velocity_y=velocity_y,
                        is_moving=is_moving
                    )
                    
                    # Publish to real-time topic
                    topic = f"factory/realtime/agv/{agv_id}/position"
                    try:
                        # Convert to JSON for Unity
                        message = {
                            "deviceId": position_data.device_id,
                            "timestamp": position_data.timestamp,
                            "position": {
                                "x": position_data.x,
                                "y": position_data.y,
                                "z": position_data.z
                            },
                            "rotation": {"y": position_data.rotation_y},
                            "velocity": {
                                "x": position_data.velocity_x,
                                "y": position_data.velocity_y
                            },
                            "isMoving": position_data.is_moving,
                            "batteryLevel": agv.battery_level,
                            "payloadCount": len(agv.payload)
                        }
                        
                        self.mqtt_client.publish(topic, json.dumps(message))
                        
                        # Only log if position actually changed (avoid spam)
                        if is_moving:
                            print(f"[{self.env.now:.2f}] 📍 Unity AGV {agv_id}: ({unity_x:.1f}, {unity_z:.1f})")
                        
                    except Exception as e:
                        print(f"[{self.env.now:.2f}] ❌ Failed to publish AGV position: {e}")
                    
                    # Update previous position
                    self.previous_agv_positions[agv_id] = current_pos
                
                # Wait for next update
                yield self.env.timeout(self.agv_position_interval)
                
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Error in AGV position publishing: {e}")
                yield self.env.timeout(1.0)  # Wait before retrying

    def _publish_device_status(self):
        """Publish device status changes for Unity visualization."""
        while True:
            try:
                # Check stations
                for station_id, station in self.factory.stations.items():
                    current_state = {
                        'status': station.status.value,
                        'buffer_level': len(station.buffer.items) if hasattr(station, 'buffer') else 0,
                        'has_fault': hasattr(station, 'fault_symptom') and station.fault_symptom is not None
                    }
                    
                    previous_state = self.previous_device_states.get(station_id, {})
                    
                    # Only publish if state changed
                    if current_state != previous_state:
                        self._publish_station_animation_event(station_id, current_state, previous_state)
                        self.previous_device_states[station_id] = current_state
                
                # Check AGVs status changes (not position, which is handled separately)
                for agv_id, agv in self.factory.agvs.items():
                    current_state = {
                        'status': agv.status.value,
                        'battery_level': agv.battery_level,
                        'is_charging': agv.is_charging,
                        'payload_count': len(agv.payload)
                    }
                    
                    previous_state = self.previous_device_states.get(f"{agv_id}_status", {})
                    
                    if current_state != previous_state:
                        self._publish_agv_animation_event(agv_id, current_state, previous_state)
                        self.previous_device_states[f"{agv_id}_status"] = current_state
                
                yield self.env.timeout(self.device_status_interval)
                
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Error in device status publishing: {e}")
                yield self.env.timeout(1.0)

    def _publish_station_animation_event(self, station_id: str, current: Dict, previous: Dict):
        """Publish station animation events for Unity."""
        events = []
        
        # Status change animations
        if current.get('status') != previous.get('status'):
            if current['status'] == 'processing':
                events.append(('start_processing', 2.0))
            elif current['status'] == 'idle':
                events.append(('stop_processing', 0.5))
            elif current['status'] == 'error':
                events.append(('fault_alarm', 5.0))
        
        # Fault-related animations
        if current.get('has_fault') and not previous.get('has_fault'):
            events.append(('fault_warning', 3.0))
        elif not current.get('has_fault') and previous.get('has_fault'):
            events.append(('repair_complete', 2.0))
        
        # Buffer level changes
        buffer_diff = current.get('buffer_level', 0) - previous.get('buffer_level', 0)
        if buffer_diff > 0:
            events.append(('buffer_increase', 1.0))
        elif buffer_diff < 0:
            events.append(('buffer_decrease', 1.0))
        
        # Queue animation events
        for animation_type, duration in events:
            event = DeviceAnimationEvent(
                device_id=station_id,
                timestamp=self.env.now,
                animation_type=animation_type,
                duration=duration,
                parameters={
                    'new_status': current['status'],
                    'buffer_level': current['buffer_level']
                }
            )
            self.animation_events_queue.append(event)

    def _publish_agv_animation_event(self, agv_id: str, current: Dict, previous: Dict):
        """Publish AGV animation events for Unity."""
        events = []
        
        # Status change animations
        if current.get('status') != previous.get('status'):
            if current['status'] == 'processing':
                events.append(('start_task', 1.0))
            elif current['status'] == 'idle':
                events.append(('task_complete', 0.5))
        
        # Battery level changes
        battery_diff = current.get('battery_level', 100) - previous.get('battery_level', 100)
        if battery_diff < -10:  # Significant battery drop
            events.append(('battery_warning', 2.0))
        
        # Charging state changes
        if current.get('is_charging') and not previous.get('is_charging'):
            events.append(('start_charging', 3.0))
        elif not current.get('is_charging') and previous.get('is_charging'):
            events.append(('stop_charging', 1.0))
        
        # Payload changes
        payload_diff = current.get('payload_count', 0) - previous.get('payload_count', 0)
        if payload_diff > 0:
            events.append(('load_product', 2.0))
        elif payload_diff < 0:
            events.append(('unload_product', 2.0))
        
        # Queue animation events
        for animation_type, duration in events:
            event = DeviceAnimationEvent(
                device_id=agv_id,
                timestamp=self.env.now,
                animation_type=animation_type,
                duration=duration,
                parameters={
                    'new_status': current['status'],
                    'battery_level': current['battery_level'],
                    'payload_count': current['payload_count']
                }
            )
            self.animation_events_queue.append(event)

    def _publish_animation_events(self):
        """Process and publish queued animation events."""
        while True:
            try:
                if self.animation_events_queue:
                    # Process all queued events
                    while self.animation_events_queue:
                        event = self.animation_events_queue.pop(0)
                        
                        topic = f"factory/realtime/device/{event.device_id}/animation"
                        message = {
                            "deviceId": event.device_id,
                            "timestamp": event.timestamp,
                            "animationType": event.animation_type,
                            "duration": event.duration,
                            "parameters": event.parameters or {}
                        }
                        
                        try:
                            self.mqtt_client.publish(topic, json.dumps(message))
                            print(f"[{self.env.now:.2f}] 🎬 Unity Animation: {event.device_id} - {event.animation_type}")
                        except Exception as e:
                            print(f"[{self.env.now:.2f}] ❌ Failed to publish animation event: {e}")
                
                yield self.env.timeout(0.1)  # Process events quickly
                
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ Error in animation event publishing: {e}")
                yield self.env.timeout(1.0)

    def add_custom_event(self, device_id: str, animation_type: str, duration: float = 2.0, parameters: Optional[Dict[str, Any]] = None):
        """Add a custom animation event to the queue."""
        event = DeviceAnimationEvent(
            device_id=device_id,
            timestamp=self.env.now,
            animation_type=animation_type,
            duration=duration,
            parameters=parameters or {}
        )
        self.animation_events_queue.append(event)

    def set_unity_scale(self, scale: float, origin_offset: tuple = (0, 0)):
        """Configure Unity coordinate system conversion."""
        self.unity_scale = scale
        self.unity_origin_offset = origin_offset
        print(f"[{self.env.now:.2f}] 🎮 Unity coordinate system: scale={scale}, offset={origin_offset}")

    def get_current_positions(self) -> Dict[str, RealTimePosition]:
        """Get current positions of all AGVs for Unity initialization."""
        positions = {}
        for agv_id, agv in self.factory.agvs.items():
            unity_x, unity_y, unity_z = self._convert_to_unity_coordinates(
                agv.position[0], agv.position[1]
            )
            
            positions[agv_id] = RealTimePosition(
                device_id=agv_id,
                timestamp=self.env.now,
                x=unity_x,
                y=unity_y,
                z=unity_z,
                rotation_y=0.0,
                velocity_x=0.0,
                velocity_y=0.0,
                is_moving=False
            )
        
        return positions 