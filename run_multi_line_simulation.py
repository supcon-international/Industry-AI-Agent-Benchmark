# run_multi_line_simulation.py
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.utils.mqtt_client import MQTTClient
from src.simulation.factory_multi import Factory
from src.utils.config_loader import load_factory_config
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT

def run_simulation_multi():
    """Runs the multi-line factory simulation."""
    try:
        layout_config = load_factory_config('factory_layout_multi.yml')
        print(f"✅ Successfully loaded multi-line factory configuration from {layout_config}")
    except Exception as e:
        print(f"❌ Failed to load multi-line factory configuration: {e}")
        raise e

    # MQTT Client setup (optional)
    mqtt_client = None
    mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT, client_id="factory_multi_sim")
    mqtt_client.connect()

    # Create and run the multi-line factory simulation
    factory = Factory(layout_config, mqtt_client, no_faults=False) # no_faults for cleaner testing
    
    print("--- Starting Multi-Line Factory Simulation ---")
    factory.run(until=1000) # Run for a short duration for testing
    print("--- Multi-Line Factory Simulation Finished ---")

if __name__ == '__main__':
    run_simulation_multi()
