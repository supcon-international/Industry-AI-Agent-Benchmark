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
import argparse
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

    def initialize(self, no_faults: bool = False):
        """Initialize all simulation components."""
        logger.info("🏭 Initializing Factory Simulation...")
        
        # Create MQTT client first
        self.mqtt_client = MQTTClient(MQTT_BROKER_HOST, MQTT_BROKER_PORT, "factory_simulation")
        
        # Connect to MQTT
        self.mqtt_client.connect()
        logger.info(f"📡 Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")

        # Wait for MQTT client to be fully connected
        max_retries = 20
        retry_interval = 0.5
        for i in range(max_retries):
            if self.mqtt_client.is_connected():
                logger.info("✅ MQTT client is fully connected.")
                break
            logger.info(f"Waiting for MQTT connection... ({i+1}/{max_retries})")
            time.sleep(retry_interval)
        else:
            logger.error("❌ Failed to connect to MQTT broker within the given time. Exiting simulation.")
            raise ConnectionError("MQTT connection failed.")

        # Create the factory with MQTT client
        self.factory = Factory(load_factory_config(), self.mqtt_client, no_faults=no_faults)
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
        if self.factory is None:
            logger.error("❌ Factory is not initialized. Call initialize() first.")
            return

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

def menu_input_thread(mqtt_client):
    import json
    from config.topics import AGENT_COMMANDS_TOPIC
    while True:
        print("\n请选择操作类型：")
        print("1. 移动AGV")
        print("2. 装载")
        print("3. 卸载")
        print("4. 充电")
        print("5. 退出")
        op = input("> ").strip()
        if op == "1":
            agv_id = input("请输入AGV编号: ").strip()
            target_point = input("请输入目标点: ").strip()
            agv_id = "AGV_" + agv_id
            target_point = "P" + target_point
            cmd = {
                "action": "move_agv",
                "target": agv_id,
                "params": {"target_point": target_point}
            }
        elif op == "2":
            agv_id = input("请输入AGV编号: ").strip()
            device_id = input("请输入装载设备编号: ").strip()
            agv_id = "AGV_" + agv_id
            buffer_type = input("请输入buffer类型: ").strip()
            cmd = {
                "action": "load_agv",
                "target": agv_id,
                "params": {"device_id": device_id, "buffer_type": buffer_type}
            }
        elif op == "3":
            agv_id = input("请输入AGV编号: ").strip()
            agv_id = "AGV_" + agv_id
            device_id = input("请输入卸载设备编号: ").strip()
            buffer_type = input("请输入buffer类型: ").strip()
            cmd = {
                "action": "unload_agv",
                "target": agv_id,
                "params": {"device_id": device_id, "buffer_type": buffer_type}
            }
        elif op == "4":
            agv_id = input("请输入AGV编号: ").strip()
            agv_id = "AGV_" + agv_id
            target_level = input("请输入目标电量(如80): ").strip()
            try:
                target_level = float(target_level)
            except Exception:
                print("目标电量需为数字！")
                continue
            cmd = {
                "action": "charge_agv",
                "target": agv_id,
                "params": {"target_level": target_level}
            }
        elif op == "5":
            print("退出菜单输入线程。")
            break
        else:
            print("无效选择，请重试。")
            continue
        # Publish command to MQTT
        mqtt_client.publish(AGENT_COMMANDS_TOPIC, json.dumps(cmd))
        print(f"已发送命令: {cmd}")

def main(argv=None):
    """Main function."""
    # Add argparse to handle command-line arguments
    parser = argparse.ArgumentParser(description="SUPCON Factory Simulation Launcher")
    parser.add_argument(
        "--no-faults",
        action="store_true", # This makes it a boolean flag
        help="Run the simulation without the fault system enabled."
    )
    args = parser.parse_args(argv)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run simulation
    simulation = FactorySimulation()
    
    try:
        simulation.initialize(no_faults=args.no_faults) # Pass the argument to initialize
        # Start menu input thread after MQTT client is ready
        import threading
        threading.Thread(target=menu_input_thread, args=(simulation.mqtt_client,), daemon=True).start()
        simulation.run()  # Run indefinitely
    except Exception as e:
        logger.error(f"❌ Failed to start simulation: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 