# src/game_logic/state_space_manager.py
import numpy as np
import simpy
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json

from config.schemas import NewOrder, OrderPriority
from src.game_logic.fault_system import FaultSystem

class DeviceState(Enum):
    IDLE = "idle"
    PROCESSING = "processing" 
    ERROR = "error"
    MAINTENANCE = "maintenance"
    BLOCKED = "blocked"
    OVERHEATING = "overheating"
    DEGRADED = "degraded"

class AGVState(Enum):
    IDLE = "idle"
    MOVING = "moving"
    LOADING = "loading"
    UNLOADING = "unloading"
    CHARGING = "charging"
    ERROR = "error"
    WAITING = "waiting"

@dataclass
class ComplexDeviceState:
    """Extended device state with many more dimensions."""
    device_id: str
    status: DeviceState
    utilization_history: List[float] = field(default_factory=list)  # Last 100 data points
    temperature: float = 25.0  # Operating temperature
    vibration_level: float = 0.0  # Vibration intensity 0-100
    wear_level: float = 0.0  # Component wear 0-100
    efficiency: float = 1.0  # Current efficiency multiplier
    last_maintenance: float = 0.0  # Time since last maintenance
    buffer_history: List[int] = field(default_factory=list)  # Buffer level history
    processed_products: Dict[str, int] = field(default_factory=dict)  # Product type counts
    energy_consumption: float = 0.0  # Cumulative energy usage
    error_count: int = 0  # Number of errors since last reset

@dataclass
class ComplexAGVState:
    """Extended AGV state with position, load, and complex behaviors."""
    agv_id: str
    status: AGVState
    position: Tuple[float, float]
    target_position: Optional[Tuple[float, float]]
    battery_level: float
    battery_degradation: float = 0.0  # Battery aging factor
    load_history: List[int] = field(default_factory=list)  # Load over time
    travel_distance: float = 0.0  # Total distance traveled
    speed_profile: List[float] = field(default_factory=list)  # Speed history
    collision_count: int = 0  # Near-miss collisions
    payload_weight: float = 0.0  # Current cargo weight
    route_efficiency: float = 1.0  # Path optimization metric
    last_charging_time: float = 0.0

@dataclass
class ComplexOrderState:
    """Extended order tracking with detailed progress."""
    order_id: str
    products: Dict[str, int]  # Product type -> quantity
    priority: OrderPriority
    created_at: float
    deadline: float
    current_stage: str = "waiting"  # waiting/processing/quality_check/completed
    progress_by_station: Dict[str, int] = field(default_factory=dict)
    quality_failures: int = 0
    rework_count: int = 0
    cost_accumulation: float = 0.0
    priority_changes: List[Tuple[float, OrderPriority]] = field(default_factory=list)
    delay_factors: List[str] = field(default_factory=list)  # Reasons for delays

class ComplexStateSpaceManager:
    """
    Manages the massive state space of the factory simulation.
    Tracks millions of state combinations and provides state encoding for RL.
    """
    
    def __init__(self, env: simpy.Environment, factory, fault_system: FaultSystem):
        self.env = env
        self.factory = factory
        self.fault_system = fault_system
        
        # State tracking
        self.device_states: Dict[str, ComplexDeviceState] = {}
        self.agv_states: Dict[str, ComplexAGVState] = {}
        self.order_states: Dict[str, ComplexOrderState] = {}
        
        # Historical data
        self.state_history: List[Dict] = []
        self.action_history: List[Dict] = []
        
        # State space metrics
        self.state_transitions = 0
        self.unique_states_seen = set()
        
        # Complex environmental factors
        self.environmental_factors = {
            'ambient_temperature': 25.0,
            'humidity': 50.0,
            'power_grid_stability': 1.0,
            'material_quality_variance': 0.05,
            'operator_skill_level': 0.8,
            'supply_chain_disruption': 0.0,
            'market_demand_pressure': 1.0
        }
        
        # Initialize device states
        self._initialize_complex_states()
        
        # Start state evolution process
        self.env.process(self._evolve_states())

    def _initialize_complex_states(self):
        """Initialize complex state tracking for all devices."""
        # Initialize station states
        for station_id in self.factory.stations:
            self.device_states[station_id] = ComplexDeviceState(
                device_id=station_id,
                status=DeviceState.IDLE
            )
        
        # Initialize AGV states
        for agv_id in self.factory.agvs:
            agv = self.factory.agvs[agv_id]
            self.agv_states[agv_id] = ComplexAGVState(
                agv_id=agv_id,
                status=AGVState.IDLE,
                position=agv.position,
                target_position=None,
                battery_level=agv.battery_level
            )

    def _evolve_states(self):
        """Continuous state evolution process - creates complex temporal dependencies."""
        while True:
            yield self.env.timeout(1.0)  # Update every second
            
            # Evolve device states
            self._update_device_degradation()
            self._update_environmental_factors()
            self._calculate_complex_metrics()
            self._record_state_snapshot()
            
            # Trigger random complex events
            if np.random.random() < 0.001:  # 0.1% chance per second
                self._trigger_complex_event()

    def _update_device_degradation(self):
        """Update wear, efficiency, and other degradation factors."""
        for device_id, state in self.device_states.items():
            # Wear increases based on usage
            if state.status == DeviceState.PROCESSING:
                state.wear_level += np.random.uniform(0.001, 0.005)
                state.temperature += np.random.uniform(0.1, 0.5)
                state.energy_consumption += np.random.uniform(0.5, 2.0)
            
            # Temperature cooling when idle
            if state.status == DeviceState.IDLE:
                state.temperature *= 0.99  # Gradual cooling
            
            # Efficiency degradation with wear
            state.efficiency = max(0.3, 1.0 - state.wear_level / 100)
            
            # Update utilization history
            current_util = 1.0 if state.status == DeviceState.PROCESSING else 0.0
            state.utilization_history.append(current_util)
            if len(state.utilization_history) > 100:
                state.utilization_history.pop(0)

    def _update_environmental_factors(self):
        """Update environmental factors that affect the entire factory."""
        # Simulate daily temperature variation
        time_of_day = (self.env.now % 86400) / 86400  # 0-1 cycle
        base_temp = 25 + 10 * np.sin(2 * np.pi * time_of_day)
        self.environmental_factors['ambient_temperature'] = base_temp + np.random.normal(0, 2)
        
        # Power grid instability
        self.environmental_factors['power_grid_stability'] *= np.random.uniform(0.98, 1.02)
        self.environmental_factors['power_grid_stability'] = np.clip(
            self.environmental_factors['power_grid_stability'], 0.7, 1.3
        )
        
        # Material quality variance
        self.environmental_factors['material_quality_variance'] += np.random.normal(0, 0.001)
        self.environmental_factors['material_quality_variance'] = np.clip(
            self.environmental_factors['material_quality_variance'], 0.01, 0.2
        )

    def _calculate_complex_metrics(self):
        """Calculate complex interdependent metrics."""
        for agv_id, agv_state in self.agv_states.items():
            # Battery degradation based on usage patterns
            if agv_state.status == AGVState.MOVING:
                degradation_rate = 0.001 * (1 + agv_state.payload_weight / 100)
                agv_state.battery_degradation += degradation_rate
            
            # Route efficiency based on historical performance
            if len(agv_state.speed_profile) > 10:
                avg_speed = np.mean(agv_state.speed_profile[-10:])
                agv_state.route_efficiency = min(1.5, avg_speed / 2.0)  # Normalized to expected speed

    def _trigger_complex_event(self):
        """Trigger complex system-wide events that affect multiple components."""
        event_type = np.random.choice([
            'power_fluctuation',
            'supply_chain_delay', 
            'quality_batch_issue',
            'operator_shift_change',
            'equipment_resonance',
            'network_latency_spike'
        ])
        
        if event_type == 'power_fluctuation':
            # Affects all device efficiency temporarily
            for state in self.device_states.values():
                state.efficiency *= np.random.uniform(0.9, 1.1)
        
        elif event_type == 'supply_chain_delay':
            # Increases material quality variance
            self.environmental_factors['material_quality_variance'] *= 1.5
        
        elif event_type == 'equipment_resonance':
            # Increases vibration in all devices
            for state in self.device_states.values():
                state.vibration_level += np.random.uniform(5, 15)
        
        print(f"[{self.env.now:.2f}] 🌪️ Complex event triggered: {event_type}")

    def register_new_order(self, order: NewOrder):
        """Register a new order with complex state tracking."""
        products_dict = {item.product_type: item.quantity for item in order.items}
        
        self.order_states[order.order_id] = ComplexOrderState(
            order_id=order.order_id,
            products=products_dict,
            priority=order.priority,
            created_at=order.created_at,
            deadline=order.deadline
        )

    def get_state_vector(self) -> np.ndarray:
        """
        Generate a massive state vector for RL algorithms.
        This is why RL is challenging - the state space is enormous!
        """
        state_vector = []
        
        # Device states (4 devices × 15 features = 60 dimensions)
        for device_id in sorted(self.device_states.keys()):
            state = self.device_states[device_id]
            device_features = [
                float(state.status.value == s.value) for s in DeviceState  # One-hot encoding
            ] + [
                state.temperature / 100,  # Normalized
                state.vibration_level / 100,
                state.wear_level / 100,
                state.efficiency,
                (self.env.now - state.last_maintenance) / 10000,  # Normalized time
                state.energy_consumption / 1000,
                float(state.error_count) / 10,
                np.mean(state.utilization_history) if state.utilization_history else 0.0
            ]
            state_vector.extend(device_features)
        
        # AGV states (2 AGVs × 20 features = 40 dimensions)
        for agv_id in sorted(self.agv_states.keys()):
            state = self.agv_states[agv_id]
            agv_features = [
                float(state.status.value == s.value) for s in AGVState  # One-hot encoding
            ] + [
                state.position[0] / 100,  # Normalized coordinates
                state.position[1] / 100,
                state.battery_level / 100,
                state.battery_degradation,
                state.travel_distance / 10000,
                state.payload_weight / 100,
                state.route_efficiency,
                float(state.collision_count) / 10,
                np.mean(state.speed_profile) / 5.0 if state.speed_profile else 0.0
            ]
            state_vector.extend(agv_features)
        
        # Order states (up to 20 orders × 10 features = 200 dimensions)
        order_features = []
        for order in sorted(self.order_states.values(), key=lambda x: x.created_at)[:20]:
            priority_features = [float(order.priority.value == p.value) for p in OrderPriority]
            features = [
                len(order.products),
                (self.env.now - order.created_at) / 10000,  # Normalized time
                (order.deadline - self.env.now) / 10000,  # Time to deadline
                order.quality_failures / 5.0,
                order.rework_count / 3.0,
                order.cost_accumulation / 1000
            ] + priority_features
            order_features.extend(features)
        
        # Pad or trim to exactly 200 dimensions
        while len(order_features) < 200:
            order_features.append(0.0)
        order_features = order_features[:200]
        state_vector.extend(order_features)
        
        # Environmental factors (7 dimensions)
        env_features = [
            self.environmental_factors['ambient_temperature'] / 50,
            self.environmental_factors['humidity'] / 100,
            self.environmental_factors['power_grid_stability'],
            self.environmental_factors['material_quality_variance'] * 10,
            self.environmental_factors['operator_skill_level'],
            self.environmental_factors['supply_chain_disruption'],
            self.environmental_factors['market_demand_pressure']
        ]
        state_vector.extend(env_features)
        
        # Fault system state (complex fault interactions)
        fault_features = self._get_fault_features()
        state_vector.extend(fault_features)
        
        return np.array(state_vector, dtype=np.float32)

    def _get_fault_features(self) -> List[float]:
        """Get complex fault interaction features."""
        features = []
        
        # Active faults by type (5 fault types)
        fault_types = ['station_vibration', 'precision_degradation', 'agv_path_blocked', 
                      'agv_battery_drain', 'efficiency_anomaly']
        
        for fault_type in fault_types:
            count = sum(1 for fault in self.fault_system.active_faults.values() 
                       if fault.fault_type.value == fault_type)
            features.append(float(count) / 6)  # Normalized by max devices
        
        # Fault interaction complexity
        active_devices = set(self.fault_system.active_faults.keys())
        
        # Check for cascading fault potential
        cascading_risk = 0.0
        for device_id in active_devices:
            device_state = self.device_states.get(device_id)
            if device_state:
                cascading_risk += device_state.wear_level * device_state.temperature / 10000
        
        features.append(min(1.0, cascading_risk))
        
        # System-wide fault correlation
        correlation_score = len(active_devices) / 6.0 * np.mean([
            self.environmental_factors['power_grid_stability'],
            1.0 - self.environmental_factors['material_quality_variance'] * 5
        ]) if active_devices else 0.0
        
        features.append(correlation_score)
        
        return features

    def _record_state_snapshot(self):
        """Record current state for analysis."""
        if int(self.env.now) % 10 == 0:  # Every 10 seconds
            state_vector = self.get_state_vector()
            state_hash = hashlib.md5(state_vector.tobytes()).hexdigest()
            
            self.unique_states_seen.add(state_hash)
            self.state_transitions += 1
            
            # Store state snapshot
            snapshot = {
                'timestamp': self.env.now,
                'state_hash': state_hash,
                'state_vector_size': len(state_vector),
                'active_orders': len(self.order_states),
                'active_faults': len(self.fault_system.active_faults),
                'environmental_score': np.mean(list(self.environmental_factors.values()))
            }
            
            self.state_history.append(snapshot)
            
            # Keep only last 1000 snapshots
            if len(self.state_history) > 1000:
                self.state_history.pop(0)

    def get_state_space_statistics(self) -> Dict[str, Any]:
        """Get comprehensive state space statistics."""
        state_vector = self.get_state_vector()
        
        return {
            'current_state_dimension': len(state_vector),
            'unique_states_observed': len(self.unique_states_seen),
            'state_transitions': self.state_transitions,
            'theoretical_state_space_size': self._estimate_theoretical_state_space(),
            'exploration_ratio': len(self.unique_states_seen) / max(1, self.state_transitions),
            'active_orders_count': len(self.order_states),
            'active_faults_count': len(self.fault_system.active_faults),
            'environmental_complexity': np.std(list(self.environmental_factors.values())),
            'average_device_wear': np.mean([s.wear_level for s in self.device_states.values()]),
            'system_efficiency': np.mean([s.efficiency for s in self.device_states.values()])
        }

    def _estimate_theoretical_state_space(self) -> float:
        """Estimate the theoretical state space size (why RL is hard!)."""
        # This is a conservative estimate
        device_combinations = 7 ** 4  # 7 device states, 4 devices
        agv_combinations = 7 ** 2 * 100 * 100  # 7 AGV states, 2 AGVs, position grid
        order_combinations = 10 ** min(len(self.order_states), 10)  # Limited to prevent overflow
        fault_combinations = 2 ** 6  # Binary fault presence for 6 devices
        environmental_combinations = 1000  # Discretized environmental factors
        
        total = device_combinations * agv_combinations * order_combinations * fault_combinations * environmental_combinations
        return float(total)

    def update_order_progress(self, order_id: str, station_id: str, progress: int):
        """Update order progress with complex tracking."""
        if order_id in self.order_states:
            order = self.order_states[order_id]
            order.progress_by_station[station_id] = progress
            
            # Calculate stage progression
            total_progress = sum(order.progress_by_station.values())
            total_required = sum(order.products.values()) * 4  # 4 stations
            
            if total_progress >= total_required:
                order.current_stage = "completed"
            elif total_progress >= total_required * 0.75:
                order.current_stage = "quality_check"
            elif total_progress > 0:
                order.current_stage = "processing"

    def record_action(self, action_type: str, target: str, params: Dict[str, Any], success: bool):
        """Record action for state-action analysis."""
        action_record = {
            'timestamp': self.env.now,
            'action_type': action_type,
            'target': target,
            'params': params,
            'success': success,
            'state_hash': hashlib.md5(self.get_state_vector().tobytes()).hexdigest()
        }
        
        self.action_history.append(action_record)
        
        # Keep only last 1000 actions
        if len(self.action_history) > 1000:
            self.action_history.pop(0) 