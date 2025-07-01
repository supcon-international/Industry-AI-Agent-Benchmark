#!/usr/bin/env python3
# tools/mock_agent.py

"""
A simple mock agent for testing the factory simulation.
This script connects to MQTT and sends predefined commands to test the system.
"""

import time
import json
from src.utils.mqtt_client import MQTTClient
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from config.topics import AGENT_COMMANDS_TOPIC

def create_test_commands():
    """Returns a list of test commands to send to the factory."""
    return [
        # Test AGV movement
        {
            "command_id": "test_001",
            "agent_id": "mock_agent",
            "action": "move_agv",
            "target": "AGV_1",
            "params": {"destination_id": "P1"}
        },
        # Test fault diagnosis - AGV_2 has "AGV电量突降" fault
        # Try correct diagnosis first
        {
            "command_id": "test_002",
            "agent_id": "mock_agent",
            "action": "request_maintenance", 
            "target": "AGV_2",
            "params": {"maintenance_type": "optimize_schedule"}  # Correct for high_load_task
        },
        # Test wrong diagnosis for comparison
        {
            "command_id": "test_003",
            "agent_id": "mock_agent",
            "action": "request_maintenance",
            "target": "StationA",
            "params": {"maintenance_type": "wrong_command"}  # Intentionally wrong
        }
    ]

def main():
    """Main function to run the mock agent."""
    print("🤖 Mock Agent starting...")
    
    # Create MQTT client
    mqtt_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, "mock_agent")
    
    try:
        # Connect to MQTT broker
        mqtt_client.connect()
        print(f"📡 Connected to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        
        # Wait a moment for connection to stabilize
        time.sleep(2)
        
        # Send test commands
        test_commands = create_test_commands()
        
        for i, command in enumerate(test_commands):
            print(f"📤 Sending command {i+1}/{len(test_commands)}: {command['action']} -> {command['target']}")
            mqtt_client.publish(AGENT_COMMANDS_TOPIC, json.dumps(command))
            time.sleep(3)  # Wait 3 seconds between commands
            
        print("✅ All test commands sent!")
        print("🔄 Keeping connection alive for 30 seconds to observe responses...")
        time.sleep(30)
        
    except KeyboardInterrupt:
        print("\n🛑 Mock agent interrupted by user")
    except Exception as e:
        print(f"❌ Error in mock agent: {e}")
    finally:
        mqtt_client.disconnect()
        print("👋 Mock agent disconnected")

if __name__ == "__main__":
    main() 