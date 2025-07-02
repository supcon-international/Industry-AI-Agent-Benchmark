#!/usr/bin/env python3
"""
故障诊断系统演示测试
展示改进后的智能故障诊断功能
"""

import sys
import os
import time
import random

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
from src.utils.mqtt_client import MQTTClient
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from src.game_logic.fault_system import FaultType

class FaultDiagnosisDemo:
    """故障诊断系统演示"""
    
    def __init__(self):
        print("🚀 初始化故障诊断演示系统...")
        self.mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        self.factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        print("✅ 系统初始化完成!")

    def demo_symptom_based_diagnosis(self):
        """演示1: 基于症状的诊断（不直接暴露根因）"""
        print("\n" + "="*60)
        print("📋 演示1: 基于症状的诊断系统")
        print("="*60)
        print("💡 核心改进：玩家只能看到症状，需要通过探索学习根因")
        
        # 注入一个故障
        print("\n🔬 注入故障到 StationA...")
        self.factory.fault_system.inject_random_fault("StationA", FaultType.STATION_VIBRATION)
        
        fault = self.factory.fault_system.active_faults["StationA"]
        print(f"✅ 故障已注入!")
        print(f"🔍 玩家可见症状: {fault.symptom}")
        print(f"🔒 隐藏根因: {fault.actual_root_cause} (玩家无法直接看到)")
        print(f"🎯 正确修复命令: {fault.correct_repair_command} (需要玩家探索发现)")
        
        # 展示设备状态检查功能
        print(f"\n🔍 使用 inspect 功能检查设备详细状态:")
        detailed_status = self.factory.fault_system.inspect_device("StationA")
        
        print(f"\n💡 通过多次检查和实验，玩家可以学习症状与根因的映射关系")

    def demo_correct_diagnosis_reward(self):
        """演示2: 正确诊断的奖励机制"""
        print("\n" + "="*60)
        print("🎯 演示2: 正确诊断奖励机制")
        print("="*60)
        print("💡 核心改进：正确诊断获得基础修复时间，可选择跳过等待")
        
        # 确保有故障存在
        if "StationA" not in self.factory.fault_system.active_faults:
            self.factory.fault_system.inject_random_fault("StationA", FaultType.PRECISION_DEGRADATION)
        
        fault = self.factory.fault_system.active_faults["StationA"]
        print(f"\n📊 当前故障: {fault.symptom}")
        print(f"⏱️  正确修复基础时间: {fault.correct_repair_time:.1f}秒")
        
        # 模拟正确诊断
        print(f"\n✅ 执行正确诊断: {fault.correct_repair_command}")
        start_time = self.factory.env.now
        
        result = self.factory.fault_system.handle_maintenance_request(
            "StationA", fault.correct_repair_command, "demo_agent"
        )
        
        print(f"🎉 诊断结果:")
        print(f"   - 诊断正确: {result.is_correct}")
        print(f"   - 修复时间: {result.repair_time:.1f}秒")
        print(f"   - 可跳过等待: {result.can_skip}")
        print(f"   - 无惩罚: {not result.penalty_applied}")
        
        if result.can_skip:
            print(f"\n⏭️  演示跳过功能...")
            skip_success = self.factory.fault_system.skip_repair_time("StationA")
            print(f"   跳过结果: {'成功' if skip_success else '失败'}")

    def demo_wrong_diagnosis_penalty(self):
        """演示3: 错误诊断的惩罚机制"""
        print("\n" + "="*60)
        print("❌ 演示3: 错误诊断惩罚机制") 
        print("="*60)
        print("💡 核心改进：错误诊断触发时间惩罚、设备冻结、可能影响其他设备")
        
        # 注入新故障进行错误诊断演示
        print("\n🔬 注入故障到 StationB...")
        self.factory.fault_system.inject_random_fault("StationB", FaultType.EFFICIENCY_ANOMALY)
        
        fault = self.factory.fault_system.active_faults["StationB"]
        print(f"📊 故障信息:")
        print(f"   - 症状: {fault.symptom}")
        print(f"   - 基础修复时间: {fault.correct_repair_time:.1f}秒")
        print(f"   - 错误惩罚倍数: {fault.definition.error_penalty_multiplier}x")
        
        # 执行错误诊断
        wrong_command = "wrong_repair_command"
        print(f"\n❌ 执行错误诊断: {wrong_command}")
        
        available_before = self.factory.fault_system.get_available_devices()
        print(f"🔧 错误诊断前可操作设备: {len(available_before)}个")
        
        result = self.factory.fault_system.handle_maintenance_request(
            "StationB", wrong_command, "demo_agent"
        )
        
        available_after = self.factory.fault_system.get_available_devices()
        
        print(f"\n💥 惩罚结果:")
        print(f"   - 诊断正确: {result.is_correct}")
        print(f"   - 惩罚时间: {result.repair_time:.1f}秒")
        print(f"   - 设备被冻结: {result.penalty_applied}")
        print(f"   - 影响其他设备: {len(result.affected_devices)}个")
        print(f"   - 错误诊断后可操作设备: {len(available_after)}个")
        
        if result.affected_devices:
            print(f"   - 受影响设备: {', '.join(result.affected_devices)}")
        
        print(f"\n⚠️  重要：设备仍有故障，需要正确诊断才能真正修复")

    def demo_device_relationships(self):
        """演示4: 设备关系和连锁反应"""
        print("\n" + "="*60)
        print("🔗 演示4: 设备关系和连锁反应")
        print("="*60)
        print("💡 核心改进：错误诊断可能引发其他设备故障，增加系统复杂性")
        
        print("\n📊 设备关系映射:")
        relationships = self.factory.fault_system.device_relationship_map
        for device, related in relationships.items():
            print(f"   - {device}: 关联 {', '.join(related)}")
        
        # 统计当前故障数量
        initial_faults = len(self.factory.fault_system.active_faults)
        print(f"\n📈 当前活跃故障数: {initial_faults}")
        
        # 注入AGV故障并错误诊断，观察连锁反应
        print(f"\n🔬 注入AGV故障并进行多次错误诊断...")
        
        if "AGV_1" not in self.factory.fault_system.active_faults:
            self.factory.fault_system.inject_random_fault("AGV_1", FaultType.AGV_PATH_BLOCKED)
        
        # 多次错误诊断增加触发连锁反应的概率
        for i in range(3):
            print(f"\n❌ 第{i+1}次错误诊断...")
            result = self.factory.fault_system.handle_maintenance_request(
                "AGV_1", f"wrong_command_{i}", "demo_agent"
            )
            
            if result.affected_devices:
                print(f"   触发连锁反应，影响: {', '.join(result.affected_devices)}")
            
            # 等待一段时间让次级故障有机会触发
            self.factory.run(until=int(self.factory.env.now + 35))
        
        # 统计最终故障数量
        final_faults = len(self.factory.fault_system.active_faults)
        new_faults = final_faults - initial_faults
        
        print(f"\n📊 连锁反应结果:")
        print(f"   - 初始故障数: {initial_faults}")
        print(f"   - 最终故障数: {final_faults}")
        print(f"   - 新增故障数: {new_faults}")
        
        if new_faults > 0:
            print(f"   ✅ 成功展示连锁反应机制!")
        else:
            print(f"   📝 此次未触发连锁反应（概率性事件）")

    def demo_learning_process(self):
        """演示5: 学习过程模拟"""
        print("\n" + "="*60)
        print("🧠 演示5: AI Agent学习过程模拟")
        print("="*60)
        print("💡 核心改进：通过多次尝试和观察，AI Agent可以学习症状-根因映射")
        
        print("\n🎯 模拟AI Agent的学习过程...")
        
        # 创建一个简单的学习记录
        learning_record = {}
        test_cases = [
            (FaultType.STATION_VIBRATION, "StationC"),
            (FaultType.PRECISION_DEGRADATION, "QualityCheck"),
            (FaultType.AGV_BATTERY_DRAIN, "AGV_2")
        ]
        
        for i, (fault_type, device) in enumerate(test_cases, 1):
            print(f"\n📚 学习案例 {i}: {fault_type.value}")
            print("-" * 40)
            
            # 清除之前的故障
            if device in self.factory.fault_system.active_faults:
                self.factory.fault_system._clear_fault(device)
            
            # 注入故障
            self.factory.fault_system.inject_random_fault(device, fault_type)
            fault = self.factory.fault_system.active_faults[device]
            
            print(f"🔍 观察到症状: {fault.symptom}")
            
            # 模拟Agent检查设备状态
            print(f"🔬 Agent检查设备详细状态...")
            detailed_status = self.factory.fault_system.inspect_device(device)
            
            # 记录学习数据
            symptom = fault.symptom
            if symptom not in learning_record:
                learning_record[symptom] = {
                    'attempts': [],
                    'correct_command': fault.correct_repair_command
                }
            
            # 模拟不同的尝试
            test_commands = ["wrong_cmd1", "wrong_cmd2", fault.correct_repair_command]
            random.shuffle(test_commands)
            
            for attempt, cmd in enumerate(test_commands, 1):
                result = self.factory.fault_system.handle_maintenance_request(device, cmd, f"learning_agent")
                
                learning_record[symptom]['attempts'].append({
                    'command': cmd,
                    'success': result.is_correct,
                    'repair_time': result.repair_time
                })
                
                print(f"   尝试 {attempt}: {cmd} -> {'成功' if result.is_correct else '失败'} ({result.repair_time:.1f}s)")
                
                if result.is_correct:
                    print(f"   ✅ 找到正确修复方法!")
                    break
                
                # 重新注入故障继续学习
                if device not in self.factory.fault_system.active_faults:
                    self.factory.fault_system.inject_random_fault(device, fault_type)
        
        # 展示学习成果
        print(f"\n🎓 AI Agent学习成果总结:")
        print("="*40)
        for symptom, data in learning_record.items():
            success_rate = sum(1 for attempt in data['attempts'] if attempt['success']) / len(data['attempts'])
            print(f"📊 症状: {symptom}")
            print(f"   - 正确修复命令: {data['correct_command']}")
            print(f"   - 学习成功率: {success_rate*100:.1f}%")
            print(f"   - 尝试次数: {len(data['attempts'])}")

    def run_comprehensive_demo(self):
        """运行完整的故障诊断系统演示"""
        print("🚀 SUPCON 智能故障诊断系统演示")
        print("="*80)
        print("展示基于PRD 3.2改进的故障诊断功能")
        print("目标：让AI Agent通过探索学习，而不是直接获得答案")
        print("="*80)
        
        # 依次运行各个演示
        demos = [
            ("基于症状的诊断", self.demo_symptom_based_diagnosis),
            ("正确诊断奖励机制", self.demo_correct_diagnosis_reward),
            ("错误诊断惩罚机制", self.demo_wrong_diagnosis_penalty),
            ("设备关系和连锁反应", self.demo_device_relationships),
            ("AI Agent学习过程", self.demo_learning_process)
        ]
        
        for demo_name, demo_func in demos:
            try:
                demo_func()
                print(f"\n✅ {demo_name} 演示完成")
                time.sleep(1)  # 短暂暂停让用户看清结果
            except Exception as e:
                print(f"\n❌ {demo_name} 演示失败: {e}")
        
        # 生成总结报告
        self.generate_summary_report()

    def generate_summary_report(self):
        """生成演示总结报告"""
        print("\n" + "="*80)
        print("📋 故障诊断系统改进总结")
        print("="*80)
        
        print("🎯 核心改进点:")
        print("   1. ✅ 症状导向：玩家只能看到症状，需探索根因")
        print("   2. ✅ 智能惩罚：错误诊断触发时间惩罚和设备冻结")
        print("   3. ✅ 连锁反应：错误可能影响关联设备，增加复杂性")
        print("   4. ✅ 学习机制：通过多次尝试建立症状-根因映射")
        print("   5. ✅ 跳过选项：正确诊断可选择跳过等待时间")
        
        print("\n🎮 对AI Agent开发的影响:")
        print("   - 💡 需要开发探索策略来学习故障模式")
        print("   - 🧠 需要记忆和推理能力来建立知识库") 
        print("   - ⚖️ 需要权衡风险：快速尝试 vs 谨慎分析")
        print("   - 🔗 需要考虑设备间关系，避免连锁故障")
        print("   - 📊 需要优化诊断策略以提高成功率")
        
        # 统计当前系统状态
        active_faults = len(self.factory.fault_system.active_faults)
        fault_stats = self.factory.fault_system.get_fault_stats()
        
        print(f"\n📊 当前系统状态:")
        print(f"   - 活跃故障: {active_faults}个")
        print(f"   - 故障设备: {', '.join(fault_stats['fault_devices']) if fault_stats['fault_devices'] else '无'}")
        print(f"   - 仿真时间: {self.factory.env.now:.1f}秒")
        
        print(f"\n🎉 演示完成！故障诊断系统已升级为智能学习型系统")
        print(f"💻 AI Agent开发者现在可以基于这些机制开发更智能的诊断策略")

def main():
    """主程序入口"""
    print("🧪 SUPCON 故障诊断系统演示")
    print("展示PRD 3.2中的智能故障诊断改进功能")
    
    try:
        demo = FaultDiagnosisDemo()
        demo.run_comprehensive_demo()
        return True
        
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 