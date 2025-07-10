# SUPCON 工厂仿真系统 v2.0 (简化版)

> 企业级智能制造仿真平台 - 为黑客松设计的简洁基础版本

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