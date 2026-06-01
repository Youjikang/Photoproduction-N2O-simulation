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
import gc
import re
from matplotlib.ticker import FuncFormatter

warnings.filterwarnings('ignore')

# 设置全局字体 - 字体大小调整为28，字体改为Arial
plt.rcParams['font.family'] = 'Arial'
plt.rcParams['font.size'] = 28
plt.rcParams['font.weight'] = 'bold'


class ChunkedOceanLightVisualizer:
    def __init__(self):
        self.data = None
        self.input_folder = ""
        self.csv_files = []
        self.output_folder = ""
        self.plot_method = "high_res_grid"
        self.color_scale_mode = "auto"
        self.color_limits = {}
        self.plot_type = "both"
        self.error_type = "sem"
        self.chunk_size = 100000  # 每次处理10万行数据

        # 定义光谱区域
        self.spectral_bands = {
            'UVB': {'range': (290, 315), 'unit': 'mW/m²'},
            'UVA': {'range': (315, 400), 'unit': 'mW/m²'},
            'BLUE': {'range': (400, 490), 'unit': 'mW/m²'}
        }

        # 可选的配色方案
        self.available_colormaps = {
            1: ('viridis', '🔥 深蓝→亮黄 - 极高对比度，数据差异明显'),
            2: ('hot', '🔥 黑→红→白 - 经典热力图，对比强烈'),
            3: ('PRGn', '🔥 紫→绿对比 - 颜色互补，视觉冲击强'),
            4: ('gist_rainbow', '🔥 分段彩虹 - 多色分段，区分度极高'),
            5: ('coolwarm', '🔥 蓝→白→红 - 发散式配色，中性点明显'),
            6: ('turbo', '🔥 科学专用 - Google Turbo风格，感知均匀'),
            7: ('jet', '🔥 增强Jet - 改进的彩虹配色，对比度优化'),
            8: ('seismic', '🔥 极限对比 - 黑白彩色混合，最强对比'),
            9: ('inferno', '⭐ 经典Inferno - 黑→紫→红→黄（科学标准）'),
            10: ('cividis', '⭐ 色盲友好 - 蓝→绿→黄（无障碍设计）'),
            11: ('plasma', '⭐ 经典Plasma - 紫→粉→黄（高对比度）'),
            12: ('magma', '⭐ 经典Magma - 黑→紫→粉→白（温暖色调）')
        }

        self.selected_colormap = 'viridis'

        # 为不同光谱区域定义标签 - 修改为UVA (mW/m²)格式，2为上标
        self.color_schemes = {
            'UVB': {'label': 'UVB (mW/m$^2$)'},
            'UVA': {'label': 'UVA (mW/m$^2$)'},
            'BLUE': {'label': 'Blue Light (mW/m$^2$)'}
        }

        # 图形尺寸设置
        self.global_fig_size = (16, 10)
        self.lat_fig_size = (4, 8)

    def longitude_formatter(self, x, pos):
        """经度格式化函数 - 正负值表示（正号不显示）"""
        if x == 0:
            return '0°'
        elif x > 0:
            return f'{int(x)}°'
        else:
            return f'{int(x)}°'  # 负号会自动显示

    def latitude_formatter(self, y, pos):
        """纬度格式化函数 - 正负值表示（正号不显示）"""
        if y == 0:
            return '0°'
        elif y > 0:
            return f'{int(y)}°'
        else:
            return f'{int(y)}°'  # 负号会自动显示

    def get_file_info(self, file_path):
        """获取文件基本信息而不加载全部数据"""
        try:
            # 只读取前几行来获取列信息
            sample_df = pd.read_csv(file_path, nrows=1000)

            # 获取波长列
            wavelengths, wavelength_columns = self.find_wavelength_columns(sample_df)

            # 获取文件总行数（使用更高效的方法）
            total_rows = sum(1 for _ in open(file_path, 'r', encoding='utf-8')) - 1  # 减去标题行

            # 获取可用深度和年份
            available_depths = sorted(sample_df['depth'].unique()) if 'depth' in sample_df.columns else []
            available_years = sorted(sample_df['year'].unique()) if 'year' in sample_df.columns else []

            return {
                'total_rows': total_rows,
                'wavelengths': wavelengths,
                'wavelength_columns': wavelength_columns,
                'available_depths': available_depths,
                'available_years': available_years,
                'sample_data': sample_df
            }
        except Exception as e:
            print(f"  ✗ 获取文件信息出错: {e}")
            return None

    def read_csv_chunks(self, file_path, chunk_size=None):
        """分块读取CSV文件"""
        if chunk_size is None:
            chunk_size = self.chunk_size

        try:
            return pd.read_csv(file_path, chunksize=chunk_size, dtype={
                'longitude': 'float32',
                'latitude': 'float32',
                'depth': 'float32'
            })
        except Exception as e:
            print(f"  ✗ 分块读取出错: {e}")
            return None

    def find_wavelength_columns(self, data):
        """查找数据中所有的波长列（Ed_xxx格式）"""
        wavelength_columns = []
        wavelengths = []

        for col in data.columns:
            match = re.match(r'Ed_(\d+)', col)
            if match:
                wavelength = int(match.group(1))
                wavelength_columns.append(col)
                wavelengths.append(wavelength)

        # 按波长排序
        sorted_pairs = sorted(zip(wavelengths, wavelength_columns))
        wavelengths = [pair[0] for pair in sorted_pairs]
        wavelength_columns = [pair[1] for pair in sorted_pairs]

        return wavelengths, wavelength_columns

    def calculate_spectral_irradiance_chunk(self, chunk_data, band_name, wavelengths, wavelength_columns):
        """对数据块计算特定光谱区域的总辐射强度"""
        band_range = self.spectral_bands[band_name]['range']
        min_wl, max_wl = band_range

        # 找到在指定波长范围内的列
        band_columns = []
        band_wavelengths = []

        for wl, col in zip(wavelengths, wavelength_columns):
            if min_wl <= wl <= max_wl and col in chunk_data.columns:
                band_columns.append(col)
                band_wavelengths.append(wl)

        if not band_columns:
            return pd.Series([np.nan] * len(chunk_data), index=chunk_data.index, name=band_name)

        # 计算积分值
        integrated_values = []
        for idx in chunk_data.index:
            row_values = []
            row_wavelengths = []

            # 获取该行有效的波长数据
            for wl, col in zip(band_wavelengths, band_columns):
                if pd.notna(chunk_data.loc[idx, col]):
                    row_values.append(chunk_data.loc[idx, col])
                    row_wavelengths.append(wl)

            if len(row_values) < 2:
                integrated_values.append(np.nan)
            else:
                integral = np.trapz(row_values, row_wavelengths)
                integrated_values.append(integral)

        return pd.Series(integrated_values, index=chunk_data.index, name=band_name)

    def process_chunks_for_depth_variable(self, file_path, depth, variable, wavelengths, wavelength_columns):
        """分块处理特定深度和变量的数据"""
        print(f"      分块处理深度 {depth}m, 变量 {variable}...")

        processed_data = []
        chunk_count = 0

        try:
            # 分块读取文件
            for chunk in self.read_csv_chunks(file_path):
                chunk_count += 1

                # 过滤深度
                depth_chunk = chunk[chunk['depth'] == depth].copy()

                if len(depth_chunk) == 0:
                    continue

                # 处理年份（如果存在）
                if 'year' in depth_chunk.columns:
                    years = sorted(depth_chunk['year'].unique())
                    latest_year = max(years)
                    year_chunk = depth_chunk[depth_chunk['year'] == latest_year].copy()
                else:
                    year_chunk = depth_chunk.copy()

                if len(year_chunk) == 0:
                    continue

                # 计算光谱积分
                integrated_values = self.calculate_spectral_irradiance_chunk(
                    year_chunk, variable, wavelengths, wavelength_columns
                )

                # 添加积分结果到数据中
                year_chunk[variable] = integrated_values

                # 移除缺失值
                valid_chunk = year_chunk.dropna(subset=[variable, 'longitude', 'latitude'])

                if len(valid_chunk) > 0:
                    # 只保留必要的列以节省内存
                    essential_columns = ['longitude', 'latitude', 'depth', variable]
                    if 'year' in valid_chunk.columns:
                        essential_columns.append('year')

                    processed_chunk = valid_chunk[essential_columns].copy()
                    processed_data.append(processed_chunk)

                # 清理内存
                del depth_chunk, year_chunk, valid_chunk, integrated_values
                gc.collect()

                # 每处理50个块显示一次进度
                if chunk_count % 50 == 0:
                    print(f"        已处理 {chunk_count} 个数据块...")

        except Exception as e:
            print(f"      ✗ 分块处理出错: {e}")
            return None

        # 合并所有处理过的数据块
        if processed_data:
            print(f"      合并 {len(processed_data)} 个有效数据块...")
            combined_data = pd.concat(processed_data, ignore_index=True)

            # 清理临时数据
            del processed_data
            gc.collect()

            print(f"      ✓ 处理完成，有效数据点: {len(combined_data)}")
            return combined_data
        else:
            print(f"      ✗ 没有找到有效数据")
            return None

    def calculate_latitudinal_statistics(self, data_subset, variable, lat_bin_size=1.0):
        """计算纬度统计数据"""
        lat_min = data_subset['latitude'].min()
        lat_max = data_subset['latitude'].max()
        lat_bins = np.arange(lat_min, lat_max + lat_bin_size, lat_bin_size)
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        means = []
        errors = []
        counts = []

        for i in range(len(lat_bins) - 1):
            mask = (data_subset['latitude'] >= lat_bins[i]) & (data_subset['latitude'] < lat_bins[i + 1])
            bin_data = data_subset[mask][variable].dropna()

            if len(bin_data) > 0:
                mean_val = bin_data.mean()
                count_val = len(bin_data)

                if self.error_type == "sem":
                    error_val = stats.sem(bin_data) if len(bin_data) > 1 else 0
                elif self.error_type == "ci95":
                    if len(bin_data) > 1:
                        ci = stats.t.interval(0.95, len(bin_data) - 1,
                                              loc=mean_val,
                                              scale=stats.sem(bin_data))
                        error_val = (ci[1] - ci[0]) / 2
                    else:
                        error_val = 0
                elif self.error_type == "std":
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

    def get_color_config(self, variable):
        """获取变量的配色配置"""
        if variable in self.color_schemes:
            return {
                'cmap': self.selected_colormap,
                'label': self.color_schemes[variable]['label']
            }
        else:
            return {
                'cmap': self.selected_colormap,
                'label': f'{variable} (mW/m$^2$)'
            }

    def create_chunked_grid(self, data_subset, variable, depth, year=None, grid_resolution=0.5):
        """使用分块处理创建网格化数据"""
        print(f"      创建网格 (分辨率: {grid_resolution}度)...")

        # 创建网格
        lon_bins = np.arange(-180, 180 + grid_resolution, grid_resolution)
        lat_bins = np.arange(-90, 90 + grid_resolution, grid_resolution)

        lon_centers = (lon_bins[:-1] + lon_bins[1:]) / 2
        lat_centers = (lat_bins[:-1] + lat_bins[1:]) / 2

        # 初始化网格
        value_grid = np.full((len(lat_centers), len(lon_centers)), np.nan)
        count_grid = np.zeros((len(lat_centers), len(lon_centers)))

        # 分块处理数据以避免内存问题
        chunk_size = min(10000, len(data_subset))
        n_chunks = len(data_subset) // chunk_size + (1 if len(data_subset) % chunk_size > 0 else 0)

        for chunk_idx in range(n_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min((chunk_idx + 1) * chunk_size, len(data_subset))
            chunk = data_subset.iloc[start_idx:end_idx]

            # 为每个数据点找到对应的网格位置
            lon_indices = np.digitize(chunk['longitude'], lon_bins) - 1
            lat_indices = np.digitize(chunk['latitude'], lat_bins) - 1

            # 确保索引在有效范围内
            valid_mask = (
                    (lon_indices >= 0) & (lon_indices < len(lon_centers)) &
                    (lat_indices >= 0) & (lat_indices < len(lat_centers)) &
                    pd.notna(chunk[variable])
            )

            if valid_mask.sum() == 0:
                continue

            # 使用有效的索引和数据
            valid_lon_idx = lon_indices[valid_mask]
            valid_lat_idx = lat_indices[valid_mask]
            valid_values = chunk[variable].values[valid_mask]

            # 累积数据到网格中
            for i, (lat_idx, lon_idx, value) in enumerate(zip(valid_lat_idx, valid_lon_idx, valid_values)):
                if np.isnan(value_grid[lat_idx, lon_idx]):
                    value_grid[lat_idx, lon_idx] = value
                    count_grid[lat_idx, lon_idx] = 1
                else:
                    # 计算加权平均
                    old_count = count_grid[lat_idx, lon_idx]
                    new_count = old_count + 1
                    value_grid[lat_idx, lon_idx] = (value_grid[lat_idx, lon_idx] * old_count + value) / new_count
                    count_grid[lat_idx, lon_idx] = new_count

            if (chunk_idx + 1) % 10 == 0:
                print(f"        网格化进度: {chunk_idx + 1}/{n_chunks}")

        return value_grid, lon_centers, lat_centers

    def create_global_map_chunked(self, data_subset, variable, depth, year=None):
        """创建全球分布图（优化版本）"""
        fig = plt.figure(figsize=self.global_fig_size)
        ax = plt.axes(projection=ccrs.Robinson())

        # 添加地理特征
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

        if self.plot_method == "scatter":
            # 直接使用全部数据点，不进行采样
            print(f"      绘制散点图，数据点数: {len(data_subset)}")

            scatter = ax.scatter(
                data_subset['longitude'], data_subset['latitude'],
                c=data_subset[variable],
                s=1,
                cmap=color_config['cmap'],
                transform=ccrs.PlateCarree(),
                alpha=0.8,
                vmin=vmin, vmax=vmax
            )
        else:
            # 网格化方法
            if self.plot_method == "high_res_grid":
                grid_resolution = 0.5
            elif self.plot_method == "interpolation":
                # 对于插值，如果数据点太多会影响性能，但保留更多数据点
                if len(data_subset) > 200000:
                    data_subset = data_subset.sample(n=200000, random_state=42)
                    print(f"      插值前采样到200000点...")

                lon_interp = np.arange(-180, 181, 1.5)
                lat_interp = np.arange(-90, 91, 1.5)
                lon_grid, lat_grid = np.meshgrid(lon_interp, lat_interp)

                points = data_subset[['longitude', 'latitude']].values.astype(np.float32)
                values = data_subset[variable].values.astype(np.float32)

                print(f"      正在进行插值计算...")
                value_grid = griddata(
                    points, values,
                    (lon_grid, lat_grid),
                    method='linear',
                    fill_value=np.nan
                )

                value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_interp)

                scatter = ax.pcolormesh(
                    lon_cyclic, lat_interp, value_grid_cyclic,
                    transform=ccrs.PlateCarree(),
                    cmap=color_config['cmap'],
                    shading='auto',
                    vmin=vmin, vmax=vmax
                )
            else:  # high_res_grid 或 original_grid
                grid_resolution = 0.5 if self.plot_method == "high_res_grid" else 2.0
                value_grid, lon_centers, lat_centers = self.create_chunked_grid(
                    data_subset, variable, depth, year, grid_resolution
                )

                value_grid_cyclic, lon_cyclic = add_cyclic_point(value_grid, coord=lon_centers)

                scatter = ax.pcolormesh(
                    lon_cyclic, lat_centers, value_grid_cyclic,
                    transform=ccrs.PlateCarree(),
                    cmap=color_config['cmap'],
                    shading='auto',
                    vmin=vmin, vmax=vmax
                )

        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax, orientation='horizontal',
                            pad=0.05, shrink=0.8, aspect=30)
        cbar.set_label(color_config['label'], fontsize=28, fontweight='bold', family='Arial')

        # 添加网格线（但不显示自动标签）
        ax.gridlines(xlocs=np.arange(-180, 181, 30), ylocs=np.arange(-90, 91, 30),
                     draw_labels=False, color='gray', alpha=0.5, linewidth=0.5)

        # 使用自定义格式的网格标签 - 修复经纬度显示为正负值
        gl = ax.gridlines(draw_labels=True, dms=False, x_inline=False, y_inline=False,
                          xlocs=np.arange(-180, 181, 60), ylocs=np.arange(-90, 91, 30))
        gl.top_labels = True
        gl.right_labels = True

        # 设置自定义格式化器
        gl.xformatter = FuncFormatter(self.longitude_formatter)
        gl.yformatter = FuncFormatter(self.latitude_formatter)

        gl.xlabel_style = {'family': 'Arial', 'weight': 'bold', 'size': 28}
        gl.ylabel_style = {'family': 'Arial', 'weight': 'bold', 'size': 28}

        plt.tight_layout()
        return fig

    def create_latitudinal_plot(self, data_subset, variable, depth, year=None):
        """创建纬度均值图"""
        lat_centers, means, errors, counts = self.calculate_latitudinal_statistics(data_subset, variable)

        if len(lat_centers) == 0:
            print(f"      ✗ 没有足够的数据来创建纬度图")
            return None

        fig, ax = plt.subplots(figsize=self.lat_fig_size)

        color_config = self.get_color_config(variable)

        if self.error_type == "sem":
            error_multiplier = 2
        elif self.error_type == "ci95":
            error_multiplier = 1
        else:
            error_multiplier = 1

        error_range = error_multiplier * errors

        ax.fill_betweenx(lat_centers, means - error_range, means + error_range,
                         alpha=0.5, color='darkgray', edgecolor='none')

        ax.plot(means, lat_centers, color='black', linewidth=1.5,
                linestyle='-', solid_capstyle='round')

        ax.set_ylabel('Latitude', fontsize=28, fontweight='bold', family='Arial')
        ax.set_xlabel(color_config['label'], fontsize=28, fontweight='bold', family='Arial')

        ax.set_ylim(-90, 90)
        ax.set_yticks(np.arange(-90, 91, 30))

        # 修改纬度标签为正负值表示（正号不显示，负号显示）
        lat_labels = []
        for lat in np.arange(-90, 91, 30):
            if lat == 0:
                lat_labels.append('0°')
            elif lat > 0:
                lat_labels.append(f'{int(lat)}°')  # 正值不显示+号
            else:
                lat_labels.append(f'{int(lat)}°')  # 负值自动显示-号

        ax.set_yticklabels(lat_labels)

        ax.grid(False)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_linewidth(1)
        ax.spines['bottom'].set_linewidth(1)

        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontfamily('Arial')
            label.set_fontsize(28)

        fig.subplots_adjust(left=0.15, right=0.92, top=0.95, bottom=0.08)

        return fig

    def process_single_file_chunked(self, csv_file, depths, variables):
        """分块处理单个CSV文件"""
        print(f"\n{'=' * 60}")
        print(f"分块处理文件: {os.path.basename(csv_file)}")
        print(f"{'=' * 60}")

        # 获取文件信息
        file_info = self.get_file_info(csv_file)
        if file_info is None:
            return

        print(f"  文件总行数: {file_info['total_rows']:,}")
        print(f"  波长数据列: {len(file_info['wavelength_columns'])}")
        print(f"  可用深度: {file_info['available_depths']}")
        print(f"  分块大小: {self.chunk_size:,} 行")

        wavelengths = file_info['wavelengths']
        wavelength_columns = file_info['wavelength_columns']
        file_base_name = os.path.splitext(os.path.basename(csv_file))[0]

        # 为每个深度和变量的组合分别处理
        for depth in depths:
            print(f"\n  处理深度: {depth}m")

            for variable in variables:
                print(f"    处理光谱区域: {variable}")

                try:
                    # 分块处理这个深度和变量的数据
                    processed_data = self.process_chunks_for_depth_variable(
                        csv_file, depth, variable, wavelengths, wavelength_columns
                    )

                    if processed_data is None or len(processed_data) == 0:
                        print(f"      ✗ 深度 {depth}m, 变量 {variable} 没有有效数据")
                        continue

                    # 获取年份信息
                    if 'year' in processed_data.columns:
                        year_label = processed_data['year'].iloc[0]
                        year_suffix = f"_{year_label}"
                    else:
                        year_label = None
                        year_suffix = ""

                    # 生成图像
                    if self.plot_type in ["global", "both"]:
                        print(f"      生成全球分布图...")
                        fig_global = self.create_global_map_chunked(processed_data, variable, depth, year_label)

                        method_suffix = f"_{self.plot_method}"
                        filename_global = f"{file_base_name}_{variable}_depth_{depth}m{year_suffix}_global{method_suffix}.png"
                        filepath_global = os.path.join(self.output_folder, filename_global)

                        fig_global.savefig(filepath_global, dpi=300, bbox_inches='tight')
                        print(f"      ✓ 已保存全球图: {filename_global}")
                        plt.close(fig_global)

                    if self.plot_type in ["latitudinal", "both"]:
                        print(f"      生成纬度均值图...")
                        fig_lat = self.create_latitudinal_plot(processed_data, variable, depth, year_label)

                        if fig_lat is not None:
                            error_suffix = f"_{self.error_type}"
                            filename_lat = f"{file_base_name}_{variable}_depth_{depth}m{year_suffix}_latitudinal{error_suffix}.png"
                            filepath_lat = os.path.join(self.output_folder, filename_lat)

                            fig_lat.savefig(filepath_lat, dpi=300, bbox_inches='tight')
                            print(f"      ✓ 已保存纬度图: {filename_lat}")
                            plt.close(fig_lat)

                except Exception as e:
                    print(f"      ✗ 处理 {variable} 深度 {depth}m 时出错: {e}")
                    continue
                finally:
                    # 清理内存
                    if 'processed_data' in locals():
                        del processed_data
                    plt.close('all')
                    gc.collect()

    # 保留原有的选择方法（简化版本）
    def select_input_folder(self):
        """选择包含CSV文件的输入文件夹"""
        root = tk.Tk()
        root.withdraw()

        folder_path = filedialog.askdirectory(title="选择包含CSV文件的输入文件夹")

        if folder_path:
            self.input_folder = folder_path
            self.csv_files = glob.glob(os.path.join(folder_path, "*.csv"))

            if self.csv_files:
                print(f"输入文件夹: {self.input_folder}")
                print(f"找到 {len(self.csv_files)} 个CSV文件:")
                for i, file in enumerate(self.csv_files, 1):
                    file_size = os.path.getsize(file) / (1024 ** 3)  # GB
                    print(f"  {i}. {os.path.basename(file)} ({file_size:.2f} GB)")
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

    def select_depths(self, file_info):
        """选择要绘制的深度"""
        available_depths = file_info['available_depths']

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
                continue
            except KeyboardInterrupt:
                print("\n用户取消选择")
                return []

    def select_variables(self):
        """选择要绘制的光谱区域"""
        variables = ['UVB', 'UVA', 'BLUE']

        print("\n" + "=" * 50)
        print("可用光谱区域:")
        print("=" * 50)
        for i, var in enumerate(variables):
            band_info = self.spectral_bands[var]
            print(f"{i + 1}. {var} ({band_info['range'][0]}-{band_info['range'][1]}nm)")
        print("=" * 50)

        while True:
            try:
                var_input = input(f"\n请输入光谱区域编号 (1-{len(variables)})，多个区域用逗号分隔: ").strip()

                if not var_input:
                    print("未输入任何内容，使用默认区域: UVB")
                    return ['UVB']

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
                    print("没有选择有效的光谱区域，请重新输入")
                    continue

                selected_vars = [variables[i] for i in indices]
                print(f"✓ 已选择光谱区域: {selected_vars}")
                return selected_vars

            except ValueError as e:
                print(f"✗ 输入格式错误: {e}")
                continue
            except KeyboardInterrupt:
                print("\n使用默认光谱区域: UVB")
                return ['UVB']

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

        while True:
            try:
                choice = input(f"\n请选择绘图类型 (1-3，默认3): ").strip()
                if not choice:
                    choice = "3"

                choice_num = int(choice)
                if 1 <= choice_num <= 3:
                    self.plot_type = plot_types[choice_num][0]
                    print(f"✓ 已选择: {plot_types[choice_num][1]}")
                    return self.plot_type
                else:
                    print(f"✗ 请输入 1-3 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                print("\n使用默认选择: 绘制两种图")
                self.plot_type = "both"
                return self.plot_type

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

        while True:
            try:
                choice = input(f"\n请选择误差类型 (1-3，默认1): ").strip()
                if not choice:
                    choice = "1"

                choice_num = int(choice)
                if 1 <= choice_num <= 3:
                    self.error_type = error_types[choice_num][0]
                    print(f"✓ 已选择: {error_types[choice_num][1]}")
                    return self.error_type
                else:
                    print(f"✗ 请输入 1-3 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                self.error_type = "sem"
                return self.error_type

    def select_plot_method(self):
        """选择绘图方法"""
        if self.plot_type == "latitudinal":
            self.plot_method = "high_res_grid"
            return self.plot_method

        methods = {
            1: ("scatter", "散点图 - 直接显示原始数据点（适合大数据，无采样）"),
            2: ("high_res_grid", "高分辨率网格 - 0.5度网格（推荐）"),
            3: ("interpolation", "插值网格 - 平滑插值（最美观，超过20万点时会采样）"),
            4: ("original_grid", "原始2度网格 - 快速预览（最快）")
        }

        print("\n" + "=" * 60)
        print("选择全球分布图的绘图方法:")
        print("=" * 60)
        for num, (method, desc) in methods.items():
            print(f"{num}. {desc}")

        while True:
            try:
                choice = input(f"\n请选择绘图方法 (1-4，默认2): ").strip()
                if not choice:
                    choice = "2"

                choice_num = int(choice)
                if 1 <= choice_num <= 4:
                    self.plot_method = methods[choice_num][0]
                    print(f"✓ 已选择: {methods[choice_num][1]}")
                    return self.plot_method
                else:
                    print(f"✗ 请输入 1-4 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                self.plot_method = "high_res_grid"
                return self.plot_method

    def select_colormap(self):
        """选择配色方案"""
        print("\n" + "=" * 70)
        print("🎨 专业配色方案选择")
        print("=" * 70)
        print("🔥 高对比度配色（强烈推荐）:")
        print("-" * 60)
        for i in range(1, 9):
            _, description = self.available_colormaps[i]
            print(f"  {i}. {description}")
        print()
        print("⭐ 经典科学配色:")
        print("-" * 60)
        for i in range(9, 13):
            _, description = self.available_colormaps[i]
            print(f" {i}. {description}")

        while True:
            try:
                choice = input(f"\n请选择配色方案 (1-12，默认1): ").strip()
                if not choice:
                    choice = "1"

                choice_num = int(choice)
                if 1 <= choice_num <= 12:
                    colormap, description = self.available_colormaps[choice_num]
                    self.selected_colormap = colormap
                    print(f"✓ 已选择: {description}")
                    return colormap
                else:
                    print(f"✗ 请输入 1-12 之间的数字")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                self.selected_colormap = 'viridis'
                return 'viridis'

    def select_color_scale_mode(self):
        """选择颜色刻度模式"""
        print("\n" + "=" * 50)
        print("选择颜色刻度模式:")
        print("=" * 50)
        print("1. 自动调整 - 根据每个图的数据范围自动调整")
        print("2. 手动设置 - 为每种光谱区域设置统一的上下限")

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
                self.color_scale_mode = "auto"
                return

    def set_manual_color_limits(self):
        """设置手动颜色范围"""
        variables = ['UVB', 'UVA', 'BLUE']

        for var in variables:
            color_config = self.get_color_config(var)
            print(f"\n设置 {var} 的颜色范围:")
            while True:
                try:
                    min_val = float(input(f"  {var} 最小值 (mW/m²): "))
                    max_val = float(input(f"  {var} 最大值 (mW/m²): "))
                    if min_val >= max_val:
                        print("  ✗ 最小值必须小于最大值")
                        continue
                    self.color_limits[var] = (min_val, max_val)
                    print(f"  ✓ {var} 范围设置为: {min_val} - {max_val} mW/m²")
                    break
                except ValueError:
                    print("  ✗ 请输入有效的数字")

    def set_chunk_size(self):
        """设置分块大小"""
        print("\n" + "=" * 50)
        print("设置分块处理参数:")
        print("=" * 50)
        print("推荐分块大小:")
        print("- 内存 8GB 以下: 50,000 行")
        print("- 内存 16GB: 100,000 行（默认）")
        print("- 内存 32GB 以上: 200,000 行")
        print(f"当前设置: {self.chunk_size:,} 行")

        while True:
            try:
                choice = input(f"\n请输入分块大小 (建议50000-200000，默认{self.chunk_size}): ").strip()
                if not choice:
                    break

                chunk_size = int(choice)
                if 10000 <= chunk_size <= 500000:
                    self.chunk_size = chunk_size
                    print(f"✓ 分块大小设置为: {self.chunk_size:,} 行")
                    break
                else:
                    print("✗ 分块大小应在 10,000 - 500,000 之间")

            except ValueError:
                print("✗ 请输入有效的数字")
            except KeyboardInterrupt:
                break

    def clear_memory(self):
        """清理内存"""
        plt.clf()
        plt.close('all')
        gc.collect()

    def run(self):
        """运行主程序"""
        print("=== 分块海洋光照强度可视化工具 ===")
        print("优化特性:")
        print("- 🚀 分块处理大文件，避免内存溢出")
        print("- 📊 支持处理GB级别的数据文件")
        print("- 🎨 12种专业配色方案")
        print("- 📈 自动光谱积分计算")
        print("- 🗺️ 全球分布图与纬度均值图")
        print("- 💾 智能内存管理")
        print("- 🌐 经纬度正负值显示（不显示NSWE）")
        print()

        # 1. 选择输入文件夹
        if not self.select_input_folder():
            return

        # 2. 选择输出文件夹
        if not self.select_output_folder():
            return

        # 3. 设置分块大小
        self.set_chunk_size()

        # 4. 获取文件信息
        print(f"\n分析第一个文件 '{os.path.basename(self.csv_files[0])}' 的结构...")
        file_info = self.get_file_info(self.csv_files[0])
        if file_info is None:
            return

        print(f"  文件总行数: {file_info['total_rows']:,}")
        print(f"  预计分块数: {file_info['total_rows'] // self.chunk_size + 1}")
        print(f"  波长范围: {min(file_info['wavelengths'])}nm - {max(file_info['wavelengths'])}nm")
        print(f"  波长数据列: {len(file_info['wavelength_columns'])}")

        # 5. 选择参数
        self.select_plot_type()

        if self.plot_type in ["latitudinal", "both"]:
            self.select_error_type()

        self.select_colormap()

        if self.plot_type in ["global", "both"]:
            self.select_plot_method()

        self.select_color_scale_mode()

        variables = self.select_variables()
        depths = self.select_depths(file_info)

        if not depths:
            print("未选择深度，程序退出")
            return

        # 6. 开始分块处理
        print(f"\n开始分块处理 {len(self.csv_files)} 个文件...")

        if self.plot_type == "both":
            total_images = len(self.csv_files) * len(variables) * len(depths) * 2
        else:
            total_images = len(self.csv_files) * len(variables) * len(depths)

        print(f"预计生成 {total_images} 个图像")
        print(f"使用分块大小: {self.chunk_size:,} 行")

        for i, csv_file in enumerate(self.csv_files, 1):
            print(f"\n处理进度: {i}/{len(self.csv_files)}")
            try:
                self.process_single_file_chunked(csv_file, depths, variables)
            except Exception as e:
                print(f"处理文件 {csv_file} 时出错: {e}")
                continue

        print(f"\n{'=' * 60}")
        print("分块处理完成!")
        print(f"所有图像已保存到: {self.output_folder}")
        print(f"配置总结:")
        print(f"  绘图类型: {self.plot_type}")
        print(f"  配色方案: {self.selected_colormap}")
        print(f"  分块大小: {self.chunk_size:,} 行")
        if self.plot_type in ["global", "both"]:
            print(f"  全球图方法: {self.plot_method}")
        if self.plot_type in ["latitudinal", "both"]:
            print(f"  误差类型: {self.error_type}")
        print(f"  经纬度标签: 正负值显示（无NSWE）")
        print(f"{'=' * 60}")


def main():
    """主函数"""
    try:
        visualizer = ChunkedOceanLightVisualizer()
        visualizer.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按回车键退出...")


if __name__ == "__main__":
    main()