import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import threading
from matplotlib.colors import LinearSegmentedColormap
import gc


class CSVAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV地理数据分析工具")
        self.root.geometry("700x500")
        self.root.resizable(True, True)

        # 创建界面
        self.create_widgets()

        # 数据相关变量
        self.df = None
        self.chunk_size = 100000  # 分块读取的大小，可以调整

    def create_widgets(self):
        # 创建标签框架
        input_frame = ttk.LabelFrame(self.root, text="输入设置")
        input_frame.pack(fill="x", expand="yes", padx=10, pady=10)

        # 文件输入路径
        ttk.Label(input_frame, text="CSV文件路径:").grid(column=0, row=0, padx=10, pady=10, sticky="w")
        self.input_path = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.input_path, width=50).grid(column=1, row=0, padx=10, pady=10,
                                                                            sticky="we")
        ttk.Button(input_frame, text="浏览...", command=self.browse_input_file).grid(column=2, row=0, padx=10, pady=10)

        # 输出路径
        ttk.Label(input_frame, text="输出文件夹路径:").grid(column=0, row=1, padx=10, pady=10, sticky="w")
        self.output_path = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.output_path, width=50).grid(column=1, row=1, padx=10, pady=10,
                                                                             sticky="we")
        ttk.Button(input_frame, text="浏览...", command=self.browse_output_dir).grid(column=2, row=1, padx=10, pady=10)

        # 参数设置框架
        param_frame = ttk.LabelFrame(self.root, text="参数设置")
        param_frame.pack(fill="x", expand="yes", padx=10, pady=10)

        # 采样率
        ttk.Label(param_frame, text="采样率 (0.0-1.0):").grid(column=0, row=0, padx=10, pady=10, sticky="w")
        self.sample_rate = tk.DoubleVar(value=0.1)
        ttk.Entry(param_frame, textvariable=self.sample_rate, width=10).grid(column=1, row=0, padx=10, pady=10,
                                                                             sticky="w")

        # 经度列名
        ttk.Label(param_frame, text="经度列名:").grid(column=0, row=1, padx=10, pady=10, sticky="w")
        self.longitude_col = tk.StringVar(value="longitude")
        ttk.Entry(param_frame, textvariable=self.longitude_col, width=20).grid(column=1, row=1, padx=10, pady=10,
                                                                               sticky="w")

        # 纬度列名
        ttk.Label(param_frame, text="纬度列名:").grid(column=2, row=1, padx=10, pady=10, sticky="w")
        self.latitude_col = tk.StringVar(value="latitude")
        ttk.Entry(param_frame, textvariable=self.latitude_col, width=20).grid(column=3, row=1, padx=10, pady=10,
                                                                              sticky="w")

        # 点大小
        ttk.Label(param_frame, text="点大小:").grid(column=0, row=2, padx=10, pady=10, sticky="w")
        self.point_size = tk.DoubleVar(value=0.1)
        ttk.Entry(param_frame, textvariable=self.point_size, width=10).grid(column=1, row=2, padx=10, pady=10,
                                                                            sticky="w")

        # 点透明度
        ttk.Label(param_frame, text="点透明度:").grid(column=2, row=2, padx=10, pady=10, sticky="w")
        self.point_alpha = tk.DoubleVar(value=0.5)
        ttk.Entry(param_frame, textvariable=self.point_alpha, width=10).grid(column=3, row=2, padx=10, pady=10,
                                                                             sticky="w")

        # 操作按钮框架
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", expand="yes", padx=10, pady=10)

        # 分析按钮
        ttk.Button(button_frame, text="分析CSV数据", command=self.start_analysis).pack(side=tk.LEFT, padx=10, pady=10)

        # 绘图按钮
        ttk.Button(button_frame, text="绘制地理分布图", command=self.start_plotting).pack(side=tk.LEFT, padx=10,
                                                                                          pady=10)

        # 状态框架
        status_frame = ttk.LabelFrame(self.root, text="状态")
        status_frame.pack(fill="both", expand="yes", padx=10, pady=10)

        # 进度条
        self.progress = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill="x", padx=10, pady=10)

        # 状态文本
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_var).pack(padx=10, pady=10)

        # 状态行（不显示内存使用）
        self.memory_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.memory_var).pack(padx=10, pady=5)

    def browse_input_file(self):
        filename = filedialog.askopenfilename(
            title="选择CSV文件",
            filetypes=(("CSV文件", "*.csv"), ("所有文件", "*.*"))
        )
        if filename:
            self.input_path.set(filename)

    def browse_output_dir(self):
        directory = filedialog.askdirectory(title="选择输出文件夹")
        if directory:
            self.output_path.set(directory)

    def start_analysis(self):
        # 在新线程中启动分析，避免界面冻结
        threading.Thread(target=self.analyze_csv, daemon=True).start()

    def start_plotting(self):
        # 在新线程中启动绘图，避免界面冻结
        threading.Thread(target=self.plot_geo_distribution, daemon=True).start()

    def analyze_csv(self):
        input_file = self.input_path.get()
        output_dir = self.output_path.get()

        if not input_file or not os.path.isfile(input_file):
            messagebox.showerror("错误", "请选择有效的CSV文件")
            return

        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showerror("错误", "请选择有效的输出文件夹")
            return

        try:
            self.status_var.set("正在分析CSV文件...")
            self.progress["value"] = 0
            self.root.update()

            start_time = time.time()

            # 首先获取文件的总行数（估计值）
            with open(input_file, 'r') as f:
                est_line_count = sum(1 for _ in f)

            # 使用pandas读取文件头以获取列名
            header_df = pd.read_csv(input_file, nrows=0)
            column_names = header_df.columns.tolist()

            # 收集每列的统计信息
            stats = {col: {"count": 0, "null_count": 0, "min": None, "max": None} for col in column_names}

            # 用于特定列的值分布统计（可选）
            value_counts = {}

            # 分块处理大文件
            chunk_idx = 0
            processed_rows = 0

            for chunk in pd.read_csv(input_file, chunksize=self.chunk_size):
                chunk_idx += 1
                rows_in_chunk = len(chunk)
                processed_rows += rows_in_chunk

                # 更新进度
                progress_pct = min(100, int(processed_rows / est_line_count * 100))
                self.progress["value"] = progress_pct
                self.status_var.set(f"处理中... 已处理 {processed_rows:,} 行 ({progress_pct}%)")
                self.root.update()

                # 更新统计信息
                for col in column_names:
                    if col in chunk.columns:
                        # 计数
                        stats[col]["count"] += rows_in_chunk
                        stats[col]["null_count"] += chunk[col].isna().sum()

                        # 对数值列计算最小值和最大值
                        if pd.api.types.is_numeric_dtype(chunk[col]):
                            non_null = chunk[col].dropna()
                            if len(non_null) > 0:
                                col_min = non_null.min()
                                col_max = non_null.max()

                                if stats[col]["min"] is None or col_min < stats[col]["min"]:
                                    stats[col]["min"] = col_min

                                if stats[col]["max"] is None or col_max > stats[col]["max"]:
                                    stats[col]["max"] = col_max

                # 释放内存
                del chunk
                gc.collect()

            # 分析结束后，保存统计结果到文件
            stats_file = os.path.join(output_dir, "csv_stats.txt")
            with open(stats_file, 'w', encoding='utf-8') as f:
                f.write(f"CSV文件分析报告: {os.path.basename(input_file)}\n")
                f.write(f"总行数: {processed_rows:,}\n")
                f.write(f"总列数: {len(column_names)}\n\n")

                f.write("各列统计信息:\n")
                f.write("-" * 80 + "\n")
                for col in column_names:
                    f.write(f"列名: {col}\n")
                    f.write(f"  - 数据量: {stats[col]['count']:,}\n")
                    f.write(f"  - 空值数: {stats[col]['null_count']:,}\n")
                    f.write(f"  - 空值比例: {stats[col]['null_count'] / stats[col]['count'] * 100:.2f}%\n")

                    if stats[col]["min"] is not None:
                        f.write(f"  - 最小值: {stats[col]['min']}\n")
                    if stats[col]["max"] is not None:
                        f.write(f"  - 最大值: {stats[col]['max']}\n")
                    f.write("-" * 80 + "\n")

            end_time = time.time()
            elapsed_time = end_time - start_time

            self.status_var.set(f"分析完成！用时: {elapsed_time:.2f} 秒")
            messagebox.showinfo("完成", f"CSV分析已完成，统计结果已保存至:\n{stats_file}")

        except Exception as e:
            self.status_var.set(f"错误: {str(e)}")
            messagebox.showerror("错误", f"处理CSV时发生错误:\n{str(e)}")

    def plot_geo_distribution(self):
        input_file = self.input_path.get()
        output_dir = self.output_path.get()
        longitude_col = self.longitude_col.get()
        latitude_col = self.latitude_col.get()
        sample_rate = self.sample_rate.get()
        point_size = self.point_size.get()
        point_alpha = self.point_alpha.get()

        if not input_file or not os.path.isfile(input_file):
            messagebox.showerror("错误", "请选择有效的CSV文件")
            return

        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showerror("错误", "请选择有效的输出文件夹")
            return

        try:
            self.status_var.set("准备绘制地理分布图...")
            self.progress["value"] = 0
            self.root.update()

            start_time = time.time()

            # 确保列名存在于文件中
            header_df = pd.read_csv(input_file, nrows=0)
            if longitude_col not in header_df.columns or latitude_col not in header_df.columns:
                messagebox.showerror("错误", f"无法找到列: {longitude_col} 或 {latitude_col}")
                self.status_var.set("绘图失败：找不到经纬度列")
                return

            # 采样数据以提高绘图速度
            self.status_var.set(f"正在读取并采样数据（采样率: {sample_rate}）...")
            self.root.update()

            # 计算总行数以估计要读取的行
            with open(input_file, 'r') as f:
                est_line_count = sum(1 for _ in f)

            # 计算采样间隔（每n行取1行）
            if sample_rate >= 1.0:
                sample_interval = 1  # 使用所有数据
            else:
                sample_interval = int(1 / sample_rate)

            # 准备用于绘图的数据
            longitudes = []
            latitudes = []

            # 使用迭代器按行读取CSV而不是一次性加载全部到内存
            chunk_size = self.chunk_size
            total_rows_processed = 0

            for chunk in pd.read_csv(input_file, chunksize=chunk_size, usecols=[longitude_col, latitude_col]):
                # 应用采样
                sampled_chunk = chunk.iloc[::sample_interval]

                # 过滤有效的经纬度
                valid_data = sampled_chunk.dropna(subset=[longitude_col, latitude_col])
                valid_data = valid_data[(valid_data[longitude_col] >= -180) &
                                        (valid_data[longitude_col] <= 180) &
                                        (valid_data[latitude_col] >= -90) &
                                        (valid_data[latitude_col] <= 90)]

                longitudes.extend(valid_data[longitude_col].tolist())
                latitudes.extend(valid_data[latitude_col].tolist())

                # 更新进度
                total_rows_processed += len(chunk)
                progress_pct = min(100, int(total_rows_processed / est_line_count * 100))
                self.progress["value"] = progress_pct
                self.status_var.set(f"读取数据中... {progress_pct}%")
                self.root.update()

                # 释放内存
                del chunk, sampled_chunk, valid_data
                gc.collect()

            # 显示采样后的数据点数量
            data_points = len(longitudes)
            self.status_var.set(f"绘制地理分布图... (数据点: {data_points:,})")
            self.root.update()

            if data_points == 0:
                messagebox.showwarning("警告", "没有有效的地理坐标数据可以绘图")
                self.status_var.set("绘图失败：无有效数据")
                return

            # 创建一个更好看的颜色映射
            colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
            cmap = LinearSegmentedColormap.from_list("custom_cmap", colors, N=256)

            # 创建绘图
            plt.figure(figsize=(12, 8), dpi=100)

            # 绘制散点图
            plt.scatter(longitudes, latitudes, s=point_size, alpha=point_alpha,
                        c=np.random.rand(len(longitudes)), cmap=cmap, edgecolors='none')

            plt.title(f'地理坐标分布图 - 采样 {sample_rate * 100:.1f}% 数据点: {data_points:,}')
            plt.xlabel('经度')
            plt.ylabel('纬度')
            plt.grid(True, linestyle='--', alpha=0.7)

            # 坐标轴范围
            plt.xlim(-180, 180)
            plt.ylim(-90, 90)

            # 添加颜色条
            plt.colorbar(label='点密度')

            # 保存图片
            output_file = os.path.join(output_dir, "geo_distribution.png")
            plt.savefig(output_file, bbox_inches='tight')

            # 为了更好的密度可视化，创建热力图
            self.status_var.set("创建密度热力图...")
            self.root.update()

            plt.figure(figsize=(12, 8), dpi=100)

            # 使用hexbin绘制六边形密度图
            hb = plt.hexbin(longitudes, latitudes, gridsize=100, cmap='viridis',
                            bins='log', mincnt=1)

            plt.title(f'地理坐标密度热力图 - 采样 {sample_rate * 100:.1f}% 数据点: {data_points:,}')
            plt.xlabel('经度')
            plt.ylabel('纬度')
            plt.grid(True, linestyle='--', alpha=0.7)

            # 坐标轴范围
            plt.xlim(-180, 180)
            plt.ylim(-90, 90)

            # 添加颜色条
            cb = plt.colorbar(label='日志计数')

            # 保存热力图
            heatmap_file = os.path.join(output_dir, "geo_heatmap.png")
            plt.savefig(heatmap_file, bbox_inches='tight')

            # 关闭图形以释放内存
            plt.close('all')

            end_time = time.time()
            elapsed_time = end_time - start_time

            self.status_var.set(f"绘图完成！用时: {elapsed_time:.2f} 秒")
            messagebox.showinfo("完成", f"分布图已保存至:\n{output_file}\n\n热力图已保存至:\n{heatmap_file}")

        except Exception as e:
            self.status_var.set(f"错误: {str(e)}")
            messagebox.showerror("错误", f"绘制分布图时发生错误:\n{str(e)}")


if __name__ == "__main__":
    # 检查必要的软件包是否已安装
    try:
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError as e:
        print(f"缺少必要的软件包: {str(e)}")
        print("请使用以下命令安装所需软件包:")
        print("pip install pandas numpy matplotlib seaborn")
        exit(1)

    # 启动应用程序
    root = tk.Tk()
    app = CSVAnalyzer(root)
    root.mainloop()