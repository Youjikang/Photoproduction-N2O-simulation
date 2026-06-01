import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit, differential_evolution
from sklearn.metrics import r2_score
import warnings

warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class FixedConversionN2OModel:
    def __init__(self):
        self.params = None
        self.model_type = None
        self.best_model_func = None
        self.baseline_correction = None
        self.focus_threshold = 5.0  # NO2浓度阈值
        self.no3_conversion_factor = None  # 从纯组分数据计算得到的转换系数

    def prepare_data(self, baseline_method='group_specific', focus_strategy='weighted'):
        """
        准备数据，重点关注低浓度NO2
        focus_strategy: 'filter', 'weighted', 'stratified'
        """
        # 数据组1: NO2-(2.0μmol/L)条件下的数据（只保留UVA）
        data1 = {
            'UVA': [0, 0, 0, 0, 1479018, 1479018, 1531166, 1531166, 6549466, 6549466, 11197932, 11197932],
            'N2O': [-0.14114, -0.08812, -0.16765, -0.06161, 1.31693, 1.38321, 2.19178, 2.66897, 4.33912, 4.61748,
                    8.20965, 8.05059],
            'NO2': [2.0] * 12,
            'NO3': [0.0] * 12,
            'group': ['NO2_only'] * 12
        }

        # 数据组2: NO3-(5.0μmol/L)条件下的数据（只保留UVA）
        data2 = {
            'UVA': [0, 0, 0, 0, 1479018, 1479018, 1531166, 1531166, 6549466, 6549466, 11197932, 11197932],
            'N2O': [-0.00226, 0.00233, -0.00455, 0.00404, 0.01932, 0.02008, 0.02027, 0.03956, 0.11441, 0.10277, 0.21085,
                    0.18449],
            'NO2': [0.0] * 12,
            'NO3': [5.0] * 12,
            'group': ['NO3_only'] * 12
        }

        # 数据组3: 混合实验数据（只保留UVA）
        data3 = {
            'NO2': [0.5208, 1.11884, 2.00782, 3.10692, 13.81507, 19.3025, 22.91499],
            'N2O': [0.02572, 0.97775, 1.40171, 2.2795, 2.9332, 65.35207, 45.04157],
            'NO3': [0.0, 28.2, 0.0, 28.2, 375.5, 177.7, 335.3],
            'UVA': [679000, 1630000, 1460000, 1600000, 1707640, 1012472, 925981.6],
            'group': ['mixed'] * 7
        }

        # 合并数据
        all_data = []

        # 添加NO2_only数据
        for i in range(len(data1['UVA'])):
            all_data.append([
                data1['NO2'][i], data1['NO3'][i],
                data1['UVA'][i], data1['N2O'][i], data1['group'][i]
            ])

        # 添加NO3_only数据
        for i in range(len(data2['UVA'])):
            all_data.append([
                data2['NO2'][i], data2['NO3'][i],
                data2['UVA'][i], data2['N2O'][i], data2['group'][i]
            ])

        # 添加mixed数据
        for i in range(len(data3['NO2'])):
            all_data.append([
                data3['NO2'][i], data3['NO3'][i],
                data3['UVA'][i], data3['N2O'][i], data3['group'][i]
            ])

        self.df = pd.DataFrame(all_data, columns=['NO2', 'NO3', 'UVA', 'N2O_raw', 'group'])

        # 计算总光照强度（现在只使用UVA）
        self.df['Light_total'] = self.df['UVA'] / 1e6

        # 基线校正
        self.baseline_correction = self._apply_baseline_correction(baseline_method)

        # 应用聚焦策略
        self.focus_info = self._apply_focus_strategy(focus_strategy)

        return self.df

    def _apply_baseline_correction(self, method):
        """基线校正"""
        correction_info = {'method': method}

        if method == 'group_specific':
            self.df['N2O'] = self.df['N2O_raw'].copy()
            corrections = {}

            for group in ['NO2_only', 'NO3_only']:
                group_mask = (self.df['group'] == group) & (self.df['Light_total'] == 0)
                if group_mask.sum() > 0:
                    baseline = np.mean(self.df[group_mask]['N2O_raw'])
                    group_data_mask = self.df['group'] == group
                    self.df.loc[group_data_mask, 'N2O'] = self.df.loc[group_data_mask, 'N2O_raw'] - baseline
                    corrections[group] = baseline

            # 混合数据使用整体基线
            mixed_mask = self.df['group'] == 'mixed'
            overall_baseline = np.mean([corrections.get('NO2_only', 0), corrections.get('NO3_only', 0)])
            self.df.loc[mixed_mask, 'N2O'] = self.df.loc[mixed_mask, 'N2O_raw'] - overall_baseline
            corrections['mixed'] = overall_baseline

            correction_info['corrections'] = corrections
        else:
            # 简单整体校正
            dark_mask = self.df['Light_total'] == 0
            if dark_mask.sum() > 0:
                baseline = np.mean(self.df[dark_mask]['N2O_raw'])
                self.df['N2O'] = self.df['N2O_raw'] - baseline
                correction_info['correction'] = baseline
            else:
                self.df['N2O'] = self.df['N2O_raw']
                correction_info['correction'] = 0

        return correction_info

    def _apply_focus_strategy(self, strategy):
        """应用聚焦策略，重点关注低浓度NO2"""
        focus_info = {'strategy': strategy, 'threshold': self.focus_threshold}

        # 标记低浓度和高浓度数据点
        self.df['is_low_conc'] = self.df['NO2'] <= self.focus_threshold

        if strategy == 'filter':
            # 策略1：仅使用低浓度数据
            self.df['include_in_fit'] = self.df['is_low_conc']
            focus_info['filtered_out'] = (~self.df['include_in_fit']).sum()

        elif strategy == 'weighted':
            # 策略2：加权拟合，低浓度权重更高
            self.df['include_in_fit'] = True

            # 计算权重：低浓度权重=1，高浓度权重递减
            weights = np.ones(len(self.df))
            high_conc_mask = ~self.df['is_low_conc']

            # 高浓度点的权重随浓度降低
            for i, row in self.df[high_conc_mask].iterrows():
                # 权重 = 1 / (1 + (NO2 - threshold) / threshold)
                weight_factor = 1.0 / (1.0 + (row['NO2'] - self.focus_threshold) / self.focus_threshold)
                weights[i] = weight_factor

            self.df['weight'] = weights
            focus_info['weight_range'] = (weights.min(), weights.max())

        elif strategy == 'stratified':
            # 策略3：分层拟合，低浓度和高浓度分别建模
            self.df['include_in_fit'] = True
            self.df['concentration_layer'] = np.where(self.df['is_low_conc'], 'low', 'high')
            focus_info['low_count'] = self.df['is_low_conc'].sum()
            focus_info['high_count'] = (~self.df['is_low_conc']).sum()

        else:  # 'none'
            self.df['include_in_fit'] = True

        # 统计信息
        focus_info.update({
            'total_points': len(self.df),
            'low_conc_points': self.df['is_low_conc'].sum(),
            'high_conc_points': (~self.df['is_low_conc']).sum(),
            'fit_points': self.df['include_in_fit'].sum() if 'include_in_fit' in self.df.columns else len(self.df)
        })

        return focus_info

    def calculate_no3_conversion_factor(self):
        """
        从纯NO2和纯NO3数据中计算NO3转换系数
        使用标准化数据的线性拟合方法
        """
        print("=" * 60)
        print("步骤1：计算NO3转换系数")
        print("=" * 60)

        # 分离纯NO2和纯NO3数据
        no2_data = self.df[self.df['group'] == 'NO2_only'].copy()
        no3_data = self.df[self.df['group'] == 'NO3_only'].copy()

        # 只使用有光照的数据点
        no2_light = no2_data[no2_data['Light_total'] > 0]
        no3_light = no3_data[no3_data['Light_total'] > 0]

        print(f"NO2组有效数据点: {len(no2_light)}")
        print(f"NO3组有效数据点: {len(no3_light)}")

        # 显示原始数据范围
        print(f"\n原始数据范围:")
        print(f"NO2组 (2.0 μmol/L): N2O = {no2_light['N2O'].min():.4f} - {no2_light['N2O'].max():.4f}")
        print(f"NO3组 (5.0 μmol/L): N2O = {no3_light['N2O'].min():.4f} - {no3_light['N2O'].max():.4f}")

        # 标准化数据：除以各自的浓度，得到单位浓度的N2O产生速率
        no2_normalized = no2_light['N2O'].values / 2.0  # NO2浓度是2.0 μmol/L
        no3_normalized = no3_light['N2O'].values / 5.0  # NO3浓度是5.0 μmol/L

        no2_light_values = no2_light['Light_total'].values
        no3_light_values = no3_light['Light_total'].values

        print(f"\n标准化后数据范围:")
        print(f"NO2标准化: {no2_normalized.min():.6f} - {no2_normalized.max():.6f} (nmol-N L⁻¹ per μmol/L)")
        print(f"NO3标准化: {no3_normalized.min():.6f} - {no3_normalized.max():.6f} (nmol-N L⁻¹ per μmol/L)")

        # 线性拟合：强制通过原点 (N2O_normalized = slope × Light)
        def linear_through_origin(x, slope):
            return slope * x

        # 拟合NO2标准化数据
        print(f"\n拟合NO2标准化数据...")
        try:
            from scipy.optimize import curve_fit
            popt_no2, pcov_no2 = curve_fit(linear_through_origin, no2_light_values, no2_normalized)
            slope_no2 = popt_no2[0]

            # 计算R²
            y_pred_no2 = linear_through_origin(no2_light_values, slope_no2)
            ss_res_no2 = np.sum((no2_normalized - y_pred_no2) ** 2)
            ss_tot_no2 = np.sum((no2_normalized - np.mean(no2_normalized)) ** 2)
            r2_no2 = 1 - (ss_res_no2 / ss_tot_no2)

            print(f"NO2拟合成功: 斜率 = {slope_no2:.8f}, R² = {r2_no2:.4f}")

        except Exception as e:
            print(f"NO2拟合失败: {e}")
            return None

        # 拟合NO3标准化数据
        print(f"拟合NO3标准化数据...")
        try:
            popt_no3, pcov_no3 = curve_fit(linear_through_origin, no3_light_values, no3_normalized)
            slope_no3 = popt_no3[0]

            # 计算R²
            y_pred_no3 = linear_through_origin(no3_light_values, slope_no3)
            ss_res_no3 = np.sum((no3_normalized - y_pred_no3) ** 2)
            ss_tot_no3 = np.sum((no3_normalized - np.mean(no3_normalized)) ** 2)
            r2_no3 = 1 - (ss_res_no3 / ss_tot_no3)

            print(f"NO3拟合成功: 斜率 = {slope_no3:.8f}, R² = {r2_no3:.4f}")

        except Exception as e:
            print(f"NO3拟合失败: {e}")
            return None

        # 计算转换系数
        self.no3_conversion_factor = slope_no3 / slope_no2

        print(f"\n" + "=" * 50)
        print(f"转换系数计算结果:")
        print(f"=" * 50)
        print(f"NO2斜率 (slope_NO2): {slope_no2:.8f}")
        print(f"NO3斜率 (slope_NO3): {slope_no3:.8f}")
        print(f"转换系数 = slope_NO3 / slope_NO2 = {self.no3_conversion_factor:.6f}")
        print(f"")
        print(f"物理意义:")
        print(f"  - 1 μmol/L NO3⁻ 的N2O产生能力 = {self.no3_conversion_factor:.6f} μmol/L NO2⁻")
        print(f"  - NO3⁻效率是NO2⁻的 {self.no3_conversion_factor * 100:.2f}%")

        # 显示详细的拟合信息
        print(f"\n拟合方程:")
        print(f"NO2: N2O_rate = {slope_no2:.8f} × UVA_intensity")
        print(f"NO3: N2O_rate = {slope_no3:.8f} × UVA_intensity")

        # 显示一些预测示例
        print(f"\n预测示例 (UVA强度 = 50):")
        light_example = 50
        pred_no2 = slope_no2 * light_example
        pred_no3 = slope_no3 * light_example
        print(f"1 μmol/L NO2⁻: {pred_no2:.4f} nmol-N L⁻¹")
        print(f"1 μmol/L NO3⁻: {pred_no3:.4f} nmol-N L⁻¹")
        print(f"比值: {pred_no3 / pred_no2:.6f}")

        return self.no3_conversion_factor

    def fixed_conversion_model_v1(self, X, a, b, d, e, f):
        """
        固定转换系数的模型1：线性+指数混合
        """
        NO2, NO3, Light = X[0], X[1], X[2]

        # 使用预先计算的固定转换系数
        equivalent_NO2 = NO2 + self.no3_conversion_factor * NO3

        # 线性+指数混合响应
        linear_term = a * equivalent_NO2
        exp_term = b * (np.exp(0.1 * equivalent_NO2) - 1)
        nitrogen_response = linear_term + exp_term
        light_response = d * Light + e

        return nitrogen_response * light_response + f

    def fixed_conversion_model_v2(self, X, a, b, d, e, f, g):
        """
        固定转换系数的模型2：幂函数形式
        """
        NO2, NO3, Light = X[0], X[1], X[2]

        # 使用预先计算的固定转换系数
        equivalent_NO2 = NO2 + self.no3_conversion_factor * NO3

        # 幂函数响应
        power_exp = np.clip(b, 0.3, 1.5)
        nitrogen_response = a * np.power(equivalent_NO2, power_exp)
        light_response = d * Light + e
        linear_light = f * Light

        return nitrogen_response * light_response + linear_light + g

    def fixed_conversion_model_v3(self, X, a, b, d, e, f, g, h):
        """
        固定转换系数的模型3：分段响应
        """
        NO2, NO3, Light = X[0], X[1], X[2]

        # 使用预先计算的固定转换系数
        equivalent_NO2 = NO2 + self.no3_conversion_factor * NO3

        # 分段响应函数
        low_response = a * equivalent_NO2 * (d * Light + e)
        transition = 1.0 / (1.0 + np.exp(-10 * (equivalent_NO2 - 3.0)))
        high_response = b * np.exp(f * equivalent_NO2) * (d * Light + e)
        nitrogen_response = (1 - transition) * low_response + transition * high_response

        return nitrogen_response + g * Light + h

    def fixed_conversion_model_v4(self, X, a, b, c, d, e, f):
        """
        固定转换系数的模型4：纯指数函数形式
        N2O = a * exp(b * equivalent_NO2) * (c * Light + d) + e * Light + f
        """
        NO2, NO3, Light = X[0], X[1], X[2]

        # 使用预先计算的固定转换系数
        equivalent_NO2 = NO2 + self.no3_conversion_factor * NO3

        # 对等效NO2浓度应用指数函数，限制指数避免数值溢出
        exp_factor = np.clip(b * equivalent_NO2, -10, 10)
        nitrogen_response = a * np.exp(exp_factor)

        # 光照响应：线性项
        light_response = c * Light + d

        # 额外的线性光照项和常数项
        linear_light = e * Light

        return nitrogen_response * light_response + linear_light + f

    def fit_fixed_conversion_models(self):
        """
        使用固定转换系数拟合模型
        """
        if self.no3_conversion_factor is None:
            print("错误：请先调用 calculate_no3_conversion_factor() 计算转换系数！")
            return None

        print("\n" + "=" * 60)
        print("步骤2：使用固定转换系数拟合整体模型")
        print("=" * 60)
        print(f"使用NO3转换系数: {self.no3_conversion_factor:.6f}")

        # 根据聚焦策略选择数据
        if 'include_in_fit' in self.df.columns:
            fit_mask = self.df['include_in_fit']
        else:
            fit_mask = np.ones(len(self.df), dtype=bool)

        X = np.array([self.df.loc[fit_mask, 'NO2'],
                      self.df.loc[fit_mask, 'NO3'],
                      self.df.loc[fit_mask, 'Light_total']])
        y = self.df.loc[fit_mask, 'N2O'].values

        # 获取权重
        if 'weight' in self.df.columns:
            weights = self.df.loc[fit_mask, 'weight'].values
        else:
            weights = None

        models = {
            'Fixed_Linear_Exp': {
                'func': self.fixed_conversion_model_v1,
                'bounds': [(0, 50), (0, 10), (0, 50), (-5, 5), (-5, 5)],
                'initial': [1, 1, 1, 0, 0]
            },
            'Fixed_Power': {
                'func': self.fixed_conversion_model_v2,
                'bounds': [(0, 50), (0.3, 1.5), (0, 50), (-5, 5), (-50, 50), (-5, 5)],
                'initial': [1, 1, 1, 0, 0, 0]
            },
            'Fixed_Piecewise': {
                'func': self.fixed_conversion_model_v3,
                'bounds': [(0, 50), (0, 10), (0, 50), (-5, 5), (0, 1), (-50, 50), (-5, 5)],
                'initial': [1, 1, 1, 0, 0.1, 0, 0]
            },
            'Fixed_Exponential': {
                'func': self.fixed_conversion_model_v4,
                'bounds': [(0, 50), (0, 2), (0, 50), (-5, 5), (-50, 50), (-5, 5)],
                'initial': [1, 0.1, 1, 0, 0, 0]
            }
        }

        results = {}
        best_r2 = -np.inf

        print(f"\n聚焦策略: {self.focus_info['strategy']}")
        print(f"拟合数据点: {self.focus_info['fit_points']}/{self.focus_info['total_points']}")
        print(f"低浓度点(≤{self.focus_threshold}): {self.focus_info['low_conc_points']}")
        print(f"高浓度点(>{self.focus_threshold}): {self.focus_info['high_conc_points']}")

        if 'weight_range' in self.focus_info:
            print(f"权重范围: {self.focus_info['weight_range'][0]:.3f} - {self.focus_info['weight_range'][1]:.3f}")
        print()

        for name, model_info in models.items():
            print(f"拟合 {name}...")

            try:
                # 使用curve_fit（支持权重）
                if weights is not None:
                    popt, pcov = curve_fit(
                        model_info['func'], X, y,
                        p0=model_info['initial'],
                        bounds=(
                            [bound[0] for bound in model_info['bounds']],
                            [bound[1] for bound in model_info['bounds']]
                        ),
                        sigma=1.0 / weights,
                        maxfev=10000,
                        method='trf'
                    )
                else:
                    popt, pcov = curve_fit(
                        model_info['func'], X, y,
                        p0=model_info['initial'],
                        bounds=(
                            [bound[0] for bound in model_info['bounds']],
                            [bound[1] for bound in model_info['bounds']]
                        ),
                        maxfev=10000,
                        method='trf'
                    )

                # 评估模型性能
                X_all = np.array([self.df['NO2'], self.df['NO3'], self.df['Light_total']])
                y_all = self.df['N2O'].values
                y_pred_all = model_info['func'](X_all, *popt)

                # 分别计算低浓度和高浓度的R²
                low_mask = self.df['NO2'] <= self.focus_threshold
                high_mask = self.df['NO2'] > self.focus_threshold

                r2_all = r2_score(y_all, y_pred_all)
                r2_low = r2_score(y_all[low_mask], y_pred_all[low_mask]) if low_mask.sum() > 1 else None
                r2_high = r2_score(y_all[high_mask], y_pred_all[high_mask]) if high_mask.sum() > 1 else None

                rmse_all = np.sqrt(np.mean((y_all - y_pred_all) ** 2))
                rmse_low = np.sqrt(
                    np.mean((y_all[low_mask] - y_pred_all[low_mask]) ** 2)) if low_mask.sum() > 0 else None

                results[name] = {
                    'params': popt,
                    'r2_all': r2_all,
                    'r2_low': r2_low,
                    'r2_high': r2_high,
                    'rmse_all': rmse_all,
                    'rmse_low': rmse_low,
                    'y_pred_all': y_pred_all,
                    'model_func': model_info['func'],
                    'no3_factor': self.no3_conversion_factor  # 固定的转换系数
                }

                print(f"  成功! R²_全部 = {r2_all:.4f}, RMSE_全部 = {rmse_all:.4f}")
                if r2_low is not None:
                    print(f"          R²_低浓度 = {r2_low:.4f}, RMSE_低浓度 = {rmse_low:.4f}")
                if r2_high is not None:
                    print(f"          R²_高浓度 = {r2_high:.4f}")

                # 选择最佳模型
                if r2_low is not None and r2_low > best_r2:
                    best_r2 = r2_low
                    self.best_model_func = model_info['func']
                    self.params = popt
                    self.model_type = name
                elif r2_low is None and r2_all > best_r2:
                    best_r2 = r2_all
                    self.best_model_func = model_info['func']
                    self.params = popt
                    self.model_type = name

            except Exception as e:
                print(f"  失败: {e}")
                results[name] = None

            print()

        return results

    def plot_conversion_analysis(self, results):
        """绘制转换系数分析图"""
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('固定NO3转换系数模型分析 (UVA单波段)', fontsize=16)

        # 1. 纯组分数据拟合对比
        ax1 = axes[0, 0]

        no2_data = self.df[self.df['group'] == 'NO2_only']
        no3_data = self.df[self.df['group'] == 'NO3_only']

        # 绘制纯NO2数据
        ax1.scatter(no2_data['Light_total'], no2_data['N2O'],
                    color='blue', alpha=0.7, s=50, label='纯NO2数据')

        # 绘制纯NO3数据
        ax1.scatter(no3_data['Light_total'], no3_data['N2O'],
                    color='red', alpha=0.7, s=50, label='纯NO3数据')

        ax1.set_xlabel('UVA光照强度')
        ax1.set_ylabel('N2O产生速率 (nmol-N L-1)')
        ax1.set_title('纯组分数据分布')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 2. 转换系数可视化
        ax2 = axes[0, 1]

        if self.no3_conversion_factor is not None:
            # 显示转换系数信息
            ax2.text(0.5, 0.7, f'NO3转换系数', ha='center', va='center',
                     transform=ax2.transAxes, fontsize=14, fontweight='bold')
            ax2.text(0.5, 0.5, f'{self.no3_conversion_factor:.6f}', ha='center', va='center',
                     transform=ax2.transAxes, fontsize=16, color='red')
            ax2.text(0.5, 0.3, f'物理意义:\n1 μmol/L NO3 = {self.no3_conversion_factor:.6f} μmol/L NO2',
                     ha='center', va='center', transform=ax2.transAxes, fontsize=10)
            ax2.set_title('NO3转换系数')
            ax2.axis('off')

        # 3. 模型性能对比
        ax3 = axes[0, 2]
        valid_results = {k: v for k, v in results.items() if v is not None}

        if valid_results:
            model_names = list(valid_results.keys())
            r2_all = [valid_results[name]['r2_all'] for name in model_names]
            r2_low = [valid_results[name]['r2_low'] if valid_results[name]['r2_low'] is not None else 0
                      for name in model_names]

            x = np.arange(len(model_names))
            width = 0.35

            bars1 = ax3.bar(x - width / 2, r2_all, width, label='全部数据R²', alpha=0.7)
            bars2 = ax3.bar(x + width / 2, r2_low, width, label='低浓度R²', alpha=0.7)

            ax3.set_ylabel('R²')
            ax3.set_title('模型性能对比')
            ax3.set_xticks(x)
            ax3.set_xticklabels([name.replace('Fixed_', '') for name in model_names], rotation=45)
            ax3.legend()
            ax3.grid(True, alpha=0.3)

        # 4. 预测vs实际值
        ax4 = axes[1, 0]
        if self.model_type and results.get(self.model_type):
            best_result = results[self.model_type]
            y_true = self.df['N2O']
            y_pred = best_result['y_pred_all']

            low_mask = self.df['NO2'] <= self.focus_threshold
            high_mask = self.df['NO2'] > self.focus_threshold

            ax4.scatter(y_true[low_mask], y_pred[low_mask],
                        alpha=0.7, color='blue', label='低浓度', s=50)
            ax4.scatter(y_true[high_mask], y_pred[high_mask],
                        alpha=0.7, color='red', label='高浓度', s=50)

            max_val = max(y_true.max(), y_pred.max())
            min_val = min(y_true.min(), y_pred.min())
            ax4.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5)

            ax4.set_xlabel('实际值')
            ax4.set_ylabel('预测值')
            ax4.set_title(f'最佳模型: {self.model_type.replace("Fixed_", "")}')
            ax4.legend()
            ax4.grid(True, alpha=0.3)

        # 5. 等效浓度分布
        ax5 = axes[1, 1]
        if self.no3_conversion_factor is not None:
            equiv_conc = self.df['NO2'] + self.no3_conversion_factor * self.df['NO3']

            low_mask = self.df['NO2'] <= self.focus_threshold

            ax5.scatter(equiv_conc[low_mask], self.df[low_mask]['N2O'],
                        color='blue', alpha=0.7, s=50, label='低浓度')
            ax5.scatter(equiv_conc[~low_mask], self.df[~low_mask]['N2O'],
                        color='red', alpha=0.7, s=50, label='高浓度')

            ax5.set_xlabel('等效NO2浓度 (μmol/L)')
            ax5.set_ylabel('N2O产生速率 (nmol-N L-1)')
            ax5.set_title('等效浓度分布')
            ax5.legend()
            ax5.grid(True, alpha=0.3)

        # 6. 残差分析
        ax6 = axes[1, 2]
        if self.model_type and results.get(self.model_type):
            residuals = y_true - y_pred

            ax6.scatter(y_pred[low_mask], residuals[low_mask],
                        alpha=0.7, color='blue', label='低浓度')
            ax6.scatter(y_pred[high_mask], residuals[high_mask],
                        alpha=0.7, color='red', label='高浓度')
            ax6.axhline(y=0, color='black', linestyle='--', alpha=0.5)

            ax6.set_xlabel('预测值')
            ax6.set_ylabel('残差')
            ax6.set_title('残差分析')
            ax6.legend()
            ax6.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    def predict_n2o(self, no2_conc, no3_conc, uva):
        """预测N2O产生速率（仅使用UVA）"""
        if self.best_model_func is None or self.params is None:
            print("请先拟合模型!")
            return None

        if self.no3_conversion_factor is None:
            print("请先计算NO3转换系数!")
            return None

        light_total = uva / 1e6
        X = np.array([[no2_conc], [no3_conc], [light_total]])

        prediction = self.best_model_func(X, *self.params)
        return prediction[0]


def main():
    """主函数 - 使用固定转换系数的建模方法（UVA单波段）"""
    print("基于纯组分数据计算固定NO3转换系数的N2O产生速率模型")
    print("修改为UVA单波段模型")
    print("=" * 80)

    focus_strategies = ['weighted', 'filter', 'stratified']

    for strategy in focus_strategies:
        print(f"\n使用聚焦策略: {strategy}")
        print("-" * 50)

        # 创建模型实例
        model = FixedConversionN2OModel()

        # 准备数据
        df = model.prepare_data(baseline_method='group_specific', focus_strategy=strategy)

        # 步骤1：从纯组分数据计算NO3转换系数
        conversion_factor = model.calculate_no3_conversion_factor()

        if conversion_factor is not None:
            # 步骤2：使用固定转换系数拟合整体模型
            results = model.fit_fixed_conversion_models()

            if results and any(results.values()):
                # 绘制分析结果
                model.plot_conversion_analysis(results)

                # 总结最佳结果
                valid_results = {k: v for k, v in results.items() if v is not None}
                if valid_results:
                    best_name = model.model_type
                    best_result = valid_results[best_name]

                    print(f"\n{strategy}策略最终结果:")
                    print(f"  NO3转换系数: {model.no3_conversion_factor:.6f}")
                    print(f"  最佳模型: {best_name}")
                    print(f"  R²全部数据: {best_result['r2_all']:.4f}")
                    if best_result['r2_low'] is not None:
                        print(f"  R²低浓度: {best_result['r2_low']:.4f}")
                        print(f"  RMSE低浓度: {best_result['rmse_low']:.4f}")

                    # 验证预测（仅使用UVA）
                    print(f"\n预测验证 (UVA=1500000):")
                    test_cases = [
                        (0.5, 0, "极低NO2"),
                        (1.0, 0, "低NO2"),
                        (2.0, 0, "中低NO2"),
                        (0, 5.0, "低NO3"),
                        (1.0, 5.0, "NO2+NO3混合")
                    ]

                    for no2, no3, desc in test_cases:
                        pred = model.predict_n2o(no2, no3, 1500000)
                        if pred is not None:
                            print(f"  {desc} (NO2={no2}, NO3={no3}): {pred:.4f}")

                # 显示新增指数模型的详细信息
                if 'Fixed_Exponential' in valid_results:
                    exp_result = valid_results['Fixed_Exponential']
                    params = exp_result['params']
                    print(f"\n指数函数模型参数:")
                    print(f"  a (基础倍数): {params[0]:.4f}")
                    print(f"  b (指数系数): {params[1]:.4f}")
                    print(f"  c (UVA系数): {params[2]:.4f}")
                    print(f"  d (UVA偏移): {params[3]:.4f}")
                    print(f"  e (线性UVA): {params[4]:.4f}")
                    print(f"  f (常数项): {params[5]:.4f}")
                    print(
                        f"  模型形式: N2O = {params[0]:.2f} * exp({params[1]:.3f} * equiv_NO2) * ({params[2]:.2f} * UVA + {params[3]:.2f}) + {params[4]:.2f} * UVA + {params[5]:.2f}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    main()