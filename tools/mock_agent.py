#!/usr/bin/env python3
# tools/mock_agent.py

"""
An enhanced mock agent for demonstrating the advanced fault diagnosis system.
This agent implements its own learning and pattern recognition based on inspection data.
"""

import json
import time
import random
from typing import Dict, Optional, List
from src.utils.mqtt_client import MQTTClient
from config.topics import AGENT_COMMANDS_TOPIC
from config.schemas import AgentCommand

class MockAgent:
    """
    A mock agent that demonstrates the enhanced fault diagnosis system.
    
    This agent implements its own learning system:
    1. Records inspection results and diagnosis outcomes
    2. Builds pattern recognition from device states
    3. Improves diagnosis accuracy over time
    4. Uses skip functionality when needed
    """
    
    def __init__(self, agent_id: str, mqtt_client: MQTTClient):
        self.agent_id = agent_id
        self.mqtt_client = mqtt_client
        self.fault_alerts = {}
        
        # Agent自己的学习系统
        self.inspection_history = {}  # 设备检查历史
        self.diagnosis_history = []   # 诊断历史记录
        self.learned_patterns = {}    # 学习到的故障模式
        self.diagnosis_accuracy = 0.0 # 诊断准确率
        
        # Subscribe to fault alerts and inspection results
        self.mqtt_client.subscribe("factory/alerts/+", self._handle_fault_alert)
        self.mqtt_client.subscribe("factory/inspection/+/result", self._handle_inspection_result)
        self.mqtt_client.subscribe("factory/devices/available", self._handle_available_devices)
        
        print(f"🤖 MockAgent {agent_id} initialized with self-learning capabilities")

    def _handle_fault_alert(self, topic: str, payload: bytes):
        """Handle incoming fault alerts."""
        try:
            alert_data = json.loads(payload.decode('utf-8'))
            device_id = alert_data.get('device_id')
            
            if device_id not in self.fault_alerts:
                print(f"\n🚨 New fault detected on {device_id}: {alert_data.get('symptom')}")
                self.fault_alerts[device_id] = alert_data
                
                # Immediately inspect the device to gather information
                self._inspect_device(device_id)
                
        except Exception as e:
            print(f"❌ Error handling fault alert: {e}")

    def _handle_inspection_result(self, topic: str, payload: bytes):
        """Handle inspection results and record for learning."""
        try:
            inspection_data = json.loads(payload.decode('utf-8'))
            device_id = inspection_data.get('device_id')
            status = inspection_data.get('status')
            timestamp = inspection_data.get('timestamp')
            
            print(f"🔍 Inspection result for {device_id}:")
            print(f"   - Temperature: {status.get('temperature')}°C")
            print(f"   - Vibration: {status.get('vibration_level')} mm/s")
            print(f"   - Efficiency: {status.get('efficiency_rate')}%")
            
            if status.get('device_type') == 'station':
                print(f"   - Precision: {status.get('precision_level')}%")
                print(f"   - Tool wear: {status.get('tool_wear_level')}%")
                print(f"   - Lubricant: {status.get('lubricant_level')}%")
            elif status.get('device_type') == 'agv':
                print(f"   - Battery: {status.get('battery_level')}%")
                print(f"   - Position accuracy: {status.get('position_accuracy')}%")
            
            # 记录检查历史用于学习
            self._record_inspection(device_id, status, timestamp)
            
            # Try to diagnose based on the inspection
            if status.get('has_fault'):
                self._attempt_diagnosis(device_id, status)
                
        except Exception as e:
            print(f"❌ Error handling inspection result: {e}")

    def _handle_available_devices(self, topic: str, payload: bytes):
        """Handle available devices updates."""
        try:
            data = json.loads(payload.decode('utf-8'))
            available_devices = data.get('available_devices', [])
            print(f"📋 Available devices: {', '.join(available_devices)}")
        except Exception as e:
            print(f"❌ Error handling available devices: {e}")

    def _record_inspection(self, device_id: str, status: Dict, timestamp: float):
        """记录设备检查结果，用于学习"""
        if device_id not in self.inspection_history:
            self.inspection_history[device_id] = []
        
        inspection_record = {
            'timestamp': timestamp,
            'status': status,
            'symptom': status.get('fault_symptom'),
            'has_fault': status.get('has_fault', False)
        }
        
        self.inspection_history[device_id].append(inspection_record)
        
        # 分析模式
        if status.get('has_fault'):
            self._learn_fault_pattern(device_id, status)

    def _learn_fault_pattern(self, device_id: str, status: Dict):
        """从故障状态中学习模式"""
        symptom = status.get('fault_symptom')
        if not symptom:
            return
        
        if symptom not in self.learned_patterns:
            self.learned_patterns[symptom] = {
                'occurrences': 0,
                'devices': set(),
                'typical_states': []
            }
        
        pattern = self.learned_patterns[symptom]
        pattern['occurrences'] += 1
        pattern['devices'].add(device_id)
        
        # 记录典型状态
        state_snapshot = {
            'temperature': status.get('temperature'),
            'vibration_level': status.get('vibration_level'),
            'efficiency_rate': status.get('efficiency_rate'),
            'precision_level': status.get('precision_level'),
            'tool_wear_level': status.get('tool_wear_level'),
            'battery_level': status.get('battery_level'),
            'position_accuracy': status.get('position_accuracy')
        }
        
        pattern['typical_states'].append(state_snapshot)
        
        print(f"📈 Learning: {symptom} pattern updated (total occurrences: {pattern['occurrences']})")

    def _record_diagnosis_result(self, device_id: str, command: str, result: Dict):
        """记录诊断结果用于学习"""
        diagnosis_record = {
            'timestamp': time.time(),
            'device_id': device_id,
            'command': command,
            'is_correct': result.get('is_correct', False),
            'repair_time': result.get('repair_time', 0),
            'affected_devices': result.get('affected_devices', [])
        }
        
        self.diagnosis_history.append(diagnosis_record)
        
        # 更新准确率
        total_diagnoses = len(self.diagnosis_history)
        correct_diagnoses = sum(1 for d in self.diagnosis_history if d['is_correct'])
        self.diagnosis_accuracy = correct_diagnoses / total_diagnoses if total_diagnoses > 0 else 0
        
        print(f"📊 Diagnosis accuracy: {self.diagnosis_accuracy:.2%} ({correct_diagnoses}/{total_diagnoses})")

    def _inspect_device(self, device_id: str):
        """Send inspect command for a device."""
        command = AgentCommand(
            command_id=f"inspect_{device_id}_{int(time.time())}",
            agent_id=self.agent_id,
            action="inspect_device",
            target=device_id,
            params={}
        )
        self._send_command(command)
        print(f"🔍 Sent inspect command for {device_id}")

    def _attempt_diagnosis(self, device_id: str, status: Dict):
        """基于检查数据和学习到的模式尝试诊断"""
        symptom = status.get('fault_symptom')
        
        if not symptom:
            print(f"❓ No symptom found for {device_id}, skipping diagnosis")
            return
        
        print(f"\n🧠 Attempting diagnosis for {device_id} with symptom: {symptom}")
        
        # 优先使用学习到的模式
        diagnosis_command = self._apply_learned_patterns(symptom, status)
        
        if not diagnosis_command:
            # 如果没有学习到的模式，使用规则基础诊断
            diagnosis_command = self._rule_based_diagnosis(symptom, status)
        
        if diagnosis_command:
            self._send_maintenance_request(device_id, diagnosis_command)
        else:
            print(f"❓ Unable to determine diagnosis for {symptom}, trying exploration")
            # 尝试探索性诊断
            self._try_exploration_diagnosis(device_id, symptom)

    def _apply_learned_patterns(self, symptom: str, status: Dict) -> Optional[str]:
        """应用学习到的模式进行诊断"""
        if symptom not in self.learned_patterns:
            return None
        
        pattern = self.learned_patterns[symptom]
        
        # 基于历史成功诊断推荐命令
        successful_commands = []
        for diagnosis in self.diagnosis_history:
            if diagnosis['is_correct']:
                # 找到之前成功的诊断，查找对应的状态
                for state in pattern['typical_states']:
                    if self._states_similar(status, state):
                        successful_commands.append(diagnosis['command'])
        
        if successful_commands:
            # 选择最常见的成功命令
            most_common = max(set(successful_commands), key=successful_commands.count)
            print(f"🎯 Using learned pattern: {most_common} for {symptom}")
            return most_common
        
        return None

    def _states_similar(self, state1: Dict, state2: Dict) -> bool:
        """判断两个设备状态是否相似"""
        tolerance = 0.2  # 20% 容差
        
        for key in ['temperature', 'vibration_level', 'efficiency_rate']:
            val1 = state1.get(key)
            val2 = state2.get(key)
            if val1 is not None and val2 is not None:
                if abs(val1 - val2) / max(val1, val2) > tolerance:
                    return False
        
        return True

    def _rule_based_diagnosis(self, symptom: str, status: Dict) -> Optional[str]:
        """基于规则的诊断逻辑"""
        temperature = status.get('temperature', 25)
        vibration = status.get('vibration_level', 0.5)
        efficiency = status.get('efficiency_rate', 100)
        
        # Rule-based diagnosis logic
        if symptom == "主轴振动异常":
            if vibration > 2.0:
                return "replace_bearing"  # High vibration suggests bearing wear
            else:
                return "tighten_bolts"   # Lower vibration might be loose bolts
                
        elif symptom == "加工精度下降":
            precision = status.get('precision_level', 100)
            tool_wear = status.get('tool_wear_level', 0)
            if tool_wear > 60:
                return "replace_tool"
            else:
                return "recalibrate"
                
        elif symptom == "AGV路径阻塞":
            position_accuracy = status.get('position_accuracy', 100)
            if position_accuracy < 80:
                return "reboot_device"
            else:
                return "reroute_agv"
                
        elif symptom == "AGV电量突降":
            battery = status.get('battery_level', 100)
            if battery < 20:
                return "force_charge"
            else:
                return "optimize_schedule"
                
        elif symptom == "效率异常降低":
            if temperature > 40:
                return "reduce_frequency"  # Overheating
            else:
                return "add_lubricant"     # Insufficient lubrication
        
        return None

    def _try_exploration_diagnosis(self, device_id: str, symptom: str):
        """探索性诊断，尝试学习新的模式"""
        # Common diagnosis commands
        commands = [
            "replace_bearing", "tighten_bolts", "replace_tool", "recalibrate",
            "reroute_agv", "reboot_device", "force_charge", "optimize_schedule",
            "reduce_frequency", "add_lubricant"
        ]
        
        # 避免重复尝试已知失败的组合
        avoided_commands = self._get_failed_commands_for_symptom(symptom)
        available_commands = [cmd for cmd in commands if cmd not in avoided_commands]
        
        if available_commands:
            command = random.choice(available_commands)
            print(f"🎲 Exploration diagnosis: {command} for {symptom}")
            self._send_maintenance_request(device_id, command)

    def _get_failed_commands_for_symptom(self, symptom: str) -> List[str]:
        """获取对特定症状失败的诊断命令"""
        failed_commands = []
        for diagnosis in self.diagnosis_history:
            if not diagnosis['is_correct'] and diagnosis.get('symptom') == symptom:
                failed_commands.append(diagnosis['command'])
        return failed_commands

    def _send_maintenance_request(self, device_id: str, maintenance_type: str):
        """Send maintenance request and prepare to record result."""
        command = AgentCommand(
            command_id=f"maintenance_{device_id}_{int(time.time())}",
            agent_id=self.agent_id,
            action="request_maintenance",
            target=device_id,
            params={"maintenance_type": maintenance_type}
        )
        self._send_command(command)
        print(f"🔧 Sent maintenance request: {maintenance_type} for {device_id}")
        
        # Note: The result would need to be captured through factory feedback
        # For now, we simulate learning from the command feedback

    def _send_command(self, command: AgentCommand):
        """Send command via MQTT."""
        try:
            self.mqtt_client.publish(AGENT_COMMANDS_TOPIC, command)
        except Exception as e:
            print(f"❌ Failed to send command: {e}")

    def demonstrate_enhanced_features(self):
        """Demonstrate the enhanced diagnosis features."""
        print(f"\n🚀 {self.agent_id} demonstrating enhanced diagnosis features...")
        
        # 1. Get available devices
        self._get_available_devices()
        time.sleep(2)
        
        # 2. Inspect all devices to build initial knowledge
        devices = ["StationA", "StationB", "StationC", "QualityCheck", "AGV_1", "AGV_2"]
        for device in devices:
            self._inspect_device(device)
            time.sleep(1)
        
        # 3. Show current learning status
        self._print_learning_status()
        
        print(f"✅ {self.agent_id} demonstration completed")

    def _get_available_devices(self):
        """Request list of available devices."""
        command = AgentCommand(
            command_id=f"get_devices_{int(time.time())}",
            agent_id=self.agent_id,
            action="get_available_devices",
            target="factory",
            params={}
        )
        self._send_command(command)
        print("📋 Requested available devices list")

    def _print_learning_status(self):
        """打印当前的学习状态"""
        print(f"\n📚 {self.agent_id} Learning Status:")
        print(f"   - Inspection records: {sum(len(records) for records in self.inspection_history.values())}")
        print(f"   - Diagnosis attempts: {len(self.diagnosis_history)}")
        print(f"   - Current accuracy: {self.diagnosis_accuracy:.2%}")
        print(f"   - Learned patterns: {len(self.learned_patterns)}")
        
        for symptom, pattern in self.learned_patterns.items():
            print(f"     • {symptom}: {pattern['occurrences']} occurrences on {len(pattern['devices'])} devices")

    def demonstrate_skip_functionality(self, device_id: str):
        """Demonstrate skip repair time functionality."""
        command = AgentCommand(
            command_id=f"skip_{device_id}_{int(time.time())}",
            agent_id=self.agent_id,
            action="skip_repair_time",
            target=device_id,
            params={}
        )
        self._send_command(command)
        print(f"⏭️ Sent skip repair time command for {device_id}")


def main():
    """Main function to run the enhanced mock agent."""
    from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
    
    print("🤖 Starting Enhanced Mock Agent with Self-Learning...")
    
    # Create MQTT client
    mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
    
    # Create mock agent
    agent = MockAgent("MockAgent_SelfLearning", mqtt_client)
    
    # Start demonstration
    agent.demonstrate_enhanced_features()
    
    # Keep running to handle fault alerts and learn
    print("\n👂 Listening for fault alerts and actively learning...")
    print("   - The agent records all inspection data for pattern learning")
    print("   - Diagnosis accuracy improves over time through experience")
    print("   - Uses learned patterns to make better diagnoses")
    print("   - Explores new diagnosis when patterns are unclear")
    print("   - Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(5)
            # Periodically show learning progress
            if random.random() < 0.1:  # 10% chance every 5 seconds
                agent._print_learning_status()
    except KeyboardInterrupt:
        print("\n🛑 Self-learning mock agent stopped")


if __name__ == "__main__":
    main() 