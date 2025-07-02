# src/pathfinding/astar_pathfinder.py
import heapq
import math
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass, field
from enum import Enum

@dataclass
class GridNode:
    """Grid node for A* pathfinding."""
    x: int
    y: int
    g_cost: float = float('inf')  # Cost from start
    h_cost: float = 0.0  # Heuristic cost to goal
    f_cost: float = float('inf')  # Total cost
    parent: Optional['GridNode'] = None
    is_obstacle: bool = False
    is_occupied: bool = False  # Temporarily occupied by another AGV
    
    def __post_init__(self):
        self.f_cost = self.g_cost + self.h_cost
    
    def __lt__(self, other):
        return self.f_cost < other.f_cost

class ObstacleType(Enum):
    STATIC = "static"      # Permanent obstacles (walls, equipment)
    DYNAMIC = "dynamic"    # Moving obstacles (other AGVs)
    TEMPORARY = "temporary" # Temporary obstacles (maintenance areas)

@dataclass
class PathfindingRequest:
    """Request for pathfinding service."""
    agv_id: str
    start_pos: Tuple[float, float]
    goal_pos: Tuple[float, float]
    agv_size: float = 1.0  # AGV size for collision checking
    priority: int = 1  # Higher values = higher priority
    max_path_length: Optional[int] = None
    allow_diagonal: bool = True

@dataclass
class PathfindingResult:
    """Result of pathfinding operation."""
    success: bool
    path: List[Tuple[float, float]] = field(default_factory=list)
    path_cost: float = 0.0
    computation_time: float = 0.0
    nodes_explored: int = 0
    failure_reason: Optional[str] = None

class AStarPathfinder:
    """
    Advanced A* pathfinding for AGV navigation with dynamic obstacles.
    
    Features:
    - Grid-based A* algorithm
    - Dynamic obstacle avoidance
    - Multi-AGV coordination
    - Path smoothing and optimization
    """
    
    def __init__(self, factory_width: float = 100.0, factory_height: float = 50.0, grid_resolution: float = 0.5):
        self.factory_width = factory_width
        self.factory_height = factory_height
        self.grid_resolution = grid_resolution
        
        # Grid dimensions
        self.grid_width = int(factory_width / grid_resolution)
        self.grid_height = int(factory_height / grid_resolution)
        
        # Initialize grid
        self.grid: List[List[GridNode]] = []
        self._initialize_grid()
        
        # Obstacle management
        self.static_obstacles: Set[Tuple[int, int]] = set()
        self.dynamic_obstacles: Dict[str, Tuple[int, int]] = {}  # agv_id -> grid_pos
        self.temporary_obstacles: Dict[str, Tuple[int, int, float]] = {}  # id -> (x, y, expiry_time)
        
        # Path reservations for multi-AGV coordination
        self.path_reservations: Dict[str, List[Tuple[int, int, float]]] = {}  # agv_id -> [(x, y, time), ...]
        
        # Statistics
        self.total_requests = 0
        self.successful_paths = 0
        
    def _initialize_grid(self):
        """Initialize the pathfinding grid."""
        self.grid = []
        for y in range(self.grid_height):
            row = []
            for x in range(self.grid_width):
                node = GridNode(x=x, y=y)
                row.append(node)
            self.grid.append(row)
    
    def world_to_grid(self, world_pos: Tuple[float, float]) -> Tuple[int, int]:
        """Convert world coordinates to grid coordinates."""
        x, y = world_pos
        grid_x = int(x / self.grid_resolution)
        grid_y = int(y / self.grid_resolution)
        
        # Clamp to grid bounds
        grid_x = max(0, min(grid_x, self.grid_width - 1))
        grid_y = max(0, min(grid_y, self.grid_height - 1))
        
        return grid_x, grid_y
    
    def grid_to_world(self, grid_pos: Tuple[int, int]) -> Tuple[float, float]:
        """Convert grid coordinates to world coordinates."""
        grid_x, grid_y = grid_pos
        world_x = (grid_x + 0.5) * self.grid_resolution
        world_y = (grid_y + 0.5) * self.grid_resolution
        return world_x, world_y
    
    def add_static_obstacle(self, world_pos: Tuple[float, float], size: float = 1.0):
        """Add a static obstacle (equipment, walls, etc.)."""
        center_x, center_y = self.world_to_grid(world_pos)
        radius = int(size / self.grid_resolution / 2)
        
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x, y = center_x + dx, center_y + dy
                if 0 <= x < self.grid_width and 0 <= y < self.grid_height:
                    self.static_obstacles.add((x, y))
                    self.grid[y][x].is_obstacle = True
    
    def update_dynamic_obstacle(self, agv_id: str, world_pos: Tuple[float, float]):
        """Update the position of a dynamic obstacle (another AGV)."""
        # Clear previous position
        if agv_id in self.dynamic_obstacles:
            old_x, old_y = self.dynamic_obstacles[agv_id]
            if 0 <= old_x < self.grid_width and 0 <= old_y < self.grid_height:
                self.grid[old_y][old_x].is_occupied = False
        
        # Set new position
        new_x, new_y = self.world_to_grid(world_pos)
        if 0 <= new_x < self.grid_width and 0 <= new_y < self.grid_height:
            self.dynamic_obstacles[agv_id] = (new_x, new_y)
            self.grid[new_y][new_x].is_occupied = True
    
    def remove_dynamic_obstacle(self, agv_id: str):
        """Remove a dynamic obstacle."""
        if agv_id in self.dynamic_obstacles:
            x, y = self.dynamic_obstacles[agv_id]
            if 0 <= x < self.grid_width and 0 <= y < self.grid_height:
                self.grid[y][x].is_occupied = False
            del self.dynamic_obstacles[agv_id]
    
    def find_path(self, request: PathfindingRequest) -> PathfindingResult:
        """Find optimal path using A* algorithm."""
        import time
        start_time = time.time()
        
        self.total_requests += 1
        
        # Convert coordinates
        start_grid = self.world_to_grid(request.start_pos)
        goal_grid = self.world_to_grid(request.goal_pos)
        
        # Validate start and goal
        if not self._is_valid_position(start_grid) or not self._is_valid_position(goal_grid):
            return PathfindingResult(
                success=False,
                failure_reason="Invalid start or goal position"
            )
        
        # Reset grid costs
        self._reset_grid_costs()
        
        # A* algorithm
        open_set = []
        closed_set = set()
        
        start_node = self.grid[start_grid[1]][start_grid[0]]
        start_node.g_cost = 0
        start_node.h_cost = self._heuristic(start_grid, goal_grid)
        start_node.f_cost = start_node.g_cost + start_node.h_cost
        
        heapq.heappush(open_set, start_node)
        nodes_explored = 0
        
        while open_set:
            current = heapq.heappop(open_set)
            current_pos = (current.x, current.y)
            
            if current_pos in closed_set:
                continue
                
            closed_set.add(current_pos)
            nodes_explored += 1
            
            # Check if we reached the goal
            if current_pos == goal_grid:
                path = self._reconstruct_path(current)
                world_path = [self.grid_to_world(pos) for pos in path]
                smoothed_path = self._smooth_path(world_path)
                
                computation_time = time.time() - start_time
                self.successful_paths += 1
                
                return PathfindingResult(
                    success=True,
                    path=smoothed_path,
                    path_cost=current.g_cost,
                    computation_time=computation_time,
                    nodes_explored=nodes_explored
                )
            
            # Explore neighbors
            neighbors = self._get_neighbors(current, request.allow_diagonal)
            for neighbor in neighbors:
                neighbor_pos = (neighbor.x, neighbor.y)
                
                if neighbor_pos in closed_set:
                    continue
                
                if not self._is_walkable(neighbor_pos, request.agv_id):
                    continue
                
                # Calculate movement cost
                movement_cost = self._calculate_movement_cost(current_pos, neighbor_pos)
                tentative_g_cost = current.g_cost + movement_cost
                
                if tentative_g_cost < neighbor.g_cost:
                    neighbor.parent = current
                    neighbor.g_cost = tentative_g_cost
                    neighbor.h_cost = self._heuristic(neighbor_pos, goal_grid)
                    neighbor.f_cost = neighbor.g_cost + neighbor.h_cost
                    
                    heapq.heappush(open_set, neighbor)
            
            # Early termination for performance
            if request.max_path_length and nodes_explored > request.max_path_length:
                break
        
        # No path found
        computation_time = time.time() - start_time
        return PathfindingResult(
            success=False,
            computation_time=computation_time,
            nodes_explored=nodes_explored,
            failure_reason="No path found"
        )
    
    def _reset_grid_costs(self):
        """Reset g, h, f costs for all nodes."""
        for row in self.grid:
            for node in row:
                node.g_cost = float('inf')
                node.h_cost = 0.0
                node.f_cost = float('inf')
                node.parent = None
    
    def _is_valid_position(self, grid_pos: Tuple[int, int]) -> bool:
        """Check if grid position is within bounds."""
        x, y = grid_pos
        return 0 <= x < self.grid_width and 0 <= y < self.grid_height
    
    def _is_walkable(self, grid_pos: Tuple[int, int], requesting_agv_id: str) -> bool:
        """Check if a grid position is walkable for the given AGV."""
        x, y = grid_pos
        node = self.grid[y][x]
        
        # Check static obstacles
        if node.is_obstacle:
            return False
        
        # Check if occupied by another AGV (but allow if it's the requesting AGV)
        if node.is_occupied:
            if grid_pos in self.dynamic_obstacles.values():
                # Find which AGV is at this position
                for agv_id, pos in self.dynamic_obstacles.items():
                    if pos == grid_pos and agv_id != requesting_agv_id:
                        return False
        
        return True
    
    def _heuristic(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate heuristic distance (Manhattan distance with diagonal moves)."""
        x1, y1 = pos1
        x2, y2 = pos2
        
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        
        # Diagonal distance (Chebyshev distance)
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)
    
    def _get_neighbors(self, node: GridNode, allow_diagonal: bool) -> List[GridNode]:
        """Get neighboring nodes."""
        neighbors = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # 4-connected
        
        if allow_diagonal:
            directions.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])  # 8-connected
        
        for dx, dy in directions:
            x, y = node.x + dx, node.y + dy
            
            if self._is_valid_position((x, y)):
                neighbors.append(self.grid[y][x])
        
        return neighbors
    
    def _calculate_movement_cost(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate movement cost between two positions."""
        x1, y1 = pos1
        x2, y2 = pos2
        
        # Diagonal movement costs more
        if abs(x2 - x1) == 1 and abs(y2 - y1) == 1:
            return math.sqrt(2)
        else:
            return 1.0
    
    def _reconstruct_path(self, goal_node: GridNode) -> List[Tuple[int, int]]:
        """Reconstruct path from goal to start."""
        path = []
        current = goal_node
        
        while current is not None:
            path.append((current.x, current.y))
            current = current.parent
        
        path.reverse()
        return path
    
    def _smooth_path(self, path: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Apply path smoothing to reduce sharp turns."""
        if len(path) < 3:
            return path
        
        smoothed = [path[0]]  # Keep start point
        
        for i in range(1, len(path) - 1):
            # Check if we can skip intermediate points with direct line
            if self._can_connect_directly(smoothed[-1], path[i + 1]):
                continue  # Skip this point
            else:
                smoothed.append(path[i])
        
        smoothed.append(path[-1])  # Keep end point
        return smoothed
    
    def _can_connect_directly(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> bool:
        """Check if two positions can be connected with a straight line."""
        # Simple line-of-sight check using Bresenham's algorithm
        grid1 = self.world_to_grid(pos1)
        grid2 = self.world_to_grid(pos2)
        
        x1, y1 = grid1
        x2, y2 = grid2
        
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        
        x, y = x1, y1
        
        x_inc = 1 if x1 < x2 else -1
        y_inc = 1 if y1 < y2 else -1
        
        error = dx - dy
        
        while True:
            # Check if current position is walkable
            if not self._is_valid_position((x, y)) or self.grid[y][x].is_obstacle:
                return False
            
            if x == x2 and y == y2:
                break
            
            if error * 2 > -dy:
                error -= dy
                x += x_inc
            
            if error * 2 < dx:
                error += dx
                y += y_inc
        
        return True
    
    def get_statistics(self) -> Dict:
        """Get pathfinding statistics."""
        success_rate = (self.successful_paths / self.total_requests * 100) if self.total_requests > 0 else 0
        
        return {
            'total_requests': self.total_requests,
            'successful_paths': self.successful_paths,
            'success_rate': success_rate,
            'grid_size': f"{self.grid_width}x{self.grid_height}",
            'grid_resolution': self.grid_resolution,
            'static_obstacles': len(self.static_obstacles),
            'dynamic_obstacles': len(self.dynamic_obstacles)
        }
    
    def visualize_grid(self, path: Optional[List[Tuple[int, int]]] = None) -> str:
        """Create a simple ASCII visualization of the grid (for debugging)."""
        visualization = []
        
        for y in range(min(20, self.grid_height)):  # Limit display size
            row = ""
            for x in range(min(40, self.grid_width)):
                if (x, y) in self.static_obstacles:
                    row += "█"  # Static obstacle
                elif self.grid[y][x].is_occupied:
                    row += "A"  # AGV
                elif path and (x, y) in path:
                    row += "·"  # Path
                else:
                    row += " "  # Empty space
            visualization.append(row)
        
        return "\n".join(visualization) 