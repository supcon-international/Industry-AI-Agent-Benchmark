# src/simulation/entities/smart_agv.py
import simpy
import math
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass

from config.schemas import DeviceStatus
from src.simulation.entities.base import Vehicle
from src.pathfinding.astar_pathfinder import AStarPathfinder, PathfindingRequest, PathfindingResult

@dataclass
class MovementCommand:
    """Movement command for AGV."""
    target_position: Tuple[float, float]
    priority: int = 1
    max_speed_override: Optional[float] = None
    allow_replanning: bool = True

@dataclass
class AGVKinematics:
    """AGV kinematic constraints."""
    max_speed: float = 2.0  # m/s
    max_acceleration: float = 1.0  # m/s²
    max_deceleration: float = 2.0  # m/s²
    turning_radius: float = 0.5  # m
    length: float = 1.2  # m
    width: float = 0.8  # m

class SmartAGV(Vehicle):
    """
    Enhanced AGV with intelligent pathfinding and dynamic obstacle avoidance.
    
    Features:
    - A* pathfinding with dynamic replanning
    - Kinematic constraints (acceleration, turning radius)
    - Multi-AGV coordination
    - Battery consumption modeling
    - Load-dependent performance
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[float, float],
        pathfinder: AStarPathfinder,
        kinematics: Optional[AGVKinematics] = None,
        battery_capacity: float = 100.0,
    ):
        # Initialize kinematics first
        self.kinematics = kinematics or AGVKinematics()
        
        # Call parent constructor with speed from kinematics
        super().__init__(env, id, position, self.kinematics.max_speed)
        
        # Pathfinding
        self.pathfinder = pathfinder
        self.current_path: List[Tuple[float, float]] = []
        self.current_target: Optional[Tuple[float, float]] = None
        self.path_index = 0
        
        # Battery and performance
        self.battery_level = 100.0
        self.battery_capacity = battery_capacity
        self.battery_drain_rate = 0.1  # %/second base rate
        self.payload = []
        self.is_charging = False
        
        # Movement state
        self.current_velocity = 0.0
        self.target_velocity = 0.0
        self.is_moving = False
        self.last_position = position
        self.movement_history = []
        
        # Path planning
        self.replanning_interval = 2.0  # Replan every 2 seconds if needed
        self.stuck_threshold = 0.1  # Consider stuck if moved < 0.1m in 5 seconds
        self.stuck_timer = 0.0
        self.emergency_stop_flag = False
        
        # Register with pathfinder
        self.pathfinder.update_dynamic_obstacle(self.id, self.position)
        
        # Start background processes
        self.env.process(self._battery_management())
        self.env.process(self._movement_monitoring())
        self.env.process(self._periodic_replanning())

    def move_to_intelligent(self, target_pos: Tuple[float, float], priority: int = 1) -> simpy.Process:
        """
        Intelligent movement using A* pathfinding.
        Replaces the simple move_to method.
        """
        return self.env.process(self._execute_intelligent_movement(target_pos, priority))

    def _execute_intelligent_movement(self, target_pos: Tuple[float, float], priority: int):
        """Execute intelligent movement with pathfinding and obstacle avoidance."""
        self.set_status(DeviceStatus.PROCESSING)
        self.current_target = target_pos
        self.is_moving = True
        
        print(f"[{self.env.now:.2f}] 🚗 {self.id}: Starting intelligent movement to {target_pos}")
        
        try:
            # Plan initial path
            success = yield from self._plan_path_to_target(target_pos, priority)
            if not success:
                print(f"[{self.env.now:.2f}] ❌ {self.id}: Failed to find path to {target_pos}")
                self._movement_failed()
                return
            
                         # Execute movement along path
            while self.current_path and self.path_index < len(self.current_path):
                if self.emergency_stop_flag:
                     print(f"[{self.env.now:.2f}] 🛑 {self.id}: Emergency stop during movement")
                     break
                
                # Move to next waypoint
                waypoint = self.current_path[self.path_index]
                yield from self._move_to_waypoint(waypoint)
                
                self.path_index += 1
                
                # Update position in pathfinder
                self.pathfinder.update_dynamic_obstacle(self.id, self.position)
            
            # Check if we reached the target
            distance_to_target = math.dist(self.position, target_pos)
            if distance_to_target < 0.5:  # Within 0.5m tolerance
                print(f"[{self.env.now:.2f}] ✅ {self.id}: Reached target {target_pos}")
                self._movement_completed()
            else:
                print(f"[{self.env.now:.2f}] ⚠️ {self.id}: Movement incomplete, {distance_to_target:.1f}m from target")
                self._movement_failed()
                
        except Exception as e:
            print(f"[{self.env.now:.2f}] ❌ {self.id}: Movement error: {e}")
            self._movement_failed()

    def _plan_path_to_target(self, target_pos: Tuple[float, float], priority: int):
        """Plan path using A* pathfinder."""
        request = PathfindingRequest(
            agv_id=self.id,
            start_pos=self.position,
            goal_pos=target_pos,
            agv_size=max(self.kinematics.length, self.kinematics.width),
            priority=priority,
            allow_diagonal=True
        )
        
        result: PathfindingResult = self.pathfinder.find_path(request)
        
        if result.success:
            self.current_path = result.path
            self.path_index = 0
            print(f"[{self.env.now:.2f}] 🗺️ {self.id}: Path planned with {len(result.path)} waypoints")
            print(f"   - Path cost: {result.path_cost:.1f}, computation: {result.computation_time*1000:.1f}ms")
            return True
        else:
            print(f"[{self.env.now:.2f}] ❌ {self.id}: Pathfinding failed: {result.failure_reason}")
            return False

    def _move_to_waypoint(self, waypoint: Tuple[float, float]):
        """Move to a single waypoint with kinematic constraints."""
        start_pos = self.position
        distance = math.dist(start_pos, waypoint)
        
        if distance < 0.1:  # Already at waypoint
            return
        
        # Calculate movement parameters
        direction = ((waypoint[0] - start_pos[0]) / distance, 
                    (waypoint[1] - start_pos[1]) / distance)
        
        # Apply kinematic constraints
        max_speed = self._calculate_max_speed()
        
        # Simple kinematic movement (could be enhanced with proper acceleration curves)
        travel_time = distance / max_speed
        
        # Consume battery during movement
        battery_cost = self._calculate_battery_consumption(distance, max_speed)
        
        print(f"[{self.env.now:.2f}] 🚗 {self.id}: Moving to waypoint {waypoint} (distance: {distance:.1f}m, time: {travel_time:.1f}s)")
        
        # Simulate movement time
        yield self.env.timeout(travel_time)
        
        # Update position and battery
        self.position = waypoint
        self.battery_level = max(0, self.battery_level - battery_cost)
        self.current_velocity = max_speed
        
        # Check for low battery
        if self.battery_level < 20:
            print(f"[{self.env.now:.2f}] 🔋 {self.id}: Low battery warning ({self.battery_level:.1f}%)")

    def _calculate_max_speed(self) -> float:
        """Calculate maximum speed considering load and battery level."""
        base_speed = self.kinematics.max_speed
        
        # Reduce speed based on battery level
        battery_factor = max(0.3, self.battery_level / 100.0)
        
        # Reduce speed based on payload
        load_factor = max(0.7, 1.0 - len(self.payload) * 0.1)
        
        return base_speed * battery_factor * load_factor

    def _calculate_battery_consumption(self, distance: float, speed: float) -> float:
        """Calculate battery consumption for a movement."""
        base_consumption = distance * self.battery_drain_rate
        
        # Higher speed increases consumption
        speed_factor = 1.0 + (speed / self.kinematics.max_speed - 1.0) * 0.5
        
        # Load increases consumption
        load_factor = 1.0 + len(self.payload) * 0.2
        
        return base_consumption * speed_factor * load_factor

    def _movement_completed(self):
        """Handle successful movement completion."""
        self.is_moving = False
        self.current_target = None
        self.current_path = []
        self.path_index = 0
        self.current_velocity = 0.0
        self.set_status(DeviceStatus.IDLE)

    def _movement_failed(self):
        """Handle movement failure."""
        self.is_moving = False
        self.current_velocity = 0.0
        self.set_status(DeviceStatus.ERROR)

    def _battery_management(self):
        """Background process for battery management."""
        while True:
            try:
                # Idle battery drain
                if not self.is_moving and not self.is_charging:
                    idle_drain = 0.01  # 1% per 100 seconds when idle
                    self.battery_level = max(0, self.battery_level - idle_drain)
                
                # Auto-charging when battery is critically low
                if self.battery_level < 10 and not self.is_charging and not self.is_moving:
                    yield from self._initiate_emergency_charging()
                
                yield self.env.timeout(1.0)  # Check every second
                
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ {self.id}: Battery management error: {e}")
                yield self.env.timeout(5.0)

    def _movement_monitoring(self):
        """Monitor movement and detect stuck situations."""
        while True:
            try:
                if self.is_moving:
                    # Check if AGV is stuck
                    distance_moved = math.dist(self.position, self.last_position)
                    
                    if distance_moved < self.stuck_threshold:
                        self.stuck_timer += 1.0
                        if self.stuck_timer > 5.0:  # Stuck for 5 seconds
                            print(f"[{self.env.now:.2f}] 🚫 {self.id}: Detected stuck situation, replanning...")
                            yield from self._handle_stuck_situation()
                    else:
                        self.stuck_timer = 0.0
                    
                    self.last_position = self.position
                
                yield self.env.timeout(1.0)
                
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ {self.id}: Movement monitoring error: {e}")
                yield self.env.timeout(5.0)

    def _periodic_replanning(self):
        """Periodically check if replanning is needed."""
        while True:
            try:
                if self.is_moving and self.current_target:
                    # Check if replanning would improve the path
                    remaining_distance = math.dist(self.position, self.current_target)
                    
                    if remaining_distance > 5.0:  # Only replan for longer distances
                        # Try to find a better path
                        request = PathfindingRequest(
                            agv_id=self.id,
                            start_pos=self.position,
                            goal_pos=self.current_target,
                            priority=1
                        )
                        
                        new_result = self.pathfinder.find_path(request)
                        if new_result.success and len(new_result.path) > 0:
                            # Check if new path is significantly better
                            current_remaining = len(self.current_path) - self.path_index
                            if len(new_result.path) < current_remaining * 0.8:
                                print(f"[{self.env.now:.2f}] 🔄 {self.id}: Replanning - found better path")
                                self.current_path = new_result.path
                                self.path_index = 0
                
                yield self.env.timeout(self.replanning_interval)
                
            except Exception as e:
                print(f"[{self.env.now:.2f}] ❌ {self.id}: Replanning error: {e}")
                yield self.env.timeout(5.0)

    def _handle_stuck_situation(self):
        """Handle situations where AGV is stuck."""
        print(f"[{self.env.now:.2f}] 🔧 {self.id}: Handling stuck situation")
        
        # Try emergency replanning with higher priority
        if self.current_target:
            request = PathfindingRequest(
                agv_id=self.id,
                start_pos=self.position,
                goal_pos=self.current_target,
                priority=10,  # High priority
                allow_diagonal=True
            )
            
            result = self.pathfinder.find_path(request)
            if result.success:
                self.current_path = result.path
                self.path_index = 0
                self.stuck_timer = 0.0
                print(f"[{self.env.now:.2f}] ✅ {self.id}: Emergency replanning successful")
            else:
                # If still can't find path, wait and try again
                print(f"[{self.env.now:.2f}] ⏳ {self.id}: Waiting before retry...")
                yield self.env.timeout(3.0)
                self.stuck_timer = 0.0

    def _initiate_emergency_charging(self):
        """Start emergency charging process."""
        print(f"[{self.env.now:.2f}] 🔌 {self.id}: Starting emergency charging")
        self.is_charging = True
        self.set_status(DeviceStatus.MAINTENANCE)
        
        # Simulate charging time (simplified)
        charging_time = (100 - self.battery_level) * 0.5  # 0.5 seconds per %
        yield self.env.timeout(charging_time)
        
        self.battery_level = 100.0
        self.is_charging = False
        self.set_status(DeviceStatus.IDLE)
        print(f"[{self.env.now:.2f}] 🔋 {self.id}: Charging complete")

    def emergency_stop(self):
        """Immediately stop the AGV."""
        self.emergency_stop = True
        self.current_velocity = 0.0
        self.is_moving = False
        self.set_status(DeviceStatus.ERROR)
        print(f"[{self.env.now:.2f}] 🛑 {self.id}: Emergency stop activated")

    def resume_operation(self):
        """Resume operation after emergency stop."""
        self.emergency_stop = False
        self.set_status(DeviceStatus.IDLE)
        print(f"[{self.env.now:.2f}] ▶️ {self.id}: Operation resumed")

    def load_product(self, product):
        """Load a product onto the AGV."""
        self.payload.append(product)
        print(f"[{self.env.now:.2f}] 📦 {self.id}: Loaded product {product.id} (payload: {len(self.payload)})")

    def unload_product(self, product_id: str):
        """Unload a product from the AGV."""
        product_to_remove = next((p for p in self.payload if p.id == product_id), None)
        if product_to_remove:
            self.payload.remove(product_to_remove)
            print(f"[{self.env.now:.2f}] 📤 {self.id}: Unloaded product {product_id} (payload: {len(self.payload)})")
            return product_to_remove
        else:
            print(f"[{self.env.now:.2f}] ❌ {self.id}: Product {product_id} not found in payload")
            return None

    def get_detailed_status(self):
        """Get detailed AGV status for monitoring."""
        base_status = super().get_detailed_status()
        
        # Add AGV-specific details
        base_status.battery_level = self.battery_level
        base_status.position_accuracy = 95.0 if not self.is_moving else 90.0
        
        # Add additional information
        return {
            **base_status.__dict__,
            'current_velocity': self.current_velocity,
            'target_velocity': self.target_velocity,
            'is_moving': self.is_moving,
            'payload_count': len(self.payload),
            'is_charging': self.is_charging,
            'emergency_stop': self.emergency_stop,
            'current_target': self.current_target,
            'path_progress': f"{self.path_index}/{len(self.current_path)}" if self.current_path else "0/0"
        }

    def cleanup(self):
        """Clean up resources when AGV is destroyed."""
        self.pathfinder.remove_dynamic_obstacle(self.id) 