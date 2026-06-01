import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import box, Point
import geopandas as gpd
import matplotlib.pyplot as plt
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from threading import Thread
import time
import glob
import re


class TifResamplerApp:
    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        self.root.title("TIF文件重采样工具(GEE兼容)")
        self.root.geometry("600x550")  # 增加窗口高度，为按钮提供更多空间
        self.root.resizable(True, True)

        # 设置输入文件夹和输出目录
        self.input_dir = None
        self.output_dir = None

        # 创建界面
        self.create_widgets()

    def create_widgets(self):
        """创建GUI界面元素"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(main_frame, text="TIF文件重采样工具(GEE兼容)", font=("Arial", 14))
        title_label.pack(pady=10)

        # 文件选择框架
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.pack(fill=tk.X, pady=10)

        # 输入文件夹选择
        input_frame = ttk.Frame(file_frame)
        input_frame.pack(fill=tk.X, pady=5)

        input_label = ttk.Label(input_frame, text="输入文件夹:")
        input_label.pack(side=tk.LEFT)

        self.input_entry = ttk.Entry(input_frame, width=40)
        self.input_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        input_button = ttk.Button(input_frame, text="浏览...", command=self.browse_input_dir)
        input_button.pack(side=tk.LEFT)

        # 输出目录选择
        output_frame = ttk.Frame(file_frame)
        output_frame.pack(fill=tk.X, pady=5)

        output_label = ttk.Label(output_frame, text="输出目录:")
        output_label.pack(side=tk.LEFT)

        self.output_entry = ttk.Entry(output_frame, width=40)
        self.output_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        output_button = ttk.Button(output_frame, text="浏览...", command=self.browse_output)
        output_button.pack(side=tk.LEFT)

        # 高级设置框架
        advanced_frame = ttk.LabelFrame(main_frame, text="高级设置", padding="10")
        advanced_frame.pack(fill=tk.X, pady=5)

        # 自定义网格选项
        self.use_custom_grid_var = tk.BooleanVar(value=True)
        custom_grid_check = ttk.Checkbutton(
            advanced_frame,
            text="使用GEE兼容网格",
            variable=self.use_custom_grid_var
        )
        custom_grid_check.pack(anchor=tk.W)

        # 进度显示
        self.progress_frame = ttk.Frame(main_frame)
        self.progress_frame.pack(fill=tk.X, pady=5)

        self.progress_label = ttk.Label(self.progress_frame, text="进度: ")
        self.progress_label.pack(side=tk.LEFT)

        self.progress_bar = ttk.Progressbar(self.progress_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 日志框架 - 减小高度以便为按钮留出空间
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # 创建文本框和滚动条的容器
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_container, wrap=tk.WORD, height=8)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        scrollbar = ttk.Scrollbar(log_container, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 按钮框架 - 使用单独的框架，并确保正确显示
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10, padx=10, after=log_frame)  # 放在日志框架之后，并增加内边距

        self.start_button = ttk.Button(button_frame, text="开始处理", command=self.start_processing)
        self.start_button.pack(side=tk.LEFT, padx=5)

        exit_button = ttk.Button(button_frame, text="退出", command=self.root.destroy)
        exit_button.pack(side=tk.RIGHT, padx=5)

    def browse_input_dir(self):
        """浏览并选择输入文件夹"""
        dirname = filedialog.askdirectory(title="选择包含TIF文件的文件夹")
        if dirname:
            self.input_dir = dirname
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, dirname)
            self.log("已选择输入文件夹: " + dirname)

            # 统计TIF文件数量
            tif_files = self.get_tif_files(dirname)
            self.log(f"文件夹中包含 {len(tif_files)} 个TIF文件")

    def browse_output(self):
        """浏览并选择输出目录"""
        dirname = filedialog.askdirectory(title="选择输出目录")
        if dirname:
            self.output_dir = dirname
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, dirname)
            self.log("已选择输出目录: " + dirname)

    def get_tif_files(self, directory):
        """获取目录中所有TIF文件的路径"""
        patterns = ['*.tif', '*.tiff']
        tif_files = []
        for pattern in patterns:
            tif_files.extend(glob.glob(os.path.join(directory, pattern)))
        return tif_files

    def log(self, message):
        """添加日志消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)  # 滚动到最新消息

    def extract_date_from_filename(self, filename):
        """从文件名中提取年份和月份"""
        # 匹配格式如 20220101-20220131
        pattern = r'(\d{4})(\d{2})(\d{2})-(\d{4})(\d{2})(\d{2})'
        match = re.search(pattern, filename)

        if match:
            # 提取第一个日期的年份和月份（即开始日期）
            year = match.group(1)
            month = match.group(2).lstrip('0')  # 去掉前导零
            return year, month

        # 如果没有匹配到，返回默认值
        return None, None

    def start_processing(self):
        """开始处理TIF文件"""
        # 检查输入
        if not self.input_dir:
            messagebox.showerror("错误", "请选择输入文件夹")
            return

        if not self.output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return

        # 获取TIF文件列表
        tif_files = self.get_tif_files(self.input_dir)

        if not tif_files:
            messagebox.showerror("错误", "选定的文件夹中没有TIF文件")
            return

        # 禁用开始按钮
        self.start_button.config(state=tk.DISABLED)

        # 重置进度条
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(tif_files)

        # 在新线程中运行处理过程
        thread = Thread(target=self.process_multiple_tifs, args=(tif_files,))
        thread.daemon = True
        thread.start()

    def process_multiple_tifs(self, tif_files):
        """处理多个TIF文件"""
        try:
            self.log(f"开始处理 {len(tif_files)} 个TIF文件...")

            # 处理开始时间
            total_start_time = time.time()

            # 获取参数
            use_custom_grid = self.use_custom_grid_var.get()

            # 处理每个文件
            for i, tif_path in enumerate(tif_files):
                try:
                    # 更新进度
                    self.progress_bar['value'] = i
                    self.progress_label.config(text=f"进度: {i + 1}/{len(tif_files)}")

                    # 获取文件名
                    tif_basename = os.path.basename(tif_path)
                    self.log(f"\n正在处理 ({i + 1}/{len(tif_files)}): {tif_basename}")

                    # 从文件名中提取年份和月份
                    year, month = self.extract_date_from_filename(tif_basename)
                    if year and month:
                        self.log(f"已提取日期信息: 年份={year}, 月份={month}")
                    else:
                        self.log(f"警告: 无法从文件名中提取日期信息")
                        year, month = "", ""

                    # 构建输出文件路径
                    output_basename = os.path.splitext(tif_basename)[0] + "_gee_grid.csv"
                    output_csv_path = os.path.join(self.output_dir, output_basename)
                    output_png_path = os.path.join(self.output_dir,
                                                   os.path.splitext(tif_basename)[0] + "_gee_grid.png")

                    # 处理开始时间
                    file_start_time = time.time()

                    # 开始处理
                    if use_custom_grid:
                        self.log("使用GEE兼容网格处理...")
                        result = self.resample_tif_with_exact_gee_grid(tif_path, output_csv_path)
                    else:
                        self.log("使用标准10度网格处理...")
                        result = self.resample_tif_to_grid_average(tif_path, output_csv_path, 10)

                    # 添加年份和月份列
                    result['year'] = year
                    result['month'] = month

                    # 重命名列并重新保存结果
                    result.rename(columns={'effective_radius': 'cld_reff_dcomp'}, inplace=True)
                    result.to_csv(output_csv_path, index=False)

                    # 生成可视化
                    self.log("正在生成可视化...")
                    self.plot_results(result, output_png_path, tif_basename)

                    # 计算处理时间
                    file_elapsed_time = time.time() - file_start_time

                    self.log(f"文件处理完成，共提取了 {len(result)} 个网格的数据")
                    self.log(f"处理时间: {file_elapsed_time:.2f} 秒")
                    self.log(f"结果已保存到: {output_csv_path}")
                    self.log(f"可视化图已保存到: {output_png_path}")

                except Exception as e:
                    self.log(f"处理文件 {tif_basename} 时出错: {str(e)}")

            # 更新最终进度
            self.progress_bar['value'] = len(tif_files)
            self.progress_label.config(text=f"进度: {len(tif_files)}/{len(tif_files)}")

            # 计算总处理时间
            total_elapsed_time = time.time() - total_start_time

            self.log(f"\n所有文件处理完成!")
            self.log(f"总处理时间: {total_elapsed_time:.2f} 秒")

            # 完成后启用开始按钮
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

            # 提示完成
            messagebox.showinfo("完成",
                                f"所有文件处理完成!\n共处理了 {len(tif_files)} 个TIF文件。\n结果已保存到: {self.output_dir}")

        except Exception as e:
            self.log(f"批处理过程中出错: {str(e)}")
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            messagebox.showerror("错误", f"处理过程中出错:\n{str(e)}")

    def create_exact_gee_grid(self):
        """创建与GEE完全一致的网格点"""
        # GEE生成的纬度值
        latitudes = [-83.3613, -74.5122, -64.771, -54.8935, -44.9622, -34.9992, -25.0146,
                     -15.0148, -5.00596, 5.005959, 15.01482, 25.01458, 34.99924, 44.96216,
                     54.89354, 64.77099, 74.51225, 83.36127]

        # 经度范围，从-175到175，步长为10度
        longitudes = []
        for lon in range(-175, 185, 10):
            # 确保不超过180
            if lon > 180:
                lon = 180
            longitudes.append(lon)

        # 创建网格点列表
        grid_points = []

        # 遍历所有经度值，为每个经度生成完整的纬度列表
        for lon in longitudes:
            for lat in latitudes:
                grid_points.append({
                    'geometry': Point(lon, lat),
                    'longitude': lon,
                    'latitude': lat
                })

        # 转换为GeoDataFrame
        grid_gdf = gpd.GeoDataFrame(grid_points, geometry='geometry')
        grid_gdf.crs = "EPSG:4326"  # 设置坐标参考系统为WGS84

        return grid_gdf

    def resample_tif_with_exact_gee_grid(self, tif_path, output_csv_path):
        """使用与GEE完全一致的网格点对TIF文件进行重采样"""
        # 打开TIF文件
        with rasterio.open(tif_path) as src:
            # 获取TIF文件的元数据
            meta = src.meta
            bounds = src.bounds

            self.log(f"栅格文件信息:")
            self.log(f"范围: {bounds}")
            self.log(f"CRS: {src.crs}")
            self.log(f"形状: {src.shape}")
            self.log(f"分辨率: {src.res}")

            # 读取整个栅格数据
            self.log("正在读取TIF数据...")
            data = src.read(1)
            nodata = src.nodata

            # 创建GEE兼容的网格点
            self.log("正在创建GEE兼容的网格点...")
            grid_gdf = self.create_exact_gee_grid()

            # 为每个点创建10度×10度的网格来计算平均值
            self.log("正在提取网格平均值...")
            radius_values = []

            for idx, point in grid_gdf.iterrows():
                try:
                    # 为当前网格点创建10×10度的网格
                    lon, lat = point.longitude, point.latitude
                    box_geom = box(lon - 5, lat - 5, lon + 5, lat + 5)

                    # 创建掩码
                    geoms = [box_geom]
                    grid_mask = geometry_mask(geoms, out_shape=src.shape, transform=src.transform, invert=True)

                    # 应用掩码获取网格内的所有值
                    masked_data = data.copy()
                    masked_data[~grid_mask] = nodata if nodata is not None else np.nan

                    # 计算平均值，忽略NoData值
                    if nodata is not None:
                        valid_data = masked_data[masked_data != nodata]
                    else:
                        valid_data = masked_data[~np.isnan(masked_data)]

                    if len(valid_data) > 0:
                        grid_mean = np.mean(valid_data)
                    else:
                        grid_mean = np.nan

                    radius_values.append(grid_mean)

                except Exception as e:
                    self.log(f"处理网格点 {lon}, {lat} 时出错: {e}")
                    radius_values.append(np.nan)

                # 每处理50个网格更新一次日志
                if idx % 50 == 0 and idx > 0:
                    self.log(f"已处理 {idx} 个网格点...")

            # 添加到GeoDataFrame
            grid_gdf['effective_radius'] = radius_values

            # 转换为普通DataFrame并保存为CSV
            self.log("正在保存结果...")
            result_df = pd.DataFrame({
                'longitude': grid_gdf['longitude'],
                'latitude': grid_gdf['latitude'],
                'effective_radius': grid_gdf['effective_radius']
            })

            return result_df

    def resample_tif_to_grid_average(self, tif_path, output_csv_path, grid_size=10):
        """将TIF文件按指定的网格大小重新采样，计算每个网格内所有值的平均值"""
        # 打开TIF文件
        with rasterio.open(tif_path) as src:
            # 获取TIF文件的元数据
            meta = src.meta
            bounds = src.bounds

            self.log(f"栅格文件信息:")
            self.log(f"范围: {bounds}")
            self.log(f"CRS: {src.crs}")
            self.log(f"形状: {src.shape}")
            self.log(f"分辨率: {src.res}")

            # 读取整个栅格数据
            self.log("正在读取TIF数据...")
            data = src.read(1)
            nodata = src.nodata

            # 定义全球范围的网格
            min_lon, max_lon = -180, 180
            min_lat, max_lat = -90, 90

            # 创建网格列表
            self.log("正在创建网格...")
            grid_list = []

            # 创建传统的10度×10度网格
            for lon in np.arange(min_lon, max_lon, grid_size):
                for lat in np.arange(min_lat, max_lat, grid_size):
                    # 计算网格中心点
                    center_lon = lon + grid_size / 2
                    center_lat = lat + grid_size / 2

                    # 创建网格几何形状
                    grid_geom = box(lon, lat, lon + grid_size, lat + grid_size)

                    grid_list.append({
                        'geometry': grid_geom,
                        'longitude': center_lon,
                        'latitude': center_lat
                    })

            # 转换为GeoDataFrame
            self.log("正在准备数据...")
            grid_gdf = gpd.GeoDataFrame(grid_list, geometry='geometry')
            grid_gdf.crs = "EPSG:4326"  # 设置坐标参考系统为WGS84

            # 计算每个网格的平均值
            self.log("正在计算网格平均值...")
            mean_values = []

            for idx, row in grid_gdf.iterrows():
                try:
                    # 为当前网格创建掩码
                    geoms = [row.geometry]
                    grid_mask = geometry_mask(geoms, out_shape=src.shape, transform=src.transform, invert=True)

                    # 应用掩码获取网格内的所有值
                    masked_data = data.copy()
                    masked_data[~grid_mask] = nodata if nodata is not None else np.nan

                    # 计算平均值，忽略NoData值
                    if nodata is not None:
                        grid_mean = np.mean(masked_data[masked_data != nodata])
                    else:
                        grid_mean = np.mean(masked_data[~np.isnan(masked_data)])

                    # 处理空网格
                    if np.isnan(grid_mean):
                        mean_values.append(np.nan)
                    else:
                        mean_values.append(grid_mean)

                except Exception as e:
                    self.log(f"处理网格 {row.longitude}, {row.latitude} 时出错: {e}")
                    mean_values.append(np.nan)

                # 每处理50个网格更新一次日志
                if idx % 50 == 0 and idx > 0:
                    self.log(f"已处理 {idx} 个网格...")

            # 添加到GeoDataFrame
            grid_gdf['effective_radius'] = mean_values

            # 转换为普通DataFrame并保存为CSV
            self.log("正在保存结果...")
            result_df = pd.DataFrame({
                'longitude': grid_gdf['longitude'],
                'latitude': grid_gdf['latitude'],
                'effective_radius': grid_gdf['effective_radius']
            })

            return result_df

    def plot_results(self, df, output_png_path, tif_filename):
        """绘制采样结果"""
        # 创建一个全球地图可视化
        plt.figure(figsize=(12, 8))

        # 使用重命名后的列
        if 'cld_reff_dcomp' in df.columns:
            value_column = 'cld_reff_dcomp'
        else:
            value_column = 'effective_radius'

        # 创建散点图，使用颜色表示云有效半径
        scatter = plt.scatter(
            df['longitude'],
            df['latitude'],
            c=df[value_column],
            cmap='viridis',
            s=50,
            alpha=0.7,
            edgecolors='k'
        )

        # 添加颜色条
        cbar = plt.colorbar(scatter)
        cbar.set_label('Cloud Effective Radius')

        # 获取年份和月份
        year = df['year'].iloc[0] if 'year' in df.columns and len(df) > 0 else ''
        month = df['month'].iloc[0] if 'month' in df.columns and len(df) > 0 else ''
        date_str = f"{year}-{month}" if year and month else ""

        # 设置图表属性
        title = f'Global Distribution of Cloud Effective Radius'
        if date_str:
            title += f' ({date_str})'
        plt.title(title)
        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        plt.grid(True, linestyle='--', alpha=0.7)

        # 设置坐标轴范围
        plt.xlim(-180, 180)
        plt.ylim(-90, 90)

        # 保存图表
        plt.tight_layout()
        plt.savefig(output_png_path, dpi=300)
        plt.close()

        self.log(f"已保存可视化图表到 {output_png_path}")


def main():
    root = tk.Tk()
    app = TifResamplerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()