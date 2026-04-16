import numpy as np
from baselutils import fclrprint
from math import exp, log
from scipy.sparse import diags
from scipy.sparse import dok_matrix, csr_matrix
class SpatialWeightMatrix:
    """
    根据 GeoObjectsGraph 中的地物关系，计算空间交互权重矩阵。
    w_ij = α_R · ρ_ij^γ · e^{-βd_ij}
    """

    def __init__(self, gamma=0.3,beta=0.15):
        """
        初始化权重计算参数
        :param gamma: 对于重叠实体的面积修正系数，面积幂次系数 γ ∈ (0, 0.5]
        :param beta: 对于相离实体的指数衰减系数，距离衰减系数 β > 0
        """
        self.gamma = gamma  # 面积幂次
        self.beta = beta  # 距离衰减系数
        # 拓扑关系基础权重 α_R ∈ (0, 1]
        self.topology_weights = {
            'contains': 1.0,  # 完全包含关系
            'within': 1.0,  # 完全位于内部
            'equals': 1.0,  # 相等关系
            'overlaps': 0.9,  # 部分重叠
            'touches': 0.8,  # 相邻关系
            'crosses': 0.9,  # 交叉关系
            'disjoint': 0.7  # 相离关系
        }
       # 记录计算统计信息（用于论文分析）
        self.calculation_stats = {
            'total_calculations': 0,
            'weight_distribution': {'high': 0, 'medium': 0, 'low': 0}
        }

    def calculate_weight(self,relation):
        """
        根据地物之间的关系、几何特征和距离，计算关系强度权重 - 论文核心算法公式
        w_ij = α_R · ρ_ij^γ · e^{-βd_ij}
        :param relation: RelObject 实例，包含拓扑、距离、面积等信息
        :return: 关系强度权重值
        """
        self.calculation_stats['total_calculations'] += 1

        # 1. 拓扑权重 α_R
        alpha_R  = self.topology_weights.get(relation.topology, 0.4)

        # # 实体类型增强，类型相同则权重增强
        # if relation.geo_object1.entity_type == relation.geo_object2.entity_type:
        #     alpha_R  *= 1.2

        # 2. 面积修正 ρ_ij^γ
        rho_ij = relation.overlapping_area if relation.overlapping_area and relation.overlapping_area > 0 else 1e-10
        area_correction = rho_ij ** self.gamma

        # 3. 距离衰减 e^{-βd_ij}
        d_ij = relation.normalized_distance if relation.normalized_distance else 1.0
        distance_decay = exp(-self.beta * d_ij)

        # 4. 完整公式计算
        weight = alpha_R * area_correction * distance_decay

        # 5. 确保权重在合理范围内
        weight = max(weight, 1e-6)  # 避免零权重
        weight = min(weight, 1.0)  # 不超过1.0

        # 6. 记录权重分布统计（用于论文实验分析）
        if weight > 0.7:
            self.calculation_stats['weight_distribution']['high'] += 1
        elif weight > 0.3:
            self.calculation_stats['weight_distribution']['medium'] += 1
        else:
            self.calculation_stats['weight_distribution']['low'] += 1

        # 7. 存储计算详情（用于论文方法验证）
        relation.calculation_details = {
            'alpha_R': alpha_R,
            'rho_ij': rho_ij,
            'area_correction': area_correction,
            'd_ij': d_ij,
            'distance_decay': distance_decay,
            'final_weight': weight,
            'formula_used': 'w_ij = α_R · ρ_ij^γ · e^{-βd_ij}'
        }

        fclrprint(
            f"权重计算: {relation.topology} | α_R={alpha_R:.3f} | ρ_ij={rho_ij:.6f} | d_ij={d_ij:.6f} | w={weight:.6f}",
            'c')

        return weight

    def batch_calculate_weights(self, relations):
        """
        批量计算关系权重 - 提高计算效率
        :param relations: RelObject 列表
        :return: 权重列表
        """
        weights = []
        for relation in relations:
            weight = self.calculate_weight(relation)
            weights.append(weight)
        return weights

    def get_calculation_statistics(self):
        """
        获取计算统计信息
        """
        stats = self.calculation_stats.copy()
        if stats['total_calculations'] > 0:
            total = stats['total_calculations']
            stats['weight_percentage'] = {
                'high': stats['weight_distribution']['high'] / total * 100,
                'medium': stats['weight_distribution']['medium'] / total * 100,
                'low': stats['weight_distribution']['low'] / total * 100
            }
        return stats


# 测试代码
if __name__ == '__main__':
    # 创建测试用的关系对象
    class TestRelation:
        def __init__(self, topology, overlapping_area, normalized_distance):
            self.topology = topology
            self.overlapping_area = overlapping_area
            self.normalized_distance = normalized_distance
            self.calculation_details = {}


    # 测试论文中的算法
    print("=== MDSR-KG 空间关系权重计算测试 ===")

    weight_calculator = SpatialWeightMatrix(gamma=0.3, beta=0.15)

    # 测试不同拓扑关系的权重计算
    test_cases = [
        ('contains', 0.8, 0.1),
        ('intersects', 0.3, 0.2),
        ('touches', 0.1, 0.3),
        ('disjoint', 0.0, 0.5)
    ]

    for topology, area, distance in test_cases:
        test_rel = TestRelation(topology, area, distance)
        weight = weight_calculator.calculate_weight(test_rel)
        print(f"拓扑: {topology:10} | 重叠面积: {area:.1f} | 标准化距离: {distance:.1f} | 权重: {weight:.6f}")

    # 输出统计信息
    print(f"\n计算统计: {weight_calculator.get_calculation_statistics()}")