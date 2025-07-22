import json
import threading
import time
from src.simulation.factory_multi import Factory
from src.utils.mqtt_client import MQTTClient
from config.topics import AGENT_COMMANDS_TOPIC, RESULT_TOPIC
from src.game_logic.fault_system import FaultType
from src.utils.topic_manager import TopicManager
from src.simulation.entities.product import Product

# 全局变量控制自动上料
auto_feed_threads = {}  # {line_id: {"thread": thread, "active": bool}}

def auto_feed_station_a(factory: Factory, line_id: str, interval: float = 2.0, product_types=None):
    """自动连续添加原材料到 StationA 的线程函数
    
    Args:
        factory: 工厂实例
        line_id: 生产线ID
        interval: 上料间隔时间（秒）
        product_types: 要生产的产品类型列表，如 ['P1'], ['P2', 'P3'] 或 None（全部类型）
    """
    global auto_feed_threads
    product_count = 0
    
    # 如果没有指定产品类型，则循环所有类型
    if product_types is None:
        product_types = ['P1', 'P2', 'P3']
    
    type_index = 0
    
    while auto_feed_threads.get(line_id, {}).get("active", False):
        product_count += 1
        
        # 循环选择产品类型
        product_type = product_types[type_index]
        type_index = (type_index + 1) % len(product_types)
        
        # 创建 Product 对象
        order_id = f"auto_order_{line_id}_{product_count}"
        product = Product(product_type, order_id)
        
        # 直接向 StationA 的 buffer 添加产品
        try:
            station_a = factory.lines[line_id].stations["StationA"]
            # 检查 buffer 是否已满
            if len(station_a.buffer.items) < station_a.buffer.capacity:
                station_a.buffer.put(product)
                product.add_history(factory.env.now, f"Auto-fed to StationA in {line_id}")
                print(f"{factory.env.now:.2f} ✅ 添加产品 {product.id} (类型: {product_type}) 到 {line_id} StationA")
                # 发布状态更新
                station_a.publish_status(f"Auto-fed product {product.id} added to buffer")
            else:
                print(f" {factory.env.now:.2f}⏸️  {line_id} StationA 的 buffer 已满，等待下次尝试")
        except Exception as e:
            print(f"[自动上料] ❌ 错误: {e}")
        
        time.sleep(interval)
    
    print(f"[自动上料] {line_id} 的自动上料已停止")

def get_device_map(factory: Factory) -> dict:
    """Creates a mapping from simple codes to full device IDs."""
    device_map = {
        "R": "RawMaterial", "W": "Warehouse",
        "A": "StationA", "B": "StationB", "C": "StationC", "Q": "QualityCheck",
        "C1": "Conveyor_AB", "C2": "Conveyor_BC", "C3": "Conveyor_CQ",
        "1": "AGV_1", "2": "AGV_2"
    }
    return device_map

def menu_input_thread(mqtt_client: MQTTClient, factory: Factory, topic_manager: TopicManager):
    """Thread for handling user menu input for manual control."""
    device_map = get_device_map(factory)
    
    load_unload_devices = {k: v for k, v in device_map.items() if not k.isdigit()}
    fault_devices = device_map

    load_prompt = f"请输入装载设备编号 ({', '.join(load_unload_devices.keys())}): "
    unload_prompt = f"请输入卸载设备编号 ({', '.join(load_unload_devices.keys())}): "
    fault_prompt = f"请输入设备编号 ({', '.join(fault_devices.keys())}): "

    while True:
        print("\n请选择操作类型：")
        print("1. 移动AGV")
        print("2. 装载")
        print("3. 卸载")
        print("4. 充电")
        print("5. 注入故障")
        print("6. 查看结果 (result)")
        print("7. 自动上料控制")
        print("8. 退出")
        op = input("> ").strip().lower()

        if op == "1":
            line_id = f"line{input('请输入生产线编号 (e.g., 1, 2, 3): ').strip()}"
            agv_id_short = input("请输入AGV编号 (e.g., 1, 2): ").strip()
            agv_id = f"AGV_{agv_id_short}"
            target_point = "P" + input("请输入目标点 (e.g., 1): ").strip()
            cmd = {"action": "move", "target": agv_id, "params": {"target_point": target_point}}

        elif op in ["2", "3"]: # Load/Unload
            action = "load" if op == "2" else "unload"
            line_id = f"line{input('请输入生产线编号 (e.g., 1, 2, 3): ').strip()}"
            agv_id_short = input("请输入AGV编号 (e.g., 1, 2): ").strip()
            agv_id = f"AGV_{agv_id_short}"
            
            prompt = load_prompt if action == "load" else unload_prompt
            device_id_short = input(prompt).strip().upper()
            device_id = load_unload_devices.get(device_id_short)

            if not device_id:
                print("无效设备编号，请重试。")
                continue

            buffer_type = input("请输入buffer类型 (N.A./output_buffer/upper/lower): ").strip()
            params = {"device_id": device_id, "buffer_type": buffer_type}

            if action == "load":
                product_id = input("请输入产品编号（可选）: ").strip()
                if product_id:
                    params["product_id"] = product_id
            
            cmd = {"action": action, "target": agv_id, "params": params}

        elif op == "4":
            line_id = f"line{input('请输入生产线编号 (e.g., 1, 2, 3): ').strip()}"
            agv_id_short = input("请输入AGV编号 (e.g., 1, 2): ").strip()
            agv_id = f"AGV_{agv_id_short}"
            try:
                target_level = float(input("请输入目标电量 (e.g., 80): ").strip())
            except ValueError:
                print("目标电量需为数字！")
                continue
            cmd = {"action": "charge", "target": agv_id, "params": {"target_level": target_level}}

        elif op == "5":
            line_id = f"line{input('请输入生产线编号 (e.g., 1, 2, 3): ').strip()}"
            
            if line_id not in factory.lines:
                print(f"生产线 {line_id} 不存在！")
                continue
            
            if not hasattr(factory.lines[line_id], 'fault_system') or factory.lines[line_id].fault_system is None:
                print("故障系统未初始化，请先初始化故障系统。")
                continue
            
            # 1:StationB, 2:Conveyor_BC, 3:StationC
            fast_fault = input("请输入故障类型 (1:StationA for 50s, 2:Conveyor_AB for 50s, 3.StationB for 50s,4, Conveyor_BC for 50s, 5:StationC for 50s) else manual: ").strip()
            if fast_fault == "1":
                fault_type = FaultType.STATION_FAULT
                device_id = "StationA"
                fault_duration = 50.0
            elif fast_fault == "2":
                fault_type = FaultType.CONVEYOR_FAULT
                device_id = "Conveyor_AB"
                fault_duration = 50.0
            elif fast_fault == "3":
                fault_type = FaultType.STATION_FAULT
                device_id = "StationB"
                fault_duration = 50.0
            elif fast_fault == "4":
                fault_type = FaultType.STATION_FAULT
                device_id = "Conveyor_BC"
                fault_duration = 50.0
            elif fast_fault == "5":
                fault_type = FaultType.STATION_FAULT
                device_id = "StationC"
                fault_duration = 50.0
            else:
                print("手动设置故障，请输入设备编号: ")
                fault_type_in = input("请输入故障类型 (1:AGV, 2:工站, 3:传送带): ").strip()
                fault_map = {"1": FaultType.AGV_FAULT, "2": FaultType.STATION_FAULT, "3": FaultType.CONVEYOR_FAULT}
                fault_type = fault_map.get(fault_type_in)
                device_id_short = input(fault_prompt).strip().upper()
                device_id = fault_devices.get(device_id_short)
                if not device_id:
                    print("无效设备编号，请重试。")
                    continue
                fault_duration = float(input("请输入故障持续时间 (秒): ").strip())
                try:
                    if not fault_type:
                        raise ValueError("无效的故障类型")
                except (ValueError, KeyError) as e:
                    print(f"输入无效: {e}！")
                    continue
                try:
                    if not fault_type:
                        raise ValueError("无效的故障类型")
                except (ValueError, KeyError) as e:
                    print(f"输入无效: {e}！")
                    continue
            
            factory.lines[line_id].fault_system._inject_fault_now(device_id, fault_type, fault_duration)
            print(f"已注入故障: {device_id} {fault_type.name} {fault_duration}s")
            continue

        elif op == "6" or op == "result":
            # 获取并显示最终结果
            if factory.kpi_calculator:
                final_scores = factory.kpi_calculator.get_final_score()
                
                # 打印到终端（与factory.print_final_scores()相同格式）
                print(f"\n{'='*60}")
                print("🏆 最终竞赛得分")
                print(f"{'='*60}")
                print(f"生产效率得分 (40%): {final_scores['efficiency_score']:.2f}")
                print(f"  - 订单完成率: {final_scores['efficiency_components']['order_completion']:.1f}%")
                print(f"  - 生产周期效率: {final_scores['efficiency_components']['production_cycle']:.1f}%")
                print(f"  - 设备利用率: {final_scores['efficiency_components']['device_utilization']:.1f}%")
                print(f"\n质量与成本得分 (30%): {final_scores['quality_cost_score']:.2f}")
                print(f"  - 一次通过率: {final_scores['quality_cost_components']['first_pass_rate']:.1f}%")
                print(f"  - 成本效率: {final_scores['quality_cost_components']['cost_efficiency']:.1f}%")
                print(f"\nAGV效率得分 (30%): {final_scores['agv_score']:.2f}")
                print(f"  - 充电策略效率: {final_scores['agv_components']['charge_strategy']:.1f}%")
                print(f"  - 能效比: {final_scores['agv_components']['energy_efficiency']:.1f}%")
                print(f"  - AGV利用率: {final_scores['agv_components']['utilization']:.1f}%")
                print(f"\n总得分: {final_scores['total_score']:.2f}")
                print(f"{'='*60}\n")
                
                # 发布得分到MQTT（不包含原始指标）
                result_topic = RESULT_TOPIC
                

                scores_only = {
                    "total_score": final_scores['total_score'],
                    "efficiency_score": final_scores['efficiency_score'],
                    "efficiency_components": str(final_scores['efficiency_components']),
                    "quality_cost_score": final_scores['quality_cost_score'],
                    "quality_cost_components": str(final_scores['quality_cost_components']),
                    "agv_score": final_scores['agv_score'],
                    "agv_components": str(final_scores['agv_components'])
                }
                result_json = json.dumps(scores_only)
            
                mqtt_client.publish(result_topic, result_json)
                print(f"✅ 结果已发布到 {result_topic}")
            else:
                print("❌ KPI计算器未初始化")
            continue
            
        elif op == "7":
            global auto_feed_threads
            print("\n自动上料控制:")
            print("1. 启动自动上料")
            print("2. 停止自动上料")
            print("3. 查看自动上料状态")
            sub_op = input("> ").strip()
            
            if sub_op == "1":
                line_id = f"line{input('请输入生产线编号 (e.g., 1, 2, 3): ').strip()}"
                if line_id in auto_feed_threads and auto_feed_threads[line_id]["active"]:
                    print(f"{line_id} 的自动上料已在运行中")
                else:
                    # 选择产品类型
                    print("\n选择要生产的产品类型:")
                    print("1. 只生产 P1")
                    print("2. 只生产 P2")
                    print("3. 只生产 P3")
                    print("4. 轮流生产 P1 和 P2")
                    print("5. 轮流生产 P1 和 P3")
                    print("6. 轮流生产 P2 和 P3")
                    print("7. 轮流生产所有类型 (P1, P2, P3)")
                    
                    type_choice = input("> ").strip()
                    product_types_map = {
                        "1": ["P1"],
                        "2": ["P2"],
                        "3": ["P3"],
                        "4": ["P1", "P2"],
                        "5": ["P1", "P3"],
                        "6": ["P2", "P3"],
                        "7": ["P1", "P2", "P3"]
                    }
                    
                    product_types = product_types_map.get(type_choice, ["P1", "P2", "P3"])
                    
                    try:
                        interval = float(input("请输入上料间隔时间（秒，默认2.0）: ").strip() or "2.0")
                    except ValueError:
                        interval = 2.0
                    
                    # 设置状态为激活，包含产品类型信息
                    auto_feed_threads[line_id] = {
                        "active": True,
                        "product_types": product_types,
                        "interval": interval
                    }
                    # 创建并启动线程
                    thread = threading.Thread(
                        target=auto_feed_station_a,
                        args=(factory, line_id, interval, product_types),
                        daemon=True
                    )
                    auto_feed_threads[line_id]["thread"] = thread
                    thread.start()
                    print(f"✅ 已启动 {line_id} 的自动上料")
                    print(f"   产品类型: {', '.join(product_types)}")
                    print(f"   间隔时间: {interval} 秒")
            
            elif sub_op == "2":
                line_id = f"line{input('请输入生产线编号 (e.g., 1, 2, 3): ').strip()}"
                if line_id in auto_feed_threads and auto_feed_threads[line_id]["active"]:
                    auto_feed_threads[line_id]["active"] = False
                    print(f"✅ 正在停止 {line_id} 的自动上料...")
                else:
                    print(f"{line_id} 的自动上料未在运行")
            
            elif sub_op == "3":
                print("\n自动上料状态:")
                if not auto_feed_threads:
                    print("没有自动上料在运行")
                else:
                    for line_id, info in auto_feed_threads.items():
                        status = "运行中" if info["active"] else "已停止"
                        product_types = info.get("product_types", ["未知"])
                        interval = info.get("interval", "未知")
                        print(f"  {line_id}: {status}")
                        if info["active"]:
                            print(f"    - 产品类型: {', '.join(product_types)}")
                            print(f"    - 间隔时间: {interval} 秒")
            continue
            
        elif op == "8":
            print("退出菜单输入线程。")
            break
        else:
            print("无效选择，请重试。")
            continue
        
        # Only publish command if cmd was defined and line_id exists
        if 'cmd' in locals() and 'line_id' in locals():
            mqtt_client.publish(topic_manager.get_agent_command_topic(line_id), json.dumps(cmd))
            print(f"已发送命令: {cmd}")