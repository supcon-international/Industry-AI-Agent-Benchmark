# src/game_logic/kpi_calculator.py
import simpy
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from config.schemas import KPIUpdate, NewOrder
from config.topics import KPI_UPDATE_TOPIC
from src.utils.mqtt_client import MQTTClient

@dataclass
class OrderTracking:
    """Track individual order progress for KPI calculation."""
    order_id: str
    created_at: float
    deadline: float
    items_total: int
    items_completed: int = 0
    completed_at: Optional[float] = None
    is_on_time: Optional[bool] = None
    total_cost: float = 0.0

@dataclass
class ProductionStats:
    """Production statistics for KPI calculation."""
    total_orders: int = 0
    completed_orders: int = 0
    on_time_orders: int = 0
    total_products: int = 0
    quality_passed_products: int = 0
    scrapped_products: int = 0
    
    # Time tracking
    total_production_time: float = 0.0
    total_simulation_time: float = 0.0
    
    # Cost tracking
    material_costs: float = 0.0
    energy_costs: float = 0.0
    maintenance_costs: float = 0.0
    scrap_costs: float = 0.0
    
    # Fault tracking
    total_faults: int = 0
    correct_diagnoses: int = 0
    total_recovery_time: float = 0.0
    
    # Device utilization (device_id -> working_time)
    device_working_time: Dict[str, float] = field(default_factory=dict)
    device_total_time: Dict[str, float] = field(default_factory=dict)

class KPICalculator:
    """
    Calculates KPIs according to PRD 2.7 specifications:
    - Production Efficiency (40%): Order completion rate + Average production cycle
    - Cost Control (30%): Total production cost
    - Robustness (30%): Diagnosis accuracy + Recovery time
    """
    
    def __init__(self, env: simpy.Environment, mqtt_client: Optional[MQTTClient] = None):
        self.env = env
        self.mqtt_client = mqtt_client
        self.stats = ProductionStats()
        self.active_orders: Dict[str, OrderTracking] = {}
        self.completed_orders: List[OrderTracking] = []
        
        # Cost parameters (per unit/operation)
        self.cost_parameters = {
            'material_cost_per_product': {'P1': 10.0, 'P2': 15.0, 'P3': 20.0},
            'energy_cost_per_second': 0.1,  # Base energy cost
            'energy_cost_multiplier_peak': 1.5,  # Peak hour multiplier
            'maintenance_cost_base': 50.0,  # Base maintenance cost
            'scrap_cost_multiplier': 0.8,  # Scrap cost as % of material cost
        }
        
        # Start KPI update process
        self.env.process(self.run_kpi_updates())

    def run_kpi_updates(self):
        """Periodically calculate and publish KPI updates."""
        while True:
            yield self.env.timeout(10.0)  # Update every 10 seconds
            kpi_update = self.calculate_current_kpis()
            self._publish_kpi_update(kpi_update)

    def register_new_order(self, order: NewOrder):
        """Register a new order for tracking."""
        total_items = sum(item.quantity for item in order.items)
        
        order_tracking = OrderTracking(
            order_id=order.order_id,
            created_at=order.created_at,
            deadline=order.deadline,
            items_total=total_items
        )
        
        self.active_orders[order.order_id] = order_tracking
        self.stats.total_orders += 1
        
        # Add material costs
        for item in order.items:
            material_cost = self.cost_parameters['material_cost_per_product'][item.product_type]
            order_tracking.total_cost += material_cost * item.quantity
            self.stats.material_costs += material_cost * item.quantity

    def complete_order_item(self, order_id: str, passed_quality: bool = True):
        """Mark an order item as completed."""
        if order_id not in self.active_orders:
            return
            
        order = self.active_orders[order_id]
        order.items_completed += 1
        self.stats.total_products += 1
        
        if passed_quality:
            self.stats.quality_passed_products += 1
        else:
            self.stats.scrapped_products += 1
            # Add scrap cost
            scrap_cost = order.total_cost * self.cost_parameters['scrap_cost_multiplier'] / order.items_total
            order.total_cost += scrap_cost
            self.stats.scrap_costs += scrap_cost
        
        # Check if order is complete
        if order.items_completed >= order.items_total:
            self._complete_order(order)

    def _complete_order(self, order: OrderTracking):
        """Complete an order and update statistics."""
        order.completed_at = self.env.now
        order.is_on_time = order.completed_at <= order.deadline
        
        self.stats.completed_orders += 1
        if order.is_on_time:
            self.stats.on_time_orders += 1
            
        # Add to production time tracking
        production_time = order.completed_at - order.created_at
        self.stats.total_production_time += production_time
        
        # Move to completed orders
        self.completed_orders.append(order)
        del self.active_orders[order.order_id]

    def add_energy_cost(self, device_id: str, duration: float, is_peak_hour: bool = False):
        """Add energy costs for device operation."""
        base_cost = duration * self.cost_parameters['energy_cost_per_second']
        if is_peak_hour:
            base_cost *= self.cost_parameters['energy_cost_multiplier_peak']
        
        self.stats.energy_costs += base_cost
        
        # Update device working time
        if device_id not in self.stats.device_working_time:
            self.stats.device_working_time[device_id] = 0.0
        self.stats.device_working_time[device_id] += duration

    def add_maintenance_cost(self, device_id: str, maintenance_type: str, was_correct_diagnosis: bool):
        """Add maintenance costs and track diagnosis accuracy."""
        base_cost = self.cost_parameters['maintenance_cost_base']
        
        # Penalty for incorrect diagnosis
        if not was_correct_diagnosis:
            base_cost *= 2.0  # Double cost for wrong diagnosis
            
        self.stats.maintenance_costs += base_cost
        self.stats.total_faults += 1
        
        if was_correct_diagnosis:
            self.stats.correct_diagnoses += 1

    def add_fault_recovery_time(self, recovery_time: float):
        """Track fault recovery time for robustness metrics."""
        self.stats.total_recovery_time += recovery_time

    def update_device_utilization(self, device_id: str, total_time: float):
        """Update device total time for utilization calculation."""
        self.stats.device_total_time[device_id] = total_time

    def calculate_current_kpis(self) -> KPIUpdate:
        """Calculate current KPI values according to PRD 2.7 formulas."""
        current_time = self.env.now
        self.stats.total_simulation_time = current_time
        
        # Production Efficiency Metrics (40%)
        order_completion_rate = (
            (self.stats.completed_orders / self.stats.total_orders * 100) 
            if self.stats.total_orders > 0 else 0.0
        )
        
        average_production_cycle = (
            (self.stats.total_production_time / self.stats.completed_orders)
            if self.stats.completed_orders > 0 else 0.0
        )
        
        on_time_delivery_rate = (
            (self.stats.on_time_orders / self.stats.completed_orders * 100)
            if self.stats.completed_orders > 0 else 0.0
        )
        
        # Quality Metrics
        first_pass_rate = (
            (self.stats.quality_passed_products / self.stats.total_products * 100)
            if self.stats.total_products > 0 else 0.0
        )
        
        # Device Utilization
        device_utilization = {}
        for device_id in self.stats.device_working_time:
            working_time = self.stats.device_working_time[device_id]
            total_time = self.stats.device_total_time.get(device_id, current_time)
            utilization = (working_time / total_time * 100) if total_time > 0 else 0.0
            device_utilization[device_id] = utilization
        
        average_device_utilization = (
            sum(device_utilization.values()) / len(device_utilization)
            if device_utilization else 0.0
        )
        
        # Cost Control Metrics (30%)
        total_production_cost = (
            self.stats.material_costs + self.stats.energy_costs + 
            self.stats.maintenance_costs + self.stats.scrap_costs
        )
        
        # Robustness Metrics (30%)
        diagnosis_accuracy = (
            (self.stats.correct_diagnoses / self.stats.total_faults * 100)
            if self.stats.total_faults > 0 else 100.0
        )
        
        average_recovery_time = (
            (self.stats.total_recovery_time / self.stats.total_faults)
            if self.stats.total_faults > 0 else 0.0
        )
        
        return KPIUpdate(
            timestamp=current_time,
            
            # Production Efficiency (40%)
            order_completion_rate=order_completion_rate,
            average_production_cycle=average_production_cycle,
            on_time_delivery_rate=on_time_delivery_rate,
            device_utilization=average_device_utilization,
            
            # Quality Metrics
            first_pass_rate=first_pass_rate,
            
            # Cost Control (30%)
            total_production_cost=total_production_cost,
            material_costs=self.stats.material_costs,
            energy_costs=self.stats.energy_costs,
            maintenance_costs=self.stats.maintenance_costs,
            scrap_costs=self.stats.scrap_costs,
            
            # Robustness (30%)
            diagnosis_accuracy=diagnosis_accuracy,
            average_recovery_time=average_recovery_time,
            
            # Raw Counts
            total_orders=self.stats.total_orders,
            completed_orders=self.stats.completed_orders,
            active_orders=len(self.active_orders),
            total_products=self.stats.total_products,
            active_faults=0  # Will be updated by fault system
        )

    def _publish_kpi_update(self, kpi_update: KPIUpdate):
        """Publish KPI update to MQTT."""
        try:
            if self.mqtt_client:
                self.mqtt_client.publish(KPI_UPDATE_TOPIC, kpi_update)
        except Exception as e:
            print(f"[{self.env.now:.2f}] ❌ Failed to publish KPI update: {e}")

    def get_final_score(self) -> Dict[str, float]:
        """Calculate final competition score according to PRD formula."""
        kpis = self.calculate_current_kpis()
        
        # Normalize metrics (would typically compare against baseline)
        # For demo purposes, using simple scaling
        efficiency_score = min(100, (
            kpis.order_completion_rate * 0.5 + 
            (100 / max(1, kpis.average_production_cycle / 100)) * 0.5
        )) * 0.4
        
        cost_score = min(100, 10000 / max(100, kpis.total_production_cost)) * 0.3
        
        robustness_score = min(100, (
            kpis.diagnosis_accuracy * 0.6 + 
            (100 / max(1, kpis.average_recovery_time / 10)) * 0.4
        )) * 0.3
        
        total_score = efficiency_score + cost_score + robustness_score
        
        return {
            "efficiency_score": efficiency_score,
            "cost_score": cost_score, 
            "robustness_score": robustness_score,
            "total_score": total_score
        } 