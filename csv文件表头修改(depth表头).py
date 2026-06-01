import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os
import threading
from pathlib import Path


class CSVHeaderModifier:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV表头批量修改工具")
        self.root.geometry("500x400")

        # 设置变量
        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()

        self.setup_ui()

    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 标题
        title_label = ttk.Label(main_frame, text="CSV表头批量修改工具",
                                font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # 输入文件夹选择
        ttk.Label(main_frame, text="输入文件夹:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.input_folder, width=50).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(main_frame, text="浏览", command=self.select_input_folder).grid(row=1, column=2, pady=5)

        # 输出文件夹选择
        ttk.Label(main_frame, text="输出文件夹:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_folder, width=50).grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(main_frame, text="浏览", command=self.select_output_folder).grid(row=2, column=2, pady=5)

        # 修改说明
        info_frame = ttk.LabelFrame(main_frame, text="修改说明", padding="10")
        info_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=20)

        info_text = """
        本程序将：
        1. 扫描输入文件夹中的所有CSV文件
        2. 将每个文件中的 "depth" 列名修改为 "bottom_depth"
        3. 保持其他列名不变
        4. 保存到输出文件夹中，文件名不变
        """
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W)

        # 处理按钮
        self.process_button = ttk.Button(main_frame, text="开始处理", command=self.start_processing)
        self.process_button.grid(row=4, column=0, columnspan=3, pady=20)

        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)

        # 状态显示
        self.status_text = tk.Text(main_frame, height=8, width=60)
        self.status_text.grid(row=6, column=0, columnspan=3, pady=10)

        # 滚动条
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.status_text.yview)
        scrollbar.grid(row=6, column=3, sticky=(tk.N, tk.S))
        self.status_text.configure(yscrollcommand=scrollbar.set)

        # 配置权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)

    def select_input_folder(self):
        folder = filedialog.askdirectory(title="选择输入文件夹")
        if folder:
            self.input_folder.set(folder)

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.output_folder.set(folder)

    def log_message(self, message):
        """在状态文本框中显示消息"""
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.root.update_idletasks()

    def start_processing(self):
        """开始处理文件"""
        if not self.input_folder.get() or not self.output_folder.get():
            messagebox.showerror("错误", "请选择输入和输出文件夹")
            return

        # 在新线程中运行处理，避免UI冻结
        self.process_button.config(state='disabled')
        self.status_text.delete(1.0, tk.END)

        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()

    def process_files(self):
        """处理文件的主要逻辑"""
        try:
            input_dir = Path(self.input_folder.get())
            output_dir = Path(self.output_folder.get())

            # 创建输出目录（如果不存在）
            output_dir.mkdir(parents=True, exist_ok=True)

            # 查找所有CSV文件
            csv_files = list(input_dir.glob("*.csv"))

            if not csv_files:
                self.log_message("在输入文件夹中没有找到CSV文件")
                self.process_button.config(state='normal')
                return

            self.log_message(f"找到 {len(csv_files)} 个CSV文件")
            self.progress.config(maximum=len(csv_files))

            success_count = 0
            error_count = 0

            for i, csv_file in enumerate(csv_files):
                try:
                    self.log_message(f"正在处理: {csv_file.name}")

                    # 读取CSV文件
                    df = pd.read_csv(csv_file)

                    # 检查是否有depth列
                    if 'depth' in df.columns:
                        # 重命名列
                        df = df.rename(columns={'depth': 'bottom_depth'})
                        self.log_message(f"  - 已将 'depth' 列重命名为 'bottom_depth'")
                    else:
                        self.log_message(f"  - 警告: 文件中未找到 'depth' 列")

                    # 保存到输出文件夹
                    output_file = output_dir / csv_file.name
                    df.to_csv(output_file, index=False)

                    self.log_message(f"  - 已保存到: {output_file}")
                    success_count += 1

                except Exception as e:
                    self.log_message(f"  - 错误: {str(e)}")
                    error_count += 1

                # 更新进度条
                self.progress.config(value=i + 1)
                self.root.update_idletasks()

            # 显示处理结果
            self.log_message(f"\n处理完成!")
            self.log_message(f"成功处理: {success_count} 个文件")
            if error_count > 0:
                self.log_message(f"处理失败: {error_count} 个文件")

            messagebox.showinfo("完成", f"处理完成!\n成功: {success_count} 个文件\n失败: {error_count} 个文件")

        except Exception as e:
            self.log_message(f"处理过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"处理过程中发生错误: {str(e)}")

        finally:
            self.process_button.config(state='normal')
            self.progress.config(value=0)


def main():
    root = tk.Tk()
    app = CSVHeaderModifier(root)
    root.mainloop()


if __name__ == "__main__":
    main()