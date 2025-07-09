# config/topics.py
# MQTT Topic definitions for the SUPCON AdventureX Factory Simulation

# Device status topics (published by factory devices)
STATION_STATUS_TOPIC = "factory/station/{device_id}/status"
AGV_STATUS_TOPIC = "factory/resource/{device_id}/status"
QUALITY_CHECKER_STATUS_TOPIC = "factory/quality/{device_id}/status"
FACTORY_STATUS_TOPIC = "factory/status"

# Buffer full alert topics (published by fault system)
DEVICE_ALERT_TOPIC = "factory/alerts/{device_id}"
BUFFER_FULL_ALERT_TOPIC = "factory/alerts/buffer_full"

# Order and KPI topics
NEW_ORDER_TOPIC = "factory/orders/new"
KPI_UPDATE_TOPIC = "factory/kpi/update"

# Agent command topics (published by AI agents)
AGENT_COMMANDS_TOPIC = "factory/agent/commands"
# Agent response topics (subscribed by AI agents)
AGENT_RESPONSES_TOPIC = "factory/agent/responses"

# Natural language logs for visualization
NL_LOGS_TOPIC = "factory/agent/nl_logs"

# Topic patterns for subscription
ALL_STATION_STATUS = "factory/station/+/status"
ALL_AGV_STATUS = "factory/resource/+/status"
ALL_FACTORY_TOPICS = "factory/+"

# Legacy topic definitions (keeping for backward compatibility)
FACTORY_STATUS_TOPIC_PREFIX = "factory/station"
AGV_STATUS_TOPIC_PREFIX = "factory/resource"
QUALITY_CHECKER_STATUS_TOPIC_PREFIX = "factory/quality"

def get_station_status_topic(station_id: str) -> str:
    """Returns the status topic for a specific station."""
    return f"{FACTORY_STATUS_TOPIC_PREFIX}/{station_id}/status"

def get_agv_status_topic(agv_id: str) -> str:
    """Returns the status topic for a specific AGV."""
    return f"{AGV_STATUS_TOPIC_PREFIX}/{agv_id}/status" 

def get_quality_checker_status_topic(quality_checker_id: str) -> str:
    """Returns the status topic for a specific quality checker."""
    return f"{QUALITY_CHECKER_STATUS_TOPIC_PREFIX}/{quality_checker_id}/status"