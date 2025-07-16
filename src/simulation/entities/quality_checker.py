# src/simulation/entities/quality_checker.py
import simpy
import random
from typing import Dict, Tuple
from enum import Enum

from config.schemas import DeviceStatus, StationStatus
from src.simulation.entities.station import Station
from src.simulation.entities.product import Product, QualityStatus
from config.topics import get_station_status_topic

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
        mqtt_client=None
    ):
        # 默认检测时间
        if processing_times is None:
            processing_times = {
                "P1": (10, 15),
                "P2": (12, 18), 
                "P3": (10, 15)
            }
        
        # Initialize output buffer before calling super().__init__() 
        # since publish_status() is called in parent's __init__
        self.pass_threshold = pass_threshold
        self.scrap_threshold = scrap_threshold
        self.output_buffer_capacity = output_buffer_capacity
        self.output_buffer = simpy.Store(env, capacity=output_buffer_capacity)
        
        super().__init__(env, id, position, buffer_size, processing_times, downstream_conveyor=None, mqtt_client=mqtt_client)
        
        # 简单统计
        self.stats = {
            "products_processed": 0,
            "products_scrapped": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "inspected_count": 0,
            "passed_count": 0,
            "scrapped_count": 0,
            "reworked_count": 0
        }
        
        print(f"[{self.env.now:.2f}] 🔍 {self.id}: Simple quality checker ready (pass≥{self.pass_threshold}%, scrap≤{self.scrap_threshold}%)")
        # The run process is already started by the parent Station class
        
    def publish_status(self, **kwargs):
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            return
            
        status_data = StationStatus(
            timestamp=self.env.now,
            source_id=self.id,
            status=self.status,
            buffer=[p.id for p in self.buffer.items],
            stats=self.stats,
            output_buffer=[p.id for p in self.output_buffer.items]
        )
        topic = get_station_status_topic(self.id)
        self.mqtt_client.publish(topic, status_data.model_dump_json(), retain=True)

    def process_product(self, product: Product):
        """
        Quality check process following Station's timeout-get-put pattern.
        """
        try:
            # Check if the device can operate
            if not self.can_operate():
                print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法处理产品，设备不可用")
                return

            self.set_status(DeviceStatus.PROCESSING)

            # Record processing start and get processing time
            min_time, max_time = self.processing_times.get(product.product_type, (10, 15))
            processing_time = random.uniform(min_time, max_time)
            
            # Apply efficiency and fault impacts
            efficiency_factor = getattr(self.performance_metrics, 'efficiency_rate', 100.0) / 100.0
            actual_processing_time = processing_time / efficiency_factor
            
            print(f"[{self.env.now:.2f}] 🔍 {self.id}: 检测产品中... (预计{actual_processing_time:.1f}s)")
            
            # The actual processing work (timeout-get pattern like Station)
            yield self.env.timeout(actual_processing_time)
            product = yield self.buffer.get()
            
            # Record inspection start and process
            product.process_at_station(self.id, self.env.now)
            product.start_inspection(self.env.now)
            
            # Update statistics upon successful completion
            self.stats["products_processed"] += 1
            self.stats["inspected_count"] += 1
            self.stats["total_processing_time"] += actual_processing_time
            self.stats["average_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["products_processed"]
            )
            
            # Perform quality inspection
            decision = self._perform_quality_inspection(product)
            
            # Processing finished successfully
            print(f"[{self.env.now:.2f}] {self.id}: Finished inspecting product {product.id} (实际耗时: {actual_processing_time:.1f}s)")
            
            # Set to IDLE now, as core processing is done.
            self.set_status(DeviceStatus.IDLE)
            
            # Execute decision (equivalent to transfer_product_to_next_stage)
            yield self.env.process(self._execute_quality_decision(product, decision))

        except simpy.Interrupt as e:
            print(f"[{self.env.now:.2f}] ⚠️ {self.id}: Inspection of product {product.id} was interrupted: {e.cause}")
            if product not in self.buffer.items:
                # 产品已取出，说明检测时间已经完成，应该继续流转
                print(f"[{self.env.now:.2f}] 🚚 {self.id}: 产品 {product.id} 已检测完成，继续流转")
                decision = self._perform_quality_inspection(product)
                yield self.env.process(self._execute_quality_decision(product, decision))
            else:
                # 产品还在buffer中，说明在timeout期间被中断，等待下次处理
                print(f"[{self.env.now:.2f}] ⏸️  {self.id}: 产品 {product.id} 检测被中断，留在buffer中")
        finally:
            # Clear the action handle once the process is complete or interrupted
            self.action = None

    def _perform_quality_inspection(self, product: Product) -> SimpleDecision:
        """Perform quality inspection and determine decision"""
        # Update product quality status based on existing quality score
        quality_score = product.quality_metrics.overall_score
        
        if quality_score >= self.pass_threshold:
            product.quality_status = QualityStatus.UNKNOWN  # UNKNOWN表示通过
        elif quality_score <= self.scrap_threshold:
            product.quality_status = QualityStatus.SCRAP  
        else:
            product.quality_status = QualityStatus.MAJOR_DEFECT
            
        product.complete_inspection(self.env.now, product.quality_status)
        
        # Make decision
        return self._make_simple_decision(product)

    def _execute_quality_decision(self, product: Product, decision: SimpleDecision):
        """Execute quality decision (equivalent to _transfer_product_to_next_stage)"""
        # Set status to INTERACTING before the potentially blocking operations
        self.set_status(DeviceStatus.INTERACTING)
        
        if decision == SimpleDecision.PASS:
            self.stats["passed_count"] += 1
            print(f"[{self.env.now:.2f}] ✅ {self.id}: 产品 {product.id} 通过检测")
            
            # Check if output buffer is full and report if needed
            if len(self.output_buffer.items) >= self.output_buffer_capacity:
                self.report_buffer_full("output_buffer")
            
            # Put product into output buffer (may block if full)
            yield self.output_buffer.put(product)
            print(f"[{self.env.now:.2f}] 📦 {self.id}: 产品 {product.id} 放入output buffer，等待AGV/人工搬运")
            
        elif decision == SimpleDecision.SCRAP:
            self.stats["scrapped_count"] += 1
            self.stats["products_scrapped"] += 1
            yield self.env.process(self._handle_product_scrap(product, "quality_inspection_failed"))
            
        elif decision == SimpleDecision.REWORK:
            self.stats["reworked_count"] += 1
            # 简单返工：回到最后一个加工工站
            last_station = self._get_last_processing_station(product)
            if last_station:
                product.start_rework(self.env.now, last_station)
                print(f"[{self.env.now:.2f}] 🔄 {self.id}: 产品 {product.id} 返工到 {last_station}")
                # TODO: Implement actual rework transfer logic
            else:
                print(f"[{self.env.now:.2f}] ⚠️  {self.id}: 无法确定返工工站，产品报废")
                yield self.env.process(self._handle_product_scrap(product, "rework_failed"))
        
        # Set status back to IDLE after the operation is complete
        self.set_status(DeviceStatus.IDLE)

    def _handle_product_scrap(self, product, reason: str):
        """Handle product scrapping due to quality issues"""
        from src.simulation.entities.product import QualityStatus, QualityDefect, DefectType
        
        # Set product status to scrapped
        product.quality_status = QualityStatus.SCRAP
        
        # Add defect record
        defect = QualityDefect(
            defect_type=DefectType.SURFACE,  # Use SURFACE for quality inspection issues
            severity=95.0,  # High severity for scrapped products
            description=f"Product scrapped at {self.id} due to {reason}",
            station_id=self.id,
            detected_at=self.env.now
        )
        product.add_defect(defect)
        
        print(f"[{self.env.now:.2f}] ❌ {self.id}: 产品 {product.id} 因{reason}报废")
        
        # Report scrapped product through base class
        self.report_device_error("product_scrap", f"Product {product.id} scrapped due to {reason}")
        
        # Simulate scrap handling time
        yield self.env.timeout(2.0)

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

    def _get_last_processing_station(self, product: Product) -> str:
        """获取产品最后处理的工站 (排除QualityCheck)"""
        processing_stations = [s for s in product.processing_stations if s != self.id]
        return processing_stations[-1] if processing_stations else ""

    def get_simple_stats(self) -> Dict:
        """获取简化的统计信息"""
        total = self.stats["inspected_count"]
        if total == 0:
            return {"inspected": 0, "pass_rate": 0, "scrap_rate": 0, "rework_rate": 0}
            
        return {
            "inspected": total,
            "passed": self.stats["passed_count"],
            "scrapped": self.stats["scrapped_count"], 
            "reworked": self.stats["reworked_count"],
            "pass_rate": round(self.stats["passed_count"] / total * 100, 1),
            "scrap_rate": round(self.stats["scrapped_count"] / total * 100, 1),
            "rework_rate": round(self.stats["reworked_count"] / total * 100, 1),
            "buffer_level": self.get_buffer_level()
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            "products_processed": 0,
            "products_scrapped": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "inspected_count": 0,
            "passed_count": 0,
            "scrapped_count": 0,
            "reworked_count": 0
        }
    
    def add_product_to_outputbuffer(self, product: Product):
        """Add a product to its output buffer (used by AGV for delivery)"""
        yield self.output_buffer.put(product)
        print(f"[{self.env.now:.2f}] 📦 {self.id}: 运出产品 {product.id} 到output buffer")
        return True