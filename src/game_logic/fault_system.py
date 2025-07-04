# src/game_logic/fault_system.py
import random
import simpy
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from config.schemas import DeviceDetailedStatus, DiagnosisResult, DeviceStatus

@dataclass
class FaultDefinition:
    """Fault definition from the PRD symptom diagnosis manual."""
    symptom: str
    root_causes: List[str]
    repair_commands: List[str]
    base_repair_times: List[float]  # seconds
    error_penalty_multiplier: float = 2.0
    # 新增：诊断错误可能影响的关联设备
    related_devices: Optional[List[str]] = None
    # 新增：诊断错误可能引发的次级故障
    secondary_faults: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.related_devices is None:
            self.related_devices = []
        if self.secondary_faults is None:
            self.secondary_faults = []

class FaultType(Enum):
    STATION_VIBRATION = "station_vibration"
    PRECISION_DEGRADATION = "precision_degradation" 
    AGV_PATH_BLOCKED = "agv_path_blocked"
    AGV_BATTERY_DRAIN = "agv_battery_drain"
    EFFICIENCY_ANOMALY = "efficiency_anomaly"

class FaultSystem:
    """
    Manages fault injection and diagnosis according to PRD 2.5.
    Maintains device state and provides inspection data to agents.
    """
    
    def __init__(self, env: simpy.Environment, factory_devices: Dict):
        self.env = env
        self.active_faults: Dict[str, 'ActiveFault'] = {}
        self.devices_under_repair: Dict[str, float] = {}  # device_id -> repair_end_time
        self.factory_devices = factory_devices  # 工厂中所有设备的引用
        self.device_relationship_map = self._build_device_relationships()
        
        # Fault definitions from PRD Table 2.5
        self.fault_definitions = {
            FaultType.STATION_VIBRATION: FaultDefinition(
                symptom="主轴振动异常",
                root_causes=["bearing_wear", "bolt_loose"],
                repair_commands=["replace_bearing", "tighten_bolts"],
                base_repair_times=[120.0, 30.0],
                error_penalty_multiplier=2.0,
                related_devices=["adjacent_stations"],  # 可能影响相邻工站
                secondary_faults=["precision_degradation"]  # 可能引发精度问题
            ),
            FaultType.PRECISION_DEGRADATION: FaultDefinition(
                symptom="加工精度下降", 
                root_causes=["tool_dulling", "calibration_drift"],
                repair_commands=["replace_tool", "recalibrate"],
                base_repair_times=[60.0, 90.0],
                error_penalty_multiplier=1.5,
                related_devices=["quality_check"],  # 影响质检设备
                secondary_faults=["efficiency_anomaly"]
            ),
            FaultType.AGV_PATH_BLOCKED: FaultDefinition(
                symptom="AGV路径阻塞",
                root_causes=["temporary_obstacle", "positioning_failure"],
                repair_commands=["reroute_agv", "reboot_device"],
                base_repair_times=[75.0, 60.0],
                error_penalty_multiplier=1.2,
                related_devices=["other_agvs"],  # 影响其他AGV路径
                secondary_faults=["agv_battery_drain"]
            ),
            FaultType.AGV_BATTERY_DRAIN: FaultDefinition(
                symptom="AGV电量突降",
                root_causes=["battery_aging", "high_load_task"],
                repair_commands=["force_charge", "optimize_schedule"],
                base_repair_times=[30.0, 0.0],
                error_penalty_multiplier=1.0,
                related_devices=["charging_stations"],
                secondary_faults=[]
            ),
            FaultType.EFFICIENCY_ANOMALY: FaultDefinition(
                symptom="效率异常降低",
                root_causes=["software_overheating", "insufficient_lubricant"],
                repair_commands=["reduce_frequency", "add_lubricant"],
                base_repair_times=[450.0, 120.0],
                error_penalty_multiplier=1.8,
                related_devices=["cooling_system"],
                secondary_faults=["station_vibration"]
            )
        }
        
        # Fault injection parameters
        self.fault_injection_interval = (60, 180)  # 1-3 minutes between faults
        self.fault_duration_range = (120, 600)  # 2-10 minutes if not repaired
        
        # Start fault injection process
        self.env.process(self.run_fault_injection())

    def _build_device_relationships(self) -> Dict[str, List[str]]:
        """构建设备关系映射，用于处理关联错误"""
        # 简化的设备关系映射，实际应用中可以更复杂
        relationships = {
            "StationA": ["StationB", "AGV_1"],
            "StationB": ["StationA", "StationC", "AGV_1", "AGV_2"],
            "StationC": ["StationB", "QualityCheck", "AGV_2"],
            "QualityCheck": ["StationC"],
            "AGV_1": ["StationA", "StationB"],
            "AGV_2": ["StationB", "StationC"]
        }
        return relationships

    def inspect_device(self, device_id: str) -> Optional[DeviceDetailedStatus]:
        """
        检查设备详细状态（inspect功能）
        返回设备的当前状态信息，供玩家分析学习
        """
        if device_id not in self.factory_devices:
            print(f"[{self.env.now:.2f}] ❌ 设备 {device_id} 不存在")
            return None
        
        device = self.factory_devices[device_id]
        detailed_status = device.get_detailed_status()
        
        print(f"[{self.env.now:.2f}] 🔍 检查设备 {device_id}:")
        print(f"   - 状态: {detailed_status.current_status}")
        print(f"   - 温度: {detailed_status.temperature}°C")
        print(f"   - 振动水平: {detailed_status.vibration_level} mm/s")
        print(f"   - 效率: {detailed_status.efficiency_rate}%")
        print(f"   - 运行时间: {detailed_status.operating_hours}h")
        
        if detailed_status.has_fault:
            print(f"   - ⚠️  故障症状: {detailed_status.fault_symptom}")
        
        if device_id in self.devices_under_repair:
            remaining_time = self.devices_under_repair[device_id] - self.env.now
            print(f"   - 🔧 正在维修中，剩余时间: {remaining_time:.1f}s")
        
        # 设备特定信息
        if detailed_status.device_type == "station":
            if detailed_status.precision_level is not None:
                print(f"   - 加工精度: {detailed_status.precision_level}%")
            if detailed_status.tool_wear_level is not None:
                print(f"   - 刀具磨损: {detailed_status.tool_wear_level}%")
            if detailed_status.lubricant_level is not None:
                print(f"   - 润滑油水平: {detailed_status.lubricant_level}%")
        elif detailed_status.device_type == "agv":
            if detailed_status.battery_level is not None:
                print(f"   - 电池电量: {detailed_status.battery_level}%")
            if detailed_status.position_accuracy is not None:
                print(f"   - 定位精度: {detailed_status.position_accuracy}%")
        
        return detailed_status

    def run_fault_injection(self):
        """Main fault injection loop."""
        while True:
            # Wait before next fault injection
            wait_time = random.uniform(*self.fault_injection_interval)
            yield self.env.timeout(wait_time)
            
            # Inject a random fault
            self.inject_random_fault()

    def inject_random_fault(self, target_device: Optional[str] = None, fault_type: Optional[FaultType] = None):
        """Inject a fault into the system."""
        if fault_type is None:
            fault_type = random.choice(list(FaultType))
        
        if target_device is None:
            # Select a random device to affect
            if fault_type in [FaultType.AGV_PATH_BLOCKED, FaultType.AGV_BATTERY_DRAIN]:
                available_agvs = [dev_id for dev_id in self.factory_devices.keys() if "AGV" in dev_id]
                target_device = random.choice(available_agvs) if available_agvs else "AGV_1"
            else:
                available_stations = [dev_id for dev_id in self.factory_devices.keys() if "Station" in dev_id or "Quality" in dev_id]
                target_device = random.choice(available_stations) if available_stations else "StationA"
        
        # Check if device already has an active fault or is under repair
        if target_device in self.active_faults:
            print(f"[{self.env.now:.2f}] ⚠️  Device {target_device} already has active fault, skipping injection")
            return
            
        if target_device in self.devices_under_repair:
            print(f"[{self.env.now:.2f}] 🔧 Device {target_device} is under repair, skipping fault injection")
            return
        
        # Create and inject the fault
        fault = self._create_fault(target_device, fault_type)
        self.active_faults[target_device] = fault
        
        # 🔥 关键修复：应用故障效果到设备，设置正确的故障状态
        if target_device in self.factory_devices:
            device = self.factory_devices[target_device]
            device.apply_fault_effects(fault_type.value)
            device.fault_symptom = fault.symptom
            # 🔥 设置设备为错误状态，使其无法操作
            device.set_status(DeviceStatus.ERROR)
        
        print(f"[{self.env.now:.2f}] 💥 Fault injected on {target_device}")
        print(f"   - Symptom: {fault.symptom}")
        print(f"   - Hidden root cause: {fault.actual_root_cause}")
        print(f"   - 🚫 设备已锁定，无法操作")
        
        # Start fault process
        self.env.process(self._run_fault(fault))

    def _create_fault(self, device_id: str, fault_type: FaultType) -> 'ActiveFault':
        """Create an active fault instance."""
        definition = self.fault_definitions[fault_type]
        
        # Randomly select actual root cause (hidden from agent)
        cause_index = random.randint(0, len(definition.root_causes) - 1)
        actual_root_cause = definition.root_causes[cause_index]
        correct_repair_command = definition.repair_commands[cause_index]
        correct_repair_time = definition.base_repair_times[cause_index]
        
        return ActiveFault(
            device_id=device_id,
            fault_type=fault_type,
            symptom=definition.symptom,
            actual_root_cause=actual_root_cause,
            correct_repair_command=correct_repair_command,
            correct_repair_time=correct_repair_time,
            start_time=self.env.now,
            definition=definition
        )

    def _run_fault(self, fault: 'ActiveFault'):
        """Run a fault until it's repaired or times out."""
        # Generate auto-recovery timeout
        max_duration = random.uniform(*self.fault_duration_range)
        
        try:
            # Wait for either repair or timeout
            yield self.env.timeout(max_duration)
            
            # If we reach here, the fault wasn't repaired in time
            if fault.device_id in self.active_faults:
                print(f"[{self.env.now:.2f}] ⏰ Fault on {fault.device_id} auto-recovered after {max_duration:.1f}s")
                self._clear_fault(fault.device_id)
                
        except simpy.Interrupt:
            # Fault was repaired by maintenance command
            pass

    def get_device_symptom(self, device_id: str) -> Optional[str]:
        """Get the visible symptom for a device (what agents can observe)."""
        if device_id in self.active_faults:
            return self.active_faults[device_id].symptom
        return None

    def is_device_under_repair(self, device_id: str) -> bool:
        """检查设备是否正在维修中"""
        if device_id in self.devices_under_repair:
            if self.env.now < self.devices_under_repair[device_id]:
                return True
            else:
                # 维修时间结束，清理记录
                del self.devices_under_repair[device_id]
        return False

    def handle_maintenance_request(self, device_id: str, maintenance_type: str, agent_id: str = "unknown") -> DiagnosisResult:
        """
        处理维修请求，包含完整的诊断逻辑和维修锁定
        Returns DiagnosisResult with detailed information.
        """
        # 🔥 关键修复：检查设备是否正在维修中
        if self.is_device_under_repair(device_id):
            remaining_time = self.devices_under_repair[device_id] - self.env.now
            print(f"[{self.env.now:.2f}] 🔒 设备 {device_id} 正在维修中，剩余时间: {remaining_time:.1f}s")
            return DiagnosisResult(
                device_id=device_id,
                diagnosis_command=maintenance_type,
                is_correct=False,
                repair_time=0.0,
                penalty_applied=False,
                affected_devices=[],
                can_skip=False
            )
        
        if device_id not in self.active_faults:
            print(f"[{self.env.now:.2f}] ❌ No fault on {device_id} to repair")
            return DiagnosisResult(
                device_id=device_id,
                diagnosis_command=maintenance_type,
                is_correct=False,
                repair_time=0.0,
                penalty_applied=False,
                affected_devices=[],
                can_skip=False
            )
        
        fault = self.active_faults[device_id]
        is_correct = maintenance_type == fault.correct_repair_command
        
        if is_correct:
            # 正确诊断
            repair_time = fault.correct_repair_time
            print(f"[{self.env.now:.2f}] ✅ 正确诊断 {device_id}: {maintenance_type}")
            print(f"   - 修复时间: {repair_time:.1f}s")
            
            # 🔥 关键修复：设置维修锁定
            repair_end_time = self.env.now + repair_time
            self.devices_under_repair[device_id] = repair_end_time
            
            # 设置设备为维修状态
            if device_id in self.factory_devices:
                self.factory_devices[device_id].set_status(DeviceStatus.MAINTENANCE)
            
            result = DiagnosisResult(
                device_id=device_id,
                diagnosis_command=maintenance_type,
                is_correct=True,
                repair_time=repair_time,
                penalty_applied=False,
                affected_devices=[],
                can_skip=True  # 正确诊断可以选择跳过等待
            )
            
            # 开始修复过程
            self.env.process(self._complete_repair(fault, repair_time, True))
            
        else:
            # 错误诊断 - 应用惩罚
            penalty_time = fault.correct_repair_time * fault.definition.error_penalty_multiplier
            affected_devices = self._apply_diagnosis_penalty(device_id, fault)
            
            print(f"[{self.env.now:.2f}] ❌ 错误诊断 {device_id}: {maintenance_type}")
            print(f"   - 期望命令: {fault.correct_repair_command}")
            print(f"   - 惩罚时间: {penalty_time:.1f}s")
            if affected_devices:
                print(f"   - 影响设备: {', '.join(affected_devices)}")
            
            # 🔥 关键修复：错误诊断也设置维修锁定（惩罚期间）
            penalty_end_time = self.env.now + penalty_time
            self.devices_under_repair[device_id] = penalty_end_time
            
            result = DiagnosisResult(
                device_id=device_id,
                diagnosis_command=maintenance_type,
                is_correct=False,
                repair_time=penalty_time,
                penalty_applied=True,
                affected_devices=affected_devices,
                can_skip=True  # 也可以选择跳过惩罚时间
            )
            
            # 冻结设备（额外的惩罚机制）
            if device_id in self.factory_devices:
                self.factory_devices[device_id].freeze_device(penalty_time)
        
            # 开始惩罚过程（设备保持故障状态）
            self.env.process(self._apply_penalty_process(fault, penalty_time))
        
        return result

    def _apply_diagnosis_penalty(self, device_id: str, fault: 'ActiveFault') -> List[str]:
        """
        应用诊断错误的惩罚，可能影响其他设备
        Returns list of affected devices
        """
        affected_devices = []
        definition = fault.definition
        
        # 1. 可能影响关联设备
        if definition.related_devices:
            for related_type in definition.related_devices:
                related_ids = self._get_related_device_ids(device_id, related_type)
                for related_id in related_ids:
                    if random.random() < 0.3:  # 30% 概率影响关联设备
                        self._apply_secondary_effect(related_id)
                        affected_devices.append(related_id)
        
        # 2. 可能引发次级故障
        if definition.secondary_faults and random.random() < 0.4:  # 40% 概率引发次级故障
            secondary_fault_type = random.choice(definition.secondary_faults)
            secondary_target = self._select_secondary_fault_target(device_id)
            if secondary_target and secondary_target not in self.active_faults:
                # 延迟注入次级故障
                self.env.process(self._inject_delayed_fault(secondary_target, secondary_fault_type, 30))
                affected_devices.append(secondary_target)
        
        return affected_devices

    def _get_related_device_ids(self, device_id: str, related_type: str) -> List[str]:
        """根据关系类型获取相关设备ID"""
        if related_type == "adjacent_stations":
            # 获取相邻工站
            return [dev_id for dev_id in self.device_relationship_map.get(device_id, []) 
                    if "Station" in dev_id]
        elif related_type == "other_agvs":
            # 获取其他AGV
            return [dev_id for dev_id in self.factory_devices.keys() 
                    if "AGV" in dev_id and dev_id != device_id]
        elif related_type == "quality_check":
            return ["QualityCheck"]
        elif related_type == "cooling_system":
            return ["CoolingSystem"] if "CoolingSystem" in self.factory_devices else []
        elif related_type == "charging_stations":
            return ["ChargingStation"] if "ChargingStation" in self.factory_devices else []
        
        return []

    def _apply_secondary_effect(self, device_id: str):
        """对设备应用次级效果（非故障，但性能下降）"""
        if device_id in self.factory_devices:
            device = self.factory_devices[device_id]
            # 临时降低效率
            device.performance_metrics.efficiency_rate *= random.uniform(0.7, 0.9)
            print(f"[{self.env.now:.2f}] ⚡ {device_id} 受到次级影响，效率降低")

    def _select_secondary_fault_target(self, original_device: str) -> Optional[str]:
        """选择次级故障的目标设备"""
        related_devices = self.device_relationship_map.get(original_device, [])
        available_targets = [dev for dev in related_devices if dev not in self.active_faults]
        return random.choice(available_targets) if available_targets else None

    def _inject_delayed_fault(self, target_device: str, fault_type: str, delay: float):
        """延迟注入故障"""
        yield self.env.timeout(delay)
        print(f"[{self.env.now:.2f}] 🔗 次级故障触发: {target_device} ({fault_type})")
        
        # 根据字符串转换为枚举
        fault_enum = None
        for ft in FaultType:
            if ft.value == fault_type:
                fault_enum = ft
                break
        
        if fault_enum:
            self.inject_random_fault(target_device, fault_enum)

    def _apply_penalty_process(self, fault: 'ActiveFault', penalty_time: float):
        """执行惩罚过程，设备保持故障状态"""
        yield self.env.timeout(penalty_time)
        
        # 🔥 关键修复：惩罚结束后清理维修锁定
        if fault.device_id in self.devices_under_repair:
            del self.devices_under_repair[fault.device_id]
        
        # 惩罚时间结束后，设备仍有故障，需要正确诊断才能修复
        print(f"[{self.env.now:.2f}] ⏱️  {fault.device_id} 惩罚时间结束，设备仍需正确诊断")

    def _complete_repair(self, fault: 'ActiveFault', repair_time: float, success: bool):
        """🔥 关键修复：完整的维修过程管理"""
        print(f"[{self.env.now:.2f}] 🔧 开始维修 {fault.device_id}，预计时间: {repair_time:.1f}s")
        
        # 维修期间设备完全锁定，无法进行任何操作
        yield self.env.timeout(repair_time)
        
        # 维修完成，清理所有相关状态
        if fault.device_id in self.active_faults:
            self._clear_fault(fault.device_id)
            
        # 🔥 清理维修锁定
        if fault.device_id in self.devices_under_repair:
            del self.devices_under_repair[fault.device_id]
            
            status = "successfully" if success else "with penalties"
        print(f"[{self.env.now:.2f}] ✅ Device {fault.device_id} repaired {status}")

    def _clear_fault(self, device_id: str):
        """清除设备故障并恢复正常状态"""
        if device_id in self.active_faults:
            del self.active_faults[device_id]
        
        if device_id in self.factory_devices:
            device = self.factory_devices[device_id]
            device.clear_fault_effects()
            # 🔥 恢复设备为空闲状态，使其可以正常操作
            device.set_status(DeviceStatus.IDLE)

    def skip_repair_time(self, device_id: str) -> bool:
        """
        跳过修复/惩罚等待时间
        Returns True if skip was successful
        """
        # 清理维修锁定
        if device_id in self.devices_under_repair:
            del self.devices_under_repair[device_id]
            
        if device_id in self.factory_devices:
            device = self.factory_devices[device_id]
            if device.is_frozen():
                device.unfreeze_device()
                print(f"[{self.env.now:.2f}] ⏭️  跳过 {device_id} 的等待时间")
                return True
        
        print(f"[{self.env.now:.2f}] ❌ 无法跳过 {device_id} 的等待时间")
        return False

    def get_available_devices(self) -> List[str]:
        """获取可以操作的设备列表（未冻结且未在维修的设备）"""
        available = []
        for device_id, device in self.factory_devices.items():
            if device.can_operate() and not self.is_device_under_repair(device_id):
                available.append(device_id)
        return available

    def get_fault_stats(self) -> Dict:
        """Get statistics about fault system for KPI calculation."""
        return {
            "active_faults": len(self.active_faults),
            "fault_devices": list(self.active_faults.keys()),
            "devices_under_repair": len(self.devices_under_repair),
            "repair_devices": list(self.devices_under_repair.keys())
        }

@dataclass 
class ActiveFault:
    """Represents an active fault in the system."""
    device_id: str
    fault_type: FaultType
    symptom: str  # Visible to agents
    actual_root_cause: str  # Hidden from agents
    correct_repair_command: str  # What agents should send
    correct_repair_time: float
    start_time: float
    definition: FaultDefinition 