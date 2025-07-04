# src/simulation/entities/product.py
import uuid
import random
from typing import List, Tuple, Dict, Optional
from enum import Enum
from dataclasses import dataclass

class QualityStatus(Enum):
    """产品质量状态"""
    UNKNOWN = "unknown"          # 未检测
    MAJOR_DEFECT = "major_defect"  # 严重缺陷，需返工
    SCRAP = "scrap"             # 报废

class DefectType(Enum):
    """缺陷类型"""
    DIMENSIONAL = "dimensional"   # 尺寸偏差
    SURFACE = "surface"          # 表面缺陷
    MATERIAL = "material"        # 材料缺陷
    ASSEMBLY = "assembly"        # 装配缺陷

@dataclass
class QualityDefect:
    """质量缺陷记录"""
    defect_type: DefectType
    severity: float  # 严重程度 0-100
    description: str
    station_id: str  # 产生缺陷的工站
    detected_at: float  # 检测时间

@dataclass
class QualityMetrics:
    """产品质量指标"""
    dimensional_accuracy: float = 100.0    # 尺寸精度 (%)
    surface_quality: float = 100.0         # 表面质量 (%)
    material_integrity: float = 100.0      # 材料完整性 (%)
    assembly_precision: float = 100.0      # 装配精度 (%)
    overall_score: float = 100.0           # 综合评分 (%)

class Product:
    """
    Represents a single product unit being manufactured in the factory.
    
    Attributes:
        id (str): A unique identifier for the product instance.
        product_type (str): The type of the product (e.g., 'P1', 'P2').
        order_id (str): The ID of the order this product belongs to.
        history (List[Tuple[float, str]]): A log of events for this product.
        quality_status (QualityStatus): Current quality status
        quality_metrics (QualityMetrics): Quality metrics
        defects (List[QualityDefect]): Defect records
        processing_stations (List[str]): Records of stations processed
        rework_count (int): 返工次数
        inspection_count (int): 检测次数
    """
    def __init__(self, product_type: str, order_id: str):
        self.id: str = f"prod_{uuid.uuid4().hex[:8]}"
        self.product_type: str = product_type
        self.order_id: str = order_id
        self.history: List[Tuple[float, str]] = []
        
        # 质量相关属性
        self.quality_status: QualityStatus = QualityStatus.UNKNOWN
        self.quality_metrics: QualityMetrics = QualityMetrics()
        self.defects: List[QualityDefect] = []
        self.processing_stations: List[str] = []
        self.rework_count: int = 0
        self.inspection_count: int = 0
        
        # Initialize the base quality of the product (random variation)
        self._initialize_base_quality()

    def __repr__(self) -> str:
        return f"Product(id='{self.id}', type='{self.product_type}', quality='{self.quality_status.value}')"

    def _initialize_base_quality(self):
        """Initialize the base quality metrics of the product"""
        # The base quality has a slight random variation (simulating material differences)
        base_variance = random.uniform(0.95, 1.05)
        self.quality_metrics.dimensional_accuracy *= base_variance
        self.quality_metrics.surface_quality *= base_variance
        self.quality_metrics.material_integrity *= base_variance
        self.quality_metrics.assembly_precision *= base_variance
        self._update_overall_score()

    def add_history(self, timestamp: float, event: str):
        """Adds a new event to the product's history log."""
        self.history.append((timestamp, event))
        
    def process_at_station(self, station_id: str, timestamp: float):
        """记录在工站的处理"""
        self.processing_stations.append(station_id)
        self.add_history(timestamp, f"Processed at {station_id}")
        
        # 工站处理可能影响质量
        self._apply_processing_effects(station_id)
        
    def _apply_processing_effects(self, station_id: str):
        """应用工站处理对质量的影响"""
        # 不同工站对不同质量指标的影响
        effects = {
            "StationA": {"dimensional_accuracy": 0.02},
            "StationB": {"surface_quality": 0.03, "material": 0.01},
            "StationC": {"assembly_precision": 0.02, "dimensional_accuracy": 0.01}
        }
        
        if station_id in effects:
            station_effects = effects[station_id]
            
            # 应用随机质量变化（模拟加工过程中的变异）
            for metric, variance in station_effects.items():
                change = random.uniform(-variance, variance)
                
                if metric == "dimensional_accuracy":
                    self.quality_metrics.dimensional_accuracy += change * 100
                elif metric == "surface_quality":
                    self.quality_metrics.surface_quality += change * 100
                elif metric == "assembly_precision":
                    self.quality_metrics.assembly_precision += change * 100
                elif metric == "material":
                    self.quality_metrics.material_integrity += change * 100
                    
        # 确保质量指标在合理范围内
        self._clamp_quality_metrics()
        self._update_overall_score()
        
    def _clamp_quality_metrics(self):
        """确保质量指标在0-100范围内"""
        self.quality_metrics.dimensional_accuracy = max(0, min(100, self.quality_metrics.dimensional_accuracy))
        self.quality_metrics.surface_quality = max(0, min(100, self.quality_metrics.surface_quality))
        self.quality_metrics.material_integrity = max(0, min(100, self.quality_metrics.material_integrity))
        self.quality_metrics.assembly_precision = max(0, min(100, self.quality_metrics.assembly_precision))
        
    def _update_overall_score(self):
        """更新综合质量评分"""
        # 加权平均计算综合评分
        weights = {
            "dimensional": 0.3,
            "surface": 0.2,
            "material": 0.25,
            "assembly": 0.25
        }
        
        self.quality_metrics.overall_score = (
            weights["dimensional"] * self.quality_metrics.dimensional_accuracy +
            weights["surface"] * self.quality_metrics.surface_quality +
            weights["material"] * self.quality_metrics.material_integrity +
            weights["assembly"] * self.quality_metrics.assembly_precision
        )
        
    def add_defect(self, defect: QualityDefect):
        """添加缺陷记录"""
        self.defects.append(defect)
        
        # 缺陷影响对应的质量指标
        impact = defect.severity * 0.1  # 严重程度转换为质量影响
        
        if defect.defect_type == DefectType.DIMENSIONAL:
            self.quality_metrics.dimensional_accuracy -= impact
        elif defect.defect_type == DefectType.SURFACE:
            self.quality_metrics.surface_quality -= impact
        elif defect.defect_type == DefectType.MATERIAL:
            self.quality_metrics.material_integrity -= impact
        elif defect.defect_type == DefectType.ASSEMBLY:
            self.quality_metrics.assembly_precision -= impact
            
        self._clamp_quality_metrics()
        self._update_overall_score()
        
    def start_inspection(self, timestamp: float):
        """开始质量检测"""
        self.inspection_count += 1
        self.add_history(timestamp, f"Quality inspection started (#{self.inspection_count})")
        
    def complete_inspection(self, timestamp: float, result: QualityStatus):
        """完成质量检测"""
        self.quality_status = result
        self.add_history(timestamp, f"Quality inspection completed: {result.value}")
        
    def start_rework(self, timestamp: float, target_station: str):
        """开始返工"""
        self.rework_count += 1
        self.quality_status = QualityStatus.UNKNOWN  # 返工后重新检测
        self.add_history(timestamp, f"Rework started (#{self.rework_count}) -> {target_station}")
        
    def get_quality_summary(self) -> Dict:
        """获取质量摘要信息"""
        return {
            "id": self.id,
            "product_type": self.product_type,
            "quality_status": self.quality_status.value,
            "overall_score": round(self.quality_metrics.overall_score, 2),
            "defect_count": len(self.defects),
            "rework_count": self.rework_count,
            "inspection_count": self.inspection_count,
            "processing_stations": self.processing_stations.copy(),
            "major_defects": [d for d in self.defects if d.severity >= 50],
            "can_rework": self.rework_count < 3 and len([d for d in self.defects if d.severity >= 80]) == 0
        }