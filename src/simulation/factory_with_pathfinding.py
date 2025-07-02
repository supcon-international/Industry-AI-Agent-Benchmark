"""
Enhanced Factory with A* pathfinding and Unity real-time publishing.
This version integrates all the new features while maintaining compatibility.
"""

import simpy
import random
from typing import Dict, List, Tuple, Optional

from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
from src.pathfinding.astar_pathfinder import AStarPathfinder, PathfindingRequest
from src.unity_interface.real_time_publisher import RealTimePublisher
from src.utils.mqtt_client import MQTTClient

class EnhancedFactory(Factory):
    """
    Enhanced Factory with intelligent pathfinding and Unity visualization support.
    
    New Features:
    - A* pathfinding for AGV navigation
    - Unity real-time publisher (100ms updates)
    - Dynamic obstacle avoidance
    - Improved AGV movement intelligence
    """
    
    def __init__(self, layout_config: Dict, mqtt_client: MQTTClient):
        # Initialize pathfinding system first (larger grid cells, smaller factory)
        self.pathfinder = AStarPathfinder(
            factory_width=80.0,
            factory_height=40.0, 
            grid_resolution=2.0  # Larger cells for faster pathfinding
        )
        
        # Call parent constructor
        super().__init__(layout_config, mqtt_client)
        
        # Setup pathfinding obstacles based on station positions
        self._setup_static_obstacles()
        
        # Override Unity publisher initialization message
        print(f"[{self.env.now:.2f}] 🏭 Enhanced Factory with A* pathfinding initialized")

    def _setup_static_obstacles(self):
        """Setup static obstacles in the pathfinding grid based on station positions."""
        for station_id, station_cfg in enumerate(self.layout['stations']):
            position = station_cfg['position']
            # Add station as smaller obstacle to allow path planning around them
            self.pathfinder.add_static_obstacle(position, size=1.5)
            print(f"[{self.env.now:.2f}] 🚧 Added station obstacle at {station_id}: {position}")
        
        # Add factory boundaries as obstacles
        self._add_boundary_obstacles()
    
    def _add_boundary_obstacles(self):
        """Add factory boundary walls as obstacles."""
        # Skip boundary obstacles for now to avoid blocking AGV paths
        # In a real factory, the pathfinding would account for actual physical boundaries
        print(f"[{self.env.now:.2f}] 🚧 Boundary obstacles skipped to allow free AGV movement")
        # TODO: Add smarter boundary handling that doesn't block valid paths

    def move_agv_intelligent(self, agv_id: str, target_position: Tuple[float, float]):
        """
        Move AGV using intelligent A* pathfinding.
        Replaces the original move_agv method with pathfinding capabilities.
        """
        if agv_id not in self.agvs:
            raise ValueError(f"AGV {agv_id} does not exist.")
        
        agv = self.agvs[agv_id]
        current_pos = agv.position
        
        print(f"[{self.env.now:.2f}] 🚗 {agv_id}: Planning intelligent route from {current_pos} to {target_position}")
        
        # Update AGV position in pathfinder
        self.pathfinder.update_dynamic_obstacle(agv_id, current_pos)
        
        # Plan path using A*
        request = PathfindingRequest(
            agv_id=agv_id,
            start_pos=current_pos,
            goal_pos=target_position,
            agv_size=1.0,
            priority=1,
            allow_diagonal=True
        )
        
        result = self.pathfinder.find_path(request)
        
        if result.success:
            print(f"[{self.env.now:.2f}] 🗺️ {agv_id}: Path found with {len(result.path)} waypoints")
            print(f"   - Computation time: {result.computation_time*1000:.1f}ms")
            print(f"   - Path cost: {result.path_cost:.1f}")
            
            # Execute movement along the planned path
            yield from self._execute_intelligent_movement(agv_id, result.path)
        else:
            print(f"[{self.env.now:.2f}] ❌ {agv_id}: Pathfinding failed - {result.failure_reason}")
            print(f"[{self.env.now:.2f}] 🔄 {agv_id}: Using fallback movement (direct path)")
            # Fallback to simple movement
            yield from self._fallback_movement(agv_id, target_position)

    def _execute_intelligent_movement(self, agv_id: str, path: List[Tuple[float, float]]):
        """Execute movement along the planned path."""
        agv = self.agvs[agv_id]
        
        print(f"[{self.env.now:.2f}] 🚗 {agv_id}: Starting intelligent movement")
        
        for i, waypoint in enumerate(path):
            if i == 0:
                continue  # Skip starting position
            
            # Move to waypoint
            yield from self._move_to_waypoint(agv, waypoint)
            
            # Update position in pathfinder
            self.pathfinder.update_dynamic_obstacle(agv_id, agv.position)
            
            # Small delay between waypoints for realism
            yield self.env.timeout(0.1)
        
        print(f"[{self.env.now:.2f}] ✅ {agv_id}: Intelligent movement completed")

    def _move_to_waypoint(self, agv, waypoint: Tuple[float, float]):
        """Move AGV to a single waypoint."""
        import math
        
        start_pos = agv.position
        distance = math.dist(start_pos, waypoint)
        
        if distance < 0.1:  # Already at waypoint
            return
        
        # Calculate travel time
        travel_time = distance / agv.speed_mps
        
        print(f"[{self.env.now:.2f}] 📍 {agv.id}: Moving to waypoint {waypoint} (distance: {distance:.1f}m)")
        
        # Simulate movement
        yield self.env.timeout(travel_time)
        
        # Update AGV position (convert to int tuple)
        agv.position = (int(waypoint[0]), int(waypoint[1]))

    def _fallback_movement(self, agv_id: str, target_position: Tuple[float, float]):
        """Fallback to simple movement if pathfinding fails."""
        agv = self.agvs[agv_id]
        import math
        
        distance = math.dist(agv.position, target_position)
        travel_time = distance / agv.speed_mps
        
        print(f"[{self.env.now:.2f}] 🔄 {agv_id}: Using fallback movement (direct path)")
        
        yield self.env.timeout(travel_time)
        agv.position = (int(target_position[0]), int(target_position[1]))
        
        # Update pathfinder
        self.pathfinder.update_dynamic_obstacle(agv_id, target_position)

    def demonstrate_intelligent_navigation(self):
        """Demonstrate the intelligent navigation capabilities."""
        print(f"\n[{self.env.now:.2f}] 🎯 === Demonstrating Intelligent AGV Navigation ===")
        
        # Demo 1: Move AGV_1 to different stations
        demo_positions = [
            (15, 20),   # Near StationA
            (35, 20),   # Near StationB  
            (55, 20),   # Near StationC
            (75, 20),   # Near QualityCheck
            (10, 15),   # Back to start
        ]
        
        for i, pos in enumerate(demo_positions):
            print(f"\n[{self.env.now:.2f}] 📍 Demo {i+1}: Moving AGV_1 to {pos}")
            yield self.env.process(self.move_agv_intelligent('AGV_1', pos))
            yield self.env.timeout(1.0)  # Short pause between moves
        
        # Demo 2: Coordinate multiple AGVs
        print(f"\n[{self.env.now:.2f}] 🚗🚗 Demo: Coordinated multi-AGV movement")
        
        # Move both AGVs simultaneously to test coordination
        proc1 = self.env.process(self.move_agv_intelligent('AGV_1', (40, 15)))
        proc2 = self.env.process(self.move_agv_intelligent('AGV_2', (40, 25)))
        
        yield proc1 & proc2  # Wait for both to complete
        
        print(f"\n[{self.env.now:.2f}] ✅ === Navigation demonstration completed ===")
        
        # Display pathfinding statistics
        stats = self.pathfinder.get_statistics()
        print(f"\n📊 Pathfinding Statistics:")
        for key, value in stats.items():
            print(f"   - {key}: {value}")

    def visualize_pathfinding_grid(self):
        """Visualize the current pathfinding grid state."""
        print(f"\n[{self.env.now:.2f}] 🗺️ Current Pathfinding Grid:")
        print("Legend: █=obstacle, A=AGV, ·=path, space=free")
        print(self.pathfinder.visualize_grid())

    def get_pathfinding_statistics(self) -> Dict:
        """Get comprehensive pathfinding statistics."""
        base_stats = self.pathfinder.get_statistics()
        
        # Add factory-specific information
        base_stats.update({
            'factory_agvs': len(self.agvs),
            'factory_stations': len(self.stations),
            'unity_publisher_active': hasattr(self, 'unity_publisher'),
            'simulation_time': self.env.now
        })
        
        return base_stats

# Convenience function to create enhanced factory
def create_enhanced_factory(mqtt_client: Optional[MQTTClient] = None) -> EnhancedFactory:
    """Create an enhanced factory with all new features enabled."""
    if mqtt_client is None:
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        mqtt_client = MQTTClient(
            host=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            client_id="enhanced_factory"
        )
        mqtt_client.connect()
    
    return EnhancedFactory(MOCK_LAYOUT_CONFIG, mqtt_client)

# Example usage
if __name__ == '__main__':
    print("🚀 Enhanced Factory with A* Pathfinding Demo")
    
    # Create enhanced factory
    factory = create_enhanced_factory()
    
    # Visualize initial grid
    factory.visualize_pathfinding_grid()
    
    # Run navigation demonstration
    factory.env.process(factory.demonstrate_intelligent_navigation())
    factory.run(until=60)
    
    # Show final statistics
    print("\n📊 Final Statistics:")
    stats = factory.get_pathfinding_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}") 