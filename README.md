# SUPCON NLDF (Natual Language Driven Factory) Simulator

## 开发测试
### 1. 单条产线模式 **(Deprecated)** 

- 使用[topics.py](config/topics.py)来配置topic
- [main.py](src/main.py)第51行配置mqtt client name防止重复导致断联
```zsh
uv run run_simulation.py.py (--menu) (--no-fault)
```
### 2. 三条产线工厂

```zsh
uv run run_multi_line_simulation.py (--menu) (--no-fault)
```

## 赛题背景

语言是新的协议BALABALA；Agent成了每个领域绕不开的革命火种，在工业领域也是一样，我们作为一家工业领域的国内龙头企业，也不断的在尝试将最新的agent技术融入到正常的工业厂房的流程中。随着ai agent的发展，我们进一步畅想，能否有个agent系统可以人类一样用自然语言进行决策？我们简单搭建了一个可操控的模拟工厂，由你来大显身手。

## 场景解释

工厂内部包含3条产线，一个原料仓库以及一个最终产品仓库，3条产线配置有一样的A，B，C工站以及一个质检站，AB，BC，CQ三条中间连接的自动传送带和AGV_1，AGV_2两个AGV。选手需要对3条产线的一共6个AGV进行操作（包括移动，装货卸货等），选手需要在有限的时间内操作agv协调生产，同时应对随机故障，获得尽可能高的KPI得分。（KPI 定义见下文）

为了简单起见，每个AGV的可移动路径点都使用P1-P10来表示，他们表示当前AGV路径上的相对可停顿点，如果希望AGV1或2前往某点例如原料仓库，都需要移动到P0点。AGV路径互不干扰，不考虑碰撞等因素，路径上的点ID如图。
![Factory Agent Logo](/docs/path_point.png)

## 赛前须知

### 游戏机制

游戏使用simpy实现离散工厂的仿真

1. Order Generactor: 游戏有一个全局的订单生成器，每个订单中可能有一个或多个产品等待加工，一旦生成对应待加工的product会在原料仓库中出现
2. 产品说明： 游戏定义P1，P2，P3三种产品，会在产品id:prod_1_XXXXXX中的prod和UUID中间的数字显示，产品有自己对应的工艺流程：
- 产品 P1（标准消费电子设备，60%）(_代表：基础 PCB 组件、简单电子模块、标准化产品_)(总周期155-195秒)
```
原料仓库 → [AGV:20s] → 工站A[初级加工:30-45s] → [传送带:20s] → 工站B[精密加工:45-60s] → [传送带:20s] → 工站C[综合测试:20-30s] → [传送带:20s] → 质检站[最终检验:15-25s] → [AGV:10s] → 成品仓库
```

- 产品 P2（高精度工控设备，30%）（_代表：工业控制板、精密传感器、高可靠性模块_）（200-240 秒）
```
原料仓库 → [AGV:20s] → 工站A[初级加工:40-60s] → [传送带:20s] → 工站B[精密加工:60-80s] → [传送带:20s] → 工站C[综合测试:30-40s] → [传送带:20s] → 质检站[最终检验:20-30s] → [AGV:10s] → 成品仓库
```

- 产品 P3（复杂定制设备，10%）（_代表：高复杂度产品、需要特殊工艺路径的定制产品_）（290-365 秒）
```
原料仓库 → [AGV:20s] → 工站A[初级加工:35-50s] → [传送带:20s] → 工站B[精密加工:50-70s] → [传送带:20s] → 工站C[初测:25-35s] → [暂存upper/lower buffer] → [AGV:25s] → 工站B[二次加工:40-60s] → [传送带:20s] → 工站C[全面测试:35-50s] → [传送带:20s] → 质检站[深度检验:25-35s] → [AGV:10s] → 成品仓库
```
3. 

## 🎯 **核心功能** 

### ✅ **已实现功能**
- **实时MQTT通信**: 稳定的设备状态发布和命令接收
- **故障诊断系统**: 基于PRD规范的智能故障注入和维修逻辑
- **Unity实时可视化**: 100ms高频AGV位置更新，实时动画事件
- **基础AGV系统**: 简单路径移动和碰撞避让
- **订单管理**: 自动订单生成和进度跟踪
- **KPI计算**: 实时生产效率、成本、可靠性监控

### 🔥 **故障系统特色**
- **完整维修锁定**: 故障期间设备完全无法操作
- **重复维修防护**: 维修期间锁定，防止重复操作  
- **智能诊断逻辑**: 错误诊断有时间惩罚机制
- **实时故障警报**: 增强的MQTT故障事件推送

## 🚀 **快速开始**

### 安装依赖
```bash
# 安装uv包管理器 (如果还没有)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目依赖
uv sync
```

### 运行基础仿真
```bash
# 运行基础工厂仿真系统
uv run src/simulation/factory.py
```

### 测试系统完整性
```bash
# 运行完整测试套件
uv run test/run_tests.py
```

## 📡 **MQTT接口**

### 设备状态主题 (每10秒)
```
factory/station/{station_id}/status     # 工站状态
factory/agv/{agv_id}/status             # AGV状态  
factory/status                          # 工厂总体状态
```

### Unity实时可视化主题 (高频)
```
factory/realtime/agv/{agv_id}/position     # 100ms AGV位置
factory/realtime/device/{id}/animation     # 设备动画事件
factory/alerts/{device_id}                 # 故障警报
```

### 数据格式示例
```json
// AGV位置 (100ms更新)
{
  \"agv_id\": \"AGV_1\",
  \"position\": {\"x\": 15.5, \"y\": 20.0, \"z\": 0.0},
  \"rotation\": {\"x\": 0, \"y\": 45, \"z\": 0},
  \"speed\": 2.0,
  \"battery_level\": 85.5
}

// 动画事件
{
  \"device_id\": \"StationA\",
  \"animation_type\": \"start_processing\",
  \"duration\": 5.0,
  \"params\": {\"intensity\": 0.8}
}
```

## 🛠️ **设备操作接口**

### 基础命令
```python
# 检查设备状态
factory.inspect_device(\"StationA\")

# 请求维修 (故障诊断)
factory.handle_maintenance_request(\"StationA\", \"replace_tool\")

# 跳过维修时间 (加速测试)
factory.skip_repair_time(\"StationA\")

# 获取可操作设备列表
factory.get_available_devices()
```

### 维修命令类型
```python
维修类型 = [
    \"clean_sensors\",      # 清洁传感器
    \"replace_tool\",       # 更换工具
    \"recalibrate\",        # 重新校准
    \"lubricate\",          # 润滑保养
    \"check_alignment\",    # 检查对齐
    \"restart_system\"      # 重启系统
]
```

## 🎮 **设备配置**

### 工站配置
```yaml
stations:
  - id: \"StationA\"
    position: [15, 20]
    buffer_size: 3
    processing_times:
      P1: [30, 45]  # 30-45秒处理时间
      P2: [40, 60]
      P3: [35, 50]
```

### AGV配置  
```yaml
agvs:
  - id: \"AGV_1\"
    position: [10, 15]
    speed_mps: 2.0
    battery_level: 100
```

## 📊 **KPI监控**

### 自动计算指标
- **生产效率**: 订单完成率和平均处理时间
- **成本控制**: 维修成本和资源利用率
- **系统可靠性**: 故障恢复时间和设备可用性

### 实时数据发布
```
factory/kpi/efficiency    # 效率指标
factory/kpi/cost         # 成本指标  
factory/kpi/reliability  # 可靠性指标
```

## 🔧 **故障系统详解**

### 故障类型
```python
故障类型 = [
    \"station_vibration\",      # 工站振动异常
    \"precision_degradation\",  # 精度下降
    \"agv_path_blocked\",       # AGV路径阻塞
    \"agv_battery_drain\",      # AGV电池异常消耗
    \"efficiency_anomaly\"      # 效率异常
]
```

### 诊断结果结构
```python
DiagnosisResult = {
    \"device_id\": str,         # 设备ID
    \"is_correct\": bool,       # 诊断是否正确
    \"repair_time\": float,     # 维修/惩罚时间
    \"penalty_applied\": bool,  # 是否应用惩罚
    \"affected_devices\": list, # 受影响的设备
    \"can_skip\": bool         # 是否可跳过等待时间
}
```

## 🏗️ **系统架构**

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Unity前端     │◄──►│   MQTT Broker    │◄──►│  工厂仿真后端   │
│  (可视化展示)   │    │ (实时数据通信)   │    │ (业务逻辑)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                ▲
                                │
                       ┌──────────────────┐
                       │   智能体接口     │
                       │ (命令处理/控制)  │
                       └──────────────────┘
```

## 📝 **项目结构**

```
src/
├── simulation/           # 核心仿真引擎
│   ├── factory.py       # 主工厂类
│   └── entities/        # 设备实体
│       ├── station.py   # 工站实现
│       ├── agv.py       # AGV实现
│       └── base.py      # 设备基类
├── game_logic/          # 游戏逻辑
│   ├── fault_system.py  # 故障系统
│   ├── order_generator.py # 订单生成
│   └── kpi_calculator.py  # KPI计算
├── unity_interface/     # Unity集成
│   └── real_time_publisher.py # 实时发布器
├── utils/              # 工具类
│   ├── mqtt_client.py  # MQTT客户端
│   └── config_loader.py # 配置加载器
└── main.py             # 主入口
```

## 🧪 **测试套件**

```bash
# 运行所有测试
uv run test/run_tests.py

# 单独测试模块
uv run test/test_factory_simulation.py      # 基础仿真
uv run test/test_fault_diagnosis_demo.py    # 故障诊断  
uv run test/test_interactive_factory.py     # 交互功能
```

## 🎯 **开发规划**

### v2.1 规划功能
- [ ] Web控制面板
- [ ] 数据持久化
- [ ] 高级分析工具
- [ ] 多工厂实例支持

### 黑客松建议方向
1. **AI控制器**: 基于状态空间的智能决策
2. **优化算法**: 生产调度和路径优化  
3. **预测性维护**: 基于历史数据的故障预测
4. **可视化增强**: 3D建模和高级动画
5. **协作机器人**: 多智能体协调控制

## 🤝 **贡献指南**

1. Fork项目仓库
2. 创建功能分支: `git checkout -b feature/amazing-feature`
3. 提交更改: `git commit -m 'Add amazing feature'`
4. 推送分支: `git push origin feature/amazing-feature`
5. 创建Pull Request

## 📄 **许可证**

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**�� 祝黑客松参赛者取得优异成绩！** 