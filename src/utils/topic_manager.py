# src/utils/topic_manager.py
import os

class TopicManager:
    """
    Manages the generation of all MQTT topics for the simulation.
    It ensures a consistent topic structure based on a root name.
    """
    def __init__(self, player_name: str):
        """
        Initializes the TopicManager with a root topic name.
        Args:
            player_name: The root name for all topics, typically the player's or team's name.
        """
        if not player_name or not isinstance(player_name, str) or "/" in player_name:
            raise ValueError("Player name cannot be empty or contain '/'")
        self.root = player_name
        print(f"✅ TopicManager initialized with root topic: '{self.root}'")

    def get_device_status_topic(self, line_id: str, device_id: str) -> str:
        """Generates topic for device status updates."""
        # device_id from Line class is already line_x_device_y, so we can just use it
        return f"{self.root}/{line_id}/{device_id}/status"

    def get_agv_position_topic(self, line_id: str, agv_id: str) -> str:
        """Generates topic for AGV position updates."""
        return f"{self.root}/{line_id}/{agv_id}/position"

    def get_order_topic(self) -> str:
        """Generates topic for new order announcements."""
        return f"{self.root}/orders/new"

    def get_fault_alert_topic(self, line_id: str, device_id: str) -> str:
        """Generates topic for fault alerts."""
        return f"{self.root}/{line_id}/{device_id}/alerts/fault"
        
    def get_kpi_topic(self) -> str:
        """Generates topic for factory-wide KPI updates."""
        return f"{self.root}/kpi"

    def get_factory_status_topic(self) -> str:
        """Generates topic for factory-wide status updates."""
        return f"{self.root}/factory/status"
