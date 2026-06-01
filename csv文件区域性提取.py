import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import os
from datetime import datetime


class CSVDataExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV数据提取工具")
        self.root.geometry("600x500")

        # 变量初始化
        self.input_file_path = tk.StringVar()
        self.output_folder_path = tk.StringVar()
        self.min_lat = tk.DoubleVar()
        self.max_lat = tk.DoubleVar()
        self.min_lon = tk.DoubleVar()
        self.max_lon = tk.DoubleVar()
        self.min_depth = tk.DoubleVar()
        self.max_depth = tk.DoubleVar()
        self.use_all_depths = tk.BooleanVar(value=True)

        self.df = None
        self.create_widgets()

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 文件选择部分
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 输入文件
        ttk.Label(file_frame, text="输入CSV文件:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Entry(file_frame, textvariable=self.input_file_path, width=60).grid(row=1, column=0, sticky=(tk.W, tk.E),
                                                                                padx=(0, 5))
        ttk.Button(file_frame, text="选择文件", command=self.select_input_file).grid(row=1, column=1)

        # 输出文件夹
        ttk.Label(file_frame, text="输出文件夹:").grid(row=2, column=0, sticky=tk.W, pady=(10, 5))
        ttk.Entry(file_frame, textvariable=self.output_folder_path, width=60).grid(row=3, column=0, sticky=(tk.W, tk.E),
                                                                                   padx=(0, 5))
        ttk.Button(file_frame, text="选择文件夹", command=self.select_output_folder).grid(row=3, column=1)

        file_frame.columnconfigure(0, weight=1)

        # 范围设置部分
        range_frame = ttk.LabelFrame(main_frame, text="数据范围设置", padding="10")
        range_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 添加支持的列名提示
        hint_label = ttk.Label(range_frame,
                               text="支持的列名: 纬度(lat/latitude/g2latitude/纬度/y), 经度(lon/longitude/g2longitude/经度/x), 深度(depth/深度/z)",
                               foreground="gray")
        hint_label.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))

        # 纬度范围
        ttk.Label(range_frame, text="纬度范围:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        lat_frame = ttk.Frame(range_frame)
        lat_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(lat_frame, text="最小纬度:").grid(row=0, column=0, padx=(0, 5))
        ttk.Entry(lat_frame, textvariable=self.min_lat, width=15).grid(row=0, column=1, padx=(0, 20))
        ttk.Label(lat_frame, text="最大纬度:").grid(row=0, column=2, padx=(0, 5))
        ttk.Entry(lat_frame, textvariable=self.max_lat, width=15).grid(row=0, column=3)

        # 经度范围
        ttk.Label(range_frame, text="经度范围:").grid(row=3, column=0, sticky=tk.W, pady=(0, 5))
        lon_frame = ttk.Frame(range_frame)
        lon_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(lon_frame, text="最小经度:").grid(row=0, column=0, padx=(0, 5))
        ttk.Entry(lon_frame, textvariable=self.min_lon, width=15).grid(row=0, column=1, padx=(0, 20))
        ttk.Label(lon_frame, text="最大经度:").grid(row=0, column=2, padx=(0, 5))
        ttk.Entry(lon_frame, textvariable=self.max_lon, width=15).grid(row=0, column=3)

        # 深度范围
        ttk.Label(range_frame, text="深度范围:").grid(row=5, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Checkbutton(range_frame, text="使用所有深度", variable=self.use_all_depths,
                        command=self.toggle_depth_inputs).grid(row=6, column=0, sticky=tk.W, pady=(0, 5))

        self.depth_frame = ttk.Frame(range_frame)
        self.depth_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(self.depth_frame, text="最小深度:").grid(row=0, column=0, padx=(0, 5))
        self.depth_min_entry = ttk.Entry(self.depth_frame, textvariable=self.min_depth, width=15)
        self.depth_min_entry.grid(row=0, column=1, padx=(0, 20))
        ttk.Label(self.depth_frame, text="最大深度:").grid(row=0, column=2, padx=(0, 5))
        self.depth_max_entry = ttk.Entry(self.depth_frame, textvariable=self.max_depth, width=15)
        self.depth_max_entry.grid(row=0, column=3)

        # 默认禁用深度输入框
        self.toggle_depth_inputs()

        # 按钮部分
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

        ttk.Button(button_frame, text="预览数据", command=self.preview_data).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(button_frame, text="提取数据", command=self.extract_data, style="Accent.TButton").grid(row=0,
                                                                                                          column=1,
                                                                                                          padx=(10, 0))

        # 状态显示
        self.status_text = tk.Text(main_frame, height=10, width=70)
        self.status_text.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 滚动条
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.status_text.yview)
        scrollbar.grid(row=3, column=2, sticky=(tk.N, tk.S))
        self.status_text.configure(yscrollcommand=scrollbar.set)

        # 配置权重
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

    def toggle_depth_inputs(self):
        """切换深度输入框的启用状态"""
        if self.use_all_depths.get():
            self.depth_min_entry.config(state="disabled")
            self.depth_max_entry.config(state="disabled")
        else:
            self.depth_min_entry.config(state="normal")
            self.depth_max_entry.config(state="normal")

    def select_input_file(self):
        """选择输入CSV文件"""
        file_path = filedialog.askopenfilename(
            title="选择CSV文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.input_file_path.set(file_path)
            self.log_message(f"已选择输入文件: {file_path}")

    def select_output_folder(self):
        """选择输出文件夹"""
        folder_path = filedialog.askdirectory(title="选择输出文件夹")
        if folder_path:
            self.output_folder_path.set(folder_path)
            self.log_message(f"已选择输出文件夹: {folder_path}")

    def log_message(self, message):
        """在状态文本框中显示消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
        self.root.update()

    def load_data(self):
        """加载CSV数据"""
        if not self.input_file_path.get():
            messagebox.showerror("错误", "请先选择输入文件!")
            return False

        try:
            self.log_message("正在加载CSV文件...")
            self.df = pd.read_csv(self.input_file_path.get())
            self.log_message(f"成功加载CSV文件，共 {len(self.df)} 行数据")

            # 显示列名
            columns = list(self.df.columns)
            self.log_message(f"数据列: {', '.join(columns)}")

            # 尝试识别可能的经纬度和深度列
            self.identify_columns()

            return True
        except Exception as e:
            messagebox.showerror("错误", f"加载CSV文件失败: {str(e)}")
            self.log_message(f"加载失败: {str(e)}")
            return False

    def identify_columns(self):
        """识别可能的经纬度和深度列"""
        columns = [col.lower() for col in self.df.columns]
        possible_lat = ['lat', 'latitude', '纬度', 'y', 'g2latitude', 'g2lat']
        possible_lon = ['lon', 'lng', 'longitude', '经度', 'x', 'g2longitude', 'g2lon']
        possible_depth = ['depth', '深度', 'z', 'elevation', 'alt', 'altitude']

        found_cols = []

        for col in self.df.columns:
            col_lower = col.lower()
            if any(p in col_lower for p in possible_lat):
                found_cols.append(f"可能的纬度列: {col}")
            elif any(p in col_lower for p in possible_lon):
                found_cols.append(f"可能的经度列: {col}")
            elif any(p in col_lower for p in possible_depth):
                found_cols.append(f"可能的深度列: {col}")

        if found_cols:
            self.log_message("识别到的可能列:")
            for col in found_cols:
                self.log_message(f"  {col}")
        else:
            self.log_message("未自动识别到标准的经纬度/深度列名")
            self.log_message("程序支持的列名关键词:")
            self.log_message("  纬度: lat, latitude, 纬度, y, g2latitude, g2lat")
            self.log_message("  经度: lon, lng, longitude, 经度, x, g2longitude, g2lon")
            self.log_message("  深度: depth, 深度, z, elevation, altitude, alt")

    def preview_data(self):
        """预览数据"""
        if not self.load_data():
            return

        # 显示前5行数据
        self.log_message("\n数据预览 (前5行):")
        self.log_message("-" * 50)
        preview = self.df.head().to_string()
        self.log_message(preview)
        self.log_message("-" * 50)

        # 显示将要使用的列
        lat_col = self.get_column_by_keywords(['lat', 'latitude', '纬度', 'y', 'g2latitude', 'g2lat'])
        lon_col = self.get_column_by_keywords(['lon', 'lng', 'longitude', '经度', 'x', 'g2longitude', 'g2lon'])
        depth_col = self.get_column_by_keywords(['depth', '深度', 'z', 'elevation', 'altitude', 'alt'])

        self.log_message("数据提取时将使用的列:")
        if lat_col:
            self.log_message(f"  纬度列: {lat_col}")
        else:
            self.log_message(f"  纬度列: 未找到!")

        if lon_col:
            self.log_message(f"  经度列: {lon_col}")
        else:
            self.log_message(f"  经度列: 未找到!")

        if depth_col:
            self.log_message(f"  深度列: {depth_col}")
        else:
            self.log_message(f"  深度列: 未找到 (将跳过深度过滤)")

    def validate_inputs(self):
        """验证输入参数"""
        if not self.input_file_path.get():
            messagebox.showerror("错误", "请选择输入CSV文件!")
            return False

        if not self.output_folder_path.get():
            messagebox.showerror("错误", "请选择输出文件夹!")
            return False

        try:
            # 检查经纬度范围
            if self.min_lat.get() >= self.max_lat.get():
                messagebox.showerror("错误", "最小纬度必须小于最大纬度!")
                return False

            if self.min_lon.get() >= self.max_lon.get():
                messagebox.showerror("错误", "最小经度必须小于最大经度!")
                return False

            # 检查深度范围（如果不是使用所有深度）
            if not self.use_all_depths.get():
                if self.min_depth.get() >= self.max_depth.get():
                    messagebox.showerror("错误", "最小深度必须小于最大深度!")
                    return False

        except tk.TclError:
            messagebox.showerror("错误", "请输入有效的数值!")
            return False

        return True

    def get_column_by_keywords(self, keywords):
        """根据关键词查找列名"""
        columns = self.df.columns

        # 首先尝试完全匹配（忽略大小写）
        for col in columns:
            for keyword in keywords:
                if col.lower() == keyword.lower():
                    return col

        # 然后尝试部分匹配
        for col in columns:
            col_lower = col.lower()
            for keyword in keywords:
                if keyword.lower() in col_lower:
                    return col

        return None

    def extract_data(self):
        """提取数据"""
        if not self.validate_inputs():
            return

        if not self.load_data():
            return

        try:
            # 自动识别经纬度和深度列
            self.log_message("正在识别列名...")

            lat_col = self.get_column_by_keywords(['lat', 'latitude', '纬度', 'y', 'g2latitude', 'g2lat'])
            lon_col = self.get_column_by_keywords(['lon', 'lng', 'longitude', '经度', 'x', 'g2longitude', 'g2lon'])
            depth_col = self.get_column_by_keywords(['depth', '深度', 'z', 'elevation', 'altitude', 'alt'])

            # 显示识别结果
            self.log_message(f"识别到的列名:")
            if lat_col:
                self.log_message(f"  纬度列: {lat_col}")
            if lon_col:
                self.log_message(f"  经度列: {lon_col}")
            if depth_col:
                self.log_message(f"  深度列: {depth_col}")
            else:
                self.log_message(f"  深度列: 未找到 (将跳过深度过滤)")

            if not lat_col or not lon_col:
                # 如果无法自动识别，显示所有可用列供用户参考
                missing = []
                if not lat_col:
                    missing.append("纬度")
                if not lon_col:
                    missing.append("经度")

                self.log_message(f"错误: 无法识别{'/'.join(missing)}列")
                self.log_message("支持的列名关键词:")
                if not lat_col:
                    self.log_message("  纬度列: lat, latitude, 纬度, y, g2latitude, g2lat")
                if not lon_col:
                    self.log_message("  经度列: lon, lng, longitude, 经度, x, g2longitude, g2lon")

                messagebox.showerror("错误",
                                     f"无法自动识别{'/'.join(missing)}列！\n\n"
                                     f"CSV文件中的列名: {', '.join(self.df.columns)}\n\n"
                                     f"程序支持的关键词:\n"
                                     f"• 纬度列: lat, latitude, 纬度, y, g2latitude, g2lat\n"
                                     f"• 经度列: lon, lng, longitude, 经度, x, g2longitude, g2lon\n\n"
                                     f"请确保列名包含上述关键词之一")
                return

            # 应用范围过滤
            self.log_message("开始过滤数据...")

            # 经纬度过滤
            filtered_df = self.df[
                (self.df[lat_col] >= self.min_lat.get()) &
                (self.df[lat_col] <= self.max_lat.get()) &
                (self.df[lon_col] >= self.min_lon.get()) &
                (self.df[lon_col] <= self.max_lon.get())
                ]

            self.log_message(f"经纬度过滤后剩余 {len(filtered_df)} 行数据")

            # 深度过滤（如果需要且存在深度列）
            if not self.use_all_depths.get() and depth_col:
                filtered_df = filtered_df[
                    (filtered_df[depth_col] >= self.min_depth.get()) &
                    (filtered_df[depth_col] <= self.max_depth.get())
                    ]
                self.log_message(f"深度过滤后剩余 {len(filtered_df)} 行数据")

            if len(filtered_df) == 0:
                messagebox.showwarning("警告", "在指定范围内没有找到任何数据!")
                self.log_message("没有找到符合条件的数据")
                return

            # 生成输出文件名
            input_filename = os.path.splitext(os.path.basename(self.input_file_path.get()))[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{input_filename}_filtered_{timestamp}.csv"
            output_path = os.path.join(self.output_folder_path.get(), output_filename)

            # 保存过滤后的数据
            filtered_df.to_csv(output_path, index=False, encoding='utf-8-sig')

            self.log_message(f"数据提取完成!")
            self.log_message(f"输出文件: {output_path}")
            self.log_message(f"提取了 {len(filtered_df)} 行数据")

            # 显示过滤条件总结
            self.log_message("\n过滤条件总结:")
            self.log_message(f"  纬度范围: {self.min_lat.get()} ~ {self.max_lat.get()}")
            self.log_message(f"  经度范围: {self.min_lon.get()} ~ {self.max_lon.get()}")
            if not self.use_all_depths.get() and depth_col:
                self.log_message(f"  深度范围: {self.min_depth.get()} ~ {self.max_depth.get()}")
            else:
                self.log_message(f"  深度范围: 全部")

            messagebox.showinfo("成功", f"数据提取完成!\n已保存到: {output_path}")

        except Exception as e:
            messagebox.showerror("错误", f"数据提取失败: {str(e)}")
            self.log_message(f"提取失败: {str(e)}")


def main():
    root = tk.Tk()
    app = CSVDataExtractor(root)
    root.mainloop()


if __name__ == "__main__":
    main()