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


class BaselineCorrectedN2OModel:
    def __init__(self):
        self.params = None
        self.model_type = None
        self.best_model_func = None
        self.baseline_correction = None

    def prepare_data(self, baseline_method='group_specific'):
        """
        准备数据并进行基线校正
        baseline_method: 'none', 'overall', 'group_specific', 'adaptive'
        """
        # 原始数据
        data1 = {
            'UVB': [0, 0, 0, 0, 40349, 40349, 42019.14, 42019.14, 173884.3, 173884.3, 344017.2, 344017.2],
            'UVA': [0, 0, 0, 0, 1603738, 1603738, 1649339, 1649339, 6815024, 6815024, 13460360, 13460360],
            'VIS': [0, 0, 0, 0, 11756972, 11756972, 12089807, 12089807, 50869097, 50869097, 99910634, 99910634],
            'N2O': [-0.14114, -0.08812, -0.16765, -0.06161, 1.31693, 1.38321, 2.19178, 2.66897, 4.33912, 4.61748,
                    8.20965, 8.05059],
            'NO2': [2.0] * 12,
            'NO3': [0.0] * 12,
            'group': ['NO2_only'] * 12
        }

        data2 = {
            'UVB': [0, 0, 0, 0, 40349, 40349, 42019.14, 42019.14, 173884.3, 173884.3, 344017.2, 344017.2],
            'UVA': [0, 0, 0, 0, 1603738, 1603738, 1649339, 1649339, 6815024, 6815024, 13460360, 13460360],
            'VIS': [0, 0, 0, 0, 11756972, 11756972, 12089807, 12089807, 50869097, 50869097, 99910634, 99910634],
            'N2O': [-0.00226, 0.00233, -0.00455, 0.00404, 0.01932, 0.02008, 0.02027, 0.03956, 0.11441, 0.10277, 0.21085,
                    0.18449],
            'NO2': [0.0] * 12,
            'NO3': [5.0] * 12,
            'group': ['NO3_only'] * 12
        }

        data3 = {
            'NO2': [0.5208, 1.11884, 2.00782, 3.10692, 13.81507, 19.3025, 22.91499],
            'N2O': [0.02572, 0.97775, 1.40171, 2.2795, 2.9332, 65.35207, 45.04157],
            'NO3': [0, 28.2, 0, 0, 375.5, 177.7, 335.3],
            'UVB': [6824.585, 38441.09, 37082.46, 38441.09, 42855.98, 29582.55, 20735.62],
            'UVA': [325268, 1531166, 1479018, 1531166, 1738375, 1230753, 890226.4],
            'VIS': [2096356.88, 11361357.3, 11133681.7, 11361357.3, 12925296.8, 9120420.93, 6365664.2],
            'group': ['mixed'] * 7
        }

        # 合并数据
        all_data = []

        for i in range(len(data1['UVB'])):
            all_data.append([
                data1['NO2'][i], data1['NO3'][i],
                data1['UVB'][i], data1['UVA'][i], data1['VIS'][i],
                data1['N2O'][i], data1['group'][i]
            ])

        for i in range(len(data2['UVB'])):
            all_data.append([
                data2['NO2'][i], data2['NO3'][i],
                data2['UVB'][i], data2['UVA'][i], data2['VIS'][i],
                data2['N2O'][i], data2['group'][i]
            ])

        for i in range(len(data3['NO2'])):
            all_data.append([
                data3['NO2'][i], data3['NO3'][i],
                data3['UVB'][i], data3['UVA'][i], data3['VIS'][i],
                data3['N2O'][i], data3['group'][i]
            ])

        self.df = pd.DataFrame(all_data, columns=['NO2', 'NO3', 'UVB', 'UVA', 'VIS', 'N2O_raw', 'group'])

        # 计算总光照强度
        self.df['Light_total'] = (self.df['UVB'] * 0.1 + self.df['UVA'] * 0.3 + self.df['VIS'] * 1.0) / 1e6

        # 基线校正
        self.baseline_correction = self._apply_baseline_correction(baseline_method)

        return self.df

    def _apply_baseline_correction(self, method):
        """应用基线校正"""
        correction_info = {'method': method}

        if method == 'none':
            self.df['N2O'] = self.df['N2O_raw']
            correction_info['correction'] = 0

        elif method == 'overall':
            # 使用所有无光照数据计算整体基线
            dark_mask = self.df['Light_total'] == 0
            dark_values = self.df[dark_mask]['N2O_raw']
            baseline = np.mean(dark_values)

            self.df['N2O'] = self.df['N2O_raw'] - baseline
            correction_info['correction'] = baseline

        elif method == 'group_specific':
            # 对每个组分别计算基线
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

        elif method == 'adaptive':
            # 自适应基线：仅校正明显的负偏移
            self.df['N2O'] = self.df['N2O_raw'].copy()

            # 检查无光照条件下的系统性偏移
            dark_mask = self.df['Light_total'] == 0
            dark_values = self.df[dark_mask]['N2O_raw']

            if np.mean(dark_values) < -0.01:  # 如果平均值明显为负
                baseline = np.mean(dark_values)
                self.df['N2O'] = self.df['N2O_raw'] - baseline
                correction_info['correction'] = baseline
            else:
                # 只对负值进行最小校正
                min_value = np.min(self.df['N2O_raw'])
                if min_value < 0:
                    correction = min_value - 0.001  # 稍微向上平移
                    self.df['N2O'] = self.df['N2O_raw'] - correction
                    correction_info['correction'] = correction
                else:
                    correction_info['correction'] = 0

        # 可选：设置最小阈值
        # self.df['N2O'] = np.maximum(self.df['N2O'], 0.001)

        return correction_info

    def robust_mechanistic_model(self, X, a, b, c, d, e, f, g):
        """
        稳健的机制模型，处理负值和极值
        N2O = max(a * exp(b * (NO2 + c * NO3)) * (d * Light + e) + f * Light + g, threshold)
        """
        NO2, NO3, Light = X[0], X[1], X[2]

        # 确保转换系数合理
        conversion_factor = np.clip(abs(c), 0.0001, 1.0)
        equivalent_NO2 = NO2 + conversion_factor * NO3

        # 限制指数参数避免数值爆炸
        exp_arg = np.clip(b * equivalent_NO2, -10, 10)

        # 主要响应项
        main_response = a * np.exp(exp_arg) * (d * Light + e)

        # 线性光照项（处理基线效应）
        linear_response = f * Light

        # 基线项
        baseline = g

        result = main_response + linear_response + baseline

        # 可选：设置最小阈值防止负值
        # result = np.maximum(result, 0.001)

        return result

    def mechanistic_with_consumption(self, X, a, b, c, d, e, f, g, h):
        """
        考虑N2O消耗的模型
        N2O_net = N2O_production - N2O_consumption
        """
        NO2, NO3, Light = X[0], X[1], X[2]

        # N2O产生项
        conversion_factor = np.clip(abs(c), 0.0001, 1.0)
        equivalent_NO2 = NO2 + conversion_factor * NO3
        exp_arg = np.clip(b * equivalent_NO2, -10, 10)

        production = a * np.exp(exp_arg) * (d * Light + e)

        # N2O消耗项（在低光照或无光照时可能更显著）
        consumption = f * (NO2 + g * NO3) * np.exp(-h * Light)  # 光照抑制消耗

        return production - consumption

    def fit_baseline_corrected_models(self):
        """拟合基线校正后的模型"""
        X = np.array([self.df['NO2'], self.df['NO3'], self.df['Light_total']])
        y = self.df['N2O'].values

        models = {
            'Robust_Mechanistic': {
                'func': self.robust_mechanistic_model,
                'bounds': [(0.01, 100), (0.01, 2), (0.0001, 1), (0, 100), (-10, 10), (-100, 100), (-10, 10)],
                'initial': [1, 0.1, 0.01, 1, 0, 0, 0]
            },
            'With_Consumption': {
                'func': self.mechanistic_with_consumption,
                'bounds': [(0.01, 100), (0.01, 2), (0.0001, 1), (0, 100), (-10, 10), (0, 10), (0, 1), (0, 10)],
                'initial': [1, 0.1, 0.01, 1, 0, 0.1, 0.1, 1]
            }
        }

        results = {}
        best_r2 = -np.inf

        for name, model_info in models.items():
            print(f"拟合 {name}...")

            try:
                # 尝试curve_fit
                try:
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
                    method_used = "curve_fit"
                except:
                    # 使用差分进化算法
                    def objective(params):
                        try:
                            pred = model_info['func'](X, *params)
                            return np.sum((y - pred) ** 2)
                        except:
                            return 1e10

                    result = differential_evolution(
                        objective,
                        model_info['bounds'],
                        seed=42,
                        maxiter=1000
                    )
                    popt = result.x
                    method_used = "differential_evolution"

                # 评估模型
                y_pred = model_info['func'](X, *popt)
                r2 = r2_score(y, y_pred)
                rmse = np.sqrt(np.mean((y - y_pred) ** 2))

                # 检查负值预测
                negative_predictions = np.sum(y_pred < 0)

                results[name] = {
                    'params': popt,
                    'r2': r2,
                    'rmse': rmse,
                    'y_pred': y_pred,
                    'model_func': model_info['func'],
                    'method': method_used,
                    'negative_preds': negative_predictions
                }

                print(f"  成功! R² = {r2:.4f}, RMSE = {rmse:.4f}")
                print(f"  负值预测数: {negative_predictions}")
                print(f"  NO3转换系数: {abs(popt[2]):.6f}")

                if r2 > best_r2:
                    best_r2 = r2
                    self.best_model_func = model_info['func']
                    self.params = popt
                    self.model_type = name

            except Exception as e:
                print(f"  失败: {e}")
                results[name] = None

            print()

        return results

    def analyze_baseline_effects(self):
        """分析基线校正的效果"""
        print("\\n" + "=" * 60)
        print("基线校正效果分析")
        print("=" * 60)

        print(f"\\n基线校正方法: {self.baseline_correction['method']}")

        if 'corrections' in self.baseline_correction:
            print("各组基线校正值:")
            for group, correction in self.baseline_correction['corrections'].items():
                print(f"  {group}: {correction:.6f}")
        elif 'correction' in self.baseline_correction:
            print(f"整体基线校正值: {self.baseline_correction['correction']:.6f}")

        print("\\n校正前后对比:")
        print("条件\\t\\t原始值\\t\\t校正值\\t\\t差异")

        # 分析无光照条件
        dark_mask = self.df['Light_total'] == 0
        for i, row in self.df[dark_mask].iterrows():
            diff = row['N2O'] - row['N2O_raw']
            print(f"{row['group'][:8]}\\t{row['N2O_raw']:.5f}\\t\\t{row['N2O']:.5f}\\t\\t{diff:.5f}")

        # 统计
        print(f"\\n统计信息:")
        print(f"校正前负值个数: {np.sum(self.df['N2O_raw'] < 0)}")
        print(f"校正后负值个数: {np.sum(self.df['N2O'] < 0)}")
        print(f"校正前最小值: {np.min(self.df['N2O_raw']):.6f}")
        print(f"校正后最小值: {np.min(self.df['N2O']):.6f}")

    def plot_baseline_analysis(self, results):
        """绘制基线分析图"""
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('基线校正与模型分析', fontsize=16)

        # 1. 校正前后对比
        ax1 = axes[0, 0]
        ax1.scatter(self.df['N2O_raw'], self.df['N2O'], alpha=0.7)
        min_val = min(self.df['N2O_raw'].min(), self.df['N2O'].min())
        max_val = max(self.df['N2O_raw'].max(), self.df['N2O'].max())
        ax1.plot([min_val, max_val], [min_val, max_val], 'r--', alpha=0.5)
        ax1.set_xlabel('原始N2O值')
        ax1.set_ylabel('校正后N2O值')
        ax1.set_title('基线校正前后对比')
        ax1.grid(True, alpha=0.3)

        # 2. 无光照条件分析
        ax2 = axes[0, 1]
        dark_mask = self.df['Light_total'] == 0
        groups = self.df[dark_mask]['group'].unique()
        colors = ['red', 'blue', 'green']

        for i, group in enumerate(groups):
            group_mask = dark_mask & (self.df['group'] == group)
            ax2.scatter(self.df[group_mask]['N2O_raw'], [i] * sum(group_mask),
                        color=colors[i], alpha=0.7, label=f'{group} 原始')
            ax2.scatter(self.df[group_mask]['N2O'], [i + 0.1] * sum(group_mask),
                        color=colors[i], alpha=0.7, marker='s', label=f'{group} 校正')

        ax2.axvline(x=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_xlabel('N2O值')
        ax2.set_ylabel('数据组')
        ax2.set_title('无光照条件下的基线校正')
        ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

        # 3. 最佳模型预测结果
        ax3 = axes[0, 2]
        if self.model_type and results.get(self.model_type):
            best_result = results[self.model_type]
            y_true = self.df['N2O']
            y_pred = best_result['y_pred']

            colors_group = {'NO2_only': 'red', 'NO3_only': 'blue', 'mixed': 'green'}
            for group in self.df['group'].unique():
                mask = self.df['group'] == group
                ax3.scatter(y_true[mask], y_pred[mask],
                            label=group, alpha=0.7, color=colors_group.get(group, 'gray'))

            max_val = max(y_true.max(), y_pred.max())
            min_val = min(y_true.min(), y_pred.min())
            ax3.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5)
            ax3.set_xlabel('实际值')
            ax3.set_ylabel('预测值')
            ax3.set_title(f'最佳模型: {self.model_type}\\nR² = {best_result["r2"]:.4f}')
            ax3.legend()
            ax3.grid(True, alpha=0.3)

        # 4. 残差分析
        ax4 = axes[1, 0]
        if self.model_type and results.get(self.model_type):
            residuals = y_true - y_pred
            ax4.scatter(y_pred, residuals, alpha=0.7)
            ax4.axhline(y=0, color='red', linestyle='--')
            ax4.set_xlabel('预测值')
            ax4.set_ylabel('残差')
            ax4.set_title('残差分析')
            ax4.grid(True, alpha=0.3)

        # 5. 负值预测分析
        ax5 = axes[1, 1]
        if results:
            model_names = list(results.keys())
            negative_counts = [results[name]['negative_preds'] if results[name] else 0 for name in model_names]

            bars = ax5.bar(range(len(model_names)), negative_counts, alpha=0.7)
            ax5.set_xlabel('模型')
            ax5.set_ylabel('负值预测数')
            ax5.set_title('各模型的负值预测情况')
            ax5.set_xticks(range(len(model_names)))
            ax5.set_xticklabels(model_names, rotation=45)

        # 6. 光照-N2O关系（校正后）
        ax6 = axes[1, 2]
        scatter = ax6.scatter(self.df['Light_total'], self.df['N2O'],
                              c=self.df['NO2'] + self.df['NO3'], cmap='viridis', alpha=0.7)
        ax6.set_xlabel('光照强度')
        ax6.set_ylabel('N2O产生速率（校正后）')
        ax6.set_title('光照-N2O关系（基线校正后）')
        plt.colorbar(scatter, ax=ax6, label='总氮浓度')
        ax6.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()


def main():
    """主函数 - 测试不同基线校正方法"""
    print("基线校正的N2O产生速率模型")
    print("=" * 60)

    baseline_methods = ['none', 'overall', 'group_specific', 'adaptive']

    for method in baseline_methods:
        print(f"\\n测试基线校正方法: {method}")
        print("-" * 40)

        # 创建模型实例
        model = BaselineCorrectedN2OModel()

        # 准备数据并应用基线校正
        df = model.prepare_data(baseline_method=method)

        # 分析基线校正效果
        model.analyze_baseline_effects()

        # 拟合模型
        print("\\n拟合模型...")
        results = model.fit_baseline_corrected_models()

        if results and any(results.values()):
            # 绘制分析结果
            model.plot_baseline_analysis(results)

            # 推荐
            valid_results = {k: v for k, v in results.items() if v is not None}
            if valid_results:
                best_model_name = max(valid_results.keys(), key=lambda k: valid_results[k]['r2'])
                best_result = valid_results[best_model_name]
                print(f"\\n{method}方法的最佳结果:")
                print(f"  模型: {best_model_name}")
                print(f"  R²: {best_result['r2']:.4f}")
                print(f"  RMSE: {best_result['rmse']:.4f}")
                print(f"  负值预测数: {best_result['negative_preds']}")

        print("\\n" + "=" * 60)


if __name__ == "__main__":
    main()