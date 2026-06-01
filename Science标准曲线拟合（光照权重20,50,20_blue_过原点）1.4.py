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


class ThreeBandN2OModel:
    def __init__(self):
        self.params = {}  # 存储三个波段的参数
        self.model_type = {}  # 存储三个波段的最佳模型类型
        self.best_model_func = {}  # 存储三个波段的最佳模型函数
        self.baseline_correction = None
        self.focus_threshold = 5.0  # NO2浓度阈值
        self.no3_conversion_factor = {}  # 分别存储三个波段的转换系数
        self.light_bands = ['UVB', 'UVA', 'BLUE']

    def prepare_data(self, baseline_method='group_specific', focus_strategy='weighted'):
        """
        准备数据，重点关注低浓度NO2
        """
        # 数据组1: NO2-(2.0μmol/L)条件下的数据
        data1 = {
            'UVB': [0, 0, 0, 0, 37082.46, 37082.46, 38441.09, 38441.09, 146861, 146861, 286023, 286023],
            'UVA': [0, 0, 0, 0, 1479018, 1479018, 1531166, 1531166, 5847679, 5847679, 11197932, 11197932],
            'BLUE': [0, 0, 0, 0, 3422395, 3422395, 3501715, 3501715, 13535383, 13535383, 25801623, 25801623],
            'N2O': [-0.14114, -0.08812, -0.16765, -0.06161, 1.31693, 1.38321, 2.19178, 2.66897, 4.33912, 4.61748,
                    8.20965, 8.05059],
            'NO2': [2.0] * 12,
            'NO3': [0.0] * 12,
            'group': ['NO2_only'] * 12
        }

        # 数据组2: NO3-(5.0μmol/L)条件下的数据
        data2 = {
            'UVB': [0, 0, 0, 0, 37082.46, 37082.46, 38441.09, 38441.09, 146861, 146861, 286023, 286023],
            'UVA': [0, 0, 0, 0, 1479018, 1479018, 1531166, 1531166, 5847679, 5847679, 11197932, 11197932],
            'BLUE': [0, 0, 0, 0, 3422395, 3422395, 3501715, 3501715, 13535383, 13535383, 25801623, 25801623],
            'N2O': [-0.00226, 0.00233, -0.00455, 0.00404, 0.01932, 0.02008, 0.02027, 0.03956, 0.11441, 0.10277, 0.21085,
                    0.18449],
            'NO2': [0.0] * 12,
            'NO3': [5.0] * 12,
            'group': ['NO3_only'] * 12
        }

        # 数据组3: 混合实验数据
        data3 = {
            'NO2': [0.5208, 1.11884, 2.00782, 3.10692, 13.81507, 19.3025, 22.91499],
            'N2O': [0.02572, 0.97775, 1.40171, 2.2795, 2.9332, 65.35207, 45.04157],
            'NO3': [0.0, 28.2, 0.0, 28.2, 375.5, 177.7, 335.3],
            'UVB': [14900, 41200, 36715.25, 40900, 44002.26, 24158.09, 21257.85],
            'UVA': [679000, 1630000, 1461920, 1600000, 1707640, 1012472, 925981.6],
            'BLUE': [1490744, 3755830, 3383846, 3685946, 3897292, 2283834, 2105609],
            'group': ['mixed'] * 7
        }

        # 合并数据
        all_data = []

        # 添加NO2_only数据
        for i in range(len(data1['UVB'])):
            all_data.append([
                data1['NO2'][i], data1['NO3'][i],
                data1['UVB'][i], data1['UVA'][i], data1['BLUE'][i],
                data1['N2O'][i], data1['group'][i]
            ])

        # 添加NO3_only数据
        for i in range(len(data2['UVB'])):
            all_data.append([
                data2['NO2'][i], data2['NO3'][i],
                data2['UVB'][i], data2['UVA'][i], data2['BLUE'][i],
                data2['N2O'][i], data2['group'][i]
            ])

        # 添加mixed数据
        for i in range(len(data3['NO2'])):
            all_data.append([
                data3['NO2'][i], data3['NO3'][i],
                data3['UVB'][i], data3['UVA'][i], data3['BLUE'][i],
                data3['N2O'][i], data3['group'][i]
            ])

        self.df = pd.DataFrame(all_data, columns=['NO2', 'NO3', 'UVB', 'UVA', 'BLUE', 'N2O_raw', 'group'])

        # 将光照强度转换为合适的尺度
        self.df['UVB_scaled'] = self.df['UVB'] / 1e3  # 除以1000
        self.df['UVA_scaled'] = self.df['UVA'] / 1e6  # 除以1百万
        self.df['BLUE_scaled'] = self.df['BLUE'] / 1e6  # 除以1百万（调整后的缩放因子）

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
                group_mask = (self.df['group'] == group) & (self.df['UVB'] == 0)
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
            dark_mask = self.df['UVB'] == 0
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
            self.df['include_in_fit'] = self.df['is_low_conc']
            focus_info['filtered_out'] = (~self.df['include_in_fit']).sum()

        elif strategy == 'weighted':
            self.df['include_in_fit'] = True
            weights = np.ones(len(self.df))
            high_conc_mask = ~self.df['is_low_conc']

            for i, row in self.df[high_conc_mask].iterrows():
                weight_factor = 1.0 / (1.0 + (row['NO2'] - self.focus_threshold) / self.focus_threshold)
                weights[i] = weight_factor

            self.df['weight'] = weights
            focus_info['weight_range'] = (weights.min(), weights.max())

        elif strategy == 'stratified':
            self.df['include_in_fit'] = True
            self.df['concentration_layer'] = np.where(self.df['is_low_conc'], 'low', 'high')
            focus_info['low_count'] = self.df['is_low_conc'].sum()
            focus_info['high_count'] = (~self.df['is_low_conc']).sum()

        else:  # 'none'
            self.df['include_in_fit'] = True

        focus_info.update({
            'total_points': len(self.df),
            'low_conc_points': self.df['is_low_conc'].sum(),
            'high_conc_points': (~self.df['is_low_conc']).sum(),
            'fit_points': self.df['include_in_fit'].sum() if 'include_in_fit' in self.df.columns else len(self.df)
        })

        return focus_info

    def calculate_no3_conversion_factors(self):
        """
        分别为三个波段计算NO3转换系数
        """
        print("=" * 60)
        print("步骤1：分别计算三个波段的NO3转换系数")
        print("=" * 60)

        # 分离纯NO2和纯NO3数据
        no2_data = self.df[self.df['group'] == 'NO2_only'].copy()
        no3_data = self.df[self.df['group'] == 'NO3_only'].copy()

        self.no3_conversion_factor = {}

        for band in self.light_bands:
            print(f"\n--- {band}波段分析 ---")

            # 只使用有光照的数据点
            no2_light = no2_data[no2_data[f'{band}_scaled'] > 0]
            no3_light = no3_data[no3_data[f'{band}_scaled'] > 0]

            print(f"NO2组有效数据点: {len(no2_light)}")
            print(f"NO3组有效数据点: {len(no3_light)}")

            if len(no2_light) == 0 or len(no3_light) == 0:
                print(f"{band}波段：数据不足，跳过")
                self.no3_conversion_factor[band] = None
                continue

            # 标准化数据
            no2_normalized = no2_light['N2O'].values / 2.0  # NO2浓度是2.0 μmol/L
            no3_normalized = no3_light['N2O'].values / 5.0  # NO3浓度是5.0 μmol/L

            no2_light_values = no2_light[f'{band}_scaled'].values
            no3_light_values = no3_light[f'{band}_scaled'].values

            print(f"标准化后数据范围:")
            print(f"NO2标准化: {no2_normalized.min():.6f} - {no2_normalized.max():.6f}")
            print(f"NO3标准化: {no3_normalized.min():.6f} - {no3_normalized.max():.6f}")

            # 线性拟合：强制通过原点
            def linear_through_origin(x, slope):
                return slope * x

            try:
                # 拟合NO2标准化数据
                popt_no2, pcov_no2 = curve_fit(linear_through_origin, no2_light_values, no2_normalized)
                slope_no2 = popt_no2[0]

                # 计算R²
                y_pred_no2 = linear_through_origin(no2_light_values, slope_no2)
                ss_res_no2 = np.sum((no2_normalized - y_pred_no2) ** 2)
                ss_tot_no2 = np.sum((no2_normalized - np.mean(no2_normalized)) ** 2)
                r2_no2 = 1 - (ss_res_no2 / ss_tot_no2)

                print(f"NO2拟合成功: 斜率 = {slope_no2:.8f}, R² = {r2_no2:.4f}")

                # 拟合NO3标准化数据
                popt_no3, pcov_no3 = curve_fit(linear_through_origin, no3_light_values, no3_normalized)
                slope_no3 = popt_no3[0]

                # 计算R²
                y_pred_no3 = linear_through_origin(no3_light_values, slope_no3)
                ss_res_no3 = np.sum((no3_normalized - y_pred_no3) ** 2)
                ss_tot_no3 = np.sum((no3_normalized - np.mean(no3_normalized)) ** 2)
                r2_no3 = 1 - (ss_res_no3 / ss_tot_no3)

                print(f"NO3拟合成功: 斜率 = {slope_no3:.8f}, R² = {r2_no3:.4f}")

                # 计算转换系数
                conversion_factor = slope_no3 / slope_no2
                self.no3_conversion_factor[band] = conversion_factor

                print(f"转换系数 = {conversion_factor:.6f}")
                print(f"物理意义: 1 μmol/L NO3⁻ = {conversion_factor:.6f} μmol/L NO2⁻ ({band}波段)")

            except Exception as e:
                print(f"{band}波段拟合失败: {e}")
                self.no3_conversion_factor[band] = None

        print(f"\n" + "=" * 50)
        print(f"三波段转换系数汇总:")
        print(f"=" * 50)
        for band in self.light_bands:
            factor = self.no3_conversion_factor[band]
            if factor is not None:
                print(f"{band}: {factor:.6f}")
            else:
                print(f"{band}: 计算失败")

        return self.no3_conversion_factor

    def fixed_conversion_model_v1(self, X, a, b, d):
        """固定转换系数的模型1：线性+指数混合（强制过原点）"""
        NO2, NO3, Light = X[0], X[1], X[2]
        equivalent_NO2 = NO2 + self.current_conversion_factor * NO3

        linear_term = a * equivalent_NO2
        exp_term = b * (np.exp(0.1 * equivalent_NO2) - 1)
        nitrogen_response = linear_term + exp_term
        light_response = d * Light  # 移除常数项，强制Light=0时结果为0
        return nitrogen_response * light_response

    def fixed_conversion_model_v2(self, X, a, b, d):
        """固定转换系数的模型2：幂函数形式（强制过原点）"""
        NO2, NO3, Light = X[0], X[1], X[2]
        equivalent_NO2 = NO2 + self.current_conversion_factor * NO3

        power_exp = np.clip(b, 0.3, 1.5)
        nitrogen_response = a * np.power(equivalent_NO2, power_exp)
        light_response = d * Light  # 强制过原点
        return nitrogen_response * light_response

    def fixed_conversion_model_v3(self, X, a, b, d, f):
        """固定转换系数的模型3：分段响应（强制过原点）"""
        NO2, NO3, Light = X[0], X[1], X[2]
        equivalent_NO2 = NO2 + self.current_conversion_factor * NO3

        low_response = a * equivalent_NO2
        transition = 1.0 / (1.0 + np.exp(-10 * (equivalent_NO2 - 3.0)))
        high_response = b * np.exp(f * equivalent_NO2)
        nitrogen_response = (1 - transition) * low_response + transition * high_response
        return nitrogen_response * d * Light  # 强制Light和C_eq都通过原点

    def fixed_conversion_model_v4(self, X, a, b, c):
        """固定转换系数的模型4：纯指数函数形式（强制过原点）"""
        NO2, NO3, Light = X[0], X[1], X[2]
        equivalent_NO2 = NO2 + self.current_conversion_factor * NO3

        exp_factor = np.clip(b * equivalent_NO2, -10, 10)
        nitrogen_response = a * (np.exp(exp_factor) - 1)  # 减1确保C_eq=0时为0
        light_response = c * Light  # 强制过原点
        return nitrogen_response * light_response

    def fit_models_for_all_bands(self):
        """为所有三个波段分别拟合模型"""
        if not hasattr(self, 'no3_conversion_factor') or not self.no3_conversion_factor:
            print("错误：请先调用 calculate_no3_conversion_factors() 计算转换系数！")
            return None

        print("\n" + "=" * 60)
        print("步骤2：为三个波段分别拟合模型")
        print("=" * 60)

        all_results = {}

        for band in self.light_bands:
            if self.no3_conversion_factor[band] is None:
                print(f"{band}波段：转换系数计算失败，跳过拟合")
                all_results[band] = None
                continue

            print(f"\n--- {band}波段拟合 ---")
            print(f"使用NO3转换系数: {self.no3_conversion_factor[band]:.6f}")

            # 设置当前波段的转换系数
            self.current_conversion_factor = self.no3_conversion_factor[band]

            # 根据聚焦策略选择数据
            if 'include_in_fit' in self.df.columns:
                fit_mask = self.df['include_in_fit']
            else:
                fit_mask = np.ones(len(self.df), dtype=bool)

            X = np.array([self.df.loc[fit_mask, 'NO2'],
                          self.df.loc[fit_mask, 'NO3'],
                          self.df.loc[fit_mask, f'{band}_scaled']])
            y = self.df.loc[fit_mask, 'N2O'].values

            # 获取权重
            if 'weight' in self.df.columns:
                weights = self.df.loc[fit_mask, 'weight'].values
            else:
                weights = None

            models = {
                'Fixed_Linear_Exp': {
                    'func': self.fixed_conversion_model_v1,
                    'bounds': [(0, 50), (0, 10), (0, 50)],
                    'initial': [1, 1, 1]
                },
                'Fixed_Power': {
                    'func': self.fixed_conversion_model_v2,
                    'bounds': [(0, 50), (0.3, 1.5), (0, 50)],
                    'initial': [1, 1, 1]
                },
                'Fixed_Piecewise': {
                    'func': self.fixed_conversion_model_v3,
                    'bounds': [(0, 50), (0, 10), (0, 50), (0, 1)],
                    'initial': [1, 1, 1, 0.1]
                },
                'Fixed_Exponential': {
                    'func': self.fixed_conversion_model_v4,
                    'bounds': [(0, 50), (0, 2), (0, 50)],
                    'initial': [1, 0.1, 1]
                }
            }

            band_results = {}
            best_r2 = -np.inf

            for name, model_info in models.items():
                print(f"  拟合 {name}...")

                try:
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
                    X_all = np.array([self.df['NO2'], self.df['NO3'], self.df[f'{band}_scaled']])
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

                    band_results[name] = {
                        'params': popt,
                        'r2_all': r2_all,
                        'r2_low': r2_low,
                        'r2_high': r2_high,
                        'rmse_all': rmse_all,
                        'rmse_low': rmse_low,
                        'y_pred_all': y_pred_all,
                        'model_func': model_info['func'],
                        'no3_factor': self.no3_conversion_factor[band]
                    }

                    print(f"    成功! R²_全部 = {r2_all:.4f}, RMSE_全部 = {rmse_all:.4f}")
                    if r2_low is not None:
                        print(f"            R²_低浓度 = {r2_low:.4f}, RMSE_低浓度 = {rmse_low:.4f}")
                    if r2_high is not None:
                        print(f"            R²_高浓度 = {r2_high:.4f}")

                    # 输出具体参数值
                    print(f"    拟合参数: {[f'{p:.6f}' for p in popt]}")

                    # 输出具体方程
                    conversion_factor = self.no3_conversion_factor[band]
                    print(f"    完整方程: ", end="")
                    if name == 'Fixed_Linear_Exp':
                        print(f"N2O = [{popt[0]:.4f}×C_eq + {popt[1]:.4f}×(e^(0.1×C_eq)-1)] × {popt[2]:.4f}×Light")
                        print(f"             其中 C_eq = NO2 + {conversion_factor:.6f}×NO3")
                        print(f"             强制约束: Light=0或C_eq=0时，N2O=0")
                    elif name == 'Fixed_Power':
                        print(f"N2O = {popt[0]:.4f} × C_eq^{popt[1]:.4f} × {popt[2]:.4f}×Light")
                        print(f"             其中 C_eq = NO2 + {conversion_factor:.6f}×NO3")
                        print(f"             强制约束: Light=0或C_eq=0时，N2O=0")
                    elif name == 'Fixed_Piecewise':
                        print(f"N2O = 分段模型:")
                        print(f"             低浓度: {popt[0]:.4f} × C_eq")
                        print(f"             高浓度: {popt[1]:.4f} × e^({popt[3]:.4f}×C_eq)")
                        print(f"             过渡函数: T = 1/(1 + e^(-10×(C_eq - 3.0)))")
                        print(f"             最终: [(1-T)×低浓度 + T×高浓度] × {popt[2]:.4f}×Light")
                        print(f"             其中 C_eq = NO2 + {conversion_factor:.6f}×NO3")
                        print(f"             强制约束: Light=0或C_eq=0时，N2O=0")
                    elif name == 'Fixed_Exponential':
                        print(f"N2O = {popt[0]:.4f} × (e^({popt[1]:.4f}×C_eq) - 1) × {popt[2]:.4f}×Light")
                        print(f"             其中 C_eq = NO2 + {conversion_factor:.6f}×NO3")
                        print(f"             强制约束: Light=0或C_eq=0时，N2O=0")

                    # 选择最佳模型
                    if r2_low is not None and r2_low > best_r2:
                        best_r2 = r2_low
                        self.best_model_func[band] = model_info['func']
                        self.params[band] = popt
                        self.model_type[band] = name
                    elif r2_low is None and r2_all > best_r2:
                        best_r2 = r2_all
                        self.best_model_func[band] = model_info['func']
                        self.params[band] = popt
                        self.model_type[band] = name

                except Exception as e:
                    print(f"    失败: {e}")
                    band_results[name] = None

            all_results[band] = band_results

        return all_results

    def plot_three_band_analysis(self, all_results):
        """绘制三波段分析图"""
        fig, axes = plt.subplots(3, 4, figsize=(20, 15))
        fig.suptitle('三波段独立拟合分析结果 (UVB-UVA-BLUE)', fontsize=16)

        for i, band in enumerate(self.light_bands):
            if all_results[band] is None:
                # 如果该波段拟合失败，显示空白图
                for j in range(4):
                    axes[i, j].text(0.5, 0.5, f'{band}波段\n拟合失败',
                                    ha='center', va='center', transform=axes[i, j].transAxes)
                    axes[i, j].set_title(f'{band}波段')
                continue

            # 设置当前波段的转换系数用于预测
            self.current_conversion_factor = self.no3_conversion_factor[band]

            # 1. 纯组分数据分布
            ax1 = axes[i, 0]
            no2_data = self.df[self.df['group'] == 'NO2_only']
            no3_data = self.df[self.df['group'] == 'NO3_only']

            ax1.scatter(no2_data[f'{band}_scaled'], no2_data['N2O'],
                        color='blue', alpha=0.7, s=50, label='纯NO2')
            ax1.scatter(no3_data[f'{band}_scaled'], no3_data['N2O'],
                        color='red', alpha=0.7, s=50, label='纯NO3')
            ax1.set_xlabel(f'{band}光照强度')
            ax1.set_ylabel('N2O产生速率')
            ax1.set_title(f'{band}波段 - 纯组分数据')
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # 2. 转换系数信息
            ax2 = axes[i, 1]
            factor = self.no3_conversion_factor[band]
            if factor is not None:
                ax2.text(0.5, 0.7, f'{band}转换系数', ha='center', va='center',
                         transform=ax2.transAxes, fontsize=12, fontweight='bold')
                ax2.text(0.5, 0.5, f'{factor:.6f}', ha='center', va='center',
                         transform=ax2.transAxes, fontsize=14, color='red')
                ax2.text(0.5, 0.3, f'1 μmol/L NO3 =\n{factor:.6f} μmol/L NO2',
                         ha='center', va='center', transform=ax2.transAxes, fontsize=9)
            ax2.set_title(f'{band}转换系数')
            ax2.axis('off')

            # 3. 预测vs实际值
            ax3 = axes[i, 2]
            if band in self.model_type and all_results[band].get(self.model_type[band]):
                best_result = all_results[band][self.model_type[band]]
                y_true = self.df['N2O']
                y_pred = best_result['y_pred_all']

                low_mask = self.df['NO2'] <= self.focus_threshold
                high_mask = self.df['NO2'] > self.focus_threshold

                ax3.scatter(y_true[low_mask], y_pred[low_mask],
                            alpha=0.7, color='blue', label='低浓度', s=50)
                ax3.scatter(y_true[high_mask], y_pred[high_mask],
                            alpha=0.7, color='red', label='高浓度', s=50)

                max_val = max(y_true.max(), y_pred.max())
                min_val = min(y_true.min(), y_pred.min())
                ax3.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5)

                ax3.set_xlabel('实际值')
                ax3.set_ylabel('预测值')
                ax3.set_title(f'{band} - {self.model_type[band].replace("Fixed_", "")}')
                ax3.legend()
                ax3.grid(True, alpha=0.3)

            # 4. 模型性能对比
            ax4 = axes[i, 3]
            valid_results = {k: v for k, v in all_results[band].items() if v is not None}

            if valid_results:
                model_names = list(valid_results.keys())
                r2_all = [valid_results[name]['r2_all'] for name in model_names]
                r2_low = [valid_results[name]['r2_low'] if valid_results[name]['r2_low'] is not None else 0
                          for name in model_names]

                x = np.arange(len(model_names))
                width = 0.35

                ax4.bar(x - width / 2, r2_all, width, label='全部R²', alpha=0.7)
                ax4.bar(x + width / 2, r2_low, width, label='低浓度R²', alpha=0.7)

                ax4.set_ylabel('R²')
                ax4.set_title(f'{band}模型性能')
                ax4.set_xticks(x)
                ax4.set_xticklabels([name.replace('Fixed_', '') for name in model_names], rotation=45)
                ax4.legend()
                ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    def predict_n2o_for_band(self, band, no2_conc, no3_conc, light_intensity):
        """预测特定波段的N2O产生速率"""
        if band not in self.best_model_func or self.best_model_func[band] is None:
            print(f"{band}波段模型未拟合!")
            return None

        if self.no3_conversion_factor[band] is None:
            print(f"{band}波段转换系数计算失败!")
            return None

        # 设置当前波段的转换系数
        self.current_conversion_factor = self.no3_conversion_factor[band]

        # 根据波段调整光照强度尺度
        if band == 'UVB':
            light_scaled = light_intensity / 1e3
        elif band == 'UVA':
            light_scaled = light_intensity / 1e6
        else:  # BLUE
            light_scaled = light_intensity / 1e6

        X = np.array([[no2_conc], [no3_conc], [light_scaled]])
        prediction = self.best_model_func[band](X, *self.params[band])
        return prediction[0]

    def predict_n2o_all_bands(self, no2_conc, no3_conc, uvb, uva, blue):
        """预测所有三个波段的N2O产生速率"""
        results = {}
        light_values = {'UVB': uvb, 'UVA': uva, 'BLUE': blue}

        for band in self.light_bands:
            prediction = self.predict_n2o_for_band(band, no2_conc, no3_conc, light_values[band])
            results[band] = prediction

        return results


def main():
    """主函数 - 三波段独立拟合"""
    print("三波段独立拟合N2O产生速率模型 (UVB-UVA-BLUE)")
    print("=" * 80)

    focus_strategies = ['weighted', 'filter', 'stratified']

    for strategy in focus_strategies:
        print(f"\n使用聚焦策略: {strategy}")
        print("-" * 50)

        # 创建模型实例
        model = ThreeBandN2OModel()

        # 准备数据
        df = model.prepare_data(baseline_method='group_specific', focus_strategy=strategy)

        # 步骤1：计算三个波段的NO3转换系数
        conversion_factors = model.calculate_no3_conversion_factors()

        # 步骤2：为三个波段分别拟合模型
        all_results = model.fit_models_for_all_bands()

        if all_results:
            # 绘制分析结果
            model.plot_three_band_analysis(all_results)

            # 总结所有波段的结果
            print(f"\n{strategy}策略 - 三波段拟合结果汇总:")
            print("=" * 60)

            for band in model.light_bands:
                print(f"\n{band}波段:")
                if model.no3_conversion_factor.get(band) is not None:
                    print(f"  NO3转换系数: {model.no3_conversion_factor[band]:.6f}")

                    if band in model.model_type:
                        best_name = model.model_type[band]
                        if all_results[band] and best_name in all_results[band]:
                            best_result = all_results[band][best_name]
                            print(f"  最佳模型: {best_name}")
                            print(f"  R²全部数据: {best_result['r2_all']:.4f}")
                            if best_result['r2_low'] is not None:
                                print(f"  R²低浓度: {best_result['r2_low']:.4f}")
                                print(f"  RMSE低浓度: {best_result['rmse_low']:.4f}")

                            # 输出最佳模型的完整方程
                            popt = model.params[band]
                            conversion_factor = model.no3_conversion_factor[band]
                            print(f"  最佳模型完整方程:")
                            if best_name == 'Fixed_Linear_Exp':
                                print(
                                    f"    N2O = [{popt[0]:.4f}×C_eq + {popt[1]:.4f}×(e^(0.1×C_eq)-1)] × {popt[2]:.4f}×Light")
                            elif best_name == 'Fixed_Power':
                                print(f"    N2O = {popt[0]:.4f} × C_eq^{popt[1]:.4f} × {popt[2]:.4f}×Light")
                            elif best_name == 'Fixed_Piecewise':
                                print(f"    N2O = 分段模型:")
                                print(f"      低浓度: {popt[0]:.4f} × C_eq")
                                print(f"      高浓度: {popt[1]:.4f} × e^({popt[3]:.4f}×C_eq)")
                                print(f"      最终: [(1-T)×低浓度 + T×高浓度] × {popt[2]:.4f}×Light")
                            elif best_name == 'Fixed_Exponential':
                                print(f"    N2O = {popt[0]:.4f} × (e^({popt[1]:.4f}×C_eq) - 1) × {popt[2]:.4f}×Light")
                            print(f"    其中 C_eq = NO2 + {conversion_factor:.6f}×NO3")
                            print(f"    物理约束: Light=0或C_eq=0时，N2O=0")
                else:
                    print(f"  转换系数计算失败")

            # 预测验证
            print(f"\n预测验证 (标准光照条件):")
            print("-" * 40)
            test_cases = [
                (0.5, 0, "极低NO2"),
                (1.0, 0, "低NO2"),
                (2.0, 0, "中低NO2"),
                (0, 5.0, "低NO3"),
                (1.0, 5.0, "NO2+NO3混合")
            ]

            for no2, no3, desc in test_cases:
                predictions = model.predict_n2o_all_bands(no2, no3, 37000, 1500000, 3500000)
                print(f"\n{desc} (NO2={no2}, NO3={no3}):")
                for band in model.light_bands:
                    if predictions[band] is not None:
                        print(f"  {band}: {predictions[band]:.4f}")
                    else:
                        print(f"  {band}: 预测失败")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    main()