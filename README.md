# SUPCON AdventureX Factory Simulation

这是 SUPCON AdventureX 黑客松的工厂仿真后端系统。该系统提供了一个基于数字孪生技术的智能工厂仿真平台，参赛者可以开发 AI Agent 来优化工厂生产效率、处理故障、管理资源。

## 🏗️ 系统架构

- **仿真核心 (SimPy)**: 基于离散事件仿真的工厂环境
- **MQTT 通信**: 实时的设备状态发布和 Agent 指令接收
- **路径冲突避免**: AGV 智能路径管理，防止碰撞
- **模块化设计**: 清晰的代码结构，易于扩展和维护

## 🚀 快速开始

### 环境要求

- Python 3.9+
- uv (Python 包管理工具)

### 安装依赖

```bash
# 使用 uv 安装项目依赖
uv sync
```

### 运行仿真

```bash
# 启动工厂仿真系统（推荐方式）
uv run python run_simulation.py

# 或者使用传统方式
uv run python src/main.py
```

系统启动后将会：
- 连接到 MQTT Broker (`supos-ce-instance1.supos.app:1883`)
- 初始化工厂设备（4个工站，2个AGV）
- 开始监听 Agent 指令
- 定期发布设备状态

### 测试系统

在另一个终端中运行测试 Agent：

```bash
# 发送测试指令（推荐方式）
uv run python run_mock_agent.py

# 或者使用传统方式
uv run python tools/mock_agent.py
```

## 📡 MQTT 接口

### 订阅主题 (Agent 可以监听)

- `factory/station/{station_id}/status` - 工站状态
- `factory/resource/{agv_id}/status` - AGV 状态  
- `factory/orders/new` - 新订单
- `factory/kpi/update` - KPI 更新

### 发布主题 (Agent 发送指令)

- `factory/agent/commands` - Agent 指令

### 支持的指令

```json
{
  "command_id": "unique_id",
  "agent_id": "your_team_id", 
  "action": "move_agv",
  "target": "AGV_1",
  "params": {"destination_id": "P1"}
}
```

支持的 action:
- `move_agv` - 移动 AGV
- `request_maintenance` - 请求设备维护
- `emergency_stop` - 紧急停止
- `adjust_priority` - 调整订单优先级
- `reroute_order` - 重新路由订单

## 🏭 工厂布局

- **路径点**: P0-P9 (详见 PRD 文档)
- **工站**: StationA (组装), StationB (焊接), StationC (测试), QualityCheck (质检)
- **AGV**: AGV_1, AGV_2 (速度 2.0 m/s)

## 🔧 开发指南

### 项目结构

```
├── config/          # 配置文件 (MQTT 主题、数据结构等)
├── src/
│   ├── simulation/     # 仿真核心
│   ├── agent_interface/ # Agent 接口
│   ├── utils/          # 工具类
│   └── main.py         # 主程序
├── tools/           # 测试工具
├── run_simulation.py   # 主程序启动器
└── run_mock_agent.py   # 测试 Agent 启动器
```

### 使用 uv 运行

```bash
# ✅ 推荐：使用 uv run，无需手动激活虚拟环境
uv run python run_simulation.py

# ❌ 不推荐：手动激活环境（uv 不需要这样做）
# source .venv/bin/activate
# python run_simulation.py
```

### 扩展功能

1. **添加新的指令类型**: 在 `src/agent_interface/command_handler.py` 中添加新的处理函数
2. **修改工厂布局**: 编辑 `src/simulation/factory.py` 中的 `MOCK_LAYOUT_CONFIG`
3. **添加新的设备类型**: 在 `src/simulation/entities/` 中创建新的设备类

## 📝 注意事项

- 推荐使用根目录的启动脚本（`run_simulation.py`, `run_mock_agent.py`）
- 确保 MQTT Broker 可访问

## 🎯 下一步开发

根据 TODO.md 规划：
- [ ] 实现订单生成系统
- [ ] 添加故障注入机制  
- [ ] 实现 KPI 计算器
- [ ] 添加动态约束系统
- [ ] 创建配置文件加载器

## 🤝 贡献

这是一个黑客松项目，欢迎参赛选手基于此系统开发自己的 AI Agent！ 