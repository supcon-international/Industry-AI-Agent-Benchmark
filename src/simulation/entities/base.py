# simulation/entities/base.py
import simpy
from enum import Enum
from typing import Tuple

from config.schemas import DeviceStatus

class Device:
    """
    Base class for all simulated devices in the factory.

    This class provides common attributes and methods that all devices,
    such as stations, AGVs, and conveyors, will inherit.

    Attributes:
        env (simpy.Environment): The simulation environment.
        id (str): The unique identifier for the device.
        status (DeviceStatus): The current operational status of the device.
        position (Tuple[int, int]): The (x, y) coordinates of the device in the factory layout.
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int]):
        if not isinstance(env, simpy.Environment):
            raise ValueError("env must be a valid simpy.Environment object.")
        
        self.env = env
        self.id = id
        self.status = DeviceStatus.IDLE
        self.position = position

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.id}', status='{self.status.value}')"

    def set_status(self, new_status: DeviceStatus):
        """
        Updates the device's status and logs the change.
        """
        if self.status != new_status:
            # In a real implementation, we would use the logger here.
            print(f"[{self.env.now:.2f}] {self.id}: Status changed from {self.status.value} to {new_status.value}")
            self.status = new_status

# Example of a more specific base class that could inherit from Device
class Vehicle(Device):
    """
    Base class for all mobile entities, like AGVs.
    It can be extended with attributes like speed, battery, etc.
    """
    def __init__(self, env: simpy.Environment, id: str, position: Tuple[int, int], speed_mps: float):
        super().__init__(env, id, position)
        self.speed_mps = speed_mps # meters per second 