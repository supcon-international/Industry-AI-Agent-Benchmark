# src/game_logic/fault_system.py
import random
import simpy
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

@dataclass
class FaultDefinition:
    """Fault definition from the PRD symptom diagnosis manual."""
    symptom: str
    root_causes: List[str]
    repair_commands: List[str]
    base_repair_times: List[float]  # seconds
    error_penalty_multiplier: float = 2.0

class FaultType(Enum):
    STATION_VIBRATION = "station_vibration"
    PRECISION_DEGRADATION = "precision_degradation" 
    AGV_PATH_BLOCKED = "agv_path_blocked"
    AGV_BATTERY_DRAIN = "agv_battery_drain"
    EFFICIENCY_ANOMALY = "efficiency_anomaly"

class FaultSystem:
    """
    Manages fault injection and diagnosis according to PRD 2.5.
    Provides symptoms to agents, requires proper diagnosis for efficient repair.
    """
    
    def __init__(self, env: simpy.Environment):
        self.env = env
        self.active_faults: Dict[str, 'ActiveFault'] = {}
        
        # Fault definitions from PRD Table 2.5
        self.fault_definitions = {
            FaultType.STATION_VIBRATION: FaultDefinition(
                symptom="主轴振动异常",
                root_causes=["bearing_wear", "bolt_loose"],
                repair_commands=["replace_bearing", "tighten_bolts"],
                base_repair_times=[120.0, 30.0],
                error_penalty_multiplier=2.0
            ),
            FaultType.PRECISION_DEGRADATION: FaultDefinition(
                symptom="加工精度下降", 
                root_causes=["tool_dulling", "calibration_drift"],
                repair_commands=["replace_tool", "recalibrate"],
                base_repair_times=[60.0, 90.0],
                error_penalty_multiplier=1.0  # Special: causes product scrap
            ),
            FaultType.AGV_PATH_BLOCKED: FaultDefinition(
                symptom="AGV路径阻塞",
                root_causes=["temporary_obstacle", "positioning_failure"],
                repair_commands=["reroute_agv", "reboot_device"],
                base_repair_times=[75.0, 60.0],  # Auto-recovery 30-120s avg=75s
                error_penalty_multiplier=1.0  # Special: causes task timeout
            ),
            FaultType.AGV_BATTERY_DRAIN: FaultDefinition(
                symptom="AGV电量突降",
                root_causes=["battery_aging", "high_load_task"],
                repair_commands=["force_charge", "optimize_schedule"],
                base_repair_times=[30.0, 0.0],  # Schedule optimization is instant
                error_penalty_multiplier=1.0
            ),
            FaultType.EFFICIENCY_ANOMALY: FaultDefinition(
                symptom="效率异常降低",
                root_causes=["software_overheating", "insufficient_lubricant"],
                repair_commands=["reduce_frequency", "add_lubricant"],
                base_repair_times=[450.0, 120.0],  # Auto-recovery 300-600s avg=450s
                error_penalty_multiplier=1.0
            )
        }
        
        # Fault injection parameters
        self.fault_injection_interval = (60, 180)  # 1-3 minutes between faults (more frequent for testing)
        self.fault_duration_range = (120, 600)  # 2-10 minutes if not repaired
        
        # Start fault injection process
        self.env.process(self.run_fault_injection())

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
                target_device = random.choice(["AGV_1", "AGV_2"])
            else:
                target_device = random.choice(["StationA", "StationB", "StationC", "QualityCheck"])
        
        # Check if device already has an active fault
        if target_device in self.active_faults:
            print(f"[{self.env.now:.2f}] ⚠️  Device {target_device} already has active fault, skipping injection")
            return
        
        # Create and inject the fault
        fault = self._create_fault(target_device, fault_type)
        self.active_faults[target_device] = fault
        
        print(f"[{self.env.now:.2f}] 💥 Fault injected on {target_device}")
        print(f"   - Symptom: {fault.symptom}")
        print(f"   - Hidden root cause: {fault.actual_root_cause}")
        
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
                del self.active_faults[fault.device_id]
                
        except simpy.Interrupt:
            # Fault was repaired by maintenance command
            pass

    def get_device_symptom(self, device_id: str) -> Optional[str]:
        """Get the visible symptom for a device (what agents can observe)."""
        if device_id in self.active_faults:
            return self.active_faults[device_id].symptom
        return None

    def handle_maintenance_request(self, device_id: str, maintenance_type: str) -> Tuple[bool, float]:
        """
        Handle a maintenance request from an agent.
        Returns (success, repair_time).
        """
        if device_id not in self.active_faults:
            print(f"[{self.env.now:.2f}] ❌ No fault on {device_id} to repair")
            return False, 0.0
        
        fault = self.active_faults[device_id]
        
        # Check if diagnosis is correct
        if maintenance_type == fault.correct_repair_command:
            # Correct diagnosis
            repair_time = fault.correct_repair_time
            success = True
            print(f"[{self.env.now:.2f}] ✅ Correct diagnosis for {device_id}: {maintenance_type}")
            print(f"   - Repair time: {repair_time:.1f}s")
        else:
            # Incorrect diagnosis - apply penalty
            repair_time = fault.correct_repair_time * fault.definition.error_penalty_multiplier
            success = False
            print(f"[{self.env.now:.2f}] ❌ Incorrect diagnosis for {device_id}: {maintenance_type}")
            print(f"   - Expected: {fault.correct_repair_command}")
            print(f"   - Penalty repair time: {repair_time:.1f}s")
        
        # Schedule repair completion
        self.env.process(self._complete_repair(fault, repair_time, success))
        
        return success, repair_time

    def _complete_repair(self, fault: 'ActiveFault', repair_time: float, success: bool):
        """Complete the repair process."""
        yield self.env.timeout(repair_time)
        
        # Remove the fault
        if fault.device_id in self.active_faults:
            del self.active_faults[fault.device_id]
            status = "successfully" if success else "with penalties"
            print(f"[{self.env.now:.2f}] 🔧 Device {fault.device_id} repaired {status}")

    def get_fault_stats(self) -> Dict:
        """Get statistics about fault system for KPI calculation."""
        return {
            "active_faults": len(self.active_faults),
            "fault_devices": list(self.active_faults.keys())
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