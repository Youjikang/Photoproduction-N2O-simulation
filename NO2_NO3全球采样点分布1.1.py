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


class OceanNitrateNitriteVisualizer:
    def __init__(self):
        self.data = None
        self.input_folder = ""
        self.csv_files = []
        self.output_folder = ""
        self.plot_method = "high_res_grid"  # 默认方法
        self.color_scale_mode = "auto"  # 'auto' 或 'manual'
        self.color_limits = {}  # 存储每个变量的颜色范围

        # 为nitrate和nitrite定义固定的配色方案 - 参考plasma配色
        self.color_schemes = {
            'G2nitrate': {
                'color': 'lightseagreen',  # 淡的海绿色，类似第二个图的淡色
                'label': 'Nitrate Concentration (μmol/L)',
                'alpha': 0.1
            },
            'G2nitrite': {
                'color': 'plum',  # 淡的plasma色（淡紫色）
                'label': 'Nitrite Concentration (μmol/L)',
                'alpha': 0.1
            }
        }

    def get_color_config(self, variable):
        """获取变量的配色配置"""
        if variable in self.color_schemes:
            return self.color_schemes[variable]
        else:
            # 默认配色
            return {
                'color': 'lightblue',  # 默认也使用淡色
                'label': f'{variable} concentration',
                'alpha': 0.1
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
            1: ("scatter", "标准散点图 - 点大小28，清晰显示每个数据点"),  # 40*0.7=28
            2: ("high_res_grid", "高分辨率散点 - 点大小14，适合大数据量"),  # 20*0.7=14
            3: ("interpolation", "中等散点 - 点大小21，平衡显示效果"),  # 30*0.7=21
            4: ("original_grid", "微小散点 - 点大小7，快速预览全貌")  # 10*0.7=7
        }

        print("\n" + "=" * 60)
        print("选择绘图方法:")
        print("=" * 60)
        for num, (method, desc) in methods.items():
            print(f"{num}. {desc}")
        print("=" * 60)

        print("\n说明:")
        print("- 只显示数据点位置，不映射数值到颜色")
        print("- ≤250m深度：三角形，>250m深度：圆形")
        print("- nitrate显示为淡海绿色，nitrite显示为淡紫色，边框90%透明")
        print("- 不同方法的点大小不同，适合不同的数据量和显示需求")
        print("- 边框宽度0.5，无图例")
        print("- 包含三条横断面线：太平洋(-150°,红色)、大西洋(-30°,黑色)、印度洋(67.5°,蓝色)")

        while True:
            try:
                choice = input(f"\n请选择绘图方法 (1-{len(methods)}，默认1): ").strip()
                if not choice:
                    choice = "1"  # 默认选择标准散点图

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
                print("\n使用默认方法: 标准散点图")
                self.plot_method = "scatter"
                return self.plot_method

    def select_color_scale_mode(self):
        """颜色刻度模式已简化 - 只显示数据点位置"""
        print("\n" + "=" * 50)
        print("颜色设置:")
        print("=" * 50)
        print("- nitrate: 淡海绿色边框 (lightseagreen)，90%透明（10%不透明度）")
        print("- nitrite: 淡紫色边框 (plum)，90%透明（10%不透明度）")
        print("- 海洋背景: 空白（白色），突出plasma配色数据点")
        print("- 边框宽度: 0.5")
        print("- 深度形状: ≤250m三角形，>250m圆形")
        print("- 横断面线: 太平洋(-150°,红色)、大西洋(-30°,黑色)、印度洋(67.5°,蓝色)")
        print("- 无图例显示")
        print("- 只显示数据点位置，不映射数值到颜色")
        print("=" * 50)

        self.color_scale_mode = "position_only"
        print("✓ 使用位置显示模式")
        return

    def set_manual_color_limits(self):
        """设置手动颜色范围"""
        variables = ['G2nitrate', 'G2nitrite']

        for var in variables:
            color_config = self.get_color_config(var)
            print(f"\n设置 {var} 的颜色范围 (颜色: {color_config['color']}):")
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

    def filter_data_by_year(self, data):
        """过滤数据，保留1978-2023年之间的数据"""
        if 'G2year' not in data.columns:
            print("  警告: 数据中没有'G2year'列，跳过年份过滤")
            return data

        original_count = len(data)
        filtered_data = data[(data['G2year'] >= 1978) & (data['G2year'] <= 2023)].copy()
        filtered_count = len(filtered_data)

        print(f"  年份过滤: {original_count} -> {filtered_count} 条记录 (保留1978-2023年)")
        if filtered_count == 0:
            print("  警告: 过滤后没有数据")

        return filtered_data

    def analyze_depth_distribution(self, data, variable):
        """分析深度分布统计"""
        if 'G2depth' not in data.columns:
            print(f"  警告: 数据中没有'G2depth'列，跳过深度分析")
            return

        # 移除缺失值
        valid_data = data.dropna(subset=[variable, 'G2depth'])

        if len(valid_data) == 0:
            print(f"  {variable}: 没有有效的深度数据")
            return

        # 统计不同深度范围的数据量
        shallow_data = valid_data[valid_data['G2depth'] <= 250]
        deep_data = valid_data[valid_data['G2depth'] > 250]

        print(f"  {variable} 深度分布统计:")
        print(f"    0-250m (三角形): {len(shallow_data)} 条记录")
        print(f"    >250m (圆形):   {len(deep_data)} 条记录")
        print(f"    总计:           {len(valid_data)} 条记录")

        if len(shallow_data) > 0:
            shallow_mean = shallow_data[variable].mean()
            shallow_std = shallow_data[variable].std()
            print(f"    0-250m 平均值: {shallow_mean:.3f} ± {shallow_std:.3f}")

        if len(deep_data) > 0:
            deep_mean = deep_data[variable].mean()
            deep_std = deep_data[variable].std()
            print(f"    >250m 平均值:  {deep_mean:.3f} ± {deep_std:.3f}")

    def analyze_year_distribution(self, data):
        """分析年份分布统计"""
        if 'G2year' not in data.columns:
            print("  警告: 数据中没有'G2year'列，跳过年份分析")
            return

        years = sorted(data['G2year'].unique())
        print(f"  年份分布统计:")
        print(f"    年份范围: {min(years)} - {max(years)}")
        print(f"    总年份数: {len(years)} 年")

        # 显示每个年代的数据量
        decade_counts = {}
        for year in years:
            decade = int(year // 10) * 10
            if decade not in decade_counts:
                decade_counts[decade] = 0
            year_data = data[data['G2year'] == year]
            decade_counts[decade] += len(year_data)

        print("    各年代数据量:")
        for decade in sorted(decade_counts.keys()):
            print(f"      {decade}s: {decade_counts[decade]} 条记录")

    def load_single_csv(self, file_path):
        """加载单个CSV文件，优化内存使用"""
        try:
            print(f"  加载: {os.path.basename(file_path)}")

            # 只读取需要的列，减少内存使用
            required_columns = ['G2longitude', 'G2latitude', 'G2nitrate', 'G2nitrite']
            optional_columns = ['G2year', 'G2depth']

            # 先读取列名
            sample_df = pd.read_csv(file_path, nrows=0)
            available_columns = sample_df.columns.tolist()

            columns_to_read = [col for col in required_columns if col in available_columns]
            columns_to_read.extend([col for col in optional_columns if col in available_columns])

            # 使用数据类型优化减少内存
            dtype_dict = {
                'G2longitude': 'float32',
                'G2latitude': 'float32',
                'G2nitrate': 'float32',
                'G2nitrite': 'float32'
            }

            df = pd.read_csv(file_path, usecols=columns_to_read, dtype=dtype_dict)

            # 过滤年份数据
            df = self.filter_data_by_year(df)

            print(f"  过滤后数据行数: {len(df)}")
            print(f"  数据列: {list(df.columns)}")
            print(f"  内存使用: {df.memory_usage(deep=True).sum() / 1024 ** 2:.2f} MB")

            # 显示数据分辨率信息
            if len(df) > 0 and 'G2longitude' in df.columns and 'G2latitude' in df.columns:
                lon_resolution = self.estimate_resolution(df, 'G2longitude')
                lat_resolution = self.estimate_resolution(df, 'G2latitude')
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

    def create_combined_scatter_plot(self, data_subset, variables, year_range=None):
        """方法1: 散点图 - 在同一张图上显示多个变量，根据深度使用不同形状"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 海洋为空白（白色）
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')  # 空白海洋背景
        ax.set_global()

        # 为每个变量绘制散点
        for variable in variables:
            if variable not in data_subset.columns:
                continue

            # 获取有效数据
            var_data = data_subset.dropna(subset=[variable, 'G2longitude', 'G2latitude'])
            if len(var_data) == 0:
                continue

            # 获取变量的配色配置
            color_config = self.get_color_config(variable)

            # 确定颜色 - 使用plasma风格配色
            if color_config['color'] == 'lightseagreen':
                edge_color = (0.13, 0.70, 0.67, 0.1)  # nitrate使用淡海绿色
            elif color_config['color'] == 'plum':
                edge_color = (0.87, 0.63, 0.87, 0.1)  # nitrite使用淡plasma色（淡紫色）
            else:
                edge_color = (0.0, 0.0, 1.0, 0.1)  # 默认蓝色边框

            # 如果有深度数据，根据深度分层绘制
            if 'G2depth' in var_data.columns:
                # 浅层数据 (≤250m) - 三角形
                shallow_data = var_data[var_data['G2depth'] <= 250]
                if len(shallow_data) > 0:
                    ax.scatter(
                        shallow_data['G2longitude'], shallow_data['G2latitude'],
                        facecolors='none',
                        edgecolors=[edge_color] * len(shallow_data),
                        s=28,  # 40*0.7=28
                        marker='^',  # 三角形
                        transform=ccrs.PlateCarree(),
                        linewidths=0.5
                    )
                    print(f"    绘制 {variable} 浅层(≤250m): {len(shallow_data)} 个三角形，颜色RGBA{edge_color}")

                # 深层数据 (>250m) - 圆形
                deep_data = var_data[var_data['G2depth'] > 250]
                if len(deep_data) > 0:
                    ax.scatter(
                        deep_data['G2longitude'], deep_data['G2latitude'],
                        facecolors='none',
                        edgecolors=[edge_color] * len(deep_data),
                        s=28,  # 40*0.7=28
                        marker='o',  # 圆形
                        transform=ccrs.PlateCarree(),
                        linewidths=0.5
                    )
                    print(f"    绘制 {variable} 深层(>250m): {len(deep_data)} 个圆形，颜色RGBA{edge_color}")
            else:
                # 没有深度数据，默认使用圆形
                ax.scatter(
                    var_data['G2longitude'], var_data['G2latitude'],
                    facecolors='none',
                    edgecolors=[edge_color] * len(var_data),
                    s=28,  # 40*0.7=28
                    marker='o',
                    transform=ccrs.PlateCarree(),
                    linewidths=0.5
                )
                print(f"    绘制 {variable}: {len(var_data)} 个圆形（无深度数据），颜色RGBA{edge_color}")

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        # 添加横断面线
        # 太平洋横断面 (-150°, -65°S to 58°N) - 红色
        ax.plot([-150, -150], [-65, 58], color='red', linewidth=4, transform=ccrs.PlateCarree(), label='Pacific')
        # 大西洋横断面 (-30°, -65°S to 60°N) - 黑色
        ax.plot([-30, -30], [-65, 60], color='black', linewidth=4, transform=ccrs.PlateCarree(), label='Atlantic')
        # 印度洋横断面 (67.5°, -65°S to 21°N) - 蓝色
        ax.plot([67.5, 67.5], [-65, 21], color='blue', linewidth=4, transform=ccrs.PlateCarree(), label='Indian')

        plt.tight_layout()
        return fig

    def create_combined_high_res_grid(self, data_subset, variables, year_range=None):
        """方法2: 高分辨率网格 - 根据深度使用不同形状"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 海洋为空白（白色）
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')  # 空白海洋背景
        ax.set_global()

        # 为每个变量创建点密度图
        for variable in variables:
            if variable not in data_subset.columns:
                continue

            var_data = data_subset.dropna(subset=[variable, 'G2longitude', 'G2latitude'])
            if len(var_data) == 0:
                continue

            # 获取变量的配色配置
            color_config = self.get_color_config(variable)

            # 确定颜色
            if color_config['color'] == 'darkturquoise':
                edge_color = (0.0, 0.6, 0.8, 0.1)
            elif color_config['color'] == 'lightcoral':
                edge_color = (1.0, 0.5, 0.5, 0.1)
            else:
                edge_color = (0.0, 0.0, 1.0, 0.1)

            # 如果有深度数据，根据深度分层绘制
            if 'G2depth' in var_data.columns:
                # 浅层数据 (≤250m) - 三角形
                shallow_data = var_data[var_data['G2depth'] <= 250]
                if len(shallow_data) > 0:
                    ax.scatter(
                        shallow_data['G2longitude'], shallow_data['G2latitude'],
                        facecolors='none',
                        edgecolors=[edge_color] * len(shallow_data),
                        s=14,  # 20*0.7=14
                        marker='^',  # 三角形
                        transform=ccrs.PlateCarree(),
                        linewidths=0.5
                    )
                    print(f"    绘制 {variable} 浅层(≤250m): {len(shallow_data)} 个三角形，颜色RGBA{edge_color}")

                # 深层数据 (>250m) - 圆形
                deep_data = var_data[var_data['G2depth'] > 250]
                if len(deep_data) > 0:
                    ax.scatter(
                        deep_data['G2longitude'], deep_data['G2latitude'],
                        facecolors='none',
                        edgecolors=[edge_color] * len(deep_data),
                        s=14,  # 20*0.7=14
                        marker='o',  # 圆形
                        transform=ccrs.PlateCarree(),
                        linewidths=0.5
                    )
                    print(f"    绘制 {variable} 深层(>250m): {len(deep_data)} 个圆形，颜色RGBA{edge_color}")
            else:
                # 没有深度数据，默认使用圆形
                ax.scatter(
                    var_data['G2longitude'], var_data['G2latitude'],
                    facecolors='none',
                    edgecolors=[edge_color] * len(var_data),
                    s=14,  # 20*0.7=14
                    marker='o',
                    transform=ccrs.PlateCarree(),
                    linewidths=0.5
                )
                print(f"    绘制 {variable}: {len(var_data)} 个圆形（无深度数据），颜色RGBA{edge_color}")

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        # 添加横断面线
        # 太平洋横断面 (-150°, -65°S to 58°N) - 红色
        ax.plot([-150, -150], [-65, 58], color='red', linewidth=4, transform=ccrs.PlateCarree(), label='Pacific')
        # 大西洋横断面 (-30°, -65°S to 60°N) - 黑色
        ax.plot([-30, -30], [-65, 60], color='black', linewidth=4, transform=ccrs.PlateCarree(), label='Atlantic')
        # 印度洋横断面 (67.5°, -65°S to 21°N) - 蓝色
        ax.plot([67.5, 67.5], [-65, 21], color='blue', linewidth=4, transform=ccrs.PlateCarree(), label='Indian')

        plt.tight_layout()
        return fig

    def create_combined_interpolated_grid(self, data_subset, variables, year_range=None):
        """方法3: 插值网格 - 根据深度使用不同形状"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 海洋为空白（白色）
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')  # 空白海洋背景
        ax.set_global()

        # 为每个变量直接绘制散点
        for variable in variables:
            if variable not in data_subset.columns:
                continue

            var_data = data_subset.dropna(subset=[variable, 'G2longitude', 'G2latitude'])
            if len(var_data) == 0:
                continue

            # 如果数据点太多，进行采样以节省内存
            if len(var_data) > 50000:
                print(f"  {variable} 数据量较大({len(var_data)}点)，进行采样以优化显示...")
                sample_size = min(50000, len(var_data))
                var_data = var_data.sample(n=sample_size, random_state=42)
                print(f"  采样后数据量: {len(var_data)}点")

            # 获取变量的配色配置
            color_config = self.get_color_config(variable)

            # 确定颜色
            if color_config['color'] == 'darkturquoise':
                edge_color = (0.0, 0.6, 0.8, 0.1)
            elif color_config['color'] == 'lightcoral':
                edge_color = (1.0, 0.5, 0.5, 0.1)
            else:
                edge_color = (0.0, 0.0, 1.0, 0.1)

            # 如果有深度数据，根据深度分层绘制
            if 'G2depth' in var_data.columns:
                # 浅层数据 (≤250m) - 三角形
                shallow_data = var_data[var_data['G2depth'] <= 250]
                if len(shallow_data) > 0:
                    ax.scatter(
                        shallow_data['G2longitude'], shallow_data['G2latitude'],
                        facecolors='none',
                        edgecolors=[edge_color] * len(shallow_data),
                        s=21,  # 30*0.7=21
                        marker='^',  # 三角形
                        transform=ccrs.PlateCarree(),
                        linewidths=0.5
                    )
                    print(f"    绘制 {variable} 浅层(≤250m): {len(shallow_data)} 个三角形，颜色RGBA{edge_color}")

                # 深层数据 (>250m) - 圆形
                deep_data = var_data[var_data['G2depth'] > 250]
                if len(deep_data) > 0:
                    ax.scatter(
                        deep_data['G2longitude'], deep_data['G2latitude'],
                        facecolors='none',
                        edgecolors=[edge_color] * len(deep_data),
                        s=21,  # 30*0.7=21
                        marker='o',  # 圆形
                        transform=ccrs.PlateCarree(),
                        linewidths=0.5
                    )
                    print(f"    绘制 {variable} 深层(>250m): {len(deep_data)} 个圆形，颜色RGBA{edge_color}")
            else:
                # 没有深度数据，默认使用圆形
                ax.scatter(
                    var_data['G2longitude'], var_data['G2latitude'],
                    facecolors='none',
                    edgecolors=[edge_color] * len(var_data),
                    s=21,  # 30*0.7=21
                    marker='o',
                    transform=ccrs.PlateCarree(),
                    linewidths=0.5
                )
                print(f"    绘制 {variable}: {len(var_data)} 个圆形（无深度数据），颜色RGBA{edge_color}")

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        # 添加横断面线
        # 太平洋横断面 (-150°, -65°S to 58°N) - 红色
        ax.plot([-150, -150], [-65, 58], color='red', linewidth=4, transform=ccrs.PlateCarree(), label='Pacific')
        # 大西洋横断面 (-30°, -65°S to 60°N) - 黑色
        ax.plot([-30, -30], [-65, 60], color='black', linewidth=4, transform=ccrs.PlateCarree(), label='Atlantic')
        # 印度洋横断面 (67.5°, -65°S to 21°N) - 蓝色
        ax.plot([67.5, 67.5], [-65, 21], color='blue', linewidth=4, transform=ccrs.PlateCarree(), label='Indian')

        plt.tight_layout()
        return fig

    def create_combined_original_grid(self, data_subset, variables, year_range=None):
        """方法4: 原始网格 - 根据深度使用不同形状，快速预览"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征 - 海洋为空白（白色）
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='white')
        ax.add_feature(cfeature.OCEAN, color='white')  # 空白海洋背景
        ax.set_global()

        # 为每个变量直接绘制散点
        for variable in variables:
            if variable not in data_subset.columns:
                continue

            var_data = data_subset.dropna(subset=[variable, 'G2longitude', 'G2latitude'])
            if len(var_data) == 0:
                continue

            # 获取变量的配色配置
            color_config = self.get_color_config(variable)

            # 确定颜色
            if color_config['color'] == 'darkturquoise':
                rgba_color = (0.0, 0.6, 0.8, 0.1)
            elif color_config['color'] == 'lightcoral':
                rgba_color = (1.0, 0.5, 0.5, 0.1)
            else:
                rgba_color = (0.0, 0.0, 1.0, 0.1)

            # 如果有深度数据，根据深度分层绘制
            if 'G2depth' in var_data.columns:
                # 浅层数据 (≤250m) - 三角形
                shallow_data = var_data[var_data['G2depth'] <= 250]
                if len(shallow_data) > 0:
                    ax.scatter(
                        shallow_data['G2longitude'], shallow_data['G2latitude'],
                        c=[rgba_color] * len(shallow_data),
                        s=7,  # 10*0.7=7
                        marker='^',  # 三角形
                        transform=ccrs.PlateCarree(),
                        edgecolors='none',
                        linewidths=0
                    )
                    print(f"    绘制 {variable} 浅层(≤250m): {len(shallow_data)} 个三角形，颜色RGBA{rgba_color}")

                # 深层数据 (>250m) - 圆形
                deep_data = var_data[var_data['G2depth'] > 250]
                if len(deep_data) > 0:
                    ax.scatter(
                        deep_data['G2longitude'], deep_data['G2latitude'],
                        c=[rgba_color] * len(deep_data),
                        s=7,  # 10*0.7=7
                        marker='o',  # 圆形
                        transform=ccrs.PlateCarree(),
                        edgecolors='none',
                        linewidths=0
                    )
                    print(f"    绘制 {variable} 深层(>250m): {len(deep_data)} 个圆形，颜色RGBA{rgba_color}")
            else:
                # 没有深度数据，默认使用圆形
                ax.scatter(
                    var_data['G2longitude'], var_data['G2latitude'],
                    c=[rgba_color] * len(var_data),
                    s=7,  # 10*0.7=7
                    marker='o',
                    transform=ccrs.PlateCarree(),
                    edgecolors='none',
                    linewidths=0
                )
                print(f"    绘制 {variable}: {len(var_data)} 个圆形（无深度数据），颜色RGBA{rgba_color}")

        # 添加更密集的网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True
        gl.xlabel_style = {'family': 'Times New Roman', 'weight': 'bold'}
        gl.ylabel_style = {'family': 'Times New Roman', 'weight': 'bold'}

        # 添加横断面线
        # 太平洋横断面 (-150°, -65°S to 58°N) - 红色
        ax.plot([-150, -150], [-65, 58], color='red', linewidth=4, transform=ccrs.PlateCarree(), label='Pacific')
        # 大西洋横断面 (-30°, -65°S to 60°N) - 黑色
        ax.plot([-30, -30], [-65, 60], color='black', linewidth=4, transform=ccrs.PlateCarree(), label='Atlantic')
        # 印度洋横断面 (67.5°, -65°S to 21°N) - 蓝色
        ax.plot([67.5, 67.5], [-65, 21], color='blue', linewidth=4, transform=ccrs.PlateCarree(), label='Indian')

        plt.tight_layout()
        return fig

    def create_combined_global_map(self, data_subset, variables, year_range=None):
        """根据选择的方法创建组合地图"""
        if self.plot_method == "scatter":
            return self.create_combined_scatter_plot(data_subset, variables, year_range)
        elif self.plot_method == "high_res_grid":
            return self.create_combined_high_res_grid(data_subset, variables, year_range)
        elif self.plot_method == "interpolation":
            return self.create_combined_interpolated_grid(data_subset, variables, year_range)
        elif self.plot_method == "original_grid":
            return self.create_combined_original_grid(data_subset, variables, year_range)
        else:
            return self.create_combined_high_res_grid(data_subset, variables, year_range)

    def process_single_file(self, csv_file, variables):
        """处理单个CSV文件，将所有变量绘制在同一张图上"""
        print(f"\n{'=' * 60}")
        print(f"处理文件: {os.path.basename(csv_file)}")
        print(f"{'=' * 60}")

        # 加载数据
        data = self.load_single_csv(csv_file)
        if data is None:
            return

        file_base_name = os.path.splitext(os.path.basename(csv_file))[0]

        # 年份分析
        self.analyze_year_distribution(data)

        # 获取年份范围用于文件名
        if 'G2year' in data.columns:
            years = sorted(data['G2year'].unique())
            year_range = f"{min(years)}-{max(years)}"
        else:
            year_range = None

        # 为每个变量进行深度分析
        for variable in variables:
            if variable in data.columns:
                print(f"\n  分析变量: {variable}")
                color_config = self.get_color_config(variable)
                print(f"    使用颜色: {color_config['color']}，透明度: {color_config['alpha']}")
                self.analyze_depth_distribution(data, variable)

        try:
            # 检查是否有有效的变量数据
            valid_variables = []
            for variable in variables:
                if variable in data.columns:
                    variable_data = data.dropna(subset=[variable, 'G2longitude', 'G2latitude'])
                    if len(variable_data) > 0:
                        valid_variables.append(variable)
                        print(f"      {variable} 有效数据点: {len(variable_data)}")

            if not valid_variables:
                print("      ✗ 没有有效的变量数据")
                return

            print(f"\n  创建组合图像，包含变量: {valid_variables}")

            # 创建组合地图
            fig = self.create_combined_global_map(data, valid_variables, year_range)

            # 保存图像
            year_suffix = f"_{year_range}" if year_range else ""
            method_suffix = f"_{self.plot_method}"
            variables_str = "_".join(valid_variables)
            filename = f"{file_base_name}_{variables_str}_combined{year_suffix}{method_suffix}.png"
            filepath = os.path.join(self.output_folder, filename)

            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            print(f"      ✓ 已保存组合图像: {filename}")

        except Exception as e:
            print(f"      ✗ 绘图出错: {e}")
        finally:
            # 清理这个图的内存
            plt.close('all')

        # 处理完这个文件后清理内存
        del data
        self.clear_memory()
        print(f"  内存清理完成")

    def run(self):
        """运行主程序"""
        print("=== 海洋硝酸盐和亚硝酸盐数据可视化工具 ===")
        print("🌊 特性:")
        print("- 将nitrate (淡海绿色) 和 nitrite (淡紫色) 绘制在同一张图上")
        print("- 使用plasma风格配色，在空白海洋背景上突出显示")
        print("- 空心数据点，90%透明边框，只显示数据点位置（不映射数值到颜色）")
        print("- 海洋背景为空白（白色），让plasma配色数据点更加突出，无图表标题")
        print("- 自动过滤1978-2023年数据")
        print("- 点大小减少30%，不同方法使用不同的点大小优化显示效果")
        print("- 边框宽度0.5，无图例显示")
        print("- 深度分层显示：≤250m使用三角形，>250m使用圆形")
        print("- 包含三条横断面线：太平洋(-150°,红色)、大西洋(-30°,黑色)、印度洋(67.5°,蓝色)")
        print("- 深度分布统计（0-250m vs >250m）")
        print("- 优化内存管理，支持大数据集")
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

        # 4. 选择绘图方法
        self.select_plot_method()

        # 5. 选择颜色刻度模式
        self.select_color_scale_mode()

        # 6. 固定使用nitrate和nitrite两个变量
        variables = ['G2nitrate', 'G2nitrite']
        print(f"\n将绘制变量: {variables}")
        print("- G2nitrate: 淡海绿色，≤250m三角形，>250m圆形，边框90%透明（10%不透明）")
        print("- G2nitrite: 淡紫色，≤250m三角形，>250m圆形，边框90%透明（10%不透明）")
        print("- 散点大小: 减少30%")
        print("- 边框宽度: 0.5")
        print("- 海洋背景: 空白（白色），突出plasma配色数据点")
        print("- 横断面线: 太平洋横断面(-150°,红色)、大西洋横断面(-30°,黑色)、印度洋横断面(67.5°,蓝色)")
        print("- 组合显示: 两个变量在同一张图上，无图例")

        # 清理示例数据
        del sample_data
        self.clear_memory()

        # 7. 批量处理所有文件
        print(f"\n开始批量处理 {len(self.csv_files)} 个文件...")
        print(f"将生成 {len(self.csv_files)} 个组合图像")
        print(f"数据过滤: 保留1978-2023年的所有数据")
        print(f"深度统计: 分析0-250m和>250m的数据分布")
        print(f"形状区分: ≤250m三角形，>250m圆形")
        print(f"横断面线: 太平洋(-150°,红色)、大西洋(-30°,黑色)、印度洋(67.5°,蓝色)，线宽4")

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
        print(f"所有组合图像已保存到: {self.output_folder}")
        print(f"使用的绘图方法: {self.plot_method}")
        print(f"显示模式: 只显示数据点位置")
        print(f"配色方案: nitrate=深青色RGBA(0.0,0.6,0.8,0.1), nitrite=淡红色RGBA(1.0,0.5,0.5,0.1)")
        print(f"海洋背景: 淡青色 (lightcyan)")
        print(f"显示模式: 空心点，边框90%透明度（10%不透明度），无图例")
        print(f"点大小: 方法1=28, 方法2=14, 方法3=21, 方法4=7 (均减少30%)")
        print(f"边框宽度: 0.5")
        print(f"形状区分: ≤250m深度三角形，>250m深度圆形")
        print(f"数据处理: 使用1978-2023年的所有过滤数据")
        print(f"深度分析: 0-250m vs >250m")
        print(f"图像特点: 组合显示，无标题，无图例，形状区分深度，透明边框效果")
        print(f"{'=' * 60}")


def main():
    """主函数"""
    try:
        visualizer = OceanNitrateNitriteVisualizer()
        visualizer.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按回车键退出...")


if __name__ == "__main__":
    main()