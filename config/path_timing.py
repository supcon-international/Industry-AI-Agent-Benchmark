# config/path_timing.py
"""
Path segment timing configuration for AGV navigation.
Defines the time required to travel between specific path points.
"""

from typing import Dict, Tuple

# Path segment timing hashtable
# Key: (point_from, point_to) tuple
# Value: travel time in seconds
# Note: Bidirectional paths have the same timing (P0-P1 == P1-P0)
PATH_SEGMENT_TIMES: Dict[Tuple[str, str], float] = {
    # Main production line forward
    ("P0", "P1"): 3.5,  # Raw material to StationA
    ("P1", "P2"): 6.5,  # StationA to Conveyor_AB
    ("P2", "P3"): 3.5,  # Conveyor_AB to StationB
    ("P3", "P4"): 6.5,  # StationB to Conveyor_BC
    ("P4", "P5"): 3.5,  # Conveyor_BC to StationC
    ("P5", "P6"): 6.5,  # StationC to Conveyor_CQ
    ("P6", "P7"): 3.5,  # Conveyor_CQ to QualityChecker
    ("P7", "P8"): 4.0,  # QualityChecker to output
    ("P8", "P9"): 7.5,  # Output to Warehouse
    
    # Return path (same timing as forward)
    ("P1", "P0"): 3.5,
    ("P2", "P1"): 6.5,
    ("P3", "P2"): 3.5,
    ("P4", "P3"): 6.5,
    ("P5", "P4"): 3.5,
    ("P6", "P5"): 6.5,
    ("P7", "P6"): 3.5,
    ("P8", "P7"): 4.0,
    ("P9", "P8"): 7.5,
    
    # Cross connections and shortcuts
    ("P0", "P2"): 9.8,  # Direct route skipping P1
    ("P2", "P0"): 9.8,
    ("P1", "P3"): 9.8,  # Direct route skipping P2
    ("P3", "P1"): 9.8,
    ("P2", "P4"): 9.8,  # Direct route skipping P3
    ("P4", "P2"): 9.8,
    ("P3", "P5"): 9.8,  # Direct route skipping P4
    ("P5", "P3"): 9.8,
    ("P4", "P6"): 9.8,  # Direct route skipping P5
    ("P6", "P4"): 9.8,
    ("P5", "P7"): 9.8,  # Direct route skipping P6
    ("P7", "P5"): 9.8,
    ("P6", "P8"): 7.3,  # Direct route skipping P7
    ("P8", "P6"): 7.3,
    ("P7", "P9"): 11.3,  # Direct route skipping P8
    ("P9", "P7"): 11.3,
    
    # Charging point connections
    ("P10", "P0"): 5.0,  # Charging to raw material
    ("P0", "P10"): 5.0,
    ("P10", "P1"): 4.2,  # Charging to StationA
    ("P1", "P10"): 4.2,
    ("P10", "P2"): 7.8,  # Charging to Conveyor_AB
    ("P2", "P10"): 7.8,
    ("P10", "P3"): 8.5,  # Charging to StationB
    ("P3", "P10"): 8.5,
    ("P10", "P4"): 11.8,  # Charging to Conveyor_BC
    ("P4", "P10"): 11.8,
    ("P10", "P5"): 12.5,  # Charging to StationC
    ("P5", "P10"): 12.5,
    ("P10", "P6"): 15.8,  # Charging to Conveyor_CQ
    ("P6", "P10"): 15.8,
    ("P10", "P7"): 16.5,  # Charging to QualityChecker
    ("P7", "P10"): 16.5,
    ("P10", "P8"): 18.2,  # Charging to output
    ("P8", "P10"): 18.2,
    ("P10", "P9"): 22.5,  # Charging to Warehouse
    ("P9", "P10"): 22.5,
    
    # Emergency direct connections (longer but possible)
    ("P0", "P9"): 45.0,  # Full production line traverse
    ("P9", "P0"): 45.0,
    ("P0", "P5"): 23.5,  # Raw material to StationC
    ("P5", "P0"): 23.5,
    ("P1", "P6"): 26.8,  # StationA to Conveyor_CQ
    ("P6", "P1"): 26.8,
    ("P2", "P7"): 23.3,  # Conveyor_AB to QualityChecker
    ("P7", "P2"): 23.3,
    ("P3", "P8"): 19.8,  # StationB to output
    ("P8", "P3"): 19.8,
    ("P4", "P9"): 16.3,  # Conveyor_BC to Warehouse
    ("P9", "P4"): 16.3,
}


def get_travel_time(from_point: str, to_point: str) -> float:
    """
    Get travel time between two path points.
    
    Args:
        from_point: Starting path point (e.g., "P0")
        to_point: Destination path point (e.g., "P1")
        
    Returns:
        Travel time in seconds, or -1 if path not found
    """
    segment = (from_point, to_point)
    return PATH_SEGMENT_TIMES.get(segment, -1.0)


def get_all_reachable_points(from_point: str) -> Dict[str, float]:
    """
    Get all points reachable from a given point with their travel times.
    
    Args:
        from_point: Starting path point
        
    Returns:
        Dictionary mapping destination points to travel times
    """
    reachable = {}
    for (start, end), time in PATH_SEGMENT_TIMES.items():
        if start == from_point:
            reachable[end] = time
    return reachable


def is_path_available(from_point: str, to_point: str) -> bool:
    """
    Check if a direct path exists between two points.
    
    Args:
        from_point: Starting path point
        to_point: Destination path point
        
    Returns:
        True if direct path exists, False otherwise
    """
    return (from_point, to_point) in PATH_SEGMENT_TIMES