#!/usr/bin/env python3
# src/main.py

"""
Main entry point for the SUPCON Factory Simulation.

This script initializes and runs the complete simulation environment:
- Factory with stations and AGVs
- MQTT connectivity for agent communication
- Command handling for external control
"""

import logging
import signal
import sys
import time
from typing import Optional

from src.simulation.factory import Factory
from src.utils.config_loader import load_factory_config
from src.utils.mqtt_client import MQTTClient
from src.agent_interface.command_handler import CommandHandler
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FactorySimulation:
    """
    Main orchestrator class that combines all components of the factory simulation.
    """
    
    def __init__(self):
        self.factory: Optional[Factory] = None
        self.mqtt_client: Optional[MQTTClient] = None
        self.command_handler: Optional[CommandHandler] = None
        self.running = False

    def initialize(self):
        """Initialize all simulation components."""
        logger.info("🏭 Initializing Factory Simulation...")
        
        # Create MQTT client first
        self.mqtt_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, "factory_simulation")
        
        # Connect to MQTT
        self.mqtt_client.connect()
        logger.info(f"📡 Connected to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        
        # Create the factory with MQTT client
        self.factory = Factory(load_factory_config(), self.mqtt_client)
        logger.info(f"✅ Factory created with {len(self.factory.stations)} stations and {len(self.factory.agvs)} AGVs")
        logger.info("📋 Order generation, fault system, and KPI calculation initialized")
        
        # Create command handler (this will start listening for commands)
        self.command_handler = CommandHandler(self.factory, self.mqtt_client)
        logger.info("🎯 Command handler initialized and listening for agent commands")
        
    def _calculate_station_utilization(self, station) -> float:
        """Calculate actual utilization of a station based on processing time and idle time."""
        if not hasattr(station, 'total_processing_time') or not hasattr(station, 'total_idle_time'):
            # If tracking isn't implemented yet, estimate based on status
            if station.status.value == 'processing':
                return 0.85  # High utilization when processing
            elif station.status.value == 'idle':
                return 0.15  # Low utilization when idle
            elif station.status.value == 'error':
                return 0.0   # No utilization during errors
            else:
                return 0.5   # Medium utilization for other states
        
        total_time = station.total_processing_time + station.total_idle_time
        if total_time == 0:
            return 0.0
        
        return min(1.0, station.total_processing_time / total_time)

    def run(self, duration: Optional[int] = None):
        """Run the simulation."""
        logger.info("🚀 Starting Factory Simulation...")
        self.running = True
        
        try:
            if duration:
                logger.info(f"⏱️  Running simulation for {duration} seconds")
                self.factory.run(until=duration)
            else:
                logger.info("🔄 Running simulation indefinitely (Ctrl+C to stop)")
                while self.running:
                    # Run simulation for 1 second at a time
                    self.factory.run(until=int(self.factory.env.now) + 1)
                    time.sleep(1)  # Small delay to prevent busy waiting
                    
        except KeyboardInterrupt:
            logger.info("🛑 Simulation interrupted by user")
        except Exception as e:
            logger.error(f"❌ Simulation error: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Clean up resources."""
        logger.info("🧹 Shutting down Factory Simulation...")
        self.running = False
        
        if self.mqtt_client:
            self.mqtt_client.disconnect()
            
        logger.info("👋 Factory Simulation stopped")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    sys.exit(0)

def main():
    """Main function."""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run simulation
    simulation = FactorySimulation()
    
    try:
        simulation.initialize()
        simulation.run()  # Run indefinitely
    except Exception as e:
        logger.error(f"❌ Failed to start simulation: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 