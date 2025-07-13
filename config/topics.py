# config/topics.py
# MQTT Topic definitions for the SUPCON AdventureX Factory Simulation

# Device status topics (published by factory devices)
STATION_STATUS_TOPIC = "NLDF/{line}/station/{device_id}/status"
AGV_STATUS_TOPIC = "NLDF/{line}/resource/{device_id}/status"
QUALITY_CHECKER_STATUS_TOPIC = "NLDF/{line}/quality/{device_id}/status"
FACTORY_STATUS_TOPIC = "NLDF/{line}/status"

# Buffer full alert topics (published by fault system)
DEVICE_ALERT_TOPIC = "NLDF/{line}/alerts/{device_id}"
BUFFER_FULL_ALERT_TOPIC = "NLDF/{line}/alerts/buffer_full"
AGV_BATTERY_LOW_ALERT_TOPIC = "NLDF/{line}/alerts/agv_battery_low"

# Order and KPI topics
NEW_ORDER_TOPIC = "NLDF/{line}/orders/new"
KPI_UPDATE_TOPIC = "NLDF/{line}/kpi/update"

# Agent command topics (published by AI agents)
AGENT_COMMANDS_TOPIC = "NLDF/{line}/agent/commands"
# Agent response topics (subscribed by AI agents)
AGENT_RESPONSES_TOPIC = "NLDF/{line}/agent/responses"

# Natural language logs for visualization
NL_LOGS_TOPIC = "NLDF/{line}/agent/nl_logs"

# Topic patterns for subscription
ALL_STATION_STATUS = "NLDF/{line}/station/+/status"
ALL_AGV_STATUS = "NLDF/{line}/resource/+/status"
ALL_FACTORY_TOPICS = "NLDF/{line}/+"

# Legacy topic definitions (keeping for backward compatibility)
FACTORY_STATUS_TOPIC_PREFIX = "NLDF/line1/station"
AGV_STATUS_TOPIC_PREFIX = "NLDF/line1/agv"
# QUALITY_CHECKER_STATUS_TOPIC_PREFIX = "NLDF/line1/quality"

def get_station_status_topic(station_id: str) -> str:
    """Returns the status topic for a specific station."""
    return f"{FACTORY_STATUS_TOPIC_PREFIX}/{station_id}/status"

def get_agv_status_topic(agv_id: str) -> str:
    """Returns the status topic for a specific AGV."""
    return f"{AGV_STATUS_TOPIC_PREFIX}/{agv_id}/status" 

# def get_quality_checker_status_topic(quality_checker_id: str) -> str:
#     """Returns the status topic for a specific quality checker."""
#     return f"{QUALITY_CHECKER_STATUS_TOPIC_PREFIX}/{quality_checker_id}/status"