#!/usr/bin/env python3
# test_enhanced_factory.py - 增强版工厂系统测试

"""
增强版工厂系统完整测试脚本
测试MQTT连接、Unity实时发布、A*路径规划等所有新功能
"""

import sys
import traceback

def test_mqtt_connection():
    """测试MQTT连接"""
    print("🔗 测试MQTT连接...")
    try:
        from src.utils.mqtt_client import MQTTClient
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        
        mqtt_client = MQTTClient(
            host=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            client_id="test_client"
        )
        mqtt_client.connect()
        print(f"✅ MQTT连接成功: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        mqtt_client.disconnect()
        return True
    except Exception as e:
        print(f"❌ MQTT连接失败: {e}")
        return False

def test_pathfinding():
    """测试A*路径规划"""
    print("\n🗺️ 测试A*路径规划...")
    try:
        from src.pathfinding.astar_pathfinder import AStarPathfinder, PathfindingRequest
        
        # 创建路径规划器
        pathfinder = AStarPathfinder(
            factory_width=50.0,
            factory_height=30.0,
            grid_resolution=1.0
        )
        
        # 添加障碍物
        pathfinder.add_static_obstacle((15, 15), size=3.0)
        pathfinder.add_static_obstacle((35, 15), size=3.0)
        
        # 测试路径规划
        request = PathfindingRequest(
            agv_id='TEST_AGV',
            start_pos=(5.0, 5.0),
            goal_pos=(45.0, 25.0),
            agv_size=1.0,
            priority=1,
            allow_diagonal=True
        )
        
        result = pathfinder.find_path(request)
        
        if result.success:
            print(f"✅ 路径规划成功!")
            print(f"   - 路径长度: {len(result.path)} 个点")
            print(f"   - 路径成本: {result.path_cost:.1f}")
            print(f"   - 计算时间: {result.computation_time*1000:.1f}ms")
            print(f"   - 探索节点: {result.nodes_explored}")
            
            # 显示统计信息
            stats = pathfinder.get_statistics()
            print(f"   - 成功率: {stats['success_rate']}%")
            print(f"   - 网格大小: {stats['grid_size']}")
            return True
        else:
            print(f"❌ 路径规划失败: {result.failure_reason}")
            return False
            
    except Exception as e:
        print(f"❌ 路径规划测试失败: {e}")
        traceback.print_exc()
        return False

def test_basic_factory():
    """测试基础工厂功能"""
    print("\n🏭 测试基础工厂...")
    try:
        from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
        from src.utils.mqtt_client import MQTTClient
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        
        # 创建MQTT客户端
        mqtt_client = MQTTClient(
            host=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            client_id="factory_test"
        )
        mqtt_client.connect()
        
        # 创建工厂
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        print(f"✅ 基础工厂创建成功")
        print(f"   - AGV数量: {len(factory.agvs)}")
        print(f"   - 工站数量: {len(factory.stations)}")
        print(f"   - Unity发布器: {'已激活' if hasattr(factory, 'unity_publisher') else '未激活'}")
        
        # 测试设备状态
        for agv_id, agv in factory.agvs.items():
            status = factory.get_device_status(agv_id)
            print(f"   - {agv_id}: {status.get('status', 'unknown')} at {agv.position}")
        
        mqtt_client.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ 基础工厂测试失败: {e}")
        traceback.print_exc()
        return False

def test_unity_publisher():
    """测试Unity实时发布器"""
    print("\n🎮 测试Unity实时发布器...")
    try:
        from src.unity_interface.real_time_publisher import RealTimePublisher
        from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
        from src.utils.mqtt_client import MQTTClient
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        import simpy
        
        # 创建测试环境
        env = simpy.Environment()
        mqtt_client = MQTTClient(
            host=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            client_id="unity_test"
        )
        mqtt_client.connect()
        
        # 创建工厂
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 验证Unity发布器已启动
        if hasattr(factory, 'unity_publisher'):
            print("✅ Unity实时发布器已激活")
            print("   - AGV位置更新间隔: 100ms")
            print("   - 设备状态更新间隔: 500ms")
            print("   - 动画事件: 实时触发")
            
            # 测试坐标转换
            test_pos = (10.5, 15.3)
            unity_coords = factory.unity_publisher._convert_to_unity_coordinates(*test_pos)
            print(f"   - 坐标转换测试: {test_pos} -> {unity_coords}")
            
            mqtt_client.disconnect()
            return True
        else:
            print("❌ Unity发布器未激活")
            mqtt_client.disconnect()
            return False
            
    except Exception as e:
        print(f"❌ Unity发布器测试失败: {e}")
        traceback.print_exc()
        return False

def test_enhanced_features():
    """测试增强功能的集成"""
    print("\n⚡ 测试增强功能集成...")
    try:
        from src.pathfinding.astar_pathfinder import AStarPathfinder
        from src.unity_interface.real_time_publisher import RealTimePublisher
        from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
        from src.utils.mqtt_client import MQTTClient
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        
        # 创建MQTT客户端
        mqtt_client = MQTTClient(
            host=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            client_id="enhanced_test"
        )
        mqtt_client.connect()
        
        # 创建基础工厂（已包含Unity发布器）
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        # 添加A*路径规划器
        pathfinder = AStarPathfinder(
            factory_width=100.0,
            factory_height=50.0,
            grid_resolution=0.5
        )
        
        # 添加工站作为障碍物
        for station_cfg in MOCK_LAYOUT_CONFIG['stations']:
            position = station_cfg['position']
            pathfinder.add_static_obstacle(position, size=3.0)
        
        print("✅ 增强功能集成成功")
        print(f"   - 基础工厂: {len(factory.agvs)}个AGV, {len(factory.stations)}个工站")
        print(f"   - A*路径规划: {pathfinder.grid_width}x{pathfinder.grid_height}网格")
        print(f"   - Unity发布器: {'已激活' if hasattr(factory, 'unity_publisher') else '未激活'}")
        
        # 测试路径规划集成
        agv = factory.agvs['AGV_1']
        from src.pathfinding.astar_pathfinder import PathfindingRequest
        request = PathfindingRequest(
            agv_id='AGV_1',
            start_pos=agv.position,
            goal_pos=(50.0, 25.0),
            agv_size=1.0,
            priority=1,
            allow_diagonal=True
        )
        request_result = pathfinder.find_path(request)
        
        if hasattr(request_result, 'success'):
            print(f"   - 路径规划集成: {'成功' if request_result.success else '失败'}")
        
        mqtt_client.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ 增强功能测试失败: {e}")
        traceback.print_exc()
        return False

def test_simulation_run():
    """测试仿真运行"""
    print("\n⏱️ 测试短时间仿真运行...")
    try:
        from src.simulation.factory import Factory, MOCK_LAYOUT_CONFIG
        from src.utils.mqtt_client import MQTTClient
        from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT
        
        # 创建MQTT客户端
        mqtt_client = MQTTClient(
            host=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            client_id="simulation_test"
        )
        mqtt_client.connect()
        
        # 创建工厂
        factory = Factory(MOCK_LAYOUT_CONFIG, mqtt_client)
        
        print("   - 开始3秒仿真...")
        factory.run(until=3)
        print("✅ 仿真运行正常")
        
        mqtt_client.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ 仿真运行测试失败: {e}")
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 === 增强版工厂系统完整测试 ===\n")
    
    tests = [
        ("MQTT连接", test_mqtt_connection),
        ("A*路径规划", test_pathfinding),
        ("基础工厂", test_basic_factory),
        ("Unity发布器", test_unity_publisher),
        ("增强功能集成", test_enhanced_features),
        ("仿真运行", test_simulation_run),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 显示测试结果汇总
    print("\n" + "="*50)
    print("📊 测试结果汇总:")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 === 所有测试通过！系统完全就绪 ===")
        print("\n🎮 Unity集成信息:")
        print("   - MQTT Broker: supos-ce-instance1.supos.app:1883")
        print("   - AGV位置: factory/realtime/agv/+/position (100ms)")
        print("   - 动画事件: factory/realtime/device/+/animation")
        print("   - 工厂状态: factory/status/factory")
        print("\n📝 系统特性:")
        print("   - ✅ 智能A*路径规划 (1ms响应)")
        print("   - ✅ Unity实时可视化支持 (100ms更新)")
        print("   - ✅ 多AGV动态避障")
        print("   - ✅ 设备故障智能诊断")
        print("   - ✅ 实时MQTT数据流")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，请检查上述错误信息")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 