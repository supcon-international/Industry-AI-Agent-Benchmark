# AdventureX-SUPCON-Competition 后端开发 TODO List (v2 - PRD Aligned)
# ----------------------------------------------------
# 开发者 A (Dev A): 仿真内核与物理世界
# 开发者 B (Dev B): 游戏逻辑与交互层
# ----------------------------------------------------

############################################################
## 第一周: 地基与蓝图 (Foundation & Contracts)
## 目标: 搭建项目骨架，焊死通信协议，让一个"空"工厂跑起来。
############################################################

### Day 1-2: 项目初始化与核心协议定义

#### SYNC POINT 1 (项目启动会 - 关键会议!)
- [X] **两人共同**: 讨论并最终确定 `config/schemas.py` 中的所有 MQTT Topic 和 JSON 消息结构。这是你们未来三周工作的"宪法"。一旦确定，尽量不再修改。
- [X] **两人共同**: 在 `config/topics.py` 中用常量定义所有 Topic 字符串，避免手写错误。
- [X] **两人共同**: 初始化 Git 仓库，并建立 `main` 和 `develop` 分支。
- [X] **两人共同**:
    - **验收标准**: `config/schemas.py` 中所有 Pydantic 模型字段与 PRD 3.2 和 3.4 中的 JSON 示例完全一致。`config/topics.py` 中所有 topic 字符串与 PRD 3.2 中定义的完全一致。

#### Dev A: 仿真内核骨架
- [ ] **任务**: 创建 Python 项目 (`pyproject.toml`, `README.md`)。
- [ ] **任务**: 实现最基础的仿真主循环 (`simulation/main.py`)。
- [ ] **任务**: 创建核心实体基类。
    - **文件**: `simulation/entities/base.py`
    - **验收标准**: `Device` 类必须包含 `id: str`, `env: simpy.Environment`, `status: Enum`, `position: tuple[int, int]`。`status` 枚举至少包含 `IDLE`, `PROCESSING`, `ERROR`, `MAINTENANCE`。

#### Dev B: 通信与验证骨架
- [ ] **任务**: 定义所有 MQTT 消息的精确格式。
    - **文件**: `config/schemas.py`
    - **验收标准**:
        - `StationStatus` 必须包含 `timestamp`, `source_id`, `status`, `utilization`, `buffer_level`, 以及可选的 `symptom`。
        - `AgentCommand` 必须包含 `command_id`, `agent_id`, `action`, `target`, `params: dict`。
        - 其他如 `AGVStatus`, `NewOrder` 等模型也需严格按 PRD 定义。
- [ ] **任务**: 定义所有 Topic 名称 (`config/topics.py`)。
- [ ] **任务**: 编写一个健壮的 MQTT 客户端封装 (`utils/mqtt_client.py`)。

### Day 3-5: 基础管道铺设与模拟

#### SYNC POINT 2 (管道连接测试)
- [ ] **两人共同**: Dev B 运行 `CommandValidator`；Dev A 运行 `Factory` 并用简单脚本发送一条符合 Schema 的 MQTT 消息；Dev B 确认能收到并验证通过。这个节点打通，意味着你们可以真正独立开发了。
- [ ] **两人共同**: 将 `config/schemas.py` 和 `config/topics.py` 文件同步给 Unity Pro，让他们可以开始开发前端。
- [ ] **两人共同**:
    - **验收标准**: Dev A 的工厂能发布 `factory/station/StationA/status` 消息，Dev B 的验证器能成功接收并按 Pydantic 模型解析。Dev B 的 `mock_agent` 发送的指令能被 Dev A 的仿真环境接收。

#### Dev A: 工厂实例化
- [ ] **任务**: 编写 Docker & Docker Compose 配置 (`Dockerfile`, `docker-compose.yml`)。
- [ ] **任务**: 创建具体的设备类。
    - **文件**: `simulation/entities/station.py`, `simulation/entities/agv.py`, `simulation/entities/conveyor.py`
    - **验收标准**:
        - `Station` 的构造函数接收 `buffer_size` 和 `processing_times: dict` (e.g., `{'P1': (30, 45)}`)。
        - `AGV` 的构造函数接收 `move_speed` 和 `battery_capacity`。
        - `Conveyor` 的构造函数接收 `length`, `speed`, `capacity`。
- [ ] **任务**: 创建并初始化工厂。
    - **文件**: `simulation/factory.py`
    - **验收标准**: `Factory` 类能根据 PRD 2.1 的表格数据，用正确的参数实例化所有设备。它必须包含一个 `path_points` 字典，存储 P0-P9 的坐标。
- [ ] **任务**: (临时)让设备定时发布状态。
    - **验收标准**: 启动仿真后，所有设备每隔10秒发布一次符合 `schemas.py` 定义的自身状态消息。

#### Dev B: 指令接收与模拟
- [ ] **任务**: 实现指令验证器 (`agent_interface/command_validator.py`)。
- [ ] **任务**: 实现一个全局日志系统 (`utils/logger.py`)。
- [ ] **任务**: 开发一个 Agent 模拟器 (`tools/mock_agent.py`)。

############################################################
## 第二周: 核心功能并行开发 (Core Feature Development)
## 目标: 分头实现仿真世界的物理行为和比赛的游戏规则。
############################################################

### Day 6-8: 生产流程与游戏规则

#### SYNC POINT 3 (内部 API 定义)
- [ ] **两人共同**: 讨论并定义 B 如何调用 A 的实体对象方法。例如：`agv.move_to(destination_id)`、`station.start_maintenance('replace_bearing')`。B 是调用方，A 是实现方。
- [ ] **两人共同**:
    - **验收标准**: 定义出清晰的函数签名，例如 `agv.move_to(destination_id: str)`，`station.start_processing(product: Product)`，并写入一个共享的 `INTERNAL_API.md` 文档中。

#### Dev A: 实现物理世界
- [ ] **任务**: 实现工站的完整加工逻辑。
    - **文件**: `simulation/entities/station.py`
    - **验收标准**: `process(product)` 方法能根据 `product.type` 从构造函数参数中获取正确的处理时间范围（如 P1 在工站A为 30-45 秒），并 `yield` 一个该范围内的随机超时。能正确管理自身 `buffer` 的增减。
- [ ] **任务**: 实现 AGV 的移动逻辑。
    - **文件**: `simulation/entities/agv.py`
    - **验收标准**: `move_to(destination_id)` 能从 `factory.path_points` 查找坐标，计算欧几里得距离，并根据速度 `yield` 正确的移动时间。
- [ ] **任务**: 实现传送带的传送逻辑。
    - **文件**: `simulation/entities/conveyor.py`
    - **验收标准**: 传送时间固定为 PRD 中定义的 20 秒。传送前必须检查自身容量和下游工站缓冲区容量。

#### Dev B: 实现游戏规则
- [ ] **任务**: 实现订单生成器。
    - **文件**: `game_logic/order_generator.py`
    - **验收标准**: 生成的订单严格遵守 PRD 2.4 中定义的全部参数：间隔(30-60s)，数量(权重分布)，产品组合(P1/P2/P3概率)，优先级分布，以及截止日期的计算公式。
- [ ] **任务**: 实现指令处理器。
    - **文件**: `agent_interface/command_handler.py`
    - **验收标准**: 能处理 PRD 3.4 指令表中的**所有** `action` 类型，并正确调用 Dev A 实现的相应实体方法。对于无效的 `target` 或 `params` 能优雅地打印错误日志。

### Day 9-10: 故障与计分

#### SYNC POINT 4 (功能联调)
- [ ] **两人共同**: B 启动订单生成器，A 的工厂开始运转。B 用 `mock_agent` 发送移动指令，观察整个流程是否顺畅。
- [ ] **两人共同**:
    - **验收标准**: B 启动订单生成器，A 的工厂能根据工艺路径自动流转（需B在指令处理器中实现自动搬运逻辑）。B 能用 `mock_agent` 手动下达 AGV 指令并成功执行。

#### Dev A: 故障实现
- [ ] **任务**: 为设备添加故障状态和维修逻辑。
    - **文件**: `simulation/entities/station.py` (及 `base.py`)
    - **验收标准**:
        - `set_fault(root_cause, symptom)` 方法能正确记录内部原因，只对外发布症状。
        - `start_maintenance(maintenance_type)` 能正确匹配 `maintenance_type` 和 `internal_root_cause`。如果不匹配，维修时间必须施加 PRD 2.5 中定义的惩罚（例如 +100%）。维修时间基准值来自 PRD 表格。

#### Dev B: 故障注入与计分
- [ ] **任务**: 实现故障注入系统。
    - **文件**: `game_logic/fault_injector.py`
    - **验收标准**: 能从 PRD 2.5 的《故障症状与诊断手册》中随机选择一个有效的 "根本原因-症状" 对，并注入到随机的、合适类型的设备中。
- [ ] **任务**: 实现 KPI 计算器。
    - **文件**: `game_logic/kpi_calculator.py`
    - **验收标准**: 能正确计算 PRD 2.7 中定义的**所有 KPI**。`总生产成本`需要包含物料、能源、维修、报废四项成本。

############################################################
## 第三周: 集成、测试与交付 (Integration, Testing & Delivery)
## 目标: 整合所有功能，密集测试，修复 bug，准备交付。
############################################################

### Day 11-13: 端到端测试与配置化

#### SYNC POINT 5 (坐在一起联调)
- [ ] **两人共同**: 用一个复杂的 `mock_agent` 脚本运行一个完整的、包含故障的端到端场景。一起看日志，修复遇到的所有 bug。这是最关键的 debug 阶段。
- [ ] **两人共同**:
    - **验收标准**: 运行一个包含所有产品类型（P1, P2, P3）和多种故障场景的复杂测试脚本，系统能稳定运行至少1小时（仿真时间），且最终的 KPI 计算结果符合预期。

#### Dev A: 健壮性与灵活性
- [ ] **任务**: 实现配置化。
    - **文件**: `config/local_dev.yml`, `config/cloud_eval.yml`
    - **验收标准**: 所有在 PRD 中提到的数字（处理时间、速度、概率、成本系数等）都必须从配置文件加载，而不是硬编码。提供两个不同的配置文件用于本地开发和云端评估。
- [ ] **任务**: 编写配置加载器 (`utils/config_loader.py`)。

#### Dev B: 动态约束与工具
- [ ] **任务**: 实现动态约束。
    - **文件**: `game_logic/dynamic_constraints.py`
    - **验收标准**:
        - **能源成本**: `KPICalculator` 能根据仿真时间从该模块获取正确的电价乘数。
        - **维护资源限制**: `Station.start_maintenance` 在执行前必须向该模块请求一个"维修许可"，如果达到上限（如1），则必须等待。
        - 其他约束如"材料兼容性"、"供应链波动"也需实现。
- [ ] **任务**: 完善裁判/管理员工具 (`tools/`)。

### Day 14-15: 文档与发布

#### SYNC POINT 6 (最终交付物审查)
- [ ] **两人共同**: 互相 Code Review。检查代码注释、文档清晰度。
- [ ] **两人共同**: 最终测试 `docker-compose up` 是否能一键为选手启动一个完整的本地开发环境。
- [ ] **两人共同**:
    - **验收标准**: 互相 Code Review。最终的 `docker-compose up` 能为选手一键启动一个功能完整、连接到 MQTT 的本地开发环境。

#### Dev A: 打包与清理
- [ ] **任务**: 完善 Dockerfile。
- [ ] **任务**: 编写核心模块文档（Docstrings）。

#### Dev B: 交付文档
- [ ] **任务**: 编写最终的 **《选手开发指南》(Player's Guide)**。
    - **验收标准**: 文档必须包含一个 Quick Start 章节，MQTT Broker 地址，所有 Topic 列表，所有消息的精确 JSON 格式（带示例），支持的 Agent 指令列表（带示例），以及 PRD 2.7 中的评分公式。
- [ ] **任务**: 编写 `README.md`。
    - **内容**: 项目简介，如何为开发者（你们自己）设置环境，如何运行测试。

# SUPCON 智能故障诊断系统 - 任务状态

## ✅ 核心功能已完成

### 🏭 基础仿真架构 (100%)
- ✅ SimPy 离散事件仿真引擎
- ✅ 4个制造工站 + 2个AGV + 10个路径点
- ✅ MQTT 通信层和消息验证
- ✅ 订单生成系统 (严格按PRD 2.4规范)
- ✅ KPI 计算系统 (效率40% + 成本30% + 鲁棒性30%)
- ✅ Agent命令处理系统

### 🧠 智能故障诊断系统 (PRD 3.2改进)

**已解决的核心问题**：
~~1. 选手无法根据症状进行诊断 没给具体设备状态信息只能靠猜~~ ✅ 已完成
~~2. 诊断过程中~~ ✅ 已完成
    ~~1. 诊断错误 引发惩罚~~ ✅ 已完成
        ~~1. 冻结时间~~ ✅ 已完成
            ~~1. 可以跳过~~ ✅ 已完成 
            ~~2. 操作不受影响的机器~~ ✅ 已完成
        ~~2. 可能引发其他设备错误~~ ✅ 已完成
    ~~2. 诊断正确~~ ✅ 已完成
        ~~1. 修复时间 比冻结时间短~~ ✅ 已完成
            ~~1. 可以跳过~~ ✅ 已完成
            ~~2. 操作不受影响的机器~~ ✅ 已完成
    ~~3. 定义状态变化和root cause的mapping~~ ✅ 已完成
        ~~不直接给选手 让选手自己摸索，agent学习判断规则~~ ✅ 已完成

## 🎯 新增功能总结

### 1. 设备详细状态系统 (`DeviceDetailedStatus`)
- **性能指标**：温度、振动、效率等实时状态
- **设备特定属性**：
  - 工站：精度水平、刀具磨损、润滑油水平
  - AGV：电池电量、定位精度、载重状态
- **故障信息**：症状显示、冻结状态等

### 2. Inspect功能 (`inspect_device`)
- **详细状态检查**：玩家可检查任何设备的完整状态
- **实时状态维护**：simpy环境中持续更新设备状态
- **智能信息显示**：根据设备类型显示相关指标
- **MQTT集成**：检查结果实时发布给agents

### 3. 增强的诊断惩罚系统
- **设备冻结机制**：错误诊断暂时冻结设备
- **关联设备影响**：诊断错误可能影响相关设备 (30%概率)
- **次级故障触发**：可能在其他设备引发新故障 (40%概率)
- **动态惩罚倍数**：不同故障类型有不同惩罚系数

### 4. 跳过功能 (`skip_repair_time`)
- **时间控制**：可选择跳过修复/惩罚等待时间
- **操作灵活性**：继续操作未冻结的设备
- **可用设备查询**：`get_available_devices`显示可操作设备

### 5. 故障效果映射系统
- **状态变化映射**：不同故障对设备状态的特定影响
  - `station_vibration`: 振动↑, 温度↑, 精度↓
  - `precision_degradation`: 精度↓, 刀具磨损↑
  - `efficiency_anomaly`: 效率↓, 温度↑, 润滑油↓
  - `agv_battery_drain`: 电池电量↓
  - `agv_path_blocked`: 定位精度↓
- **隐式学习**：玩家需通过观察和试验学习规律

### 6. AI Agent学习支持
- **数据提供**：系统提供详细设备状态和诊断反馈
- **学习自主性**：玩家完全控制学习过程和策略
- **模式识别支持**：通过inspection历史数据建立知识库
- **渐进改进**：支持试错学习和诊断策略优化

## 🔧 测试系统优化

### 已完成的测试改进
- ✅ 新增 `test_fault_diagnosis_demo.py` - 完整功能演示
- ✅ 删除重复测试文件 `test_fault_scenarios.py`
- ✅ 修复BrokenPipeError (性能测试管道输出问题)
- ✅ 更新API兼容性 (DiagnosisResult返回格式)
- ✅ 优化测试菜单和文档

### 推荐测试流程
```bash
# 5分钟了解所有改进功能
uv run test/run_tests.py
# 选择选项3：故障诊断系统演示

# 完整系统验证
uv run test/run_tests.py
# 选择选项5：运行所有自动化测试
```

## 📋 核心文档

- `README.md` - 项目主要文档
- `docs/fault_diagnosis_manual.md` - 故障诊断手册
- `test/README.md` - 测试使用指南
- `PROJECT_STATUS_REPORT.md` - 项目完成状态

## 🎉 项目状态总结

**系统完成度**: 100% ✅
**核心功能**: 智能故障诊断系统按PRD 3.2要求完全实现
**测试覆盖**: 完整的功能演示和自动化测试
**文档完整性**: 精简且完整的使用指南

# 7.4:
1. Quality Checker derermine 残次品，发送unity前端（直接舍弃 or 返回重新加工）
2. test mqtt topic
3. 维持一系列变量来对应系统状态（正常状态也非恒定），维护动作与变量变化的映射，agent学习采取动作来让变量趋紧当前产品周期的正确变量值
4. 设置两条AGV路径，平行不相交
5. refine KPI Calculation

# 7.5
1. 产线设计，同步加工3个产品，实现不同产品的逻辑产线
2. P3产品的出料设置2队列进行存放storage，若满就报故障，将产线停掉