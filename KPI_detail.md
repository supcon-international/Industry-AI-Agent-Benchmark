# KPI 系统计算说明

本文档说明智能制造挑战赛的 KPI 计算方法和评分规则。

## 评分结构

总分 100 分，分为三个部分：

- **生产效率**：40 分
- **质量成本**：30 分
- **AGV 效率**：30 分

## 生产效率指标（40 分）

### 订单完成率（16 分）

```
订单完成率 = (按时完成订单数 / 总订单数) × 100%
```

- 必须在 deadline 前完成所有产品才算按时完成订单
- 满分 16 分，按完成率比例给分

### 平均生产周期（16 分）

```
基础比率 = Σ(实际时间/理论时间) / 已完成产品数
完成率 = 已完成产品数 / (已完成产品数 + 进行中产品数)
平均生产周期 = 基础比率 / 完成率
```

理论时间：P1=160 秒，P2=200 秒，P3=250 秒

**重要**：只完成快速产品会被惩罚。如果完成率只有 50%，周期值会翻倍。

得分计算：

- 周期值越接近 1.0 得分越高，满分 16 分
- 周期值=1.0 时得满分，周期值=2.0 时得 8 分
- 没有产品完成时得 0 分

### 设备利用率（8 分）

```
设备利用率 = (工作时间 / 总时间) × 100%
```

- 包含所有 Station 和 Conveyor，不包含 AGV
- 满分 8 分，按利用率比例给分

## 质量成本指标（30 分）

### 一次通过率（12 分）

```
一次通过率 = (通过质检产品数 / 总产品数) × 100%
```

满分 12 分，按通过率比例给分

### 成本效率（18 分）

```
基准成本 = 已完成产品数 × 平均材料成本(15元)
成本效率 = min(100, 基准成本 / 实际成本 × 100)
```

**总生产成本包括**：

- 材料成本：P1=$10，P2=$15，P3=$20（从仓库取货时计算）
- 能源成本：$0.1/秒
- 维护成本：$8/次故障
- 报废成本：材料成本 ×80%

满分 18 分，成本控制越好得分越高

## AGV 效率指标（30 分）

### 充电策略效率（9 分）

```
充电策略效率 = (主动充电次数 / 总充电次数) × 100%
```

- 主动充电：AGV 提前规划充电
- 被动充电：电量耗尽被迫充电
- 满分 9 分，主动充电比例越高得分越高

### AGV 能效比（12 分）

```
AGV能效比 = 完成任务数 / 总充电时间(秒)
```

- 单位：任务/秒
- 满分 12 分，0.1 任务/秒时得满分
- 能效比越高得分越高

### AGV 利用率（9 分）

```
有效时间 = 总时间 - 故障时间 - 充电时间
AGV利用率 = 运输时间 / 有效时间 × 100%
```

满分 9 分，按利用率比例给分

## 成本参数

| 项目        | 数值    | 说明                        |
| ----------- | ------- | --------------------------- |
| P1 材料成本 | $10     | 从仓库取出时计算            |
| P2 材料成本 | $15     | 从仓库取出时计算            |
| P3 材料成本 | $20     | 从仓库取出时计算            |
| 能源成本    | $0.1/秒 | 设备运行时产生              |
| 维护成本    | $8/次   | 故障发生时产生              |
| 报废倍率    | 0.8     | 不合格品成本为材料成本 ×80% |

## 常见问题

**Q: 为什么某些 KPI 是 0？**

- scrap_costs=0：所有产品都通过质检（正常）
- charge_strategy_efficiency=0：只有紧急充电，需要改进充电策略
- agv_energy_efficiency=0：AGV 没有完成任务
- average_production_cycle=0：没有产品完成生产
- order_completion_rate： 没有将订单的产品都完成，或者没有产品被完成

## 数据获取

### KPI 实时数据

通过 MQTT 订阅 `{player_name}/kpi/status` 获取实时 KPI 数据。

数据格式示例：

```json
{
  "timestamp": 150.0,
  "order_completion_rate": 75.0,
  "average_production_cycle": 1.25,
  "device_utilization": 68.5,
  "first_pass_rate": 92.0,
  "total_production_cost": 856.5,
  "charge_strategy_efficiency": 80.0,
  "agv_energy_efficiency": 0.08,
  "agv_utilization": 72.0,
  "total_orders": 20,
  "completed_orders": 15,
  "total_products": 85,
  "active_faults": 1
}
```

通过 MQTT 订阅 `{player_name}/result/status`

```json
{
  "total_score": 30.34,
  "efficiency_score": 0.72,
  "efficiency_components": {
    "order_completion": 0,
    "production_cycle": 3.13,
    "device_utilization": 2.74
  },
  "quality_cost_score": 17.34,
  "quality_cost_components": {
    "first_pass_rate": 100,
    "cost_efficiency": 29.67
  },
  "agv_score": 12.28,
  "agv_components": {
    "charge_strategy": 100,
    "energy_efficiency": 21,
    "utilization": 8.5
  }
}
```
