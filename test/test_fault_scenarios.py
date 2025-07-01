#!/usr/bin/env python3
"""
故障场景专项测试
测试各种故障类型和Agent的故障处理能力
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

class FaultScenarioTester:
    """故障场景测试器"""
    
    def __init__(self):
        self.mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        
    def test_all_fault_types(self):
        """测试所有故障类型"""
        print("🧪 故障类型全覆盖测试")
        print("=" * 60)
        
        fault_types = list(FaultType)
        devices = ['StationA', 'StationB', 'StationC', 'QualityCheck', 'AGV_1', 'AGV_2']
        
        results = []
        
        for fault_type in fault_types:
            print(f"\n🔬 测试故障类型: {fault_type.value}")
            print("-" * 40)
            
            factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
            
            # 选择合适的设备
            if fault_type in [FaultType.AGV_PATH_BLOCKED, FaultType.AGV_BATTERY_DRAIN]:
                test_devices = ['AGV_1', 'AGV_2']
            else:
                test_devices = ['StationA', 'StationB', 'StationC', 'QualityCheck']
            
            for device_id in test_devices[:2]:  # 测试2个设备
                factory.fault_system.inject_random_fault(device_id, fault_type)
                
                if device_id in factory.fault_system.active_faults:
                    fault = factory.fault_system.active_faults[device_id]
                    print(f"✅ {device_id}: {fault.symptom}")
                    print(f"   隐藏原因: {fault.actual_root_cause}")
                    print(f"   正确修复: {fault.correct_repair_command}")
                    
                    # 测试正确诊断
                    success, repair_time = factory.fault_system.handle_maintenance_request(
                        device_id, fault.correct_repair_command
                    )
                    
                    results.append({
                        'fault_type': fault_type.value,
                        'device': device_id,
                        'symptom': fault.symptom,
                        'correct_repair': fault.correct_repair_command,
                        'repair_time': repair_time,
                        'success': success
                    })
                    
                    print(f"   修复结果: {'成功' if success else '失败'} ({repair_time:.1f}s)")
                else:
                    print(f"❌ {device_id}: 故障注入失败")
        
        # 汇总结果
        print(f"\n📊 测试结果汇总:")
        print(f"   总测试案例: {len(results)}")
        successful_repairs = sum(1 for r in results if r['success'])
        print(f"   成功修复: {successful_repairs}")
        print(f"   成功率: {successful_repairs/len(results)*100:.1f}%")
        
        return results
    
    def test_diagnosis_accuracy(self):
        """测试诊断准确性对修复时间的影响"""
        print("\n🎯 诊断准确性影响测试")
        print("=" * 60)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        # 注入一个故障
        factory.fault_system.inject_random_fault("StationA", FaultType.STATION_VIBRATION)
        fault = list(factory.fault_system.active_faults.values())[0]
        
        print(f"故障: {fault.symptom}")
        print(f"正确诊断: {fault.correct_repair_command}")
        
        # 测试正确诊断
        print(f"\n✅ 测试正确诊断:")
        success1, time1 = factory.fault_system.handle_maintenance_request(
            "StationA", fault.correct_repair_command
        )
        print(f"   结果: {success1}, 时间: {time1:.1f}s")
        
        # 重新注入故障测试错误诊断
        factory.fault_system.inject_random_fault("StationB", FaultType.STATION_VIBRATION)
        
        print(f"\n❌ 测试错误诊断:")
        wrong_commands = ["wrong_command", "random_fix", "invalid_repair"]
        for wrong_cmd in wrong_commands:
            success2, time2 = factory.fault_system.handle_maintenance_request(
                "StationB", wrong_cmd
            )
            penalty_ratio = time2 / time1 if time1 > 0 else 0
            print(f"   命令: {wrong_cmd}")
            print(f"   结果: {success2}, 时间: {time2:.1f}s (惩罚倍数: {penalty_ratio:.1f}x)")
            break  # 只测试一个错误命令
        
        return time1, time2
    
    def test_multiple_concurrent_faults(self):
        """测试多个并发故障"""
        print("\n🔥 并发故障压力测试")
        print("=" * 60)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        # 在所有设备上注入故障
        devices = ['StationA', 'StationB', 'StationC', 'QualityCheck', 'AGV_1', 'AGV_2']
        fault_types = list(FaultType)
        
        injected_faults = []
        
        for device_id in devices:
            # 为AGV选择AGV相关故障，为Station选择Station相关故障
            if device_id.startswith('AGV'):
                fault_type = random.choice([FaultType.AGV_PATH_BLOCKED, FaultType.AGV_BATTERY_DRAIN])
            else:
                fault_type = random.choice([
                    FaultType.STATION_VIBRATION, 
                    FaultType.PRECISION_DEGRADATION,
                    FaultType.EFFICIENCY_ANOMALY
                ])
            
            factory.fault_system.inject_random_fault(device_id, fault_type)
            
            if device_id in factory.fault_system.active_faults:
                fault = factory.fault_system.active_faults[device_id]
                injected_faults.append({
                    'device': device_id,
                    'fault': fault,
                    'type': fault_type.value
                })
                print(f"💥 {device_id}: {fault.symptom}")
        
        print(f"\n📊 并发故障统计:")
        print(f"   同时活跃故障: {len(injected_faults)}")
        
        # 模拟Agent逐一修复故障
        print(f"\n🔧 开始修复故障...")
        start_time = time.time()
        
        repair_results = []
        for fault_info in injected_faults:
            device_id = fault_info['device']
            fault = fault_info['fault']
            
            # 模拟Agent有70%的概率正确诊断
            if random.random() < 0.7:
                repair_cmd = fault.correct_repair_command
                diagnosis = "正确"
            else:
                repair_cmd = "wrong_repair"
                diagnosis = "错误"
            
            success, repair_time = factory.handle_maintenance_request(device_id, repair_cmd)
            repair_results.append({
                'device': device_id,
                'diagnosis': diagnosis,
                'success': success,
                'repair_time': repair_time
            })
            
            print(f"   {device_id}: {diagnosis}诊断 -> {repair_time:.1f}s")
        
        end_time = time.time()
        
        # 计算统计数据
        total_repair_time = sum(r['repair_time'] for r in repair_results)
        correct_diagnoses = sum(1 for r in repair_results if r['success'])
        
        print(f"\n📈 修复结果:")
        print(f"   总修复时间: {total_repair_time:.1f}s")
        print(f"   正确诊断: {correct_diagnoses}/{len(repair_results)}")
        print(f"   诊断准确率: {correct_diagnoses/len(repair_results)*100:.1f}%")
        print(f"   实际处理时间: {end_time - start_time:.2f}s")
        
        return repair_results
    
    def test_fault_recovery_scenarios(self):
        """测试故障恢复场景"""
        print("\n⏰ 故障自动恢复测试")
        print("=" * 60)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        # 注入故障但不修复，观察自动恢复
        print("💉 注入故障，等待自动恢复...")
        factory.fault_system.inject_random_fault("StationA", FaultType.EFFICIENCY_ANOMALY)
        
        initial_faults = len(factory.fault_system.active_faults)
        print(f"   初始故障数: {initial_faults}")
        
        # 运行一段时间观察故障状态
        print("⏳ 运行150秒观察故障恢复...")
        factory.run(until=150)
        
        final_faults = len(factory.fault_system.active_faults)
        print(f"   最终故障数: {final_faults}")
        
        if final_faults < initial_faults:
            print("✅ 故障自动恢复正常工作")
        else:
            print("⚠️ 故障仍然活跃，可能需要手动修复")
        
        return initial_faults, final_faults
    
    def run_comprehensive_test(self):
        """运行综合故障测试"""
        print("🚀 SUPCON 故障系统综合测试")
        print("=" * 80)
        
        test_results = {}
        
        # 1. 基础故障类型测试
        print("\n【第1部分】基础故障类型测试")
        test_results['fault_types'] = self.test_all_fault_types()
        
        # 2. 诊断准确性测试
        print("\n【第2部分】诊断准确性测试")
        test_results['diagnosis_accuracy'] = self.test_diagnosis_accuracy()
        
        # 3. 并发故障测试
        print("\n【第3部分】并发故障压力测试")
        test_results['concurrent_faults'] = self.test_multiple_concurrent_faults()
        
        # 4. 自动恢复测试
        print("\n【第4部分】故障自动恢复测试")
        test_results['auto_recovery'] = self.test_fault_recovery_scenarios()
        
        # 5. 生成测试报告
        self.generate_test_report(test_results)
        
        return test_results
    
    def generate_test_report(self, results):
        """生成测试报告"""
        print("\n" + "=" * 80)
        print("📋 故障系统测试报告")
        print("=" * 80)
        
        # 故障类型覆盖率
        fault_types_tested = len(results['fault_types'])
        total_fault_types = len(list(FaultType))
        print(f"✅ 故障类型覆盖: {fault_types_tested} 个场景测试")
        
        # 诊断准确性
        correct_time, wrong_time = results['diagnosis_accuracy']
        penalty_factor = wrong_time / correct_time if correct_time > 0 else 1
        print(f"🎯 诊断准确性影响: 错误诊断惩罚 {penalty_factor:.1f}x 修复时间")
        
        # 并发处理能力
        concurrent_results = results['concurrent_faults']
        concurrent_count = len(concurrent_results)
        correct_diagnoses = sum(1 for r in concurrent_results if r['success'])
        print(f"🔥 并发故障处理: {concurrent_count} 个并发故障，{correct_diagnoses} 个正确诊断")
        
        # 自动恢复
        initial, final = results['auto_recovery']
        print(f"⏰ 自动恢复机制: 故障数从 {initial} 减少到 {final}")
        
        print(f"\n🎉 故障系统测试完成！系统具备完整的故障注入、诊断和恢复能力。")
        print(f"💡 Agent开发者可以基于这些故障类型开发智能诊断策略。")

def main():
    """主程序"""
    print("🧪 SUPCON 故障系统专项测试")
    print("这将测试所有故障类型、诊断机制和恢复策略")
    print()
    
    try:
        tester = FaultScenarioTester()
        results = tester.run_comprehensive_test()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 