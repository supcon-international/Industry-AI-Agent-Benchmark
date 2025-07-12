# simulation/entities/warehouse.py
import simpy
import random
from typing import Dict, Tuple, Optional

from src.simulation.entities.station import Station
from src.simulation.entities.product import Product

class RawMaterial(Station):
    """
    Raw material warehouse - the starting point of the production line
    Function:
    1. Unlimited(large enough) raw material supply (according to order generation)
    2. Create various types of raw materials/semi-finished products
    3. Supply raw materials to AGV for transportation to stations
    4. Do not process any products
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str = "RawMaterial",
        position: Tuple[int, int] = (5, 20),
        buffer_size: int = 100,  # 大容量buffer
        mqtt_client=None
    ):
        # dont need processing time for raw material warehouse
        super().__init__(
            env=env,
            id=id,
            position=position,
            buffer_size=buffer_size,
            processing_times={},  # no processing time
            mqtt_client=mqtt_client
        )
        
        # override device type
        self.device_type = "raw_material"
        
        # statistics data
        self.stats = {
            "materials_supplied": 0,
            "total_supply_time": 0.0,
        }
        
        print(f"[{self.env.now:.2f}] 🏭 {self.id}: 原料仓库已就绪，缓冲区容量: {buffer_size}")

    def run(self):
        """原料仓库不进行主动处理，只等待AGV取货"""
        # 空循环，不自动处理产品，避免继承Station的自动加工行为
        while True:
            yield self.env.timeout(60)  # 每分钟检查一次即可

    def create_raw_material(self, product_type: str, order_id: str) -> Product:
        """创建原料产品"""
        product = Product(product_type, order_id)
        
        # 记录统计
        self.stats["materials_supplied"] += 1
        
        # 记录原料供应历史
        product.add_history(self.env.now, f"Raw material created at {self.id}")
        
        print(f"[{self.env.now:.2f}] 🔧 {self.id}: 创建原料 {product.id} (类型: {product_type})")
        # 原料仓库容量大，直接put不会阻塞，保持简单
        self.buffer.put(product)
        return product

    def is_full(self) -> bool:
        return self.get_buffer_level() >= self.buffer_size

    def get_material_stats(self) -> Dict:
        """获取原料仓库统计信息"""
        return {
            **self.stats,
            "buffer_level": self.get_buffer_level(),
            "buffer_utilization": self.get_buffer_level() / self.buffer_size,
            "can_supply": True  # always can supply
        }

class Warehouse(Station):
    """
    Finished product warehouse - the ending point of the production line
    Function:
    1. Unlimited storage of finished products
    2. Receive products transported by AGV
    3. Statistics of finished product information and quality data
    4. Do not process any products
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str = "Warehouse",
        position: Tuple[int, int] = (85, 20),
        mqtt_client=None
    ):
        # finished product warehouse dont need processing time
        super().__init__(
            env=env,
            id=id,
            position=position,
            processing_times={},  # no processing time
            mqtt_client=mqtt_client
        )
        self.buffer = simpy.Store(env)
        # override device type
        self.device_type = "warehouse"
        
        # statistics data
        self.stats = {
            "products_received": 0,
            "products_dispatched": 0,
            "quality_summary": {"P1": 0, "P2": 0, "P3": 0},
            "storage_duration_total": 0.0,
            "last_dispatch_time": 0.0
        }
        
        print(f"[{self.env.now:.2f}] 🏪 {self.id}: 成品仓库已就绪")

    def run(self):
        """成品仓库不进行主动处理，只接收成品"""
        # empty loop, dont process product, avoid auto processing behavior from Station
        while True:
            yield self.env.timeout(60)  # check every minute

    def add_product_to_buffer(self, product: Product):
        """AGV向成品仓库投放产品"""
        # SimPy Store自动处理容量，无需手动检查
        yield self.buffer.put(product)
        
        # record finished product statistics
        self.stats["products_received"] += 1
        self.stats["quality_summary"][product.product_type] += 1
        
        # record product completion history
        product.add_history(self.env.now, f"Stored in warehouse {self.id}")
        print(f"[{self.env.now:.2f}] 📦 {self.id}: Store finished product {product.id} (type: {product.product_type})")

        return True

    def get_warehouse_stats(self) -> Dict:
        """获取成品仓库统计信息"""
        return {
            **self.stats,
            "buffer_level": self.get_buffer_level(),
        }

    def get_quality_summary(self) -> Dict:
        """获取成品质量汇总"""
        total = sum(self.stats["quality_summary"].values())
        if total == 0:
            return {"total": 0, "P1_ratio": 0, "P2_ratio": 0, "P3_ratio": 0}
        
        return {
            "total": total,
            "P1_count": self.stats["quality_summary"]["P1"],
            "P2_count": self.stats["quality_summary"]["P2"],
            "P3_count": self.stats["quality_summary"]["P3"],
            "P1_ratio": round(self.stats["quality_summary"]["P1"] / total * 100, 1),
            "P2_ratio": round(self.stats["quality_summary"]["P2"] / total * 100, 1),
            "P3_ratio": round(self.stats["quality_summary"]["P3"] / total * 100, 1)
        }