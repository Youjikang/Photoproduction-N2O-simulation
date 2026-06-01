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
import warnings

warnings.filterwarnings('ignore')


class ImprovedOceanDataVisualizer:
    def __init__(self):
        self.data = None
        self.input_files = []
        self.output_folder = ""
        self.plot_method = "scatter"  # 默认方法

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

        while True:
            try:
                choice = input(f"\n请选择绘图方法 (1-{len(methods)}): ").strip()
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

    def select_input_files(self):
        """选择输入CSV文件"""
        root = tk.Tk()
        root.withdraw()

        file_paths = filedialog.askopenfilenames(
            title="选择CSV数据文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if file_paths:
            self.input_files = list(file_paths)
            print(f"已选择 {len(self.input_files)} 个文件:")
            for file in self.input_files:
                print(f"  - {os.path.basename(file)}")
            return True
        else:
            print("未选择任何文件")
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

    def load_data(self):
        """加载所有CSV文件"""
        if not self.input_files:
            print("请先选择输入文件")
            return False

        print("正在加载数据文件...")
        dataframes = []

        for file_path in self.input_files:
            try:
                print(f"加载: {os.path.basename(file_path)}")
                df = pd.read_csv(file_path)
                dataframes.append(df)
            except Exception as e:
                print(f"加载文件 {file_path} 时出错: {e}")
                continue

        if dataframes:
            self.data = pd.concat(dataframes, ignore_index=True)
            print(f"数据加载完成! 总共 {len(self.data)} 行数据")
            print(f"数据列: {list(self.data.columns)}")

            # 显示数据分辨率信息
            if len(self.data) > 0:
                lon_resolution = self.estimate_resolution('longitude')
                lat_resolution = self.estimate_resolution('latitude')
                print(f"估计的数据分辨率: 经度 {lon_resolution:.3f}°, 纬度 {lat_resolution:.3f}°")
                print(f"对应的公里分辨率: 经度 {lon_resolution * 111:.1f}km, 纬度 {lat_resolution * 111:.1f}km")

            return True
        else:
            print("没有成功加载任何数据")
            return False

    def estimate_resolution(self, coord_column):
        """估计数据的分辨率"""
        if coord_column not in self.data.columns:
            return 1.0

        # 取样本数据估计分辨率
        sample_data = self.data[coord_column].dropna().sort_values()
        if len(sample_data) < 2:
            return 1.0

        # 计算相邻点的最小差值
        diffs = sample_data.diff().dropna()
        min_diff = diffs[diffs > 0].min() if len(diffs[diffs > 0]) > 0 else 1.0

        return min_diff

    def get_available_depths(self):
        """获取可用的深度值"""
        if self.data is None:
            return []
        return sorted(self.data['depth'].unique())

    def select_depths(self):
        """选择要绘制的深度"""
        available_depths = self.get_available_depths()

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

    def select_variable(self):
        """选择要绘制的变量"""
        variables = ['nitrite_predicted', 'nitrate']

        print("\n" + "=" * 40)
        print("可用变量:")
        print("=" * 40)
        for i, var in enumerate(variables):
            print(f"{i + 1}. {var}")
        print("=" * 40)

        while True:
            try:
                var_input = input(f"\n请输入变量编号 (1-{len(variables)}): ").strip()

                if not var_input:
                    print("未输入任何内容，使用默认变量: nitrite_predicted")
                    return 'nitrite_predicted'

                index = int(var_input) - 1
                if 0 <= index < len(variables):
                    selected_var = variables[index]
                    print(f"✓ 已选择变量: {selected_var}")
                    return selected_var
                else:
                    print(f"✗ 编号超出范围，请输入 1-{len(variables)}")
                    continue

            except ValueError:
                print("✗ 请输入有效的数字")
                continue
            except KeyboardInterrupt:
                print("\n使用默认变量: nitrite_predicted")
                return 'nitrite_predicted'

    def create_scatter_plot(self, data_subset, variable, depth, year=None):
        """方法1: 散点图 - 直接显示原始数据点"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.add_feature(cfeature.BORDERS, linewidth=0.3)
        ax.set_global()

        # 直接绘制散点
        scatter = ax.scatter(
            data_subset['longitude'], data_subset['latitude'],
            c=data_subset[variable],
            s=1,  # 点的大小
            cmap='viridis',
            transform=ccrs.PlateCarree(),
            alpha=0.8
        )

        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(f'{variable} concentration', fontsize=12)

        # 添加网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
        gl.top_labels = False
        gl.right_labels = False

        # 设置标题
        year_str = f" - {year}" if year else ""
        title = f'Global Ocean {variable.replace("_", " ").title()} at {depth}m{year_str}\n(Scatter Plot - {len(data_subset)} data points)'
        plt.title(title, fontsize=14, fontweight='bold')

        plt.tight_layout()
        return fig

    def create_high_res_grid(self, data_subset, variable, depth, year=None):
        """方法2: 高分辨率网格 - 保持数据原始分辨率"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.add_feature(cfeature.BORDERS, linewidth=0.3)
        ax.set_global()

        # 使用0.5度网格 (约55km) - 比原始40km稍粗但保持高分辨率
        lon_bins = np.arange(-180, 180.5, 0.5)
        lat_bins = np.arange(-90, 90.5, 0.5)

        lon_centers = (lon_bins[:-1] + lon_bins[1:]) / 2
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        lon_grid, lat_grid = np.meshgrid(lon_centers, lat_centers)
        value_grid = np.full_like(lon_grid, np.nan)

        # 网格化数据
        print(f"  正在进行高分辨率网格化 ({len(lon_centers)}x{len(lat_centers)} 网格)...")
        for i, lat_center in enumerate(lat_centers):
            if i % 50 == 0:  # 显示进度
                print(f"    进度: {i}/{len(lat_centers)}")

            for j, lon_center in enumerate(lon_centers):
                lat_mask = (data_subset['latitude'] >= lat_bins[i]) & (data_subset['latitude'] < lat_bins[i + 1])
                lon_mask = (data_subset['longitude'] >= lon_bins[j]) & (data_subset['longitude'] < lon_bins[j + 1])
                cell_data = data_subset[lat_mask & lon_mask]

                if len(cell_data) > 0:
                    value_grid[i, j] = cell_data[variable].mean()

        # 添加循环点
        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_centers)

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap='viridis',
            shading='auto'
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(f'{variable} concentration', fontsize=12)

        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
        gl.top_labels = False
        gl.right_labels = False

        year_str = f" - {year}" if year else ""
        title = f'Global Ocean {variable.replace("_", " ").title()} at {depth}m{year_str}\n(High-Res Grid - 0.5° resolution)'
        plt.title(title, fontsize=14, fontweight='bold')

        plt.tight_layout()
        return fig

    def create_interpolated_grid(self, data_subset, variable, depth, year=None):
        """方法3: 插值网格 - 平滑插值"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.add_feature(cfeature.BORDERS, linewidth=0.3)
        ax.set_global()

        # 创建规则网格用于插值
        lon_interp = np.arange(-180, 181, 1)  # 1度网格
        lat_interp = np.arange(-90, 91, 1)
        lon_grid, lat_grid = np.meshgrid(lon_interp, lat_interp)

        # 准备插值数据
        points = data_subset[['longitude', 'latitude']].values
        values = data_subset[variable].values

        print(f"  正在进行插值计算 (使用 {len(points)} 个数据点)...")

        # 使用线性插值
        value_grid = griddata(
            points, values,
            (lon_grid, lat_grid),
            method='linear',
            fill_value=np.nan
        )

        # 添加循环点
        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_interp)

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_interp, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap='viridis',
            shading='auto'
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(f'{variable} concentration', fontsize=12)

        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
        gl.top_labels = False
        gl.right_labels = False

        year_str = f" - {year}" if year else ""
        title = f'Global Ocean {variable.replace("_", " ").title()} at {depth}m{year_str}\n(Interpolated Grid - Linear interpolation)'
        plt.title(title, fontsize=14, fontweight='bold')

        plt.tight_layout()
        return fig

    def create_original_grid(self, data_subset, variable, depth, year=None):
        """方法4: 原始2度网格 - 快速预览"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.add_feature(cfeature.BORDERS, linewidth=0.3)
        ax.set_global()

        # 使用2度网格 (原始方法)
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

        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap='viridis',
            shading='auto'
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(f'{variable} concentration', fontsize=12)

        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
        gl.top_labels = False
        gl.right_labels = False

        year_str = f" - {year}" if year else ""
        title = f'Global Ocean {variable.replace("_", " ").title()} at {depth}m{year_str}\n(Original Grid - 2° resolution)'
        plt.title(title, fontsize=14, fontweight='bold')

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
            # 默认使用高分辨率网格
            return self.create_high_res_grid(data_subset, variable, depth, year)

    def plot_depth_maps(self, depths, variable):
        """为指定深度绘制地图"""
        if self.data is None:
            print("请先加载数据")
            return

        if not self.output_folder:
            print("请先选择输出文件夹")
            return

        for depth in depths:
            print(f"正在绘制深度 {depth}m 的地图...")

            depth_data = self.data[self.data['depth'] == depth].copy()

            if len(depth_data) == 0:
                print(f"深度 {depth}m 没有数据")
                continue

            # 处理年份
            if 'year' in depth_data.columns:
                years = sorted(depth_data['year'].unique())
                latest_year = max(years)
                year_data = depth_data[depth_data['year'] == latest_year]
                year_label = latest_year
            else:
                year_data = depth_data
                year_label = None

            # 移除缺失值
            year_data = year_data.dropna(subset=[variable, 'longitude', 'latitude'])

            if len(year_data) == 0:
                print(f"深度 {depth}m 没有有效数据")
                continue

            print(f"  有效数据点: {len(year_data)}")

            # 创建地图
            fig = self.create_global_map(year_data, variable, depth, year_label)

            # 保存图像
            year_suffix = f"_{year_label}" if year_label else ""
            method_suffix = f"_{self.plot_method}"
            filename = f"{variable}_depth_{depth}m{year_suffix}{method_suffix}.png"
            filepath = os.path.join(self.output_folder, filename)

            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()

            print(f"  已保存: {filename}")

    def run(self):
        """运行主程序"""
        print("=== 改进的全球海洋数据可视化工具 ===\n")

        # 1. 选择输入文件
        if not self.select_input_files():
            return

        # 2. 选择输出文件夹
        if not self.select_output_folder():
            return

        # 3. 加载数据
        if not self.load_data():
            return

        # 4. 选择绘图方法
        self.select_plot_method()

        # 5. 选择变量
        variable = self.select_variable()

        # 6. 选择深度
        depths = self.select_depths()
        if not depths:
            print("未选择深度，程序退出")
            return

        # 7. 绘制地图
        self.plot_depth_maps(depths, variable)

        print(f"\n所有地图已保存到: {self.output_folder}")
        print(f"使用的绘图方法: {self.plot_method}")


def main():
    """主函数"""
    try:
        visualizer = ImprovedOceanDataVisualizer()
        visualizer.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()