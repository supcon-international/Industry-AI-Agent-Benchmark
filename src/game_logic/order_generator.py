# src/game_logic/order_generator.py
import random
import uuid
import simpy
from typing import Dict, List, Optional

from config.schemas import NewOrder, OrderItem, OrderPriority
from config.topics import NEW_ORDER_TOPIC
from src.utils.mqtt_client import MQTTClient
from src.simulation.entities.warehouse import RawMaterial
from src.simulation.entities.product import Product

class OrderGenerator:
    """
    Generates orders according to PRD 2.4 specifications:
    - Generation interval: 30-60 seconds (uniform random)
    - Order quantity: 1-5 items (weighted: 40%, 30%, 20%, 7%, 3%)
    - Product distribution: P1(60%), P2(30%), P3(10%)
    - Priority distribution: Low(70%), Medium(25%), High(5%)
    """
    
    def __init__(self, env: simpy.Environment, mqtt_client: MQTTClient, raw_material: RawMaterial):
        self.env = env
        self.mqtt_client = mqtt_client
        self.raw = raw_material
        # Order generation parameters from PRD
        self.generation_interval_range = (30, 60)  # seconds
        self.quantity_weights = {1: 40, 2: 30, 3: 20, 4: 7, 5: 3}
        self.product_distribution = {'P1': 60, 'P2': 30, 'P3': 10}
        self.priority_distribution = {
            OrderPriority.LOW: 70,
            OrderPriority.MEDIUM: 25, 
            OrderPriority.HIGH: 5
        }
        
        # Theoretical production times for deadline calculation (in seconds)
        self.theoretical_production_times = {
            'P1': 30 + 45 + 20 + 15 + 50,  # A+B+C+Q+Transport = ~160s
            'P2': 40 + 60 + 30 + 20 + 50,  # A+B+C+Q+Transport = ~200s 
            'P3': 35 + 50 + 20 + 30 + 20 + 25 + 20 + 50,  # A+B+A+C+Q+Transport = ~250s
        }
        
        # Priority multipliers for deadline calculation
        self.priority_multipliers = {
            OrderPriority.LOW: 3.0,
            OrderPriority.MEDIUM: 2.0,
            OrderPriority.HIGH: 1.5
        }
        
        # Start the order generation process
        self.env.process(self.run())

    def run(self):
        """Main order generation loop."""
        while True:
            # Wait for next order generation
            wait_time = random.uniform(*self.generation_interval_range)
            yield self.env.timeout(wait_time)
            
            # Generate and publish new order
            order = self._generate_order()
            if order:
                self._publish_order(order)

    def _generate_order(self) -> Optional[NewOrder]:
        """Generate a single order according to PRD specifications."""
        if self.raw.is_full():
            print(f"[{self.env.now:.2f}] ❌ Raw material warehouse is full, cannot accept new order")
            return None
        
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        created_at = self.env.now
        
        # Generate order items
        items = self._generate_order_items()
        
        # Determine priority
        priority = self._select_priority()
        
        # Calculate deadline based on priority and theoretical production time
        deadline = self._calculate_deadline(created_at, items, priority)
        
        for item in items:
            self.raw.create_raw_material(item.product_type, order_id)
        
        return NewOrder(
            order_id=order_id,
            created_at=created_at,
            items=items,
            priority=priority,
            deadline=deadline
        )

    def _generate_order_items(self) -> List[OrderItem]:
        """Generate order items with proper quantity and product distribution."""
        # Select order quantity based on weights
        quantity = self._weighted_choice(self.quantity_weights)
        
        items = []
        for _ in range(quantity):
            # Select product type based on distribution
            product_type = self._weighted_choice(self.product_distribution)
            
            # For simplicity, each item has quantity 1
            # In a more complex system, this could vary
            items.append(OrderItem(
                product_type=product_type,
                quantity=1
            ))
        
        return items

    def _select_priority(self) -> OrderPriority:
        """Select order priority based on distribution."""
        return self._weighted_choice(self.priority_distribution)

    def _calculate_deadline(self, created_at: float, items: List[OrderItem], priority: OrderPriority) -> float:
        """Calculate order deadline based on theoretical production time and priority."""
        # Calculate total theoretical production time
        total_time = 0
        for item in items:
            base_time = self.theoretical_production_times[item.product_type]
            total_time += base_time * item.quantity
        
        # Apply priority multiplier
        multiplier = self.priority_multipliers[priority]
        deadline = created_at + (total_time * multiplier)
        
        return deadline

    def _weighted_choice(self, weights_dict: Dict):
        """Select an item based on weighted probabilities."""
        items = list(weights_dict.keys())
        weights = list(weights_dict.values())
        return random.choices(items, weights=weights)[0]

    def _publish_order(self, order: NewOrder):
        """Publish the order to MQTT."""
        try:
            self.mqtt_client.publish(NEW_ORDER_TOPIC, order)
            print(f"[{self.env.now:.2f}] 📋 New order generated: {order.order_id}")
            print(f"   - Items: {[(item.product_type, item.quantity) for item in order.items]}")
            print(f"   - Priority: {order.priority.value}")
            print(f"   - Deadline: {order.deadline:.1f}s (in {order.deadline - self.env.now:.1f}s)")
        except Exception as e:
            print(f"[{self.env.now:.2f}] ❌ Failed to publish order: {e}") 