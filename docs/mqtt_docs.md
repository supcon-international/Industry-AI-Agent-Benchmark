# MQTT 通信协议文档

## 📋 目录

1. [概述](#概述)
2. [连接配置](#连接配置)
3. [主题架构](#主题架构)
4. [消息格式](#消息格式)
5. [设备数据主题](#设备数据主题)
6. [系统事件主题](#系统事件主题)
7. [代理通信主题](#代理通信主题)
8. [QoS 策略](#qos策略)
9. [使用示例](#使用示例)
10. [错误处理](#错误处理)

---

## 🏗️ 概述

SUPCON 工厂仿真系统采用 MQTT 协议进行实时通信，支持设备状态监控、代理命令控制、系统事件通知等功能。

### 设计特点

- **统一主题架构**：所有设备数据归类到 `factory/device/` 下
- **参数化主题**：支持多设备、多代理的灵活扩展
- **标准化消息格式**：统一的 JSON 结构，便于解析
- **请求响应机制**：命令和响应一一对应，支持异步追踪

---

## 🔌 连接配置

### MQTT Broker 配置

```
Host: localhost (或指定IP)
Port: 1883 (标准端口) / 8883 (TLS端口)
Protocol: MQTT v3.1.1
Keep Alive: 60秒
Clean Session: true
```

### 客户端 ID 规范

- **工厂系统**: `factory_system`
- **Unity 客户端**: `unity_client_{instance_id}`
- **代理客户端**: `agent_{agent_id}`
- **监控客户端**: `monitor_{monitor_id}`

---

## 📊 主题架构

```
NLDF/{line_id}/
├── /{device_type}/                    # 设备数据主题（统一实时）
│   ├── {device_id}/status     # 设备状态
├── alerts/                    # 系统警报主题
│   ├── fault                  # 故障警报
│   └── buffer                 # 缓冲区警报
├── order/                    # 订单管理主题
│   ├── new                    # 新订单
│   └── complete               # 完成订单
├── kpi/                       # KPI数据主题
│   └── update                 # KPI更新
└── agent/                     # 代理通信主题
    ├── command            # 命令主题
    └── response           # 响应主题
```

- agent
  - command
    - agv
      - 运动
      - 卸货/拿货

---

## 📝 消息格式

### 标准消息结构

```json
{
  "type": "status|command|response|event|alert",
  "timestamp": 1234567890.123,
  "source": "设备ID或代理ID",
  "req_id": "请求唯一ID（可选）",
  "res_id": "响应唯一ID（可选）",
  "status": "success|failed|in_progress（响应必带）",
  "payload": {
    // 具体数据内容
  },
  "error": "错误信息（可选）",
  "meta": {
    // 额外元数据（可选）
  }
}
```

### 字段说明

- `type`: 消息类型，用于快速识别消息用途
- `timestamp`: 时间戳（秒，支持小数）
- `source`: 消息来源标识
- `req_id`: 请求 ID，命令消息必带，格式：`req_{8位随机字符}`
- `res_id`: 响应 ID，响应消息必带，格式：`res_{8位随机字符}`
- `status`: 响应状态，仅响应消息使用
- `payload`: 消息具体内容
- `error`: 错误信息，出错时使用
- `meta`: 扩展字段，用于传递额外信息

---

## 🏭 设备数据主题

### 1. 设备状态 - `factory/device/{device_id}/status`

**发布者**: 工厂系统  
**订阅者**: Unity 客户端、监控客户端、代理客户端  
**QoS**: 1  
**频率**: 变化驱动（约 500ms 检查一次）

#### 工站状态消息

```json
{
  "type": "status",
  "timestamp": 1234567890.123,
  "source": "StationA",
  "payload": {
    "deviceId": "StationA",
    "deviceType": "station",
    "status": "processing|idle|error|maintenance",
    "utilization": 0.85,
    "bufferLevel": 3,
    "bufferCapacity": 5,
    "faultSymptom": null,
    "processingTime": 12.5,
    "oldStatus": "idle"
  }
}
```

#### 传送带状态消息

```json
{
  "type": "status",
  "timestamp": 1234567890.123,
  "source": "ConveyorAB",
  "payload": {
    "deviceId": "ConveyorAB",
    "deviceType": "conveyor",
    "status": "running|stopped|error",
    "speed": 1.5,
    "loadCount": 2,
    "capacity": 3,
    "direction": "forward|backward"
  }
}
```

### 2. AGV 状态 - `factory/device/agv/{agv_id}/status`

**发布者**: 工厂系统  
**订阅者**: Unity 客户端、监控客户端、代理客户端  
**QoS**: 1  
**频率**: 变化驱动（约 500ms 检查一次）

```json
{
  "type": "status",
  "timestamp": 1234567890.123,
  "source": "AGV_1",
  "payload": {
    "deviceId": "AGV_1",
    "deviceType": "agv",
    "status": "idle|moving|loading|unloading|charging|error",
    "batteryLevel": 85.5,
    "isCharging": false,
    "payloadCount": 2,
    "maxPayload": 3,
    "currentTask": "transport_task_001",
    "destination": "StationB"
  }
}
```

### 3. AGV 位置 - `factory/device/agv/{agv_id}/position`

**发布者**: Unity 实时发布器  
**订阅者**: Unity 客户端、监控客户端  
**QoS**: 0（实时性优先）  
**频率**: 100ms（高频实时更新）

```json
{
  "type": "status",
  "timestamp": 1234567890.123,
  "source": "AGV_1",
  "payload": {
    "deviceId": "AGV_1",
    "position": {
      "x": 15.5,
      "y": 20.3,
      "z": 0.0
    },
    "rotation": {
      "y": 45.0
    },
    "velocity": {
      "x": 0.8,
      "y": 0.6
    },
    "isMoving": true,
    "batteryLevel": 85.5,
    "payloadCount": 2
  }
}
```

### 4. 设备动画 - `factory/device/{device_id}/animation`

**发布者**: Unity 实时发布器  
**订阅者**: Unity 客户端  
**QoS**: 1  
**频率**: 事件驱动

```json
{
  "type": "event",
  "timestamp": 1234567890.123,
  "source": "StationA",
  "payload": {
    "deviceId": "StationA",
    "animationType": "start_processing|stop_processing|fault_alarm|repair_complete|buffer_increase|buffer_decrease",
    "duration": 2.0,
    "parameters": {
      "newStatus": "processing",
      "bufferLevel": 4,
      "processingTime": 15.0
    }
  }
}
```

---

## 🚨 系统事件主题

### 1. 故障警报 - `factory/alerts/fault`

**发布者**: 工厂系统  
**订阅者**: 监控客户端、代理客户端  
**QoS**: 2（可靠性优先）  
**频率**: 事件驱动

```json
{
  "type": "alert",
  "timestamp": 1234567890.123,
  "source": "factory_system",
  "payload": {
    "deviceId": "StationA",
    "faultType": "mechanical|electrical|software|sensor",
    "faultSymptom": "传感器读数异常",
    "severity": "low|medium|high|critical",
    "duration": 125.5,
    "canOperate": false,
    "estimatedRepairTime": 300.0,
    "affectedOperations": ["processing", "buffer_management"]
  }
}
```

### 2. 缓冲区警报 - `factory/alerts/buffer`

**发布者**: 工厂系统  
**订阅者**: 监控客户端、代理客户端  
**QoS**: 1  
**频率**: 事件驱动

```json
{
  "type": "alert",
  "timestamp": 1234567890.123,
  "source": "factory_system",
  "payload": {
    "deviceId": "StationB",
    "alertType": "buffer_full|buffer_empty|buffer_warning",
    "bufferType": "input|output",
    "currentLevel": 5,
    "capacity": 5,
    "threshold": 4,
    "affectedDevices": ["StationB", "AGV_1"]
  }
}
```

### 3. 新订单 - `factory/orders/new`

**发布者**: 订单生成器  
**订阅者**: 监控客户端、代理客户端  
**QoS**: 1  
**频率**: 事件驱动

```json
{
  "type": "event",
  "timestamp": 1234567890.123,
  "source": "order_generator",
  "payload": {
    "orderId": "ORDER_001",
    "productType": "ProductA",
    "quantity": 5,
    "priority": "normal|high|urgent",
    "deadline": 1234571490.123,
    "requiredStations": ["StationA", "StationB", "StationC"],
    "estimatedDuration": 180.0
  }
}
```

### 4. 订单完成 - `factory/orders/complete`

**发布者**: 工厂系统  
**订阅者**: 监控客户端、代理客户端  
**QoS**: 1  
**频率**: 事件驱动

```json
{
  "type": "event",
  "timestamp": 1234567890.123,
  "source": "factory_system",
  "payload": {
    "orderId": "ORDER_001",
    "productType": "ProductA",
    "completedQuantity": 5,
    "actualDuration": 175.8,
    "quality": "passed|failed|rework",
    "completionRate": 1.0,
    "defectCount": 0
  }
}
```

### 5. KPI 更新 - `factory/kpi/update`

**发布者**: KPI 计算器  
**订阅者**: 监控客户端、代理客户端  
**QoS**: 1  
**频率**: 定时（30 秒）

```json
{
  "type": "event",
  "timestamp": 1234567890.123,
  "source": "kpi_calculator",
  "payload": {
    "updateType": "realtime|hourly|daily",
    "timeRange": {
      "start": 1234567890.123,
      "end": 1234567920.123
    },
    "metrics": {
      "overallEfficiency": 0.85,
      "throughput": 12.5,
      "utilization": {
        "StationA": 0.92,
        "StationB": 0.78,
        "StationC": 0.88
      },
      "defectRate": 0.02,
      "onTimeDelivery": 0.95,
      "energyConsumption": 145.8
    }
  }
}
```

---

## 🎯 代理通信主题

### 1. 代理命令 - `factory/agent/{agent_id}/command`

**发布者**: 代理客户端  
**订阅者**: 工厂系统  
**QoS**: 1  
**频率**: 按需

#### 测试命令

```json
{
  "type": "command",
  "timestamp": 1234567890.123,
  "source": "player_001",
  "req_id": "req_abc12345",
  "payload": {
    "action": "test_command",
    "target": "StationA",
    "params": {
      "param1": "value1",
      "param2": 42,
      "testType": "connectivity"
    }
  }
}
```

#### AGV 移动命令

```json
{
  "type": "command",
  "timestamp": 1234567890.123,
  "source": "player_001",
  "req_id": "req_def67890",
  "payload": {
    "action": "move_agv",
    "target": "AGV_1",
    "params": {
      "destination_id": "P1",
      "priority": "normal",
      "timeout": 60.0
    }
  }
}
```

#### AGV 动作序列命令

```json
{
  "type": "command",
  "timestamp": 1234567890.123,
  "source": "player_001",
  "req_id": "req_ghi11111",
  "payload": {
    "action": "agv_action_sequence",
    "target": "AGV_1",
    "params": {
      "actions": [
        {
          "type": "move",
          "args": {
            "target_pos": [15, 20]
          }
        },
        {
          "type": "load",
          "args": {
            "device_id": "StationA",
            "buffer_type": "output",
            "item_count": 2
          }
        },
        {
          "type": "move",
          "args": {
            "target_pos": [25, 20]
          }
        },
        {
          "type": "unload",
          "args": {
            "device_id": "StationB",
            "buffer_type": "input"
          }
        }
      ],
      "timeout": 120.0
    }
  }
}
```

#### 设备检查命令

```json
{
  "type": "command",
  "timestamp": 1234567890.123,
  "source": "player_001",
  "req_id": "req_jkl22222",
  "payload": {
    "action": "inspect_device",
    "target": "StationA",
    "params": {
      "inspection_type": "status|detailed|diagnostics"
    }
  }
}
```

#### 维护请求命令

```json
{
  "type": "command",
  "timestamp": 1234567890.123,
  "source": "player_001",
  "req_id": "req_mno33333",
  "payload": {
    "action": "request_maintenance",
    "target": "StationB",
    "params": {
      "maintenance_type": "preventive|corrective|emergency",
      "description": "定期维护检查",
      "urgency": "low|medium|high"
    }
  }
}
```

### 2. 代理响应 - `factory/agent/{agent_id}/response`

**发布者**: 工厂系统  
**订阅者**: 对应的代理客户端  
**QoS**: 1  
**频率**: 命令响应

#### 命令确认响应

```json
{
  "type": "response",
  "timestamp": 1234567890.123,
  "source": "factory_system",
  "req_id": "req_abc12345",
  "res_id": "res_xyz98765",
  "status": "in_progress",
  "payload": {
    "message": "命令已接收: test_command",
    "data": {
      "command_received": true,
      "estimated_duration": 5.0
    }
  }
}
```

#### 命令完成响应

```json
{
  "type": "response",
  "timestamp": 1234567891.123,
  "source": "factory_system",
  "req_id": "req_abc12345",
  "res_id": "res_xyz98766",
  "status": "success",
  "payload": {
    "message": "测试命令执行成功",
    "data": {
      "target": "StationA",
      "result": "连接正常",
      "execution_time": 4.8
    }
  }
}
```

#### 命令进度响应（AGV 动作序列）

```json
{
  "type": "response",
  "timestamp": 1234567892.123,
  "source": "factory_system",
  "req_id": "req_ghi11111",
  "res_id": "res_pqr44444",
  "status": "in_progress",
  "payload": {
    "message": "执行动作 2/4: load",
    "data": {
      "progress": 0.5,
      "current_action": "load",
      "completed_actions": ["move"],
      "remaining_actions": ["move", "unload"]
    }
  }
}
```

#### 命令失败响应

```json
{
  "type": "response",
  "timestamp": 1234567893.123,
  "source": "factory_system",
  "req_id": "req_def67890",
  "res_id": "res_stu55555",
  "status": "failed",
  "payload": {
    "message": "AGV移动失败: 目标位置不可达",
    "data": {
      "error_code": "PATH_NOT_FOUND",
      "target": "AGV_1",
      "destination": "P1"
    }
  },
  "error": "目标位置P1当前不可达，路径被阻塞"
}
```

---

## 📡 QoS 策略

| 主题类型                           | QoS 级别 | 原因                 |
| ---------------------------------- | -------- | -------------------- |
| AGV 位置 (`agv/{id}/position`)     | 0        | 实时性优先，允许丢失 |
| 设备状态 (`device/{id}/status`)    | 1        | 平衡可靠性和性能     |
| 设备动画 (`device/{id}/animation`) | 1        | 确保动画事件送达     |
| 故障警报 (`alerts/fault`)          | 2        | 可靠性优先，确保送达 |
| 缓冲区警报 (`alerts/buffer`)       | 1        | 重要但可容忍偶尔丢失 |
| 订单事件 (`orders/*`)              | 1        | 确保业务数据可靠     |
| KPI 更新 (`kpi/update`)            | 1        | 统计数据需要可靠     |
| 代理命令 (`agent/{id}/command`)    | 1        | 确保命令可靠传输     |
| 代理响应 (`agent/{id}/response`)   | 1        | 确保响应可靠送达     |

---

## 💡 使用示例

### Python 客户端示例

```python
import paho.mqtt.client as mqtt
import json
import time
import uuid

class FactoryMQTTClient:
    def __init__(self, client_id, broker_host="localhost", broker_port=1883):
        self.client_id = client_id
        self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # 连接MQTT Broker
        self.client.connect(broker_host, broker_port, 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        print(f"Connected with result code {rc}")

        # 订阅所有设备状态
        self.client.subscribe("factory/device/+/status", qos=1)

        # 订阅AGV位置（如果需要）
        self.client.subscribe("factory/device/agv/+/position", qos=0)

        # 订阅警报
        self.client.subscribe("factory/alerts/+", qos=1)

        # 订阅响应（如果是代理客户端）
        if self.client_id.startswith("agent_"):
            agent_id = self.client_id.replace("agent_", "")
            self.client.subscribe(f"factory/agent/{agent_id}/response", qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            topic = msg.topic

            print(f"收到消息: {topic}")
            print(f"类型: {data.get('type')}")
            print(f"来源: {data.get('source')}")
            print(f"时间: {data.get('timestamp')}")

            if topic.endswith("/status"):
                self._handle_device_status(data)
            elif topic.endswith("/position"):
                self._handle_agv_position(data)
            elif "/alerts/" in topic:
                self._handle_alert(data)
            elif topic.endswith("/response"):
                self._handle_response(data)

        except Exception as e:
            print(f"消息处理错误: {e}")

    def _handle_device_status(self, data):
        payload = data.get("payload", {})
        device_id = payload.get("deviceId")
        status = payload.get("status")
        device_type = payload.get("deviceType", "unknown")

        print(f"设备状态更新: {device_id} ({device_type}) -> {status}")

        if device_type == "agv":
            battery = payload.get("batteryLevel", 0)
            print(f"  电量: {battery}%")
        elif device_type == "station":
            utilization = payload.get("utilization", 0)
            buffer_level = payload.get("bufferLevel", 0)
            print(f"  利用率: {utilization:.1%}, 缓冲区: {buffer_level}")

    def _handle_agv_position(self, data):
        payload = data.get("payload", {})
        device_id = payload.get("deviceId")
        position = payload.get("position", {})
        is_moving = payload.get("isMoving", False)

        print(f"AGV位置更新: {device_id} -> ({position.get('x')}, {position.get('y')}) 移动中: {is_moving}")

    def _handle_alert(self, data):
        payload = data.get("payload", {})
        device_id = payload.get("deviceId")
        alert_type = payload.get("faultType") or payload.get("alertType")

        print(f"🚨 警报: {device_id} - {alert_type}")

    def _handle_response(self, data):
        req_id = data.get("req_id")
        status = data.get("status")
        message = data.get("payload", {}).get("message")

        print(f"📤 命令响应: {req_id} - {status}")
        print(f"  消息: {message}")

    def send_command(self, action, target, params=None):
        """发送命令"""
        if not self.client_id.startswith("agent_"):
            print("只有代理客户端可以发送命令")
            return

        agent_id = self.client_id.replace("agent_", "")
        req_id = f"req_{uuid.uuid4().hex[:8]}"

        command = {
            "type": "command",
            "timestamp": time.time(),
            "source": agent_id,
            "req_id": req_id,
            "payload": {
                "action": action,
                "target": target,
                "params": params or {}
            }
        }

        topic = f"factory/agent/{agent_id}/command"
        self.client.publish(topic, json.dumps(command), qos=1)

        print(f"🎯 发送命令: {action} -> {target} (请求ID: {req_id})")
        return req_id

# 使用示例
if __name__ == "__main__":
    # 创建代理客户端
    agent = FactoryMQTTClient("agent_player_001")

    # 等待连接
    time.sleep(2)

    # 发送测试命令
    agent.send_command("test_command", "StationA", {"param1": "test_value"})

    # 发送AGV移动命令
    agent.send_command("move_agv", "AGV_1", {"destination_id": "P1"})

    # 发送设备检查命令
    agent.send_command("inspect_device", "StationB")

    # 保持运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("断开连接...")
        agent.client.loop_stop()
        agent.client.disconnect()
```

### JavaScript 客户端示例

```javascript
const mqtt = require("mqtt");

class FactoryMQTTClient {
  constructor(clientId, brokerUrl = "mqtt://localhost:1883") {
    this.clientId = clientId;
    this.client = mqtt.connect(brokerUrl, {
      clientId: clientId,
      keepalive: 60,
      clean: true,
    });

    this.setupEventHandlers();
  }

  setupEventHandlers() {
    this.client.on("connect", () => {
      console.log("Connected to MQTT broker");

      // 订阅主题
      this.client.subscribe("factory/device/+/status", { qos: 1 });
      this.client.subscribe("factory/device/agv/+/position", { qos: 0 });
      this.client.subscribe("factory/alerts/+", { qos: 1 });

      // 代理客户端订阅响应
      if (this.clientId.startsWith("agent_")) {
        const agentId = this.clientId.replace("agent_", "");
        this.client.subscribe(`factory/agent/${agentId}/response`, { qos: 1 });
      }
    });

    this.client.on("message", (topic, message) => {
      try {
        const data = JSON.parse(message.toString());
        this.handleMessage(topic, data);
      } catch (error) {
        console.error("Message parsing error:", error);
      }
    });

    this.client.on("error", (error) => {
      console.error("MQTT Error:", error);
    });
  }

  handleMessage(topic, data) {
    console.log(`收到消息: ${topic}`);
    console.log(`类型: ${data.type}, 来源: ${data.source}`);

    if (topic.endsWith("/status")) {
      this.handleDeviceStatus(data);
    } else if (topic.endsWith("/position")) {
      this.handleAGVPosition(data);
    } else if (topic.includes("/alerts/")) {
      this.handleAlert(data);
    } else if (topic.endsWith("/response")) {
      this.handleResponse(data);
    }
  }

  handleDeviceStatus(data) {
    const payload = data.payload || {};
    const deviceId = payload.deviceId;
    const status = payload.status;
    const deviceType = payload.deviceType || "unknown";

    console.log(`设备状态更新: ${deviceId} (${deviceType}) -> ${status}`);

    if (deviceType === "agv") {
      console.log(`  电量: ${payload.batteryLevel}%`);
    } else if (deviceType === "station") {
      console.log(
        `  利用率: ${(payload.utilization * 100).toFixed(1)}%, 缓冲区: ${
          payload.bufferLevel
        }`
      );
    }
  }

  handleAGVPosition(data) {
    const payload = data.payload || {};
    const deviceId = payload.deviceId;
    const position = payload.position || {};
    const isMoving = payload.isMoving;

    console.log(
      `AGV位置更新: ${deviceId} -> (${position.x}, ${position.y}) 移动中: ${isMoving}`
    );
  }

  handleAlert(data) {
    const payload = data.payload || {};
    const deviceId = payload.deviceId;
    const alertType = payload.faultType || payload.alertType;

    console.log(`🚨 警报: ${deviceId} - ${alertType}`);
  }

  handleResponse(data) {
    const reqId = data.req_id;
    const status = data.status;
    const message = data.payload?.message;

    console.log(`📤 命令响应: ${reqId} - ${status}`);
    console.log(`  消息: ${message}`);
  }

  sendCommand(action, target, params = {}) {
    if (!this.clientId.startsWith("agent_")) {
      console.log("只有代理客户端可以发送命令");
      return;
    }

    const agentId = this.clientId.replace("agent_", "");
    const reqId = `req_${Math.random().toString(36).substr(2, 8)}`;

    const command = {
      type: "command",
      timestamp: Date.now() / 1000,
      source: agentId,
      req_id: reqId,
      payload: {
        action: action,
        target: target,
        params: params,
      },
    };

    const topic = `factory/agent/${agentId}/command`;
    this.client.publish(topic, JSON.stringify(command), { qos: 1 });

    console.log(`🎯 发送命令: ${action} -> ${target} (请求ID: ${reqId})`);
    return reqId;
  }

  disconnect() {
    this.client.end();
  }
}

// 使用示例
const agent = new FactoryMQTTClient("agent_player_001");

// 等待连接后发送命令
setTimeout(() => {
  agent.sendCommand("test_command", "StationA", { param1: "test_value" });
  agent.sendCommand("move_agv", "AGV_1", { destination_id: "P1" });
  agent.sendCommand("inspect_device", "StationB");
}, 2000);

// 优雅关闭
process.on("SIGINT", () => {
  console.log("断开连接...");
  agent.disconnect();
  process.exit(0);
});
```

---

## ⚠️ 错误处理

### 常见错误类型

#### 1. 连接错误

```json
{
  "error_code": "CONNECTION_FAILED",
  "message": "无法连接到MQTT Broker",
  "details": {
    "broker": "localhost:1883",
    "reason": "Connection refused"
  }
}
```

#### 2. 权限错误

```json
{
  "error_code": "PERMISSION_DENIED",
  "message": "没有权限订阅此主题",
  "details": {
    "topic": "factory/admin/config",
    "client_id": "agent_player_001"
  }
}
```

#### 3. 命令错误

```json
{
  "type": "response",
  "req_id": "req_abc12345",
  "res_id": "res_error_001",
  "status": "failed",
  "payload": {
    "message": "未知命令类型"
  },
  "error": "不支持的命令: unknown_command"
}
```

#### 4. 参数错误

```json
{
  "type": "response",
  "req_id": "req_def67890",
  "res_id": "res_error_002",
  "status": "failed",
  "payload": {
    "message": "命令参数不正确"
  },
  "error": "缺少必需参数: destination_id"
}
```

### 错误处理建议

1. **连接重试机制**：实现指数退避重连
2. **消息验证**：发送前验证 JSON 格式和必需字段
3. **超时处理**：设置合理的命令超时时间
4. **日志记录**：记录所有错误和重要事件
5. **状态同步**：定期同步客户端状态以确保一致性

---