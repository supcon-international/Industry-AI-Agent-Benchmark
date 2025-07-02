#!/usr/bin/env python3
"""
SUPCON 工厂仿真系统 - 测试套件菜单
让您轻松选择和运行各种测试
"""

import sys
import os
import subprocess
import time

def show_menu():
    """显示测试菜单"""
    print("🧪 SUPCON 工厂仿真系统 - 测试套件")
    print("=" * 60)
    print("请选择要运行的测试:")
    print()
    print("📋 基础功能测试:")
    print("  1. 工厂仿真基础测试 (test_factory_simulation.py)")
    print("     验证所有核心系统功能是否正常工作")
    print()
    print("🎮 交互体验:")
    print("  2. 交互式工厂体验 (test_interactive_factory.py)")
    print("     亲自体验Agent开发者的工作流程")
    print()
    print("🧠 智能诊断演示:")
    print("  3. 故障诊断系统演示 (test_fault_diagnosis_demo.py)")
    print("     展示改进后的智能故障诊断功能 (推荐！)")
    print()
    print("⚡ 性能评估:")
    print("  4. 性能基准测试 (test_performance_benchmark.py)")
    print("     评估系统性能和资源使用情况")
    print()
    print("🚀 完整测试:")
    print("  5. 运行所有自动化测试 (1, 3, 4)")
    print("     完整的系统验证 (不包括交互式测试)")
    print()
    print("📊 系统信息:")
    print("  6. 显示系统状态和配置信息")
    print()
    print("  0. 退出")
    print()

def run_test_script(script_name: str, description: str):
    """运行指定的测试脚本"""
    print(f"\n🚀 启动: {description}")
    print("=" * 60)
    
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    
    if not os.path.exists(script_path):
        print(f"❌ 测试脚本不存在: {script_path}")
        return False
    
    try:
        # 运行测试脚本
        start_time = time.time()
        result = subprocess.run([sys.executable, script_path], 
                              capture_output=False, 
                              text=True)
        end_time = time.time()
        
        duration = end_time - start_time
        
        print(f"\n{'='*60}")
        if result.returncode == 0:
            print(f"✅ 测试完成! 耗时: {duration:.2f}秒")
            return True
        else:
            print(f"❌ 测试失败! 返回码: {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ 运行测试时出错: {e}")
        return False

def run_all_automated_tests():
    """运行所有自动化测试"""
    print(f"\n🚀 运行完整自动化测试套件")
    print("=" * 60)
    print("这将依次运行基础功能测试、故障系统测试和性能基准测试")
    print("预计总时间: 5-10分钟")
    print()
    
    tests = [
        ("test_factory_simulation.py", "基础功能测试"),
        ("test_fault_diagnosis_demo.py", "故障诊断系统演示"),
        ("test_performance_benchmark.py", "性能基准测试")
    ]
    
    results = []
    total_start_time = time.time()
    
    for script, description in tests:
        print(f"\n📋 正在运行: {description}")
        print("-" * 40)
        
        success = run_test_script(script, description)
        results.append((description, success))
        
        if success:
            print(f"✅ {description} - 通过")
        else:
            print(f"❌ {description} - 失败")
        
        print()
        time.sleep(1)  # 短暂休息
    
    total_end_time = time.time()
    total_duration = total_end_time - total_start_time
    
    # 汇总结果
    print("=" * 60)
    print("📊 测试套件执行结果")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for description, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {description}: {status}")
    
    print(f"\n🏆 总体结果: {passed}/{total} 测试通过")
    print(f"⏱️ 总执行时间: {total_duration:.2f}秒")
    
    if passed == total:
        print("\n🎉 所有测试通过! 系统运行正常，可以开始Agent开发!")
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，请检查系统配置")
    
    return passed == total

def show_system_info():
    """显示系统信息"""
    print(f"\n💻 SUPCON 工厂仿真系统信息")
    print("=" * 60)
    
    # Python环境信息
    print(f"Python版本: {sys.version}")
    print(f"Python路径: {sys.executable}")
    
    # 工作目录
    current_dir = os.getcwd()
    print(f"当前目录: {current_dir}")
    
    # 测试文件检查
    test_dir = os.path.dirname(__file__)
    print(f"测试目录: {test_dir}")
    
    test_files = [
        "test_factory_simulation.py",
        "test_interactive_factory.py", 
        "test_fault_diagnosis_demo.py",
        "test_performance_benchmark.py"
    ]
    
    print(f"\n📁 测试文件状态:")
    for test_file in test_files:
        file_path = os.path.join(test_dir, test_file)
        exists = os.path.exists(file_path)
        status = "✅ 存在" if exists else "❌ 缺失"
        print(f"  {test_file}: {status}")
    
    # 系统依赖检查
    print(f"\n📦 关键依赖检查:")
    dependencies = [
        ("simpy", "离散事件仿真引擎"),
        ("pydantic", "数据验证"),
        ("paho-mqtt", "MQTT通信"),
        ("psutil", "系统资源监控")
    ]
    
    for dep_name, dep_desc in dependencies:
        try:
            __import__(dep_name)
            print(f"  {dep_name} ({dep_desc}): ✅ 已安装")
        except ImportError:
            print(f"  {dep_name} ({dep_desc}): ❌ 未安装")
    
    # 配置信息
    print(f"\n⚙️ 系统配置:")
    
    # 尝试导入配置
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        print(f"  MQTT Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    except Exception as e:
        print(f"  MQTT配置: ❌ 无法加载 ({e})")
    
    # 项目结构检查
    project_root = os.path.dirname(test_dir)
    key_directories = ["src", "config", "docs", "test"]
    
    print(f"\n🏗️ 项目结构:")
    for dir_name in key_directories:
        dir_path = os.path.join(project_root, dir_name)
        exists = os.path.exists(dir_path)
        status = "✅ 存在" if exists else "❌ 缺失"
        print(f"  {dir_name}/: {status}")

def main():
    """主程序"""
    while True:
        show_menu()
        
        try:
            choice = input("请选择操作 (0-6): ").strip()
            
            if choice == "1":
                run_test_script("test_factory_simulation.py", "工厂仿真基础测试")
            elif choice == "2":
                run_test_script("test_interactive_factory.py", "交互式工厂体验")
            elif choice == "3":
                run_test_script("test_fault_diagnosis_demo.py", "故障诊断系统演示")
            elif choice == "4":
                run_test_script("test_performance_benchmark.py", "性能基准测试")
            elif choice == "5":
                run_all_automated_tests()
            elif choice == "6":
                show_system_info()
            elif choice == "0":
                print("\n👋 感谢使用SUPCON工厂仿真系统测试套件!")
                print("💡 现在您可以开始开发自己的AI Agent了!")
                break
            else:
                print("❌ 无效选择，请重试")
                
            if choice != "0":
                input("\n按回车键继续...")
                print("\n" * 2)  # 清屏效果
                
        except KeyboardInterrupt:
            print("\n\n👋 用户中断，退出程序")
            break
        except Exception as e:
            print(f"❌ 操作错误: {e}")
            input("按回车键继续...")

if __name__ == "__main__":
    main() 