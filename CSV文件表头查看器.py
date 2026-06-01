import tkinter as tk
from tkinter import filedialog
import pandas as pd
import os

# 创建一个隐藏的 Tkinter 窗口
root = tk.Tk()
root.withdraw()  # 隐藏主窗口

# 打开文件选择对话框，选择 CSV 文件
file_path = filedialog.askopenfilename(
    title="选择 CSV 文件",
    filetypes=[("CSV files", "*.csv")]
)

# 打印选择的文件路径以便调试
print(f"Selected file: {file_path}")

# 检查是否选择了文件
if file_path:
    try:
        # 检查文件是否为空
        if os.path.getsize(file_path) == 0:
            print("错误：文件为空")
        else:
            # 打印文件大小
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)  # 转换为 MB
            print(f"文件大小: {file_size_mb:.2f} MB")

            # 尝试读取 CSV 文件的表头（仅第一行）
            print("正在读取表头，请稍候...")
            encodings = ['utf-8', 'gbk', 'latin1']  # 常见编码
            df = None
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, nrows=0)
                    print(f"成功使用编码: {encoding}")
                    break
                except Exception as e:
                    print(f"编码 {encoding} 失败: {type(e).__name__} - {e}")

            if df is not None:
                # 获取表头（列名）
                headers = df.columns.tolist()
                if headers:
                    print("CSV 文件的表头：")
                    for i, header in enumerate(headers, 1):
                        print(f"{i}. {header}")
                else:
                    print("错误：文件没有表头或格式不正确")
            else:
                print("错误：无法读取文件，可能是编码或格式问题")

    except Exception as e:
        print(f"读取文件时出错：{type(e).__name__} - {e}")
else:
    print("未选择任何文件")

# 暂停程序以查看输出
input("按 Enter 键退出...")

# 销毁 Tkinter 窗口
root.destroy()