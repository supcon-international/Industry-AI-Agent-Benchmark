# src/simulation/entities/quality_checker.py
import simpy
import random
from typing import Dict, Tuple
from enum import Enum

from config.schemas import DeviceStatus
from src.simulation.entities.station import Station
from src.simulation.entities.product import Product, QualityStatus

class SimpleDecision(Enum):
    """简化的质量检测决策"""
    PASS = "pass"           # 通过
    SCRAP = "scrap"         # 报废
    REWORK = "rework"       # 返工 (回到上一个工站)

class QualityChecker(Station):
    """
    简化版质量检测站 - 只保留核心功能
    
    核心逻辑：
    1. 基于产品质量分数做出简单决策
    2. 通过/报废/返工三种结果
    3. 最小化配置参数
    4. 增加output_buffer，满时阻塞并告警
    """
    
    def __init__(
        self,
        env: simpy.Environment,
        id: str,
        position: Tuple[int, int],
        buffer_size: int = 1,
        processing_times: Dict[str, Tuple[int, int]] = {},
        pass_threshold: float = 80.0,  # 合格阈值
        scrap_threshold: float = 40.0,  # 报废阈值
        output_buffer_capacity: int = 5,  # 新增，output buffer容量
        fault_system=None  # 新增，便于buffer满时告警
    ):
        # 默认检测时间
        if processing_times is None:
            processing_times = {
                "P1": (10, 15),
                "P2": (12, 18), 
                "P3": (10, 15)
            }
        
        super().__init__(env, id, position, buffer_size, processing_times)
        
        self.pass_threshold = pass_threshold
        self.scrap_threshold = scrap_threshold
        
        # output buffer for storing passed/finished products, blocked when full
        self.output_buffer_capacity = output_buffer_capacity
        self.output_buffer = simpy.Store(env, capacity=output_buffer_capacity)
        self.fault_system = fault_system
        
        # 简单统计
        self.inspected_count = 0
        self.passed_count = 0
        self.scrapped_count = 0
        self.reworked_count = 0
        
        print(f"[{self.env.now:.2f}] 🔍 {self.id}: Simple quality checker ready (pass≥{pass_threshold}%, scrap≤{scrap_threshold}%)")
        self.env.process(self.run())
        
    def process_product(self, product: Product):
        """简化的产品检测流程"""
        if not self.can_operate():
            print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 设备不可用")
            yield self.buffer.put(product)
            return
            
        self.set_status(DeviceStatus.PROCESSING)
        self.inspected_count += 1
        
        # 记录开始检测
        product.process_at_station(self.id, self.env.now)
        product.start_inspection(self.env.now)
        
        print(f"[{self.env.now:.2f}] 🔍 {self.id}: 检测产品 {product.id}")
        
        # 执行检测 (简化为单一过程)
        yield self.env.process(self._simple_inspection(product))
        
        # 做出决策
        decision = self._make_simple_decision(product)
        
        # 执行决策
        yield self.env.process(self._execute_simple_decision(product, decision))

        self.set_status(DeviceStatus.IDLE)

    def _simple_inspection(self, product: Product):
        """简化的检测过程"""
        # 获取检测时间
        min_time, max_time = self.processing_times.get(product.product_type, (10, 15))
        inspection_time = random.uniform(min_time, max_time)
        
        # 考虑设备效率
        efficiency = self.performance_metrics.efficiency_rate / 100.0
        actual_time = inspection_time / efficiency
        
        print(f"[{self.env.now:.2f}] 🔍 {self.id}: 检测中... (预计{actual_time:.1f}s)")
        yield self.env.timeout(actual_time)
        
        # 更新产品质量状态 (基于现有质量分数)
        quality_score = product.quality_metrics.overall_score
        
        if quality_score >= self.pass_threshold:
            product.quality_status = QualityStatus.UNKNOWN  # 改用UNKNOWN表示通过
        elif quality_score <= self.scrap_threshold:
            product.quality_status = QualityStatus.SCRAP  
        else:
            product.quality_status = QualityStatus.MAJOR_DEFECT
            
        product.complete_inspection(self.env.now, product.quality_status)

    def _make_simple_decision(self, product: Product) -> SimpleDecision:
        """简化的决策逻辑"""
        # 如果已经返工过，直接报废
        if product.rework_count > 0:
            return SimpleDecision.SCRAP
            
        # 基于质量状态决策
        if product.quality_status == QualityStatus.UNKNOWN:  # UNKNOWN表示通过
            return SimpleDecision.PASS
        elif product.quality_status == QualityStatus.SCRAP:
            return SimpleDecision.SCRAP
        else:
            # 有缺陷但可以返工
            return SimpleDecision.REWORK

    def _execute_simple_decision(self, product: Product, decision: SimpleDecision):
        """执行决策，合格品放入output_buffer，满则阻塞并告警"""
        if decision == SimpleDecision.PASS:
            self.passed_count += 1
            print(f"[{self.env.now:.2f}] ✅ {self.id}: 产品 {product.id} 通过检测")
            # 放入output buffer，满则阻塞
            while len(self.output_buffer.items) >= self.output_buffer_capacity:
                if self.fault_system:
                    self.fault_system.report_buffer_full(self.id, "output_buffer")
                yield self.env.timeout(1.0)
            yield self.output_buffer.put(product)
            print(f"[{self.env.now:.2f}] 📦 {self.id}: 产品 {product.id} 放入output buffer，等待AGV/人工搬运")
        elif decision == SimpleDecision.SCRAP:
            self.scrapped_count += 1
            print(f"[{self.env.now:.2f}] ❌ {self.id}: 产品 {product.id} 报废")
        elif decision == SimpleDecision.REWORK:
            self.reworked_count += 1
            # 简单返工：回到最后一个加工工站
            last_station = self._get_last_processing_station(product)
            if last_station:
                product.start_rework(self.env.now, last_station)
                print(f"[{self.env.now:.2f}] 🔄 {self.id}: 产品 {product.id} 返工到 {last_station}")
            else:
                print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法确定返工工站，产品报废")
        # # 简单的处理延时
        # yield self.env.timeout(1.0)

    def _get_last_processing_station(self, product: Product) -> str:
        """获取产品最后处理的工站 (排除QualityCheck)"""
        processing_stations = [s for s in product.processing_stations if s != self.id]
        return processing_stations[-1] if processing_stations else ""

    def get_simple_stats(self) -> Dict:
        """获取简化的统计信息"""
        total = self.inspected_count
        if total == 0:
            return {"inspected": 0, "pass_rate": 0, "scrap_rate": 0, "rework_rate": 0}
            
        return {
            "inspected": total,
            "passed": self.passed_count,
            "scrapped": self.scrapped_count, 
            "reworked": self.reworked_count,
            "pass_rate": round(self.passed_count / total * 100, 1),
            "scrap_rate": round(self.scrapped_count / total * 100, 1),
            "rework_rate": round(self.reworked_count / total * 100, 1),
            "buffer_level": self.get_buffer_level()
        }

    def reset_stats(self):
        """重置统计数据"""
        self.inspected_count = 0
        self.passed_count = 0
        self.scrapped_count = 0
        self.reworked_count = 0 