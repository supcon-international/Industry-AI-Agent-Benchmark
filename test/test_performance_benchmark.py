#!/usr/bin/env python3
"""
性能基准测试
测试系统在不同负载和时间尺度下的性能表现
"""

import sys
import os
import time
import psutil
import gc
from typing import Dict, List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
from src.utils.mqtt_client import MQTTClient
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT

class PerformanceBenchmark:
    """性能基准测试器"""
    
    def __init__(self):
        self.mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        self.test_results = []
        
    def measure_system_resources(self):
        """测量系统资源使用情况"""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            'cpu_percent': process.cpu_percent(),
            'memory_mb': memory_info.rss / 1024 / 1024,
            'memory_percent': process.memory_percent(),
            'threads': process.num_threads()
        }
    
    def test_simulation_speed(self, duration: int = 300) -> Dict:
        """测试仿真速度"""
        print(f"⚡ 仿真速度测试 (目标: {duration}秒)")
        print("-" * 50)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        # 测量资源使用
        initial_resources = self.measure_system_resources()
        print(f"初始资源: CPU {initial_resources['cpu_percent']:.1f}%, RAM {initial_resources['memory_mb']:.1f}MB")
        
        # 运行仿真并测量时间
        start_real_time = time.time()
        start_sim_time = factory.env.now
        
        factory.run(until=duration)
        
        end_real_time = time.time()
        end_sim_time = factory.env.now
        
        # 计算性能指标
        real_time_used = end_real_time - start_real_time
        sim_time_elapsed = end_sim_time - start_sim_time
        speed_ratio = sim_time_elapsed / real_time_used
        
        # 测量最终资源使用
        final_resources = self.measure_system_resources()
        
        results = {
            'simulation_duration': sim_time_elapsed,
            'real_time_used': real_time_used,
            'speed_ratio': speed_ratio,
            'initial_resources': initial_resources,
            'final_resources': final_resources,
            'orders_generated': factory.kpi_calculator.stats.total_orders,
            'faults_occurred': len(factory.fault_system.active_faults)
        }
        
        print(f"✅ 仿真完成:")
        print(f"   仿真时间: {sim_time_elapsed:.1f}s")
        print(f"   实际时间: {real_time_used:.2f}s")
        print(f"   速度比率: {speed_ratio:.1f}x 实时")
        print(f"   内存使用: {final_resources['memory_mb']:.1f}MB")
        print(f"   生成订单: {results['orders_generated']}")
        print(f"   发生故障: {results['faults_occurred']}")
        
        return results
    
    def test_scalability(self) -> List[Dict]:
        """测试系统可扩展性"""
        print("\n📈 可扩展性测试")
        print("=" * 60)
        
        test_durations = [60, 300, 600, 1800]  # 1分钟到30分钟
        scalability_results = []
        
        for duration in test_durations:
            print(f"\n测试 {duration}秒 仿真...")
            
            # 强制垃圾回收
            gc.collect()
            
            result = self.test_simulation_speed(duration)
            result['test_duration'] = duration
            scalability_results.append(result)
            
            # 检查性能退化
            if len(scalability_results) > 1:
                prev_speed = scalability_results[-2]['speed_ratio']
                curr_speed = result['speed_ratio']
                speed_change = (curr_speed - prev_speed) / prev_speed * 100
                
                print(f"   性能变化: {speed_change:+.1f}% (相比上一级别)")
                
                if speed_change < -10:
                    print("   ⚠️ 发现性能退化")
                else:
                    print("   ✅ 性能稳定")
        
        return scalability_results
    
    def test_memory_usage(self) -> Dict:
        """测试内存使用模式"""
        print("\n🧠 内存使用测试")
        print("=" * 60)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        memory_snapshots = []
        test_points = [0, 60, 120, 300, 600]  # 不同时间点
        
        for target_time in test_points:
            if target_time > 0:
                factory.run(until=target_time)
            
            resources = self.measure_system_resources()
            memory_snapshots.append({
                'sim_time': factory.env.now,
                'memory_mb': resources['memory_mb'],
                'orders': factory.kpi_calculator.stats.total_orders,
                'active_orders': len(factory.kpi_calculator.active_orders),
                'active_faults': len(factory.fault_system.active_faults)
            })
            
            print(f"时间 {target_time:3d}s: 内存 {resources['memory_mb']:6.1f}MB | "
                  f"订单 {factory.kpi_calculator.stats.total_orders:3d} | "
                  f"故障 {len(factory.fault_system.active_faults):2d}")
        
        # 分析内存增长趋势
        initial_memory = memory_snapshots[0]['memory_mb']
        final_memory = memory_snapshots[-1]['memory_mb']
        memory_growth = final_memory - initial_memory
        
        print(f"\n📊 内存分析:")
        print(f"   初始内存: {initial_memory:.1f}MB")
        print(f"   最终内存: {final_memory:.1f}MB")
        print(f"   内存增长: {memory_growth:.1f}MB")
        print(f"   增长率: {memory_growth/initial_memory*100:.1f}%")
        
        if memory_growth / initial_memory > 0.5:
            print("   ⚠️ 内存增长较快，可能存在内存泄漏")
        else:
            print("   ✅ 内存使用合理")
        
        return {
            'snapshots': memory_snapshots,
            'growth_mb': memory_growth,
            'growth_rate': memory_growth / initial_memory
        }
    
    def test_event_processing_rate(self) -> Dict:
        """测试事件处理速率"""
        print("\n⚡ 事件处理速率测试")
        print("=" * 60)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        # 运行较长时间收集足够的事件
        test_duration = 300
        start_time = time.time()
        
        factory.run(until=test_duration)
        
        end_time = time.time()
        real_time = end_time - start_time
        
        # 计算各种事件速率
        total_orders = factory.kpi_calculator.stats.total_orders
        
        # 估算其他事件数量
        # 设备状态发布: 6设备 * (test_duration/10) 次
        device_status_events = 6 * (test_duration // 10)
        
        # KPI更新: test_duration/10 次
        kpi_events = test_duration // 10
        
        # 工厂状态: test_duration/30 次  
        factory_status_events = test_duration // 30
        
        # 故障报警事件 (估算)
        fault_alert_events = len(factory.fault_system.active_faults) * (test_duration // 5)
        
        total_events = (total_orders + device_status_events + 
                       kpi_events + factory_status_events + fault_alert_events)
        
        events_per_second = total_events / real_time
        
        results = {
            'test_duration': test_duration,
            'real_time': real_time,
            'total_events': total_events,
            'events_per_second': events_per_second,
            'order_events': total_orders,
            'device_status_events': device_status_events,
            'kpi_events': kpi_events,
            'factory_status_events': factory_status_events,
            'fault_alert_events': fault_alert_events
        }
        
        print(f"✅ 事件处理分析:")
        print(f"   测试时长: {real_time:.2f}s")
        print(f"   总事件数: {total_events}")
        print(f"   处理速率: {events_per_second:.1f} 事件/秒")
        print(f"   订单事件: {total_orders}")
        print(f"   状态更新: {device_status_events}")
        print(f"   故障报警: {fault_alert_events}")
        
        return results
    
    def test_state_space_performance(self) -> Dict:
        """测试状态空间管理性能"""
        print("\n🌐 状态空间性能测试")
        print("=" * 60)
        
        factory = Factory(MOCK_LAYOUT_CONFIG, self.mqtt_client)
        
        # 运行一段时间让状态空间充分发展
        test_duration = 300
        start_time = time.time()
        
        factory.run(until=test_duration)
        
        end_time = time.time()
        
        # 获取状态空间统计
        state_stats = factory.get_state_space_statistics()
        
        results = {
            'test_duration': test_duration,
            'real_time': end_time - start_time,
            'unique_states': state_stats['unique_states_observed'],
            'total_transitions': state_stats['total_state_transitions'],
            'state_computation_time': state_stats.get('total_computation_time', 0),
            'state_space_size': state_stats['theoretical_state_space_size']
        }
        
        states_per_second = results['unique_states'] / results['real_time']
        transitions_per_second = results['total_transitions'] / results['real_time']
        
        print(f"✅ 状态空间分析:")
        print(f"   观察到的唯一状态: {results['unique_states']:,}")
        print(f"   状态转换次数: {results['total_transitions']:,}")
        print(f"   状态生成速率: {states_per_second:.1f} 状态/秒")
        print(f"   转换速率: {transitions_per_second:.1f} 转换/秒")
        print(f"   理论状态空间: {results['state_space_size']}")
        
        coverage_percentage = results['unique_states'] / results['state_space_size'] * 100
        print(f"   状态空间覆盖: {coverage_percentage:.8f}%")
        
        return results
    
    def run_complete_benchmark(self) -> Dict:
        """运行完整的性能基准测试"""
        print("🚀 SUPCON 系统性能基准测试")
        print("=" * 80)
        print("这将测试系统在不同负载下的性能表现...")
        print()
        
        benchmark_results = {}
        
        # 1. 基础仿真速度测试
        print("【第1项】基础仿真速度测试")
        benchmark_results['simulation_speed'] = self.test_simulation_speed(300)
        
        # 2. 可扩展性测试
        print("\n【第2项】可扩展性测试")
        benchmark_results['scalability'] = self.test_scalability()
        
        # 3. 内存使用测试
        print("\n【第3项】内存使用测试")
        benchmark_results['memory_usage'] = self.test_memory_usage()
        
        # 4. 事件处理速率测试
        print("\n【第4项】事件处理速率测试")
        benchmark_results['event_processing'] = self.test_event_processing_rate()
        
        # 5. 状态空间性能测试
        print("\n【第5项】状态空间性能测试")
        benchmark_results['state_space'] = self.test_state_space_performance()
        
        # 6. 生成性能报告
        self.generate_performance_report(benchmark_results)
        
        return benchmark_results
    
    def generate_performance_report(self, results: Dict):
        """生成性能报告"""
        print("\n" + "=" * 80)
        print("📊 系统性能基准报告")
        print("=" * 80)
        
        # 基础性能
        base_speed = results['simulation_speed']['speed_ratio']
        base_memory = results['simulation_speed']['final_resources']['memory_mb']
        
        print(f"🎯 核心性能指标:")
        print(f"   仿真速度: {base_speed:.1f}x 实时")
        print(f"   内存使用: {base_memory:.1f}MB")
        print(f"   事件处理: {results['event_processing']['events_per_second']:.1f} 事件/秒")
        
        # 可扩展性评估
        scalability = results['scalability']
        speed_changes = []
        for i in range(1, len(scalability)):
            prev_speed = scalability[i-1]['speed_ratio']
            curr_speed = scalability[i]['speed_ratio']
            change = (curr_speed - prev_speed) / prev_speed * 100
            speed_changes.append(change)
        
        avg_speed_change = sum(speed_changes) / len(speed_changes) if speed_changes else 0
        
        print(f"\n📈 可扩展性评估:")
        print(f"   平均性能变化: {avg_speed_change:+.1f}% (每级别)")
        if avg_speed_change > -5:
            print(f"   评级: 优秀 ✅")
        elif avg_speed_change > -15:
            print(f"   评级: 良好 🟡")
        else:
            print(f"   评级: 需要优化 🔴")
        
        # 内存效率
        memory_growth_rate = results['memory_usage']['growth_rate']
        print(f"\n🧠 内存效率:")
        print(f"   内存增长率: {memory_growth_rate*100:.1f}%")
        if memory_growth_rate < 0.2:
            print(f"   评级: 优秀 ✅")
        elif memory_growth_rate < 0.5:
            print(f"   评级: 良好 🟡")
        else:
            print(f"   评级: 需要优化 🔴")
        
        # 状态空间处理
        state_stats = results['state_space']
        states_per_sec = state_stats['unique_states'] / state_stats['real_time']
        
        print(f"\n🌐 状态空间处理:")
        print(f"   状态生成速率: {states_per_sec:.1f} 状态/秒")
        print(f"   状态转换效率: {state_stats['total_transitions']:,} 转换")
        
        # 综合评分
        speed_score = min(100, base_speed / 1000 * 100)  # 基于1000x为满分
        memory_score = max(0, 100 - memory_growth_rate * 100)
        event_score = min(100, results['event_processing']['events_per_second'] / 100 * 100)
        
        overall_score = (speed_score + memory_score + event_score) / 3
        
        print(f"\n🏆 综合性能评分:")
        print(f"   仿真速度: {speed_score:.1f}/100")
        print(f"   内存效率: {memory_score:.1f}/100")
        print(f"   事件处理: {event_score:.1f}/100")
        print(f"   总体得分: {overall_score:.1f}/100")
        
        if overall_score >= 80:
            print(f"   系统评级: 优秀 🎉")
        elif overall_score >= 60:
            print(f"   系统评级: 良好 👍")
        else:
            print(f"   系统评级: 需要优化 💪")
        
        print(f"\n💡 系统已准备好处理大规模AI Agent开发和测试工作负载!")

def main():
    """主程序"""
    print("⚡ SUPCON 系统性能基准测试")
    print("这将全面测试系统的性能表现和资源使用情况")
    print("测试可能需要几分钟时间...")
    print()
    
    try:
        benchmark = PerformanceBenchmark()
        results = benchmark.run_complete_benchmark()
        return True
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 