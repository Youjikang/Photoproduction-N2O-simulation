import numpy as np
import pandas as pd
import rasterio
# 移除 import rasterio.sample - 这个模块导致问题
import matplotlib.pyplot as plt
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from threading import Thread
import time
import glob
import re
from datetime import datetime


class TifPointExtractorApp:
    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        self.root.title("TIF文件点数据提取工具")
        self.root.geometry("600x500")  # 增加窗口大小
        self.root.resizable(True, True)

        # 设置输入文件夹和输出目录
        self.input_dir = None
        self.output_dir = None

        # 创建界面
        self.create_widgets()

    def create_widgets(self):
        """创建GUI界面元素"""
        # 主框架 - 使用滚动条以防内容太多
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(main_frame, text="TIF文件点数据提取工具", font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 15))

        # 文件选择框架
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        # 输入文件夹选择
        input_frame = ttk.Frame(file_frame)
        input_frame.pack(fill=tk.X, pady=5)

        input_label = ttk.Label(input_frame, text="输入文件夹:", width=12)
        input_label.pack(side=tk.LEFT)

        self.input_entry = ttk.Entry(input_frame, width=40)
        self.input_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        input_button = ttk.Button(input_frame, text="浏览...", command=self.browse_input_dir)
        input_button.pack(side=tk.LEFT, padx=(5, 0))

        # 输出目录选择
        output_frame = ttk.Frame(file_frame)
        output_frame.pack(fill=tk.X, pady=5)

        output_label = ttk.Label(output_frame, text="输出目录:", width=12)
        output_label.pack(side=tk.LEFT)

        self.output_entry = ttk.Entry(output_frame, width=40)
        self.output_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        output_button = ttk.Button(output_frame, text="浏览...", command=self.browse_output)
        output_button.pack(side=tk.LEFT, padx=(5, 0))

        # 经纬度输入框架
        coord_frame = ttk.LabelFrame(main_frame, text="经纬度设置", padding="10")
        coord_frame.pack(fill=tk.X, pady=(0, 10))

        # 经纬度输入使用网格布局
        ttk.Label(coord_frame, text="经度 (Longitude):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.lon_entry = ttk.Entry(coord_frame, width=20)
        self.lon_entry.grid(row=0, column=1, padx=(10, 0), pady=5, sticky=tk.W)
        self.lon_entry.insert(0, "116.3974")  # 默认值：北京

        ttk.Label(coord_frame, text="纬度 (Latitude):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.lat_entry = ttk.Entry(coord_frame, width=20)
        self.lat_entry.grid(row=1, column=1, padx=(10, 0), pady=5, sticky=tk.W)
        self.lat_entry.insert(0, "39.9042")  # 默认值：北京

        # 进度显示框架
        progress_frame = ttk.LabelFrame(main_frame, text="处理进度", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_label = ttk.Label(progress_frame, text="等待开始...")
        self.progress_label.pack(anchor=tk.W, pady=(0, 5))

        self.progress_bar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        # 按钮框架 - 确保按钮可见
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        # 创建更明显的按钮
        self.start_button = ttk.Button(
            button_frame,
            text="🚀 开始提取数据",
            command=self.start_processing,
            style="Accent.TButton"  # 如果可用的话使用强调样式
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10), ipadx=20, ipady=5)

        # 清除日志按钮
        clear_button = ttk.Button(button_frame, text="清除日志", command=self.clear_log)
        clear_button.pack(side=tk.LEFT, padx=(0, 10))

        # 退出按钮
        exit_button = ttk.Button(button_frame, text="退出程序", command=self.root.destroy)
        exit_button.pack(side=tk.RIGHT)

        # 日志框架
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        # 创建文本框和滚动条的容器
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_container, wrap=tk.WORD, height=8, font=("Consolas", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        scrollbar = ttk.Scrollbar(log_container, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 初始化日志
        self.log("🚀 程序已启动，请选择输入文件夹和输出目录")
        self.log("💡 提示：此工具使用像素索引方法提取栅格数据，兼容性更好")

    def clear_log(self):
        """清除日志内容"""
        self.log_text.delete(1.0, tk.END)
        self.log("日志已清除")

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
        patterns = ['*.tif', '*.tiff', '*.TIF', '*.TIFF']  # 添加大写扩展名
        tif_files = []
        for pattern in patterns:
            tif_files.extend(glob.glob(os.path.join(directory, pattern)))
        return sorted(tif_files)  # 排序文件列表

    def log(self, message):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def extract_date_from_filename(self, filename):
        """从文件名中提取年份、月份和日期 - 支持更多格式"""
        # 针对各种日期格式的正则表达式
        patterns = [
            r'(\d{4})(\d{2})(\d{2})-(\d{4})(\d{2})(\d{2})',  # 20220701-20220701 (日期范围)
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2022-7-1 或 2022-07-01
            r'(\d{4})(\d{2})(\d{2})',  # 20220701
            r'(\d{4})-(\d{2})-(\d{2})',  # 2022-01-01
            r'(\d{4})_(\d{2})_(\d{2})',  # 2022_01_01
            r'(\d{4})\.(\d{2})\.(\d{2})',  # 2022.01.01
        ]

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                if len(match.groups()) >= 6:  # 日期范围格式 (取起始日期)
                    year = match.group(1)
                    month = match.group(2).lstrip('0') or '1'
                    day = match.group(3).lstrip('0') or '1'
                elif len(match.groups()) >= 3:  # 单日期格式
                    year = match.group(1)
                    month = match.group(2).lstrip('0') or '1'
                    day = match.group(3).lstrip('0') or '1'
                else:
                    continue

                return year, month, day

        # 如果没有匹配到，返回默认值
        return None, None, None

    def start_processing(self):
        """开始处理TIF文件"""
        # 检查输入
        if not self.input_dir:
            messagebox.showerror("错误", "请先选择输入文件夹！")
            return

        if not self.output_dir:
            messagebox.showerror("错误", "请先选择输出目录！")
            return

        # 验证经纬度输入
        try:
            longitude = float(self.lon_entry.get())
            latitude = float(self.lat_entry.get())

            if not (-180 <= longitude <= 180):
                messagebox.showerror("错误", "经度必须在-180到180之间")
                return
            if not (-90 <= latitude <= 90):
                messagebox.showerror("错误", "纬度必须在-90到90之间")
                return

        except ValueError:
            messagebox.showerror("错误", "请输入有效的经纬度数值")
            return

        # 获取TIF文件列表
        tif_files = self.get_tif_files(self.input_dir)

        if not tif_files:
            messagebox.showerror("错误", "选定的文件夹中没有找到TIF文件")
            return

        # 禁用开始按钮并更新文本
        self.start_button.config(state=tk.DISABLED, text="正在处理...")

        # 重置进度条
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(tif_files)
        self.progress_label.config(text="准备开始处理...")

        # 在新线程中运行处理过程
        thread = Thread(target=self.process_multiple_tifs, args=(tif_files, longitude, latitude))
        thread.daemon = True
        thread.start()

    def process_multiple_tifs(self, tif_files, longitude, latitude):
        """处理多个TIF文件，提取指定点的数据"""
        try:
            self.log(f"开始处理 {len(tif_files)} 个TIF文件...")
            self.log(f"目标坐标: 经度={longitude}, 纬度={latitude}")

            # 处理开始时间
            total_start_time = time.time()

            # 存储所有结果
            all_results = []

            # 处理每个文件
            for i, tif_path in enumerate(tif_files):
                try:
                    # 更新进度
                    self.progress_bar['value'] = i
                    self.progress_label.config(text=f"进度: {i + 1}/{len(tif_files)}")

                    # 获取文件名
                    tif_basename = os.path.basename(tif_path)
                    self.log(f"正在处理 ({i + 1}/{len(tif_files)}): {tif_basename}")

                    # 从文件名中提取年份、月份和日期
                    year, month, day = self.extract_date_from_filename(tif_basename)
                    if year and month and day:
                        self.log(f"提取日期: {year}年{month}月{day}日")
                    else:
                        self.log(f"警告: 无法从文件名中提取日期信息")
                        year, month, day = "", "", ""

                    # 提取点数据
                    point_value = self.extract_point_value(tif_path, longitude, latitude)

                    # 保存结果
                    result = {
                        'filename': tif_basename,
                        'year': year,
                        'month': month,
                        'day': day,
                        'longitude': longitude,
                        'latitude': latitude,
                        'value': point_value
                    }
                    all_results.append(result)

                    if point_value is not None and not np.isnan(point_value):
                        self.log(f"提取值: {point_value:.6f}")
                    else:
                        self.log(f"该点无数据或数据为NoData")

                except Exception as e:
                    self.log(f"处理文件 {tif_basename} 时出错: {str(e)}")
                    # 即使出错也要记录结果
                    all_results.append({
                        'filename': os.path.basename(tif_path),
                        'year': '',
                        'month': '',
                        'day': '',
                        'longitude': longitude,
                        'latitude': latitude,
                        'value': np.nan
                    })

            # 更新最终进度
            self.progress_bar['value'] = len(tif_files)
            self.progress_label.config(text=f"处理完成: {len(tif_files)}/{len(tif_files)}")

            # 保存结果到CSV
            output_path = self.save_results(all_results, longitude, latitude)

            # 计算总处理时间
            total_elapsed_time = time.time() - total_start_time
            self.log(f"所有文件处理完成! 总时间: {total_elapsed_time:.2f} 秒")

            # 完成后启用开始按钮并恢复文本
            self.root.after(0, lambda: [
                self.start_button.config(state=tk.NORMAL, text="🚀 开始提取数据"),
                self.progress_label.config(text="处理完成!")
            ])

            # 提示完成
            if output_path:
                messagebox.showinfo("完成",
                                    f"提取完成!\n共处理 {len(tif_files)} 个文件\n结果已保存到:\n{output_path}")
            else:
                messagebox.showwarning("警告", "处理完成，但保存结果时可能出现问题，请检查日志")

        except Exception as e:
            self.log(f"批处理过程中出错: {str(e)}")
            self.root.after(0, lambda: [
                self.start_button.config(state=tk.NORMAL, text="🚀 开始提取数据"),
                self.progress_label.config(text="处理出错!")
            ])
            messagebox.showerror("错误", f"处理过程中出错:\n{str(e)}")

    def extract_point_value(self, tif_path, longitude, latitude):
        """从TIF文件中提取指定点的数值 - 修复版本"""
        try:
            with rasterio.open(tif_path) as src:
                # 检查点是否在栅格范围内
                if not (src.bounds.left <= longitude <= src.bounds.right and
                        src.bounds.bottom <= latitude <= src.bounds.top):
                    self.log(f"警告: 点 ({longitude}, {latitude}) 不在栅格范围内")
                    return np.nan

                # 方法1: 使用像素索引方法（最稳定可靠）
                try:
                    # 将地理坐标转换为像素坐标
                    row, col = src.index(longitude, latitude)

                    # 检查像素坐标是否在有效范围内
                    if 0 <= row < src.height and 0 <= col < src.width:
                        # 读取数据
                        data = src.read(1)
                        value = data[row, col]

                        # 检查是否为NoData
                        if src.nodata is not None and value == src.nodata:
                            return np.nan
                        elif np.isnan(value):
                            return np.nan
                        else:
                            return float(value)
                    else:
                        self.log(f"像素坐标超出范围: 行={row}, 列={col}")
                        return np.nan

                except Exception as pixel_error:
                    self.log(f"像素索引方法失败: {str(pixel_error)}")
                    return np.nan

        except Exception as e:
            self.log(f"提取点值时出错: {str(e)}")
            return np.nan

    def save_results(self, results, longitude, latitude):
        """保存结果到CSV文件"""
        try:
            # 创建DataFrame
            df = pd.DataFrame(results)

            # 生成输出文件名，包含时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"point_data_lon{longitude}_lat{latitude}_{timestamp}.csv"
            output_path = os.path.join(self.output_dir, output_filename)

            # 保存为CSV
            df.to_csv(output_path, index=False, encoding='utf-8-sig')  # 使用UTF-8 BOM以支持中文
            self.log(f"结果已保存到: {output_path}")

            # 统计有效数据
            valid_count = df['value'].notna().sum()
            self.log(f"有效数据点数: {valid_count}/{len(df)}")

            return output_path

        except Exception as e:
            self.log(f"保存结果时出错: {str(e)}")
            return None


def main():
    """主函数"""
    try:
        root = tk.Tk()
        app = TifPointExtractorApp(root)

        # 添加一些样式
        style = ttk.Style()
        style.theme_use('clam')  # 使用现代主题

        root.mainloop()
    except Exception as e:
        messagebox.showerror("启动错误", f"程序启动失败:\n{str(e)}")


if __name__ == "__main__":
    main()