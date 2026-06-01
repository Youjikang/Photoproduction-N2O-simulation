import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
import os
import glob
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import simpledialog
from scipy.interpolate import griddata
import warnings
import gc  # 添加垃圾回收模块

warnings.filterwarnings('ignore')

# 设置全局字体
plt.rcParams['font.family'] = 'Times New Roman'
plt.rcParams['font.size'] = 12
plt.rcParams['font.weight'] = 'bold'


class ImprovedOceanDataVisualizer:
    def __init__(self):
        self.data = None
        self.input_folder = ""
        self.csv_files = []
        self.output_folder = ""
        self.plot_method = "high_res_grid"  # 默认方法
        self.color_scale_mode = "auto"  # 'auto' 或 'manual'
        self.color_limits = {}  # 存储每个变量的颜色范围
        self.selected_colormap = "inferno"  # 默认配色方案

        # 创建自定义配色方案
        self.create_custom_colormaps()

        # 为不同变量定义不同的配色方案
        self.color_schemes = {
            'N2O_integrated_nmol_N_per_m2': {
                'cmap': self.selected_colormap,
                'label': 'N2O integrated (nmol N/m²)'
            },
            'N2O_UVB_integrated_nmol_N_per_m2': {
                'cmap': self.selected_colormap,
                'label': 'N2O UVB integrated (nmol N/m²)'
            },
            'N2O_UVA_integrated_nmol_N_per_m2': {
                'cmap': self.selected_colormap,
                'label': 'N2O UVA integrated (nmol N/m²)'
            },
            'N2O_BLUE_integrated_nmol_N_per_m2': {
                'cmap': self.selected_colormap,
                'label': 'N2O BLUE integrated (nmol N/m²)'
            }
        }

    def create_custom_colormaps(self):
        """创建高对比度配色方案"""
        # 定义高对比度颜色方案
        color_schemes = {
            # 高对比度配色 - 从深色到亮色
            'deep_blue_bright_yellow': ["#000080", "#0000FF", "#00FFFF", "#FFFF00", "#FFFFFF"],
            'black_red_white': ["#000000", "#800000", "#FF0000", "#FF8000", "#FFFF00", "#FFFFFF"],
            'purple_green_contrast': ["#4A0080", "#8000FF", "#00FF80", "#80FF00", "#FFFF00"],

            # 分段式高对比配色
            'segmented_rainbow': ["#0000FF", "#0080FF", "#00FFFF", "#00FF00", "#FFFF00", "#FF8000", "#FF0000"],
            'blue_white_red': ["#000080", "#4040FF", "#8080FF", "#FFFFFF", "#FF8080", "#FF4040", "#800000"],

            # 科学专用对比配色
            'turbo_like': ["#30123B", "#4777EF", "#1AE4B6", "#72FE5E", "#E2E419", "#F1722F", "#A50026"],
            'enhanced_jet': ["#000080", "#0000FF", "#00FFFF", "#00FF00", "#FFFF00", "#FF0000", "#800000"],

            # 极高对比度配色
            'extreme_contrast': ["#000000", "#FF00FF", "#00FFFF", "#FFFF00", "#FFFFFF"]
        }

        # 创建自定义colormap并注册到matplotlib
        for name, colors in color_schemes.items():
            cmap = mcolors.LinearSegmentedColormap.from_list(name, colors, N=256)
            plt.cm.register_cmap(name, cmap)

    def get_available_colormaps(self):
        """获取可用的配色方案"""
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
        colormaps = self.get_available_colormaps()

        print("\n" + "=" * 90)
        print("选择配色方案 - 高对比度专用于科学数据可视化:")
        print("=" * 90)

        # 按类别显示，优先显示高对比度配色
        categories = {
            "🔥 高对比度配色（强烈推荐）": [
                'deep_blue_bright_yellow', 'black_red_white', 'purple_green_contrast',
                'segmented_rainbow', 'blue_white_red', 'turbo_like',
                'enhanced_jet', 'extreme_contrast'
            ],
            "⭐ 经典科学配色": ['inferno', 'viridis', 'plasma', 'turbo'],
            "♿ 特殊需求": ['cividis']
        }

        option_map = {}
        option_num = 1

        for category, cmaps in categories.items():
            print(f"\n{category}:")
            print("-" * 60)
            for cmap in cmaps:
                if cmap in colormaps:
                    print(f"{option_num}. {colormaps[cmap]}")
                    option_map[option_num] = cmap
                    option_num += 1

        print("=" * 90)
        print("⚡ 对比度建议:")
        print("- 数据范围大: 选择 1 (深蓝→亮黄) 或 2 (黑→红→白)")
        print("- 需要突出异常值: 选择 4 (分段彩虹) 或 8 (极限对比)")
        print("- 发表论文: 选择 6 (科学专用) 或 9 (经典Inferno)")
        print("- 展示汇报: 选择 3 (紫绿对比) 或 5 (蓝白红)")

        while True:
            try:
                choice = input(f"\n请选择配色方案 (1-{len(option_map)}，默认1): ").strip()
                if not choice:
                    choice = "1"  # 默认选择深蓝→亮黄高对比配色

                choice_num = int(choice)
                if choice_num in option_map:
                    self.selected_colormap = option_map[choice_num]
                    print(f"✓ 已选择: {colormaps[self.selected_colormap]}")

                    # 更新所有变量的配色方案
                    for var in self.color_schemes:
                        self.color_schemes[var]['cmap'] = self.selected_colormap

                    return self.selected_colormap
                else:
                    print(f"✗ 请输入 1-{len(option_map)} 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认配色方案: 深蓝→亮黄高对比")
                self.selected_colormap = "deep_blue_bright_yellow"
                for var in self.color_schemes:
                    self.color_schemes[var]['cmap'] = self.selected_colormap
                return self.selected_colormap

    def get_color_config(self, variable):
        """获取变量的配色配置"""
        if variable in self.color_schemes:
            return self.color_schemes[variable]
        else:
            # 默认配色
            return {
                'cmap': self.selected_colormap,
                'label': f'{variable} concentration'
            }

    def clear_memory(self):
        """清理内存"""
        # 清理matplotlib的内存
        plt.clf()
        plt.close('all')
        # 强制垃圾回收
        gc.collect()

    def select_plot_method(self):
        """选择绘图方法"""
        methods = {
            1: ("scatter", "散点图 - 直接显示原始数据点（最真实）"),
            2: ("high_res_grid", "高分辨率网格 - 0.5度网格（保持高分辨率）"),
            3: ("interpolation", "插值网格 - 平滑插值（最美观）"),
            4: ("original_grid", "原始2度网格 - 快速预览（最快）")
        }

        print("\n" + "=" * 60)
        print("选择绘图方法:")
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
        colormap_name = self.get_available_colormaps().get(self.selected_colormap, self.selected_colormap)
        print(f"注意：将使用配色方案: {colormap_name}")

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
        variables = ['N2O_integrated_nmol_N_per_m2', 'N2O_UVB_integrated_nmol_N_per_m2',
                     'N2O_UVA_integrated_nmol_N_per_m2', 'N2O_BLUE_integrated_nmol_N_per_m2']

        for var in variables:
            color_config = self.get_color_config(var)
            colormap_name = self.get_available_colormaps().get(color_config['cmap'], color_config['cmap'])
            print(f"\n设置 {var} 的颜色范围 (配色: {colormap_name}):")
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
            required_columns = ['longitude', 'latitude', 'N2O_integrated_nmol_N_per_m2',
                                'N2O_UVB_integrated_nmol_N_per_m2', 'N2O_UVA_integrated_nmol_N_per_m2',
                                'N2O_BLUE_integrated_nmol_N_per_m2']
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
                'N2O_integrated_nmol_N_per_m2': 'float32',
                'N2O_UVB_integrated_nmol_N_per_m2': 'float32',
                'N2O_UVA_integrated_nmol_N_per_m2': 'float32',
                'N2O_BLUE_integrated_nmol_N_per_m2': 'float32'
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

    def select_variables(self):
        """选择要绘制的变量（可多选）"""
        variables = ['N2O_integrated_nmol_N_per_m2', 'N2O_UVB_integrated_nmol_N_per_m2',
                     'N2O_UVA_integrated_nmol_N_per_m2', 'N2O_BLUE_integrated_nmol_N_per_m2']

        print("\n" + "=" * 60)
        print("可用变量:")
        print("=" * 60)
        colormap_name = self.get_available_colormaps().get(self.selected_colormap, self.selected_colormap)
        for i, var in enumerate(variables):
            print(f"{i + 1}. {var} (配色: {colormap_name})")
        print("=" * 60)
        print("\n输入示例:")
        print("- 选择单个变量: 输入 1")
        print("- 选择多个变量: 输入 1,2,3")
        print("- 选择所有变量: 输入 1,2,3,4")

        while True:
            try:
                var_input = input(f"\n请输入变量编号 (1-{len(variables)})，多个变量用逗号分隔: ").strip()

                if not var_input:
                    print("未输入任何内容，使用默认变量: N2O_integrated_nmol_N_per_m2")
                    return ['N2O_integrated_nmol_N_per_m2']

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
                print("\n使用默认变量: N2O_integrated_nmol_N_per_m2")
                return ['N2O_integrated_nmol_N_per_m2']

    def create_scatter_plot(self, data_subset, variable, year=None):
        """方法1: 散点图 - 直接显示原始数据点"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 只显示海岸线，不显示国界
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 获取变量的配色配置
        color_config = self.get_color_config(variable)

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
            cmap=color_config['cmap'],  # 使用变量特定的配色
            transform=ccrs.PlateCarree(),
            alpha=0.8,
            vmin=vmin, vmax=vmax
        )

        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=14, fontweight='bold', family='Times New Roman')

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_high_res_grid(self, data_subset, variable, year=None):
        """方法2: 高分辨率网格 - 保持数据原始分辨率"""
        fig = plt.figure(figsize=(16, 10))
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

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap=color_config['cmap'],  # 使用变量特定的配色
            shading='auto',
            vmin=vmin, vmax=vmax
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=14, fontweight='bold', family='Times New Roman')

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_interpolated_grid(self, data_subset, variable, year=None):
        """方法3: 插值网格 - 平滑插值，优化内存使用"""
        fig = plt.figure(figsize=(16, 10))
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

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_interp, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap=color_config['cmap'],  # 使用变量特定的配色
            shading='auto',
            vmin=vmin, vmax=vmax
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=14, fontweight='bold', family='Times New Roman')

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_original_grid(self, data_subset, variable, year=None):
        """方法4: 原始2度网格 - 快速预览"""
        fig = plt.figure(figsize=(16, 10))
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

        # 设置颜色范围
        if self.color_scale_mode == "manual" and variable in self.color_limits:
            vmin, vmax = self.color_limits[variable]
        else:
            vmin, vmax = None, None

        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap=color_config['cmap'],  # 使用变量特定的配色
            shading='auto',
            vmin=vmin, vmax=vmax
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=14, fontweight='bold', family='Times New Roman')

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        plt.tight_layout()
        return fig

    def create_global_map(self, data_subset, variable, year=None):
        """根据选择的方法创建地图"""
        if self.plot_method == "scatter":
            return self.create_scatter_plot(data_subset, variable, year)
        elif self.plot_method == "high_res_grid":
            return self.create_high_res_grid(data_subset, variable, year)
        elif self.plot_method == "interpolation":
            return self.create_interpolated_grid(data_subset, variable, year)
        elif self.plot_method == "original_grid":
            return self.create_original_grid(data_subset, variable, year)
        else:
            return self.create_high_res_grid(data_subset, variable, year)

    def process_single_file(self, csv_file, variables):
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
            # 为每个变量生成图
            for variable in variables:
                if variable not in data.columns:
                    print(f"  ✗ 变量 '{variable}' 不存在于数据中")
                    continue

                print(f"\n  处理变量: {variable}")
                color_config = self.get_color_config(variable)
                colormap_name = self.get_available_colormaps().get(color_config['cmap'], color_config['cmap'])
                print(f"    使用配色方案: {colormap_name}")

                # 处理年份
                if 'year' in data.columns:
                    years = sorted(data['year'].unique())
                    latest_year = max(years)
                    year_data = data[data['year'] == latest_year].copy()
                    year_label = latest_year
                else:
                    year_data = data.copy()
                    year_label = None

                # 移除缺失值
                year_data = year_data.dropna(subset=[variable, 'longitude', 'latitude'])

                if len(year_data) == 0:
                    print(f"      ✗ 变量 {variable} 没有有效数据")
                    continue

                print(f"      有效数据点: {len(year_data)}")

                try:
                    # 创建地图
                    fig = self.create_global_map(year_data, variable, year_label)

                    # 保存图像
                    year_suffix = f"_{year_label}" if year_label else ""
                    method_suffix = f"_{self.plot_method}"
                    colormap_suffix = f"_{self.selected_colormap}"
                    filename = f"{file_base_name}_{variable}{year_suffix}{method_suffix}{colormap_suffix}.png"
                    filepath = os.path.join(self.output_folder, filename)

                    plt.savefig(filepath, dpi=300, bbox_inches='tight')
                    print(f"      ✓ 已保存: {filename}")

                except Exception as e:
                    print(f"      ✗ 绘图出错: {e}")
                finally:
                    # 清理这个图的内存
                    plt.close('all')

                # 删除临时数据，释放内存
                del year_data
                gc.collect()

        finally:
            # 处理完这个文件后清理内存
            del data
            self.clear_memory()
            print(f"  内存清理完成")

    def run(self):
        """运行主程序"""
        print("=== 改进的全球海洋N2O数据可视化工具（高对比度配色版本） ===")
        print("🔥 高对比度特性:")
        print("- 8种高对比度配色方案，数据差异一目了然")
        print("- 极强视觉对比，突出数值变化")
        print("- 分段式和连续式配色可选")
        print("- 科学数据专用优化")
        print("- 优化内存管理，避免内存崩溃")
        print("- 大数据集自动采样")
        print("- 支持N2O相关参数可视化")
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

        # 5. 选择绘图方法
        self.select_plot_method()

        # 6. 选择颜色刻度模式
        self.select_color_scale_mode()

        # 7. 选择变量
        variables = self.select_variables()

        # 清理示例数据
        del sample_data
        self.clear_memory()

        # 8. 批量处理所有文件
        print(f"\n开始批量处理 {len(self.csv_files)} 个文件...")
        print(f"将生成 {len(self.csv_files)} × {len(variables)} = {len(self.csv_files) * len(variables)} 个图像")

        for i, csv_file in enumerate(self.csv_files, 1):
            print(f"\n处理进度: {i}/{len(self.csv_files)}")
            try:
                self.process_single_file(csv_file, variables)
            except Exception as e:
                print(f"处理文件 {csv_file} 时出错: {e}")
                continue

            # 每处理完一个文件就清理一次内存
            self.clear_memory()

        print(f"\n{'=' * 60}")
        print("批量处理完成!")
        print(f"所有图像已保存到: {self.output_folder}")
        print(f"使用的绘图方法: {self.plot_method}")
        print(f"颜色刻度模式: {self.color_scale_mode}")
        colormap_name = self.get_available_colormaps().get(self.selected_colormap, self.selected_colormap)
        print(f"使用的配色方案: {colormap_name}")

        if self.color_scale_mode == "manual":
            print("手动设置的颜色范围:")
            for var, (min_val, max_val) in self.color_limits.items():
                print(f"  {var}: {min_val} - {max_val}")
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