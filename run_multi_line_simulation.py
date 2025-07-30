# run_multi_line_simulation.py
import os
import sys
import argparse
import threading
import uuid
import logging
import time
from typing import Optional

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.utils.mqtt_client import MQTTClient
from src.simulation.factory_multi import Factory
from src.utils.config_loader import load_factory_config
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT, FACTORY_LAYOUT_MULTI_FILE
from src.agent_interface.multi_line_command_handler import MultiLineCommandHandler
from src.user_input_multi import menu_input_thread
from src.utils.topic_manager import TopicManager
from src.utils.logger_config import setup_logging, get_sim_logger

# Logger will be configured in run_simulation_multi based on command-line args
logger = logging.getLogger(__name__)

class MultiLineFactorySimulation:
    """
    Main orchestrator class that combines all components of the factory simulation.
    """
    
    def __init__(self):
        self.factory: Optional[Factory] = None
        self.mqtt_client: Optional[MQTTClient] = None
        self.topic_manager: Optional[TopicManager] = None
        self.command_handler: Optional[MultiLineCommandHandler] = None
        self.running = False
        self.sim_logger: Optional[logging.LoggerAdapter] = None

    def initialize(self, no_faults=False, no_mqtt=False):
        """Initialize all simulation components."""
        # 优先使用 CLIENT_ID，其次 USERNAME/USER，最后默认值，确保 client_name 一定为 str
        client_name = (
            os.getenv("TOPIC_ROOT")
            or os.getenv("USERNAME")
            or os.getenv("USER")
            or "NLDF_Default"
        )
        self.topic_manager = TopicManager(client_name)
        self.mqtt_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, self.topic_manager, f"factory_client_{uuid.uuid4().hex[:8]}")
        
        # Connect to MQTT
        logger.info(f"📡 Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}, client_id: {self.mqtt_client.client_id}")

        if not no_mqtt:
            self.mqtt_client.connect_with_retry()

        try:
            layout_config = load_factory_config(FACTORY_LAYOUT_MULTI_FILE)
        except Exception as e:
            logger.error(f"❌ Failed to load multi-line factory configuration: {e}", exc_info=True)
            raise e
        
        self.factory = Factory(layout_config, self.mqtt_client, self.topic_manager, no_faults=no_faults) # no_faults for cleaner testing
        self.sim_logger = get_sim_logger(self.factory.env, "simulation.main")
        self.sim_logger.info(f"✅ Factory created with {len(self.factory.lines)} lines")
        
        # Create command handler (this will start listening for commands)
        self.command_handler = MultiLineCommandHandler(self.factory, self.mqtt_client, self.factory.topic_manager)
        logger.debug("🎯 Command handler initialized and listening for agent commands")
    
    def run(self, duration: Optional[int] = None):
        """Run the simulation."""
        if self.factory is None or self.sim_logger is None:
            logger.error("❌ Factory is not initialized. Call initialize() first.")
            return

        self.running = True
        
        try:
            if duration:
                self.sim_logger.info(f"⏱️  Running simulation for {duration} seconds")
                self.factory.run(until=duration)
            else:
                self.sim_logger.info("🔄 Running simulation indefinitely (Ctrl+C to stop)")
                while self.running:
                    # Run simulation for 1 second at a time
                    self.factory.run(until=int(self.factory.env.now) + 1)
                    time.sleep(1)  # Small delay to prevent busy waiting
                    
        except KeyboardInterrupt:
            self.sim_logger.info("🛑 Simulation interrupted by user")
        except Exception as e:
            logger.error(f"❌ Simulation error: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """Clean up resources."""
        if not self.running:
            return # Avoid multiple shutdowns
            
        logger.info("🧹 Shutting down Factory Simulation...")
        self.running = False
        
        # Print final scores when shutting down
        if self.factory and self.factory.kpi_calculator:
            self.factory.kpi_calculator.print_final_scores()
        
        if self.mqtt_client:
            self.mqtt_client.disconnect()
            
        logger.info("👋 Factory Simulation stopped")

def run_simulation_multi():
    """Runs the multi-line factory simulation."""
    parser = argparse.ArgumentParser(description="SUPCON Multi-Line Factory Simulation Launcher")
    parser.add_argument(
        "-v", "--verbose",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
        help="Enable verbose logging to see detailed simulation steps."
    )
    parser.add_argument(
        "-m", "--menu",
        action="store_true",
        help="Enable the interactive menu for manual control."
    )
    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        help="Ignore mqtt connection for offline test"
    )
    parser.add_argument(
        "--no-fault",
        action="store_true",
        help="Disable random fault injection in the simulation."
    )
    args = parser.parse_args()

    # Setup logging as the first step
    setup_logging(log_level=args.loglevel)

    simulation = MultiLineFactorySimulation()
    try:
        simulation.initialize(no_faults=args.no_fault, no_mqtt=args.no_mqtt)
        
        if args.menu and simulation.factory and simulation.factory.topic_manager:
            # input_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, simulation.factory.topic_manager, f"input_client_{uuid.uuid4().hex[:8]}")
            # input_client.connect_with_retry()
            # logger.info(f"📡 Input client connected to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}, client_id: {input_client.client_id}")
            threading.Thread(target=menu_input_thread, args=(simulation.mqtt_client, simulation.factory, simulation.factory.topic_manager), daemon=True).start()
            logger.info("Interactive menu enabled. Type commands in the console.")

        simulation.run()  # Run indefinitely
    except Exception as e:
        logger.critical(f"A critical error occurred during initialization or runtime: {e}", exc_info=True)
    finally:
        simulation.shutdown()


if __name__ == '__main__':
    run_simulation_multi()
