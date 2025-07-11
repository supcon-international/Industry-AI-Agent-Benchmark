#!/usr/bin/env python3
"""
交互式工厂仿真测试
让您自己体验Agent开发的感觉！
"""

import sys
import os
import time
import threading
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.simulation.factory import Factory
from src.utils.config_loader import load_factory_config
from src.utils.mqtt_client import MQTTClient
from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from src.game_logic.fault_system import FaultType

class InteractiveFactoryAgent:
    """一个简单的交互式Agent，让用户手动控制"""
    
    def __init__(self, factory: Factory):
        self.factory = factory
        self.running = True
        
    def show_status(self):
        """显示当前工厂状态"""
        print("\n" + "="*60)
        print(f"🏭 工厂状态总览 [仿真时间: {self.factory.env.now:.1f}s]")
        print("="*60)
        
        # 显示订单状态
        active_orders = len(self.factory.kpi_calculator.active_orders)
        completed_orders = self.factory.kpi_calculator.stats.completed_orders
        total_orders = self.factory.kpi_calculator.stats.total_orders
        
        print(f"📋 订单状态:")
        print(f"   - 总订单数: {total_orders}")
        print(f"   - 活跃订单: {active_orders}")
        print(f"   - 已完成: {completed_orders}")
        
        # 显示故障状态
        fault_stats = self.factory.fault_system.get_fault_stats()
        print(f"\n⚠️ 故障状态:")
        print(f"   - 活跃故障: {fault_stats['active_faults']}")
        
        if fault_stats['fault_devices']:
            print(f"   - 故障设备:")
            for device_id in fault_stats['fault_devices']:
                fault = self.factory.fault_system.active_faults[device_id]
                duration = self.factory.env.now - fault.start_time
                print(f"     * {device_id}: {fault.symptom} (持续{duration:.1f}s)")
                print(f"       诊断提示: 检查故障诊断手册了解可能原因")
        
        # 显示设备状态
        print(f"\n🔧 设备状态:")
        for station_id, station in self.factory.stations.items():
            status = self.factory.get_device_status(station_id)
            buffer_info = f"缓冲区: {status['buffer_level']}/3"
            fault_info = f"故障: {status['symptom']}" if status['symptom'] else "正常"
            print(f"   - {station_id}: {station.status.value} | {buffer_info} | {fault_info}")
            
        for agv_id, agv in self.factory.agvs.items():
            status = self.factory.get_device_status(agv_id)
            pos_info = f"位置: {agv.position}"
            battery_info = f"电量: {agv.battery_level}%"
            fault_info = f"故障: {status['symptom']}" if status['symptom'] else "正常"
            print(f"   - {agv_id}: {agv.status.value} | {pos_info} | {battery_info} | {fault_info}")
        
        # 显示KPI得分
        try:
            kpi_data = self.factory.kpi_calculator.get_final_score()
            print(f"\n📊 当前KPI得分:")
            print(f"   - 生产效率: {kpi_data['efficiency_score']:.1f}/40")
            print(f"   - 成本控制: {kpi_data['cost_score']:.1f}/30") 
            print(f"   - 鲁棒性: {kpi_data['robustness_score']:.1f}/30")
            print(f"   - 总分: {kpi_data['total_score']:.1f}/100")
        except:
            print(f"\n📊 KPI数据尚未准备就绪")

    def show_menu(self):
        """显示操作菜单"""
        print(f"\n🎮 操作菜单:")
        print(f"   1. 查看工厂状态")
        print(f"   2. 手动注入故障")
        print(f"   3. 诊断并修复故障")
        print(f"   4. 运行仿真一段时间")
        print(f"   5. 查看故障诊断手册")
        print(f"   6. 查看所有MQTT主题")
        print(f"   0. 退出")
        
    def inject_fault_menu(self):
        """故障注入菜单"""
        print(f"\n💥 手动故障注入:")
        print(f"   选择目标设备:")
        devices = list(self.factory.stations.keys()) + list(self.factory.agvs.keys())
        for i, device in enumerate(devices, 1):
            print(f"   {i}. {device}")
        print(f"   0. 返回")
        
        try:
            choice = int(input("\n请选择设备 (0-{}): ".format(len(devices))))
            if choice == 0:
                return
            if 1 <= choice <= len(devices):
                device_id = devices[choice - 1]
                
                # 选择故障类型
                print(f"\n选择故障类型:")
                fault_types = list(FaultType)
                for i, fault_type in enumerate(fault_types, 1):
                    print(f"   {i}. {fault_type.value}")
                
                fault_choice = int(input(f"\n请选择故障类型 (1-{len(fault_types)}): "))
                if 1 <= fault_choice <= len(fault_types):
                    fault_type = fault_types[fault_choice - 1]
                    self.factory.fault_system.inject_random_fault(device_id, fault_type)
                    print(f"✅ 已在 {device_id} 注入 {fault_type.value} 故障")
        except (ValueError, IndexError):
            print("❌ 无效输入")
    
    def repair_fault_menu(self):
        """故障修复菜单"""
        active_faults = self.factory.fault_system.active_faults
        if not active_faults:
            print("🎉 当前没有活跃故障!")
            return
            
        print(f"\n🔧 故障诊断与修复:")
        fault_list = list(active_faults.items())
        
        for i, (device_id, fault) in enumerate(fault_list, 1):
            duration = self.factory.env.now - fault.start_time
            print(f"   {i}. {device_id}: {fault.symptom} (持续{duration:.1f}s)")
        print(f"   0. 返回")
        
        try:
            choice = int(input(f"\n选择要修复的设备 (0-{len(fault_list)}): "))
            if choice == 0:
                return
            if 1 <= choice <= len(fault_list):
                device_id, fault = fault_list[choice - 1]
                
                print(f"\n设备: {device_id}")
                print(f"症状: {fault.symptom}")
                print(f"请输入您的诊断和修复命令:")
                print(f"常见命令: replace_bearing, tighten_bolts, replace_tool, recalibrate,")
                print(f"         reroute_agv, reboot_device, force_charge, optimize_schedule,")
                print(f"         reduce_frequency, add_lubricant")
                
                repair_command = input("\n修复命令: ").strip()
                if repair_command:
                    success, repair_time = self.factory.handle_maintenance_request(device_id, repair_command)
                    if success:
                        print(f"✅ 诊断正确! 修复时间: {repair_time:.1f}s")
                    else:
                        print(f"❌ 诊断错误! 惩罚修复时间: {repair_time:.1f}s")
                        print(f"💡 正确的命令应该是: {fault.correct_repair_command}")
        except (ValueError, IndexError):
            print("❌ 无效输入")
    
    def show_fault_manual(self):
        """显示故障诊断手册"""
        manual_content = """
📖 故障诊断手册
================

1. 主轴振动异常
   可能原因: 
   - bearing_wear (轴承磨损) → 修复: replace_bearing
   - bolt_loose (螺栓松动) → 修复: tighten_bolts

2. 加工精度下降
   可能原因:
   - tool_dulling (刀具钝化) → 修复: replace_tool  
   - calibration_drift (校准偏移) → 修复: recalibrate

3. AGV路径阻塞
   可能原因:
   - temporary_obstacle (临时障碍) → 修复: reroute_agv
   - positioning_failure (定位故障) → 修复: reboot_device

4. AGV电量突降  
   可能原因:
   - battery_aging (电池老化) → 修复: force_charge
   - high_load_task (高负载任务) → 修复: optimize_schedule

5. 效率异常降低
   可能原因:
   - software_overheating (软件过热) → 修复: reduce_frequency
   - insufficient_lubricant (润滑不足) → 修复: add_lubricant

💡 提示: 正确诊断获得基础修复时间，错误诊断会有惩罚!
        """
        print(manual_content)
    
    def show_mqtt_topics(self):
        """显示MQTT主题信息"""
        topics_info = """
📡 MQTT主题列表
===============

基础设备状态 (每10秒发布):
- factory/station/StationA/status
- factory/station/StationB/status  
- factory/station/StationC/status
- factory/station/QualityCheck/status
- factory/resource/AGV_1/status
- factory/resource/AGV_2/status

系统监控 (定期发布):
- factory/status (每30秒) - 工厂整体状态
- factory/kpi/update (每10秒) - KPI更新

业务事件 (事件驱动):
- factory/orders/new (30-60秒随机) - 新订单
- factory/alerts/{device_id} (每5秒，有故障时) - 故障报警

💡 Agent开发提示:
1. 订阅 factory/alerts/* 快速发现故障
2. 订阅 factory/orders/new 获取生产任务
3. 订阅设备状态主题监控运行情况
4. 发布命令到 factory/commands/maintenance 进行维修
        """
        print(topics_info)
    
    def run_simulation(self):
        """运行仿真一段时间"""
        try:
            duration = float(input("\n请输入运行时间(秒): "))
            if duration > 0:
                print(f"🚀 运行仿真 {duration} 秒...")
                start_time = self.factory.env.now
                self.factory.run(until=int(start_time + duration))
                print(f"✅ 仿真完成! 当前仿真时间: {self.factory.env.now:.1f}s")
        except ValueError:
            print("❌ 请输入有效的数字")

def main():
    """主程序入口"""
    print("🎮 SUPCON 智能制造仿真 - 交互式体验")
    print("=" * 60)
    print("欢迎来到工厂仿真世界！您现在是一名AI Agent开发者")
    print("目标: 通过监控MQTT消息并发送控制命令来优化工厂运行")
    print("挑战: 处理故障、优化生产、控制成本")
    print("=" * 60)
    
    try:
        # 初始化工厂
        print("🏭 正在初始化工厂...")
        mqtt_client = MQTTClient(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT)
        factory = Factory(load_factory_config(), mqtt_client)
        agent = InteractiveFactoryAgent(factory)
        
        print("✅ 工厂初始化完成!")
        print("💡 提示: 选择选项4先运行一段时间，让系统生成订单和故障")
        
        # 主交互循环
        while agent.running:
            agent.show_menu()
            try:
                choice = input("\n请选择操作 (0-6): ").strip()
                
                if choice == "1":
                    agent.show_status()
                elif choice == "2":
                    agent.inject_fault_menu()
                elif choice == "3":
                    agent.repair_fault_menu()
                elif choice == "4":
                    agent.run_simulation()
                elif choice == "5":
                    agent.show_fault_manual()
                elif choice == "6":
                    agent.show_mqtt_topics()
                elif choice == "0":
                    print("👋 感谢体验SUPCON智能制造仿真!")
                    print("💡 现在您已经了解了AI Agent需要处理的挑战，")
                    print("   可以开始开发自己的智能Agent了!")
                    agent.running = False
                else:
                    print("❌ 无效选择，请重试")
                    
                if choice != "0":
                    input("\n按回车键继续...")
                    
            except KeyboardInterrupt:
                print("\n\n👋 用户中断，退出程序")
                agent.running = False
            except Exception as e:
                print(f"❌ 操作错误: {e}")
                input("按回车键继续...")
        
    except Exception as e:
        print(f"❌ 程序启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 