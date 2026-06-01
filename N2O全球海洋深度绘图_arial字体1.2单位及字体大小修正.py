import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
import os
import glob
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import simpledialog
from scipy.interpolate import griddata
from scipy import stats
import warnings
import gc  # 添加垃圾回收模块
from matplotlib.colors import ListedColormap, LinearSegmentedColormap

warnings.filterwarnings('ignore')


class ImprovedOceanDataVisualizer:
    def __init__(self):
        self.data = None
        self.input_folder = ""
        self.csv_files = []
        self.output_folder = ""
        self.plot_method = "high_res_grid"  # 默认方法
        self.color_scale_mode = "auto"  # 'auto' 或 'manual'
        self.color_limits = {}  # 存储每个变量的颜色范围
        self.plot_type = "both"  # 'global', 'latitudinal', 'both'
        self.error_type = "sem"  # 'sem', 'ci95', 'std'
        self.selected_colormap = "deep_blue_bright_yellow"  # 默认配色

        # 字体大小配置
        self.font_sizes = {
            'colorbar_label': 30,  # 颜色条标签字体大小
            'colorbar_ticks': 28,  # 颜色条刻度数字字体大小
            'grid_labels': 28,     # 全球图网格线标签字体大小
            'lat_ylabel': 28,      # 纬度图Y轴标签字体大小
            'lat_xlabel': 22,      # 纬度图X轴标签字体大小
            'lat_ticks': 26,       # 纬度图刻度数字字体大小
        }

        # 为不同变量定义不同的配色方案（协调但有区别）
        self.color_schemes = {
            'N2O_UVB': {
                'cmap': 'deep_blue_bright_yellow',
                'label': r'N$_{\mathbf{2}}$O emissions (nmol-N L$^{\mathbf{-1}}$ yr$^{\mathbf{-1}}$)'
            },
            'N2O_UVA': {
                'cmap': 'black_red_white',
                'label': r'N$_{\mathbf{2}}$O emissions (nmol-N L$^{\mathbf{-1}}$ yr$^{\mathbf{-1}}$)'
            },
            'N2O_BLUE': {
                'cmap': 'purple_green_contrast',
                'label': r'N$_{\mathbf{2}}$O emissions (nmol-N L$^{\mathbf{-1}}$ yr$^{\mathbf{-1}}$)'
            },
            'N2O_total': {
                'cmap': 'turbo_like',
                'label': r'N$_{\mathbf{2}}$O emissions (nmol-N L$^{\mathbf{-1}}$ yr$^{\mathbf{-1}}$)'
            }
        }

        # 图形尺寸设置 - 确保纵向比例一致，纬度图宽度一致
        self.global_fig_size = (16, 10)  # 全球图尺寸
        self.lat_fig_size = (6, 8)  # 纬度图尺寸，固定宽度6，纵向高度与全球图匹配

        # 定义自定义配色方案
        self.custom_colormaps = self.create_custom_colormaps()

    def create_custom_colormaps(self):
        """创建自定义配色方案"""
        custom_maps = {}

        # 高对比度配色
        custom_maps['deep_blue_bright_yellow'] = LinearSegmentedColormap.from_list(
            'deep_blue_bright_yellow',
            ['#000080', '#0066CC', '#00CCFF', '#FFFF00', '#FFCC00']
        )

        custom_maps['black_red_white'] = LinearSegmentedColormap.from_list(
            'black_red_white',
            ['#000000', '#800000', '#FF0000', '#FF8080', '#FFFFFF']
        )

        custom_maps['purple_green_contrast'] = LinearSegmentedColormap.from_list(
            'purple_green_contrast',
            ['#800080', '#CC00CC', '#FFFFFF', '#00CC00', '#008000']
        )

        custom_maps['segmented_rainbow'] = LinearSegmentedColormap.from_list(
            'segmented_rainbow',
            ['#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF8000', '#FF0000']
        )

        custom_maps['blue_white_red'] = LinearSegmentedColormap.from_list(
            'blue_white_red',
            ['#0000FF', '#8080FF', '#FFFFFF', '#FF8080', '#FF0000']
        )

        custom_maps['turbo_like'] = LinearSegmentedColormap.from_list(
            'turbo_like',
            ['#30123B', '#4662D7', '#36AAF9', '#1AE4B6', '#72FE5E', '#C7EF34',
             '#FABA39', '#F66B19', '#CB2A04', '#7A0403']
        )

        custom_maps['enhanced_jet'] = LinearSegmentedColormap.from_list(
            'enhanced_jet',
            ['#000080', '#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF0000', '#800000']
        )

        custom_maps['extreme_contrast'] = LinearSegmentedColormap.from_list(
            'extreme_contrast',
            ['#000000', '#FF00FF', '#00FFFF', '#FFFF00', '#FFFFFF']
        )

        return custom_maps

    def get_colormap_options(self):
        """获取配色方案选项"""
        return {
            # 高对比度配色（推荐）
            'deep_blue_bright_yellow': '🔥 深蓝→亮黄 - 极高对比度，数据差异明显',
            'black_red_white': '🔥 黑→红→白 - 经典热力图，对比强烈',
            'purple_green_contrast': '🔥 紫→绿对比 - 颜色互补，视觉冲击强',
            'segmented_rainbow': '🔥 分段彩虹 - 多色分段，区分度极高',
            'blue_white_red': '🔥 蓝→白→红 - 发散式配色，中性点明显',
            'turbo_like': '🔥 科学专用 - Google Turbo风格，感知均匀',
            'enhanced_jet': '🔥 增强Jet - 改进的彩虹配色，对比度优化',
            'extreme_contrast': '🔥 极限对比 - 黑白彩色混合，最强对比',

            # 经典配色（备选）
            'inferno': '⭐ 经典Inferno - 黑→紫→红→黄（科学标准）',
            'viridis': '⭐ 经典Viridis - 紫→蓝→绿→黄（感知均匀）',
            'plasma': '⭐ 经典Plasma - 紫→粉→黄（高对比度）',
            'turbo': '⭐ Google Turbo - 改进的Jet配色（如果可用）',
            'cividis': '♿ 色盲友好 - 蓝→黄（无障碍设计）'
        }

    def select_colormap(self):
        """选择配色方案"""
        colormap_options = self.get_colormap_options()

        print("\n" + "=" * 80)
        print("选择配色方案:")
        print("=" * 80)

        # 分类显示
        print("\n🔥 高对比度配色（推荐用于突出数据差异）:")
        high_contrast = ['deep_blue_bright_yellow', 'black_red_white', 'purple_green_contrast',
                         'segmented_rainbow', 'blue_white_red', 'turbo_like', 'enhanced_jet', 'extreme_contrast']
        for i, cmap in enumerate(high_contrast, 1):
            print(f"{i:2d}. {colormap_options[cmap]}")

        print("\n⭐ 经典科学配色:")
        classic = ['inferno', 'viridis', 'plasma', 'turbo']
        for i, cmap in enumerate(classic, len(high_contrast) + 1):
            print(f"{i:2d}. {colormap_options[cmap]}")

        print("\n♿ 无障碍配色:")
        accessible = ['cividis']
        for i, cmap in enumerate(accessible, len(high_contrast) + len(classic) + 1):
            print(f"{i:2d}. {colormap_options[cmap]}")

        print("=" * 80)
        print("说明：")
        print("- 🔥 高对比度配色：适合突出数据的细微差异")
        print("- ⭐ 经典配色：科学出版物常用，感知均匀")
        print("- ♿ 无障碍配色：色盲友好设计")

        all_cmaps = high_contrast + classic + accessible

        while True:
            try:
                choice = input(f"\n请选择配色方案 (1-{len(all_cmaps)}，默认1): ").strip()
                if not choice:
                    choice = "1"  # 默认选择深蓝→亮黄

                choice_num = int(choice)
                if 1 <= choice_num <= len(all_cmaps):
                    self.selected_colormap = all_cmaps[choice_num - 1]
                    print(f"✓ 已选择: {colormap_options[self.selected_colormap]}")

                    # 更新所有变量的默认配色
                    for var in self.color_schemes:
                        self.color_schemes[var]['cmap'] = self.selected_colormap

                    return self.selected_colormap
                else:
                    print(f"✗ 请输入 1-{len(all_cmaps)} 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认选择: 深蓝→亮黄")
                self.selected_colormap = "deep_blue_bright_yellow"
                return self.selected_colormap

    def get_colormap(self, cmap_name):
        """获取配色方案对象"""
        if cmap_name in self.custom_colormaps:
            return self.custom_colormaps[cmap_name]
        else:
            # 返回matplotlib内置配色
            try:
                return plt.cm.get_cmap(cmap_name)
            except:
                # 如果配色不存在，使用默认
                return self.custom_colormaps['deep_blue_bright_yellow']

    def get_color_config(self, variable):
        """获取变量的配色配置"""
        if variable in self.color_schemes:
            return self.color_schemes[variable]
        else:
            # 默认配色
            return {
                'cmap': self.selected_colormap,
                'label': r'N$_{\mathbf{2}}$O emissions (nmol-N L$^{\mathbf{-1}}$ yr$^{\mathbf{-1}}$)'
            }

    def clear_memory(self):
        """清理内存"""
        # 清理matplotlib的内存
        plt.clf()
        plt.close('all')
        # 强制垃圾回收
        gc.collect()

    def select_error_type(self):
        """选择误差类型"""
        error_types = {
            1: ("sem", "标准误差 (Standard Error of Mean)"),
            2: ("ci95", "95%置信区间 (95% Confidence Interval)"),
            3: ("std", "一倍标准差 (Standard Deviation)")
        }

        print("\n" + "=" * 50)
        print("选择纬度均值图的误差显示类型:")
        print("=" * 50)
        for num, (error_type, desc) in error_types.items():
            print(f"{num}. {desc}")
        print("=" * 50)
        print("说明:")
        print("- 标准误差：反映均值的精度，常用于科学论文")
        print("- 95%置信区间：统计显著性的标准范围")
        print("- 标准差：反映数据的变异程度")

        while True:
            try:
                choice = input(f"\n请选择误差类型 (1-{len(error_types)}，默认1): ").strip()
                if not choice:
                    choice = "1"  # 默认选择标准误差

                choice_num = int(choice)
                if 1 <= choice_num <= len(error_types):
                    self.error_type = error_types[choice_num][0]
                    print(f"✓ 已选择: {error_types[choice_num][1]}")
                    return self.error_type
                else:
                    print(f"✗ 请输入 1-{len(error_types)} 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认选择: 标准误差")
                self.error_type = "sem"
                return self.error_type

    def select_plot_type(self):
        """选择绘图类型"""
        plot_types = {
            1: ("global", "仅绘制全球分布图"),
            2: ("latitudinal", "仅绘制纬度均值图"),
            3: ("both", "绘制两种图（推荐）")
        }

        print("\n" + "=" * 50)
        print("选择绘图类型:")
        print("=" * 50)
        for num, (plot_type, desc) in plot_types.items():
            print(f"{num}. {desc}")
        print("=" * 50)

        while True:
            try:
                choice = input(f"\n请选择绘图类型 (1-{len(plot_types)}，默认3): ").strip()
                if not choice:
                    choice = "3"  # 默认选择两种都绘制

                choice_num = int(choice)
                if 1 <= choice_num <= len(plot_types):
                    self.plot_type = plot_types[choice_num][0]
                    print(f"✓ 已选择: {plot_types[choice_num][1]}")
                    return self.plot_type
                else:
                    print(f"✗ 请输入 1-{len(plot_types)} 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认选择: 绘制两种图")
                self.plot_type = "both"
                return self.plot_type

    def select_plot_method(self):
        """选择绘图方法（仅对全球分布图有效）"""
        if self.plot_type == "latitudinal":
            self.plot_method = "high_res_grid"  # 纬度图不需要选择方法
            return self.plot_method

        methods = {
            1: ("scatter", "散点图 - 直接显示原始数据点（最真实）"),
            2: ("high_res_grid", "高分辨率网格 - 0.5度网格（保持高分辨率）"),
            3: ("interpolation", "插值网格 - 平滑插值（最美观）"),
            4: ("original_grid", "原始2度网格 - 快速预览（最快）")
        }

        print("\n" + "=" * 60)
        print("选择全球分布图的绘图方法:")
        print("=" * 60)
        for num, (method, desc) in methods.items():
            print(f"{num}. {desc}")
        print("=" * 60)

        print("\n推荐:")
        print("- 如果数据量很大(>100万点): 选择 2 或 3")
        print("- 如果想看原始数据分布: 选择 1")
        print("- 如果想要最美观的图: 选择 3")
        print("- 如果内存有限: 选择 4")

        while True:
            try:
                choice = input(f"\n请选择绘图方法 (1-{len(methods)}，默认2): ").strip()
                if not choice:
                    choice = "2"  # 默认选择高分辨率网格

                choice_num = int(choice)
                if 1 <= choice_num <= len(methods):
                    self.plot_method = methods[choice_num][0]
                    print(f"✓ 已选择: {methods[choice_num][1]}")
                    return self.plot_method
                else:
                    print(f"✗ 请输入 1-{len(methods)} 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认方法: 高分辨率网格")
                self.plot_method = "high_res_grid"
                return self.plot_method

    def select_color_scale_mode(self):
        """选择颜色刻度模式"""
        print("\n" + "=" * 50)
        print("选择颜色刻度模式:")
        print("=" * 50)
        print("1. 自动调整 - 根据每个图的数据范围自动调整")
        print("2. 手动设置 - 为每种变量设置统一的上下限")
        print("=" * 50)
        print("注意：所有变量将使用相同的配色方案")
        print(f"当前选择的配色方案: {self.selected_colormap}")

        while True:
            try:
                choice = input("\n请选择模式 (1-2，默认1): ").strip()
                if not choice:
                    choice = "1"

                if choice == "1":
                    self.color_scale_mode = "auto"
                    print("✓ 已选择: 自动调整模式")
                    return
                elif choice == "2":
                    self.color_scale_mode = "manual"
                    print("✓ 已选择: 手动设置模式")
                    self.set_manual_color_limits()
                    return
                else:
                    print("✗ 请输入 1 或 2")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认模式: 自动调整")
                self.color_scale_mode = "auto"
                return

    def set_manual_color_limits(self):
        """设置手动颜色范围"""
        variables = ['N2O_UVB', 'N2O_UVA', 'N2O_BLUE', 'N2O_total']

        for var in variables:
            color_config = self.get_color_config(var)
            print(f"\n设置 {var} 的颜色范围:")
            while True:
                try:
                    min_val = float(input(f"  {var} 最小值: "))
                    max_val = float(input(f"  {var} 最大值: "))
                    if min_val >= max_val:
                        print("  ✗ 最小值必须小于最大值")
                        continue
                    self.color_limits[var] = (min_val, max_val)
                    print(f"  ✓ {var} 范围设置为: {min_val} - {max_val}")
                    break
                except ValueError:
                    print("  ✗ 请输入有效的数字")

    def select_input_folder(self):
        """选择包含CSV文件的输入文件夹"""
        root = tk.Tk()
        root.withdraw()

        folder_path = filedialog.askdirectory(title="选择包含CSV文件的输入文件夹")

        if folder_path:
            self.input_folder = folder_path
            # 查找所有CSV文件
            self.csv_files = glob.glob(os.path.join(folder_path, "*.csv"))

            if self.csv_files:
                print(f"输入文件夹: {self.input_folder}")
                print(f"找到 {len(self.csv_files)} 个CSV文件:")
                for i, file in enumerate(self.csv_files, 1):
                    print(f"  {i}. {os.path.basename(file)}")
                return True
            else:
                print(f"在文件夹 {folder_path} 中没有找到CSV文件")
                return False
        else:
            print("未选择输入文件夹")
            return False

    def select_output_folder(self):
        """选择输出文件夹"""
        root = tk.Tk()
        root.withdraw()

        folder_path = filedialog.askdirectory(title="选择输出文件夹")

        if folder_path:
            self.output_folder = folder_path
            print(f"输出文件夹: {self.output_folder}")
            return True
        else:
            print("未选择输出文件夹")
            return False

    def load_single_csv(self, file_path):
        """加载单个CSV文件，优化内存使用"""
        try:
            print(f"  加载: {os.path.basename(file_path)}")

            # 只读取需要的列，减少内存使用
            required_columns = ['longitude', 'latitude', 'depth', 'N2O_UVB', 'N2O_UVA', 'N2O_BLUE', 'N2O_total']
            optional_columns = ['year']

            # 先读取列名
            sample_df = pd.read_csv(file_path, nrows=0)
            available_columns = sample_df.columns.tolist()

            columns_to_read = [col for col in required_columns if col in available_columns]
            columns_to_read.extend([col for col in optional_columns if col in available_columns])

            # 使用数据类型优化减少内存
            dtype_dict = {
                'longitude': 'float32',
                'latitude': 'float32',
                'depth': 'float32',
                'N2O_UVB': 'float32',
                'N2O_UVA': 'float32',
                'N2O_BLUE': 'float32',
                'N2O_total': 'float32'
            }

            df = pd.read_csv(file_path, usecols=columns_to_read, dtype=dtype_dict)
            print(f"  数据行数: {len(df)}")
            print(f"  数据列: {list(df.columns)}")
            print(f"  内存使用: {df.memory_usage(deep=True).sum() / 1024 ** 2:.2f} MB")

            # 显示数据分辨率信息
            if len(df) > 0 and 'longitude' in df.columns and 'latitude' in df.columns:
                lon_resolution = self.estimate_resolution(df, 'longitude')
                lat_resolution = self.estimate_resolution(df, 'latitude')
                print(f"  估计的数据分辨率: 经度 {lon_resolution:.3f}°, 纬度 {lat_resolution:.3f}°")

            return df
        except Exception as e:
            print(f"  ✗ 加载文件出错: {e}")
            return None

    def estimate_resolution(self, data, coord_column):
        """估计数据的分辨率"""
        if coord_column not in data.columns:
            return 1.0

        # 取样本数据估计分辨率
        sample_data = data[coord_column].dropna().sort_values()
        if len(sample_data) < 2:
            return 1.0

        # 计算相邻点的最小差值
        diffs = sample_data.diff().dropna()
        min_diff = diffs[diffs > 0].min() if len(diffs[diffs > 0]) > 0 else 1.0

        return min_diff

    def get_available_depths(self, data):
        """获取可用的深度值"""
        if data is None or 'depth' not in data.columns:
            return []
        return sorted(data['depth'].unique())

    def select_depths(self, sample_data):
        """选择要绘制的深度"""
        available_depths = self.get_available_depths(sample_data)

        if not available_depths:
            print("数据中没有找到深度信息")
            return []

        print("\n" + "=" * 50)
        print("可用深度值:")
        print("=" * 50)
        for i, depth in enumerate(available_depths):
            print(f"{i + 1:2d}. {depth}m")
        print("=" * 50)

        print("\n输入示例:")
        print("- 选择单个深度: 输入 1")
        print("- 选择多个深度: 输入 1,3,5")
        print("- 选择前几个深度: 输入 1,2,3")
        print("-" * 30)

        while True:
            try:
                depth_input = input(f"\n请输入深度编号 (1-{len(available_depths)})，多个深度用逗号分隔: ").strip()

                if not depth_input:
                    print("未输入任何内容，请重新输入")
                    continue

                indices = []
                for item in depth_input.split(','):
                    item = item.strip()
                    if not item:
                        continue
                    index = int(item) - 1
                    if 0 <= index < len(available_depths):
                        indices.append(index)
                    else:
                        print(f"错误: 编号 {int(item)} 超出范围 (1-{len(available_depths)})")
                        raise ValueError("编号超出范围")

                if not indices:
                    print("没有选择有效的深度，请重新输入")
                    continue

                selected_depths = [available_depths[i] for i in indices]
                print(f"\n✓ 已选择深度: {selected_depths}")
                return selected_depths

            except ValueError as e:
                print(f"✗ 输入格式错误: {e}")
                print("请输入正确的数字编号，多个编号用逗号分隔")
                continue
            except KeyboardInterrupt:
                print("\n用户取消选择")
                return []

    def select_variables(self):
        """选择要绘制的变量（可多选）"""
        variables = ['N2O_UVB', 'N2O_UVA', 'N2O_BLUE', 'N2O_total']

        print("\n" + "=" * 50)
        print("可用变量:")
        print("=" * 50)
        for i, var in enumerate(variables):
            color_config = self.get_color_config(var)
            print(f"{i + 1}. {var}")
        print("=" * 50)
        print("\n输入示例:")
        print("- 选择单个变量: 输入 1")
        print("- 选择多个变量: 输入 1,2,3")
        print("- 选择所有变量: 输入 1,2,3,4")

        while True:
            try:
                var_input = input(f"\n请输入变量编号 (1-{len(variables)})，多个变量用逗号分隔: ").strip()

                if not var_input:
                    print("未输入任何内容，使用默认变量: N2O_UVB")
                    return ['N2O_UVB']

                indices = []
                for item in var_input.split(','):
                    item = item.strip()
                    if not item:
                        continue
                    index = int(item) - 1
                    if 0 <= index < len(variables):
                        indices.append(index)
                    else:
                        print(f"错误: 编号 {int(item)} 超出范围 (1-{len(variables)})")
                        raise ValueError("编号超出范围")

                if not indices:
                    print("没有选择有效的变量，请重新输入")
                    continue

                selected_vars = [variables[i] for i in indices]
                print(f"✓ 已选择变量: {selected_vars}")
                return selected_vars

            except ValueError as e:
                print(f"✗ 输入格式错误: {e}")
                continue
            except KeyboardInterrupt:
                print("\n使用默认变量: N2O_UVB")
                return ['N2O_UVB']

    def calculate_latitudinal_statistics(self, data_subset, variable, lat_bin_size=1.0):
        """计算纬度统计数据"""
        # 创建纬度区间
        lat_min = data_subset['latitude'].min()
        lat_max = data_subset['latitude'].max()
        lat_bins = np.arange(lat_min, lat_max + lat_bin_size, lat_bin_size)
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        means = []
        errors = []  # 根据error_type计算不同的误差
        counts = []

        for i in range(len(lat_bins) - 1):
            # 选择在该纬度带内的数据
            mask = (data_subset['latitude'] >= lat_bins[i]) & (data_subset['latitude'] < lat_bins[i + 1])
            bin_data = data_subset[mask][variable].dropna()

            if len(bin_data) > 0:
                mean_val = bin_data.mean()
                count_val = len(bin_data)

                # 根据误差类型计算误差值
                if self.error_type == "sem":
                    # 标准误差
                    error_val = stats.sem(bin_data) if len(bin_data) > 1 else 0
                elif self.error_type == "ci95":
                    # 95%置信区间
                    if len(bin_data) > 1:
                        ci = stats.t.interval(0.95, len(bin_data) - 1,
                                              loc=mean_val,
                                              scale=stats.sem(bin_data))
                        error_val = (ci[1] - ci[0]) / 2  # 半宽度
                    else:
                        error_val = 0
                elif self.error_type == "std":
                    # 标准差
                    error_val = bin_data.std() if len(bin_data) > 1 else 0
                else:
                    error_val = 0
            else:
                mean_val = np.nan
                error_val = np.nan
                count_val = 0

            means.append(mean_val)
            errors.append(error_val)
            counts.append(count_val)

        # 过滤掉没有数据的纬度带
        valid_indices = ~np.isnan(means)
        lat_centers_valid = lat_centers[valid_indices]
        means_valid = np.array(means)[valid_indices]
        errors_valid = np.array(errors)[valid_indices]
        counts_valid = np.array(counts)[valid_indices]

        return lat_centers_valid, means_valid, errors_valid, counts_valid

    def create_latitudinal_plot(self, data_subset, variable, depth, year=None):
        """创建纬度均值图"""
        # 计算纬度统计数据
        lat_centers, means, errors, counts = self.calculate_latitudinal_statistics(data_subset, variable)

        if len(lat_centers) == 0:
            print(f"      ✗ 没有足够的数据来创建纬度图")
            return None

        # 创建图形 - 使用固定尺寸确保与全球图纵向一致，宽度保持一致
        fig, ax = plt.subplots(figsize=self.lat_fig_size)

        # 获取变量的配色配置
        color_config = self.get_color_config(variable)

        # 根据误差类型选择合适的倍数
        if self.error_type == "sem":
            error_multiplier = 2  # ±2倍标准误差
        elif self.error_type == "ci95":
            error_multiplier = 1  # 95%置信区间本身已经是范围
        else:  # std
            error_multiplier = 1  # ±1倍标准差

        error_range = error_multiplier * errors

        # 绘制深灰色阴影区域 - 移除label参数
        ax.fill_betweenx(lat_centers, means - error_range, means + error_range,
                         alpha=0.5, color='darkgray', edgecolor='none')

        # 绘制黑色实线均值线 - 移除label参数
        ax.plot(means, lat_centers, color='black', linewidth=1.5,
                linestyle='-', solid_capstyle='round')

        # 设置坐标轴 - 纬度图的X轴和Y轴标签使用配置的字体大小
        ax.set_ylabel('Latitude', fontsize=self.font_sizes['lat_ylabel'], fontname='Arial', weight='bold')
        ax.set_xlabel(color_config['label'], fontsize=self.font_sizes['lat_xlabel'], fontname='Arial', weight='bold')

        # 关键：设置与全球图完全相同的y轴范围和刻度（恢复完整纬度范围）
        ax.set_ylim(-90, 90)
        ax.set_yticks(np.arange(-90, 91, 30))
        ax.set_yticklabels([f'{int(lat)}°' if lat != 0 else '0°' for lat in np.arange(-90, 91, 30)])

        # 设置x轴从0开始
        x_min = 0
        x_max = max(means + error_range) * 1.1  # 留一些边距
        ax.set_xlim(x_min, x_max)

        # 让matplotlib自动选择"好看"的刻度，然后限制数量
        # 先让matplotlib自动选择刻度
        ax.locator_params(axis='x', nbins=4)  # 建议最多4个刻度区间（5个刻度点）

        # 获取matplotlib自动生成的刻度
        auto_ticks = ax.get_xticks()

        # 确保0在刻度中，并过滤掉超出范围的刻度
        filtered_ticks = []
        for tick in auto_ticks:
            if x_min <= tick <= x_max:
                filtered_ticks.append(tick)

        # 如果0不在刻度中，添加0
        if 0 not in filtered_ticks and x_min <= 0 <= x_max:
            filtered_ticks.insert(0, 0)
            filtered_ticks = sorted(filtered_ticks)

        # 限制刻度数量（最多5个）
        if len(filtered_ticks) > 5:
            # 保留0和等间距的刻度
            step = len(filtered_ticks) // 4
            filtered_ticks = filtered_ticks[::step][:5]

        # 设置最终的刻度
        ax.set_xticks(filtered_ticks)

        # 不添加网格
        ax.grid(False)

        # 美化图形 - 保持简洁的边框
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_linewidth(1)
        ax.spines['bottom'].set_linewidth(1)

        # 设置刻度标签字体 - 使用配置的字体大小
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontsize(self.font_sizes['lat_ticks'])
            label.set_fontname('Arial')
            label.set_weight('bold')

        # 精确控制图形边距以确保纵向比例与全球图匹配，固定宽度
        fig.subplots_adjust(left=0.15, right=0.92, top=0.95, bottom=0.08)

        return fig

    def create_scatter_plot(self, data_subset, variable, depth, year=None):
        """方法1: 散点图 - 直接显示原始数据点"""
        fig = plt.figure(figsize=self.global_fig_size)
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 只显示海岸线，不显示国界
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 获取变量的配色配置
        color_config = self.get_color_config(variable)
        cmap = self.get_colormap(color_config['cmap'])

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        # 直接绘制散点
        scatter = ax.scatter(
            data_subset['longitude'], data_subset['latitude'],
            c=data_subset[variable],
            s=1,
            cmap=cmap,
            transform=ccrs.PlateCarree(),
            alpha=0.8,
            vmin=vmin, vmax=vmax
        )

        # 添加颜色条 - 使用配置的字体大小
        cbar = plt.colorbar(scatter, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=self.font_sizes['colorbar_label'], fontname='Arial', weight='bold')
        cbar.ax.tick_params(labelsize=self.font_sizes['colorbar_ticks'])
        # 设置颜色条刻度标签字体
        for label in cbar.ax.get_xticklabels():
            label.set_fontname('Arial')
            label.set_weight('bold')

        # 先添加所有网格线（30度间隔），但不显示标签
        ax.gridlines(xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30),
                     draw_labels=False, color='gray', alpha=0.5, linewidth=0.5)

        # 再添加标签（经度60度间隔，纬度30度间隔）- 使用正负数字格式
        gl = ax.gridlines(draw_labels=True, dms=False, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 60), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        # 自定义标签格式 - 使用正负数字而不是NWSE
        def format_lon(x, pos):
            if x == 0:
                return '0°'
            elif x > 0:
                return f'{int(x)}°'
            else:
                return f'{int(x)}°'

        def format_lat(y, pos):
            if y == 0:
                return '0°'
            elif y > 0:
                return f'{int(y)}°'
            else:
                return f'{int(y)}°'

        gl.xformatter = plt.FuncFormatter(format_lon)
        gl.yformatter = plt.FuncFormatter(format_lat)
        gl.xlabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}
        gl.ylabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_high_res_grid(self, data_subset, variable, depth, year=None):
        """方法2: 高分辨率网格 - 保持数据原始分辨率"""
        fig = plt.figure(figsize=self.global_fig_size)
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 只显示海岸线，不显示国界
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 使用0.5度网格
        lon_bins = np.arange(-180, 180.5, 0.5)
        lat_bins = np.arange(-90, 90.5, 0.5)

        lon_centers = (lon_bins[:-1] + lon_bins[1:]) / 2
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        lon_grid, lat_grid = np.meshgrid(lon_centers, lat_centers)
        value_grid = np.full_like(lon_grid, np.nan)

        # 网格化数据
        print(f"  正在进行高分辨率网格化 ({len(lon_centers)}x{len(lat_centers)} 网格)...")
        for i, lat_center in enumerate(lat_centers):
            if i % 50 == 0:
                print(f"    进度: {i}/{len(lat_centers)}")

            for j, lon_center in enumerate(lon_centers):
                lat_mask = (data_subset['latitude'] >= lat_bins[i]) & (data_subset['latitude'] < lat_bins[i + 1])
                lon_mask = (data_subset['longitude'] >= lon_bins[j]) & (data_subset['longitude'] < lon_bins[j + 1])
                cell_data = data_subset[lat_mask & lon_mask]

                if len(cell_data) > 0:
                    value_grid[i, j] = cell_data[variable].mean()

        # 添加循环点
        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_centers)

        # 获取变量的配色配置
        color_config = self.get_color_config(variable)
        cmap = self.get_colormap(color_config['cmap'])

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap=cmap,
            shading='auto',
            vmin=vmin, vmax=vmax
        )

        # 添加颜色条 - 使用配置的字体大小
        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=self.font_sizes['colorbar_label'], fontname='Arial', weight='bold')
        cbar.ax.tick_params(labelsize=self.font_sizes['colorbar_ticks'])
        # 设置颜色条刻度标签字体
        for label in cbar.ax.get_xticklabels():
            label.set_fontname('Arial')
            label.set_weight('bold')

        # 先添加所有网格线（30度间隔），但不显示标签
        ax.gridlines(xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30),
                     draw_labels=False, color='gray', alpha=0.5, linewidth=0.5)

        # 再添加标签（经度60度间隔，纬度30度间隔）- 使用正负数字格式
        gl = ax.gridlines(draw_labels=True, dms=False, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 60), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        # 自定义标签格式 - 使用正负数字而不是NWSE
        def format_lon(x, pos):
            if x == 0:
                return '0°'
            elif x > 0:
                return f'{int(x)}°'
            else:
                return f'{int(x)}°'

        def format_lat(y, pos):
            if y == 0:
                return '0°'
            elif y > 0:
                return f'{int(y)}°'
            else:
                return f'{int(y)}°'

        gl.xformatter = plt.FuncFormatter(format_lon)
        gl.yformatter = plt.FuncFormatter(format_lat)
        gl.xlabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}
        gl.ylabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_interpolated_grid(self, data_subset, variable, depth, year=None):
        """方法3: 插值网格 - 平滑插值，优化内存使用"""
        fig = plt.figure(figsize=self.global_fig_size)
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 只显示海岸线，不显示国界
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 如果数据点太多，进行采样以节省内存
        if len(data_subset) > 50000:
            print(f"  数据量较大({len(data_subset)}点)，进行采样以优化内存...")
            sample_size = min(50000, len(data_subset))
            data_subset = data_subset.sample(n=sample_size, random_state=42)
            print(f"  采样后数据量: {len(data_subset)}点")

        # 创建规则网格用于插值 - 使用更粗的网格节省内存
        lon_interp = np.arange(-180, 181, 1.5)  # 从1度改为1.5度
        lat_interp = np.arange(-90, 91, 1.5)
        lon_grid, lat_grid = np.meshgrid(lon_interp, lat_interp)

        # 准备插值数据
        points = data_subset[['longitude', 'latitude']].values.astype(np.float32)
        values = data_subset[variable].values.astype(np.float32)

        print(f"  正在进行插值计算 (使用 {len(points)} 个数据点)...")

        try:
            # 使用线性插值
            value_grid = griddata(
                points, values,
                (lon_grid, lat_grid),
                method='linear',
                fill_value=np.nan
            )
        except MemoryError:
            print("  内存不足，使用更粗的网格...")
            lon_interp = np.arange(-180, 181, 2)
            lat_interp = np.arange(-90, 91, 2)
            lon_grid, lat_grid = np.meshgrid(lon_interp, lat_interp)
            value_grid = griddata(
                points, values,
                (lon_grid, lat_grid),
                method='linear',
                fill_value=np.nan
            )

        # 添加循环点
        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_interp)

        # 获取变量的配色配置
        color_config = self.get_color_config(variable)
        cmap = self.get_colormap(color_config['cmap'])

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_interp, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap=cmap,
            shading='auto',
            vmin=vmin, vmax=vmax
        )

        # 添加颜色条 - 使用配置的字体大小
        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=self.font_sizes['colorbar_label'], fontname='Arial', weight='bold')
        cbar.ax.tick_params(labelsize=self.font_sizes['colorbar_ticks'])
        # 设置颜色条刻度标签字体
        for label in cbar.ax.get_xticklabels():
            label.set_fontname('Arial')
            label.set_weight('bold')

        # 先添加所有网格线（30度间隔），但不显示标签
        ax.gridlines(xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30),
                     draw_labels=False, color='gray', alpha=0.5, linewidth=0.5)

        # 再添加标签（经度60度间隔，纬度30度间隔）- 使用正负数字格式
        gl = ax.gridlines(draw_labels=True, dms=False, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 60), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        # 自定义标签格式 - 使用正负数字而不是NWSE
        def format_lon(x, pos):
            if x == 0:
                return '0°'
            elif x > 0:
                return f'{int(x)}°'
            else:
                return f'{int(x)}°'

        def format_lat(y, pos):
            if y == 0:
                return '0°'
            elif y > 0:
                return f'{int(y)}°'
            else:
                return f'{int(y)}°'

        gl.xformatter = plt.FuncFormatter(format_lon)
        gl.yformatter = plt.FuncFormatter(format_lat)
        gl.xlabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}
        gl.ylabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_original_grid(self, data_subset, variable, depth, year=None):
        """方法4: 原始2度网格 - 快速预览"""
        fig = plt.figure(figsize=self.global_fig_size)
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 只显示海岸线，不显示国界
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 使用2度网格
        lon_bins = np.arange(-180, 181, 2)
        lat_bins = np.arange(-90, 91, 2)

        lon_centers = (lon_bins[:-1] + lon_bins[1:]) / 2
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        lon_grid, lat_grid = np.meshgrid(lon_centers, lat_centers)
        value_grid = np.full_like(lon_grid, np.nan)

        for i, lat_center in enumerate(lat_centers):
            for j, lon_center in enumerate(lon_centers):
                lat_mask = (data_subset['latitude'] >= lat_bins[i]) & (data_subset['latitude'] < lat_bins[i + 1])
                lon_mask = (data_subset['longitude'] >= lon_bins[j]) & (data_subset['longitude'] < lon_bins[j + 1])
                cell_data = data_subset[lat_mask & lon_mask]

                if len(cell_data) > 0:
                    value_grid[i, j] = cell_data[variable].mean()

        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_centers)

        # 获取变量的配色配置
        color_config = self.get_color_config(variable)
        cmap = self.get_colormap(color_config['cmap'])

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap=cmap,
            shading='auto',
            vmin=vmin, vmax=vmax
        )

        # 添加颜色条 - 使用配置的字体大小
        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=self.font_sizes['colorbar_label'], fontname='Arial', weight='bold')
        cbar.ax.tick_params(labelsize=self.font_sizes['colorbar_ticks'])
        # 设置颜色条刻度标签字体
        for label in cbar.ax.get_xticklabels():
            label.set_fontname('Arial')
            label.set_weight('bold')

        # 先添加所有网格线（30度间隔），但不显示标签
        ax.gridlines(xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30),
                     draw_labels=False, color='gray', alpha=0.5, linewidth=0.5)

        # 再添加标签（经度60度间隔，纬度30度间隔）- 使用正负数字格式
        gl = ax.gridlines(draw_labels=True, dms=False, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 60), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        # 自定义标签格式 - 使用正负数字而不是NWSE
        def format_lon(x, pos):
            if x == 0:
                return '0°'
            elif x > 0:
                return f'{int(x)}°'
            else:
                return f'{int(x)}°'

        def format_lat(y, pos):
            if y == 0:
                return '0°'
            elif y > 0:
                return f'{int(y)}°'
            else:
                return f'{int(y)}°'

        gl.xformatter = plt.FuncFormatter(format_lon)
        gl.yformatter = plt.FuncFormatter(format_lat)
        gl.xlabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}
        gl.ylabel_style = {'size': self.font_sizes['grid_labels'], 'family': 'Arial', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_global_map(self, data_subset, variable, depth, year=None):
        """根据选择的方法创建地图"""
        if self.plot_method == "scatter":
            return self.create_scatter_plot(data_subset, variable, depth, year)
        elif self.plot_method == "high_res_grid":
            return self.create_high_res_grid(data_subset, variable, depth, year)
        elif self.plot_method == "interpolation":
            return self.create_interpolated_grid(data_subset, variable, depth, year)
        elif self.plot_method == "original_grid":
            return self.create_original_grid(data_subset, variable, depth, year)
        else:
            return self.create_high_res_grid(data_subset, variable, depth, year)

    def process_single_file(self, csv_file, depths, variables):
        """处理单个CSV文件，优化内存管理"""
        print(f"\n{'=' * 60}")
        print(f"处理文件: {os.path.basename(csv_file)}")
        print(f"{'=' * 60}")

        # 加载数据
        data = self.load_single_csv(csv_file)
        if data is None:
            return

        file_base_name = os.path.splitext(os.path.basename(csv_file))[0]

        try:
            # 为每个变量和每个深度生成图
            for variable in variables:
                if variable not in data.columns:
                    print(f"  ✗ 变量 '{variable}' 不存在于数据中")
                    continue

                print(f"\n  处理变量: {variable}")
                color_config = self.get_color_config(variable)
                print(f"    使用配色方案: {color_config['cmap']}")

                for depth in depths:
                    print(f"    绘制深度 {depth}m...")

                    depth_data = data[data['depth'] == depth].copy()

                    if len(depth_data) == 0:
                        print(f"      ✗ 深度 {depth}m 没有数据")
                        continue

                    # 处理年份
                    if 'year' in depth_data.columns:
                        years = sorted(depth_data['year'].unique())
                        latest_year = max(years)
                        year_data = depth_data[depth_data['year'] == latest_year].copy()
                        year_label = latest_year
                    else:
                        year_data = depth_data.copy()
                        year_label = None

                    # 移除缺失值
                    year_data = year_data.dropna(subset=[variable, 'longitude', 'latitude'])

                    if len(year_data) == 0:
                        print(f"      ✗ 深度 {depth}m 没有有效数据")
                        continue

                    print(f"      有效数据点: {len(year_data)}")

                    try:
                        # 根据选择的图类型绘制
                        year_suffix = f"_{year_label}" if year_label else ""

                        if self.plot_type in ["global", "both"]:
                            # 创建全球分布图
                            fig_global = self.create_global_map(year_data, variable, depth, year_label)

                            # 保存全球图
                            method_suffix = f"_{self.plot_method}"
                            filename_global = f"{file_base_name}_{variable}_depth_{depth}m{year_suffix}_global{method_suffix}.png"
                            filepath_global = os.path.join(self.output_folder, filename_global)

                            fig_global.savefig(filepath_global, dpi=300, bbox_inches='tight')
                            print(f"      ✓ 已保存全球图: {filename_global}")
                            plt.close(fig_global)

                        if self.plot_type in ["latitudinal", "both"]:
                            # 创建纬度均值图
                            fig_lat = self.create_latitudinal_plot(year_data, variable, depth, year_label)

                            if fig_lat is not None:
                                # 保存纬度图
                                error_suffix = f"_{self.error_type}"
                                filename_lat = f"{file_base_name}_{variable}_depth_{depth}m{year_suffix}_latitudinal{error_suffix}.png"
                                filepath_lat = os.path.join(self.output_folder, filename_lat)

                                fig_lat.savefig(filepath_lat, dpi=300, bbox_inches='tight')
                                print(f"      ✓ 已保存纬度图: {filename_lat}")
                                plt.close(fig_lat)

                    except Exception as e:
                        print(f"      ✗ 绘图出错: {e}")
                    finally:
                        # 清理这个图的内存
                        plt.close('all')

                    # 删除临时数据，释放内存
                    del year_data
                    if 'depth_data' in locals():
                        del depth_data
                    gc.collect()

        finally:
            # 处理完这个文件后清理内存
            del data
            self.clear_memory()
            print(f"  内存清理完成")

    def run(self):
        """运行主程序"""
        print("=== 改进的全球海洋N2O数据可视化工具 ===")
        print("功能特性:")
        print("- 全球分布图与纬度均值图纵向高度完全一致")
        print("- 纬度均值图宽度保持一致，横坐标从0开始")
        print("- 多种误差类型：标准误差、95%置信区间、标准差")
        print("- 纬度均值图：黑色线条+深灰色误差区域（无图例）")
        print("- 丰富的配色方案选择（高对比度和经典配色）")
        print("- 优化内存管理，避免内存崩溃")
        print("- 经度标签间隔60度，网格线间隔30度")
        print("- 单位已更新为 nmol-N L-1 yr-1，字体上下标加粗")
        print("- 所有字体使用Arial加粗")
        print("- 纬度图横坐标智能优化，避免数字重叠")
        print("- 经纬度标注使用正负数字格式（而非NWSE）")
        print("- 字体大小可配置，便于调整")
        print()

        # 1. 选择输入文件夹
        if not self.select_input_folder():
            return

        # 2. 选择输出文件夹
        if not self.select_output_folder():
            return

        # 3. 使用第一个文件来确定参数
        print(f"\n使用第一个文件 '{os.path.basename(self.csv_files[0])}' 来确定绘图参数...")
        sample_data = self.load_single_csv(self.csv_files[0])
        if sample_data is None:
            print("无法加载示例文件")
            return

        # 4. 选择配色方案
        self.select_colormap()

        # 5. 选择绘图类型
        self.select_plot_type()

        # 6. 选择误差类型（如果需要绘制纬度图）
        if self.plot_type in ["latitudinal", "both"]:
            self.select_error_type()

        # 7. 选择绘图方法（如果需要绘制全球图）
        if self.plot_type in ["global", "both"]:
            self.select_plot_method()

        # 8. 选择颜色刻度模式
        self.select_color_scale_mode()

        # 9. 选择变量
        variables = self.select_variables()

        # 10. 选择深度
        depths = self.select_depths(sample_data)
        if not depths:
            print("未选择深度，程序退出")
            return

        # 清理示例数据
        del sample_data
        self.clear_memory()

        # 11. 批量处理所有文件
        print(f"\n开始批量处理 {len(self.csv_files)} 个文件...")

        # 计算总图片数量
        if self.plot_type == "both":
            total_images = len(self.csv_files) * len(variables) * len(depths) * 2  # 每个配置2张图
        else:
            total_images = len(self.csv_files) * len(variables) * len(depths)

        print(f"将生成约 {total_images} 个图像")

        for i, csv_file in enumerate(self.csv_files, 1):
            print(f"\n处理进度: {i}/{len(self.csv_files)}")
            try:
                self.process_single_file(csv_file, depths, variables)
            except Exception as e:
                print(f"处理文件 {csv_file} 时出错: {e}")
                continue

            # 每处理完一个文件就清理一次内存
            self.clear_memory()

        print(f"\n{'=' * 60}")
        print("批量处理完成!")
        print(f"所有图像已保存到: {self.output_folder}")
        print(f"使用的配色方案: {self.selected_colormap}")
        print(f"绘图类型: {self.plot_type}")
        if self.plot_type in ["latitudinal", "both"]:
            print(f"误差类型: {self.error_type}")
            print("纬度范围: -90°S - 90°N（完整范围）")
            print("横坐标: 从0开始，智能刻度优化")
        if self.plot_type in ["global", "both"]:
            print(f"全球图绘图方法: {self.plot_method}")
        print(f"颜色刻度模式: {self.color_scale_mode}")
        if self.color_scale_mode == "manual":
            print("手动设置的颜色范围:")
            for var, (min_val, max_val) in self.color_limits.items():
                print(f"  {var}: {min_val} - {max_val}")
        print(f"单位: nmol-N L-1 yr-1（上下标加粗）")
        print(f"字体: Arial加粗")
        print(f"经纬度标注: 正负数字格式（如：-180°, 0°, 180°）")
        print("字体大小配置:")
        for key, value in self.font_sizes.items():
            print(f"  {key}: {value}")
        print(f"{'=' * 60}")


def main():
    """主函数"""
    try:
        visualizer = ImprovedOceanDataVisualizer()
        visualizer.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按回车键退出...")


if __name__ == "__main__":
    main()