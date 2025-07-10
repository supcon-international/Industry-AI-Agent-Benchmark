"""
Configuration loader for SUPCON Factory Simulation
Loads configuration from YAML files and provides typed access to configuration data.
"""

import yaml
import os
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class StationConfig:
    """Configuration for a factory station."""
    id: str
    name: str
    position: Tuple[int, int]
    buffer_size: int
    processing_times: Dict[str, Tuple[int, int]]
    precision_level: float
    maintenance_cost: float

@dataclass
class AGVConfig:
    """Configuration for an AGV."""
    id: str
    name: str
    initial_position: Tuple[int, int]
    speed_mps: float
    battery_level: float
    battery_consumption_rate: float
    charging_rate: float
    payload_capacity: int
    maintenance_cost: float

@dataclass
class ProductionConfig:
    """Production-related configuration."""
    order_generation: Dict[str, Any]
    material_costs: Dict[str, float]
    energy: Dict[str, Any]
    defect_costs: Dict[str, float]

@dataclass
class FaultSystemConfig:
    """Fault system configuration."""
    injection_interval: Tuple[int, int]
    auto_recovery_time: Tuple[int, int]
    device_relationships: Dict[str, List[str]]

@dataclass
class SystemConfig:
    """System-level configuration."""
    status_publish_interval: float
    simulation_step_size: float
    max_concurrent_orders: int

@dataclass
class FactoryConfig:
    """Complete factory configuration."""
    factory: Dict[str, str]
    path_points: Dict[str, Tuple[int, int]]
    path_segments: List[Tuple[str, str]]
    stations: List[StationConfig]
    agvs: List[AGVConfig]
    production: ProductionConfig
    fault_system: FaultSystemConfig
    kpi_weights: Dict[str, float]
    system: SystemConfig

class ConfigLoader:
    """Loads and validates configuration from YAML files."""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._config_cache: Dict[str, Any] = {}
    
    def load_factory_layout(self) -> FactoryConfig:
        """Load factory layout configuration from YAML file."""
        config_file = self.config_dir / "factory_layout.yml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        # Load raw YAML
        with open(config_file, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # Parse and validate configuration
        return self._parse_factory_config(raw_config)
    
    def _parse_factory_config(self, raw_config: Dict[str, Any]) -> FactoryConfig:
        """Parse raw configuration into typed objects."""
        
        # Parse path points
        path_points = {}
        for point_id, coords in raw_config['path_points'].items():
            path_points[point_id] = tuple(coords)
        
        # Parse path segments
        path_segments = []
        for segment in raw_config['path_segments']:
            path_segments.append(tuple(segment))
        
        # Parse stations
        stations = []
        for station_data in raw_config['stations']:
            # Convert processing times to tuples
            processing_times = {}
            for product, times in station_data['processing_times'].items():
                processing_times[product] = tuple(times)
            
            station = StationConfig(
                id=station_data['id'],
                name=station_data['name'],
                position=tuple(station_data['position']),
                buffer_size=station_data['buffer_size'],
                processing_times=processing_times,
                precision_level=station_data['precision_level'],
                maintenance_cost=station_data['maintenance_cost']
            )
            stations.append(station)
        
        # Parse AGVs
        agvs = []
        for agv_data in raw_config['agvs']:
            agv = AGVConfig(
                id=agv_data['id'],
                name=agv_data['name'],
                initial_position=tuple(agv_data['initial_position']),
                speed_mps=agv_data['speed_mps'],
                battery_level=agv_data['battery_level'],
                battery_consumption_rate=agv_data['battery_consumption_rate'],
                charging_rate=agv_data['charging_rate'],
                payload_capacity=agv_data['payload_capacity'],
                maintenance_cost=agv_data['maintenance_cost']
            )
            agvs.append(agv)
        
        # Parse production config
        production = ProductionConfig(
            order_generation=raw_config['production']['order_generation'],
            material_costs=raw_config['production']['material_costs'],
            energy=raw_config['production']['energy'],
            defect_costs=raw_config['production']['defect_costs']
        )
        
        # Parse fault system config
        fault_system = FaultSystemConfig(
            injection_interval=tuple(raw_config['fault_system']['injection_interval']),
            auto_recovery_time=tuple(raw_config['fault_system']['auto_recovery_time']),
            device_relationships=raw_config['fault_system']['device_relationships']
        )
        
        # Parse system config
        system = SystemConfig(
            status_publish_interval=raw_config['system']['status_publish_interval'],
            simulation_step_size=raw_config['system']['simulation_step_size'],
            max_concurrent_orders=raw_config['system']['max_concurrent_orders']
        )
        
        return FactoryConfig(
            factory=raw_config['factory'],
            path_points=path_points,
            path_segments=path_segments,
            stations=stations,
            agvs=agvs,
            production=production,
            fault_system=fault_system,
            kpi_weights=raw_config['kpi_weights'],
            system=system
        )
    
    def get_legacy_layout_config(self) -> Dict[str, Any]:
        """
        Convert new configuration format to legacy MOCK_LAYOUT_CONFIG format
        for backward compatibility.
        """
        config = self.load_factory_layout()
        
        # Convert to legacy format
        legacy_config = {
            'path_points': config.path_points,
            'path_segments': config.path_segments,
            'stations': [],
            'agvs': []
        }
        
        # Convert stations to legacy format
        for station in config.stations:
            legacy_station = {
                'id': station.id,
                'position': station.position,
                'buffer_size': station.buffer_size,
                'processing_times': station.processing_times
            }
            legacy_config['stations'].append(legacy_station)
        
        # Convert AGVs to legacy format
        for agv in config.agvs:
            legacy_agv = {
                'id': agv.id,
                'position': agv.initial_position,  # Use initial_position as position
                'speed_mps': agv.speed_mps,
                'battery_level': agv.battery_level
            }
            legacy_config['agvs'].append(legacy_agv)
        
        return legacy_config
    
    def validate_config(self, config: FactoryConfig) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Validate path points exist
        if not config.path_points:
            errors.append("No path points defined")
        
        # Validate stations
        if not config.stations:
            errors.append("No stations defined")
        
        for station in config.stations:
            if not station.processing_times:
                errors.append(f"Station {station.id} has no processing times defined")
        
        # Validate AGVs
        if not config.agvs:
            errors.append("No AGVs defined")
        
        # Validate path segments reference valid points
        for segment in config.path_segments:
            start, end = segment
            if start not in config.path_points:
                errors.append(f"Path segment references unknown point: {start}")
            if end not in config.path_points:
                errors.append(f"Path segment references unknown point: {end}")
        
        # Validate device relationships
        all_device_ids = [s.id for s in config.stations] + [a.id for a in config.agvs]
        for device_id, related_devices in config.fault_system.device_relationships.items():
            if device_id not in all_device_ids:
                errors.append(f"Device relationship references unknown device: {device_id}")
            for related_id in related_devices:
                if related_id not in all_device_ids:
                    errors.append(f"Device {device_id} references unknown related device: {related_id}")
        
        return errors

# Global configuration loader instance
_config_loader: Optional[ConfigLoader] = None

def get_config_loader() -> ConfigLoader:
    """Get or create the global configuration loader instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader

def load_factory_config() -> FactoryConfig:
    """Convenience function to load factory configuration."""
    return get_config_loader().load_factory_layout()

def get_legacy_layout_config() -> Dict[str, Any]:
    """Convenience function to get legacy layout configuration."""
    return get_config_loader().get_legacy_layout_config()

# Cache the configuration for performance
_cached_config: Optional[FactoryConfig] = None

def get_cached_factory_config() -> FactoryConfig:
    """Get cached factory configuration, loading if necessary."""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_factory_config()
        
        # Validate configuration
        loader = get_config_loader()
        errors = loader.validate_config(_cached_config)
        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors))
    
    return _cached_config 