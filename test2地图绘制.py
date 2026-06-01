import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
import os
from tkinter import filedialog, messagebox
import tkinter as tk
from scipy.interpolate import griddata
import warnings
import gc

warnings.filterwarnings('ignore')

# 设置全局字体
plt.rcParams['font.family'] = 'Times New Roman'
plt.rcParams['font.size'] = 12
plt.rcParams['font.weight'] = 'bold'


class SimpleN2OVisualizer:
    def __init__(self):
        self.data = None
        self.csv_file_path = ""
        self.output_folder = ""
        self.plot_method = "high_res_grid"  # 默认方法
        self.variable = "N2O_integrated_nmol_N_per_m2"  # 固定变量

    def clear_memory(self):
        """清理内存"""
        plt.clf()
        plt.close('all')
        gc.collect()

    def select_csv_file(self):
        """选择输入CSV文件"""
        root = tk.Tk()
        root.withdraw()

        file_path = filedialog.askopenfilename(
            title="选择输入CSV文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if file_path:
            self.csv_file_path = file_path
            print(f"已选择文件: {os.path.basename(file_path)}")
            return True
        else:
            print("未选择文件")
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

    def select_plot_method(self):
        """选择绘图方法"""
        methods = {
            1: ("scatter", "散点图 - 直接显示原始数据点"),
            2: ("high_res_grid", "高分辨率网格 - 0.5度网格（推荐）"),
            3: ("interpolation", "插值网格 - 平滑插值"),
            4: ("original_grid", "原始2度网格 - 快速预览")
        }

        print("\n" + "=" * 50)
        print("选择绘图方法:")
        print("=" * 50)
        for num, (method, desc) in methods.items():
            print(f"{num}. {desc}")
        print("=" * 50)

        while True:
            try:
                choice = input(f"\n请选择绘图方法 (1-{len(methods)}，默认2): ").strip()
                if not choice:
                    choice = "2"

                choice_num = int(choice)
                if 1 <= choice_num <= len(methods):
                    self.plot_method = methods[choice_num][0]
                    print(f"✓ 已选择: {methods[choice_num][1]}")
                    return
                else:
                    print(f"✗ 请输入 1-{len(methods)} 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认方法: 高分辨率网格")
                self.plot_method = "high_res_grid"
                return

    def load_csv(self):
        """加载CSV文件"""
        try:
            print(f"正在加载文件: {os.path.basename(self.csv_file_path)}")

            # 先检查文件中是否包含必需的列
            sample_df = pd.read_csv(self.csv_file_path, nrows=5)
            required_columns = ['longitude', 'latitude', self.variable]
            missing_columns = [col for col in required_columns if col not in sample_df.columns]

            if missing_columns:
                print(f"✗ 文件缺少必需的列: {missing_columns}")
                print(f"文件中的列: {list(sample_df.columns)}")
                return False

            # 优化数据类型以节省内存
            dtype_dict = {
                'longitude': 'float32',
                'latitude': 'float32',
                self.variable: 'float32'
            }

            # 只读取需要的列
            columns_to_read = ['longitude', 'latitude', self.variable]

            self.data = pd.read_csv(self.csv_file_path, usecols=columns_to_read, dtype=dtype_dict)

            # 移除缺失值
            initial_rows = len(self.data)
            self.data = self.data.dropna()
            final_rows = len(self.data)

            print(f"✓ 数据加载成功")
            print(f"  总行数: {initial_rows}")
            print(f"  有效行数: {final_rows}")
            print(f"  数据列: {list(self.data.columns)}")
            print(
                f"  {self.variable} 数据范围: {self.data[self.variable].min():.3f} - {self.data[self.variable].max():.3f}")
            print(f"  图例显示范围: 0.0 - 800,000 (固定)")
            print(f"  内存使用: {self.data.memory_usage(deep=True).sum() / 1024 ** 2:.2f} MB")

            return True

        except Exception as e:
            print(f"✗ 加载文件出错: {e}")
            return False

    def create_scatter_plot(self):
        """散点图方法"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 绘制散点
        scatter = ax.scatter(
            self.data['longitude'], self.data['latitude'],
            c=self.data[self.variable],
            s=1,
            cmap='viridis',  # 高对比度配色
            transform=ccrs.PlateCarree(),
            alpha=0.7,
            vmin=0, vmax=800000  # 设置图例范围为800,000
        )

        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label('N₂O integrated (nmol N/m²)', fontsize=14, fontweight='bold')

        # 添加网格线
        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        plt.title('Global N₂O Integrated Distribution', fontsize=16, fontweight='bold', pad=20)
        plt.tight_layout()
        return fig

    def create_high_res_grid(self):
        """高分辨率网格方法"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 创建0.5度网格
        lon_bins = np.arange(-180, 180.5, 0.5)
        lat_bins = np.arange(-90, 90.5, 0.5)

        lon_centers = (lon_bins[:-1] + lon_bins[1:]) / 2
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        value_grid = np.full((len(lat_centers), len(lon_centers)), np.nan)

        print("  正在进行网格化处理...")
        for i, lat_center in enumerate(lat_centers):
            if i % 50 == 0:
                print(f"    进度: {i}/{len(lat_centers)}")

            for j, lon_center in enumerate(lon_centers):
                lat_mask = (self.data['latitude'] >= lat_bins[i]) & (self.data['latitude'] < lat_bins[i + 1])
                lon_mask = (self.data['longitude'] >= lon_bins[j]) & (self.data['longitude'] < lon_bins[j + 1])
                cell_data = self.data[lat_mask & lon_mask]

                if len(cell_data) > 0:
                    value_grid[i, j] = cell_data[self.variable].mean()

        # 添加循环点
        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_centers)

        # 绘制数据
        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap='viridis',  # 高对比度配色
            shading='auto',
            vmin=0, vmax=0.8e6  # 设置图例范围为800,000
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label('N₂O integrated (nmol N/m²)', fontsize=14, fontweight='bold')

        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        plt.title('Global N₂O Integrated Distribution (High Resolution)', fontsize=16, fontweight='bold', pad=20)
        plt.tight_layout()
        return fig

    def create_interpolated_grid(self):
        """插值网格方法"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 如果数据点太多，进行采样
        data_subset = self.data
        if len(self.data) > 50000:
            print(f"  数据量较大({len(self.data)}点)，进行采样...")
            data_subset = self.data.sample(n=50000, random_state=42)
            print(f"  采样后数据量: {len(data_subset)}点")

        # 创建插值网格
        lon_interp = np.arange(-180, 181, 1.5)
        lat_interp = np.arange(-90, 91, 1.5)
        lon_grid, lat_grid = np.meshgrid(lon_interp, lat_interp)

        points = data_subset[['longitude', 'latitude']].values
        values = data_subset[self.variable].values

        print("  正在进行插值计算...")
        value_grid = griddata(
            points, values,
            (lon_grid, lat_grid),
            method='linear',
            fill_value=np.nan
        )

        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_interp)

        im = ax.pcolormesh(
            lon_cyclic, lat_interp, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap='viridis',  # 高对比度配色
            shading='auto',
            vmin=0, vmax=0.8e6  # 设置图例范围为800,000
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label('N₂O integrated (nmol N/m²)', fontsize=14, fontweight='bold')

        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        plt.title('Global N₂O Integrated Distribution (Interpolated)', fontsize=16, fontweight='bold', pad=20)
        plt.tight_layout()
        return fig

    def create_original_grid(self):
        """原始2度网格方法"""
        fig = plt.figure(figsize=(16, 10))
        ax = plt.axes(projection=ccrs.Robinson())

        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black')
        ax.add_feature(cfeature.LAND, color='lightgray')
        ax.add_feature(cfeature.OCEAN, color='white')
        ax.set_global()

        # 使用2度网格
        lon_bins = np.arange(-180, 181, 2)
        lat_bins = np.arange(-90, 91, 2)

        lon_centers = (lon_bins[:-1] + lon_bins[1:]) / 2
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        value_grid = np.full((len(lat_centers), len(lon_centers)), np.nan)

        print("  正在进行快速网格化...")
        for i, lat_center in enumerate(lat_centers):
            for j, lon_center in enumerate(lon_centers):
                lat_mask = (self.data['latitude'] >= lat_bins[i]) & (self.data['latitude'] < lat_bins[i + 1])
                lon_mask = (self.data['longitude'] >= lon_bins[j]) & (self.data['longitude'] < lon_bins[j + 1])
                cell_data = self.data[lat_mask & lon_mask]

                if len(cell_data) > 0:
                    value_grid[i, j] = cell_data[self.variable].mean()

        value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_centers)

        im = ax.pcolormesh(
            lon_cyclic, lat_centers, value_grid_cyclic,
            transform=ccrs.PlateCarree(),
            cmap='viridis',  # 高对比度配色
            shading='auto',
            vmin=0, vmax=0.8e6  # 设置图例范围为800,000
        )

        cbar = plt.colorbar(im, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label('N₂O integrated (nmol N/m²)', fontsize=14, fontweight='bold')

        gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        plt.title('Global N₂O Integrated Distribution (2° Grid)', fontsize=16, fontweight='bold', pad=20)
        plt.tight_layout()
        return fig

    def create_map(self):
        """根据选择的方法创建地图"""
        if self.plot_method == "scatter":
            return self.create_scatter_plot()
        elif self.plot_method == "high_res_grid":
            return self.create_high_res_grid()
        elif self.plot_method == "interpolation":
            return self.create_interpolated_grid()
        elif self.plot_method == "original_grid":
            return self.create_original_grid()
        else:
            return self.create_high_res_grid()

    def save_map(self, fig):
        """保存地图"""
        file_base_name = os.path.splitext(os.path.basename(self.csv_file_path))[0]
        filename = f"{file_base_name}_N2O_integrated_{self.plot_method}.png"
        filepath = os.path.join(self.output_folder, filename)

        fig.savefig(filepath, dpi=300, bbox_inches='tight')
        print(f"✓ 地图已保存: {filename}")
        return filename

    def run(self):
        """运行主程序"""
        print("=== 简化版 N₂O 海洋数据可视化工具 ===")
        print("专门用于绘制 N2O_integrated_nmol_N_per_m2 参数")
        print("使用高对比度 viridis 配色方案，图例范围：0-800,000")
        print()

        # 1. 选择输入CSV文件
        if not self.select_csv_file():
            return

        # 2. 选择输出文件夹
        if not self.select_output_folder():
            return

        # 3. 加载数据
        if not self.load_csv():
            return

        # 4. 选择绘图方法
        self.select_plot_method()

        # 5. 创建地图
        print(f"\n正在使用 {self.plot_method} 方法创建地图...")
        try:
            fig = self.create_map()

            # 6. 保存地图
            filename = self.save_map(fig)

            # 7. 显示地图（可选）
            show_map = input("\n是否显示地图？(y/n，默认n): ").strip().lower()
            if show_map == 'y':
                plt.show()

            print(f"\n{'=' * 50}")
            print("处理完成!")
            print(f"输出文件: {filename}")
            print(f"保存路径: {self.output_folder}")
            print(f"使用方法: {self.plot_method}")
            print(f"配色方案: viridis (高对比度)")
            print(f"图例范围: 0.0 - 800,000")
            print(f"数据点数: {len(self.data)}")
            print(f"{'=' * 50}")

        except Exception as e:
            print(f"✗ 创建地图时出错: {e}")
        finally:
            self.clear_memory()


def main():
    """主函数"""
    try:
        visualizer = SimpleN2OVisualizer()
        visualizer.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按回车键退出...")


if __name__ == "__main__":
    main()