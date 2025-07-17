#!/usr/bin/env python3
"""
真实的质量检测器测试脚本
使用实际的layout，通过AGV移动产品，测试完整的流程
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simpy
from typing import Dict, List
from src.simulation.entities.product import Product
from src.simulation.entities.agv import AGV
from src.simulation.entities.station import Station
from src.simulation.entities.quality_checker import QualityChecker
from src.simulation.entities.conveyor import Conveyor
from src.game_logic.order_generator import OrderGenerator
from src.simulation.factory import Factory
from src.utils.config_loader import load_factory_config

class RealFlowTester:
    """真实流程测试器"""
    def __init__(self):
        self.env = simpy.Environment()
        self.agvs: List[AGV] = []
        self.quality_history: Dict[str, List[Dict]] = {}
        
        # 加载布局
        self.config = load_factory_config()
        self.factory = Factory(self.config)
        
    def track_quality(self, product: Product, location: str, event: str):
        """跟踪产品质量变化"""
        if product.id not in self.quality_history:
            self.quality_history[product.id] = []
            
        self.quality_history[product.id].append({
            'time': self.env.now,
            'location': location,
            'event': event,
            'quality_score': round(product.quality_score * 100, 2),
            'rework_count': product.rework_count,
            'factors': product.quality_factors.copy(),
            'current_location': product.current_location,
            'process_step': product.process_step
        })
        
    def print_product_journey(self, product_id: str):
        """打印产品旅程"""
        if product_id not in self.quality_history:
            return
            
        print(f"\n{'='*100}")
        print(f"产品 {product_id} 完整旅程")
        print(f"{'='*100}")
        print(f"{'时间':>8} | {'位置':^15} | {'事件':^20} | {'质量':>6} | {'返工':>4} | {'当前位置':^15} | 质量因素")
        print(f"{'-'*100}")
        
        for record in self.quality_history[product_id]:
            factors = record['factors']
            factors_str = f"缺陷:{factors['processing_defects']:.3f} 损伤:{factors['handling_damage']:.3f} 改善:{factors['rework_improvement']:.3f}"
            print(f"{record['time']:>8.1f} | {record['location']:^15} | {record['event']:^20} | {record['quality_score']:>5.1f}% | {record['rework_count']:>4} | {record['current_location']:^15} | {factors_str}")

    def test_product_flow(self, product_type: str, quality_preset: str = "normal"):
        """测试单个产品的完整流程"""
        print(f"\n\n{'='*80}")
        print(f"测试产品类型: {product_type}, 质量预设: {quality_preset}")
        print(f"{'='*80}")
        
        # 创建产品
        product = Product(product_type, f"test_order_{product_type}")
        
        # 设置初始质量
        if quality_preset == "good":
            product.quality_score = 0.92
        elif quality_preset == "defective":
            product.quality_score = 0.75
            product.quality_factors["processing_defects"] = 0.10
            product._update_quality_score()
        elif quality_preset == "bad":
            product.quality_score = 0.65
            product.quality_factors["processing_defects"] = 0.20
            product._update_quality_score()
            
        print(f"创建产品 {product.id}, 初始质量分数: {product.quality_score*100:.1f}%")
        print(f"工艺路线: {' -> '.join(product.PROCESS_ROUTES[product_type])}")
        
        # 跟踪初始状态
        self.track_quality(product, "RawMaterial", "产品创建")
        
        # 开始流程
        yield self.env.process(self.process_product_through_route(product))
        
        # 打印旅程
        self.print_product_journey(product.id)
        
        return product

    def process_product_through_route(self, product: Product):
        """处理产品通过整个工艺路线"""
        route = product.PROCESS_ROUTES[product.product_type]
        current_location = product.current_location
        
        # 找一个空闲的AGV
        agv = self.factory.agvs['AGV_1']  # 简化：使用第一个AGV
        
        while True:
            # 获取下一个目标位置
            next_location = product.get_next_expected_location()
            
            if not next_location:
                print(f"[{self.env.now:.1f}] ✅ 产品 {product.id} 已完成所有工序")
                break
                
            print(f"\n[{self.env.now:.1f}] 🚚 AGV准备移动产品从 {current_location} 到 {next_location}")
            
            # 检查移动是否合法
            can_move, reason = product.next_move_checker(self.env.now, next_location)
            print(f"移动检查: {'✓' if can_move else '✗'} - {reason}")
            
            if not can_move:
                print(f"[{self.env.now:.1f}] ❌ 无法移动到 {next_location}")
                break
                
            # AGV取货
            if current_location in self.factory.stations:
                station = self.factory.stations[current_location]
                if hasattr(station, 'output_buffer'):
                    # 从output buffer取货
                    yield station.output_buffer.put(product)
                    product_from_buffer = yield station.output_buffer.get()
                    print(f"[{self.env.now:.1f}] 📦 AGV从 {current_location} 的output buffer取货")
            
            # 更新产品位置（模拟AGV运输）
            yield self.env.timeout(5)  # 运输时间
            product.update_location(next_location, self.env.now)
            self.track_quality(product, next_location, "到达")
            
            # 在工站处理
            if next_location in self.factory.stations:
                station = self.factory.stations[next_location]
                
                if isinstance(station, QualityChecker):
                    # 质检站处理
                    print(f"\n[{self.env.now:.1f}] 🔍 开始质量检测")
                    self.track_quality(product, next_location, "质检开始")
                    
                    # 放入质检站buffer
                    yield station.buffer.put(product)
                    
                    # 触发质检处理
                    yield self.env.timeout(10)  # 检测时间
                    
                    # 执行质检决策
                    decision = station._make_simple_decision(product)
                    print(f"[{self.env.now:.1f}] 质检决策: {decision.value}")
                    print(f"当前质量分数: {product.quality_score*100:.1f}%")
                    
                    if decision.value == "pass":
                        station.stats["passed_count"] += 1
                        product.complete_inspection(self.env.now, product.quality_status)
                        self.track_quality(product, next_location, "质检通过")
                        
                    elif decision.value == "scrap":
                        station.stats["scrapped_count"] += 1
                        product.quality_status = product.QualityStatus.SCRAP
                        self.track_quality(product, next_location, "质检报废")
                        print(f"[{self.env.now:.1f}] ❌ 产品报废")
                        break
                        
                    elif decision.value == "rework":
                        station.stats["reworked_count"] += 1
                        last_station = station._get_last_processing_station(product)
                        if last_station:
                            product.start_rework(self.env.now, last_station)
                            self.track_quality(product, next_location, f"返工到{last_station}")
                            print(f"[{self.env.now:.1f}] 🔄 产品需要返工到 {last_station}")
                            # 更新当前位置，准备返工
                            current_location = next_location
                            continue
                        else:
                            print(f"[{self.env.now:.1f}] ❌ 无法确定返工站点，产品报废")
                            break
                            
                else:
                    # 普通工站处理
                    print(f"\n[{self.env.now:.1f}] 🏭 {next_location} 开始加工")
                    self.track_quality(product, next_location, "加工开始")
                    
                    # 放入工站buffer
                    yield station.buffer.put(product)
                    
                    # 处理时间
                    processing_time = 15
                    yield self.env.timeout(processing_time)
                    
                    # 记录加工
                    product.process_at_station(next_location, self.env.now)
                    
                    # 加工可能引入缺陷（基于工站类型）
                    if next_location == "StationA":
                        defect_prob = 0.05
                    elif next_location == "StationB":
                        defect_prob = 0.08
                    elif next_location == "StationC":
                        defect_prob = 0.10
                    else:
                        defect_prob = 0.05
                        
                    import random
                    if random.random() < defect_prob:
                        defect = random.uniform(0.02, 0.05)
                        product.quality_factors["processing_defects"] += defect
                        product._update_quality_score()
                        print(f"[{self.env.now:.1f}] ⚠️ 加工引入缺陷: -{defect:.2%}")
                        
                    self.track_quality(product, next_location, "加工完成")
                    print(f"[{self.env.now:.1f}] ✅ 加工完成，质量分数: {product.quality_score*100:.1f}%")
            
            # 更新当前位置
            current_location = next_location

    def run_tests(self):
        """运行所有测试"""
        def test_scenarios():
            # 测试1: P1正常产品
            p1_good = yield self.env.process(self.test_product_flow("P1", "good"))
            
            yield self.env.timeout(10)
            
            # 测试2: P1缺陷产品（需要返工）
            p1_defective = yield self.env.process(self.test_product_flow("P1", "defective"))
            
            yield self.env.timeout(10)
            
            # 测试3: P1严重缺陷产品（报废）
            p1_bad = yield self.env.process(self.test_product_flow("P1", "bad"))
            
            yield self.env.timeout(10)
            
            # 测试4: P3正常产品（展示标准双重加工流程）
            p3_good = yield self.env.process(self.test_product_flow("P3", "good"))
            
            yield self.env.timeout(10)
            
            # 测试5: P3缺陷产品（质检返工）
            p3_defective = yield self.env.process(self.test_product_flow("P3", "defective"))
            
            # 打印总结
            print(f"\n\n{'='*80}")
            print("测试总结")
            print(f"{'='*80}")
            print(f"共测试 {len(self.quality_history)} 个产品")
            
            # 打印质检站统计
            for qc in self.factory.stations.values():
                if isinstance(qc, QualityChecker):
                stats = qc.get_simple_stats()
                print(f"\n{qc.id} 统计:")
                print(f"  - 检测总数: {stats['inspected']}")
                print(f"  - 通过: {stats['passed']} ({stats['pass_rate']}%)")
                print(f"  - 返工: {stats['reworked']} ({stats['rework_rate']}%)")
                print(f"  - 报废: {stats['scrapped']} ({stats['scrap_rate']}%)")
        
        self.env.process(test_scenarios())
        self.env.run(until=500)

def main():
    """主函数"""
    import random
    random.seed(42)  # 保证可重复性
    
    tester = RealFlowTester()
    tester.run_tests()

if __name__ == "__main__":
    main()