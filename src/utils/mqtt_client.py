# utils/mqtt_client.py
import logging
import threading
import paho.mqtt.client as mqtt
from typing import Callable, Optional
from pydantic import BaseModel
import time
import os
from src.utils.topic_manager import TopicManager

# Configure logger
logger = logging.getLogger(__name__)

class MQTTClient:
    """
    A robust wrapper for the paho-mqtt client providing easy-to-use
    methods for connecting, publishing, and subscribing.
    """

    def __init__(self, host: str, port: int, topic_manager: TopicManager, client_id: str = ""):
        self._host = host
        self._port = port
        # NOTE: The client_id is passed as the first argument for compatibility.
        self.client_id = client_id
        self._client = mqtt.Client(client_id=client_id,protocol=mqtt.MQTTv5)
        self._topic_manager = topic_manager
        
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._message_callbacks = {}

        self.heartbeat_interval = 20  # 心跳间隔（秒）
        self.heartbeat_timeout = 60   # 心跳超时（秒）
        self.last_pong_time: Optional[float] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.alert_callback = None  # 告警回调函数

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.debug(f"Successfully connected to MQTT Broker at {self._host}:{self._port}")
            if self._topic_manager:
                pong_topic = self._topic_manager.get_heartbeat_topic(ping=False)
                self._client.subscribe(pong_topic)
            self._start_heartbeat()
        else:
            logger.error(f"Failed to connect to MQTT Broker, reason code: {reason_code}")

    def _start_heartbeat(self):
        def heartbeat_loop():
            while True:
                time.sleep(self.heartbeat_interval)
                if self._topic_manager:
                    ping_topic = self._topic_manager.get_heartbeat_topic(ping=True)
                    self.publish(ping_topic, "ping")
                
                    # 检查超时
                    if self.last_pong_time and (time.time() - self.last_pong_time > self.heartbeat_timeout):
                        logger.warning("❌ Heartbeat timeout! Broker may be down.")
                        if self.alert_callback:
                            self.alert_callback("MQTT Broker heartbeat timeout")
                        self._client.reconnect()  # 触发重连
                else:
                    logger.warning("Topic manager not set, cannot send heartbeat.")

        if self.heartbeat_thread is None:
            self.last_pong_time = time.time()  # Initialize pong time
            self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
            logger.debug("Heartbeat thread started.")

    def set_alert_callback(self, callback):
        """设置告警回调函数（如发送邮件/Slack）"""
        self.alert_callback = callback
        print(f"🔔 Alert callback set: {callback}")

    def _on_disconnect(self, client, userdata, reason_code, properties=None):
        logger.warning(f"Disconnected from MQTT Broker with reason code: {reason_code}. Reconnecting...")

    def _on_message(self, client, userdata, msg):
        """
        Internal callback to route messages to the appropriate topic-specific callback.
        """
        # logger.debug(f"Received message on topic {msg.topic}")
        if self._topic_manager and msg.topic == self._topic_manager.get_heartbeat_topic(ping=False):
            if msg.payload.decode() == "pong":
                self.update_last_pong_time()
                return

        # Iterate over subscribed topics and check for a match
        for topic_filter, callback in self._message_callbacks.items():
            if mqtt.topic_matches_sub(topic_filter, msg.topic):
                callback(msg.topic, msg.payload)
                break
        else:
            logger.warning(f"No callback registered for message on topic {msg.topic}")

    def update_last_pong_time(self):
        self.last_pong_time = time.time()

    def connect(self):
        """
        Connects to the MQTT broker and starts the network loop in a separate thread.
        """
        try:
            self._client.connect(self._host, self._port, 60)
            self._client.loop_start()
        except Exception as e:
            logger.error(f"Error connecting to MQTT Broker: {e}")
            raise

    def connect_with_retry(self):
        self.connect()
        # Wait for MQTT client to be fully connected
        max_retries = 20
        retry_interval = 0.5
        for i in range(max_retries):
            if self.is_connected():
                break
            logger.debug(f"Waiting for MQTT connection... ({i+1}/{max_retries})")
            time.sleep(retry_interval)
        else:
            logger.error("❌ Failed to connect to MQTT broker within the given time. Exiting simulation.")
            raise ConnectionError("MQTT connection failed.")
    
    def disconnect(self):
        """
        Stops the network loop and disconnects from the MQTT broker.
        """
        # logger.debug("Disconnecting from MQTT Broker.")
        self._client.loop_stop()
        self._client.disconnect()

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None], qos: int = 0):
        """
        Subscribes to a topic and registers a callback for incoming messages.

        Args:
            topic (str): The topic to subscribe to (can include wildcards).
            callback (Callable): A function to call when a message is received.
                                 The callback should accept (topic, payload).
            qos (int): The Quality of Service level for the subscription.
        """
        if not callable(callback):
            raise TypeError("Callback must be a callable function")
            
        # logger.debug(f"Subscribing to topic: {topic}")
        self._message_callbacks[topic] = callback
        self._client.subscribe(topic, qos)

    def publish(self, topic: str, payload: str | BaseModel, qos: int = 1, retain: bool = False):
        """
        Publishes a message to a topic.

        Args:
            topic (str): The topic to publish to.
            payload (str | BaseModel): The message payload. If it's a Pydantic BaseModel,
                                       it will be automatically converted to a JSON string.
            qos (int): The Quality of Service level for the message.
            retain (bool): Whether the message should be retained by the broker.
        """
        if isinstance(payload, BaseModel):
            message = payload.model_dump_json()
        elif isinstance(payload, str):
            message = payload
        else:
            message = str(payload)
            # raise TypeError("Payload must be a string or a Pydantic BaseModel")
        result = self._client.publish(topic, message, qos, retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Failed to publish to topic {topic}: {mqtt.error_string(result.rc)}") 

    def is_connected(self):
        return self._client.is_connected()