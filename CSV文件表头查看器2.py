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

            # 尝试读取 CSV 文件的表头和前20行数据
            print("正在读取数据，请稍候...")
            encodings = ['utf-8', 'gbk', 'latin1']  # 常见编码
            df = None
            for encoding in encodings:
                try:
                    # 尝试读取前20行数据
                    df = pd.read_csv(file_path, encoding=encoding, nrows=20)
                    print(f"成功使用编码: {encoding}")
                    break
                except Exception as e:
                    print(f"编码 {encoding} 失败: {type(e).__name__} - {e}")

            if df is not None:
                # 获取表头（列名）
                headers = df.columns.tolist()
                if headers:
                    print("\n=== CSV 文件的表头 ===")
                    for i, header in enumerate(headers, 1):
                        print(f"{i}. {header}")

                    # 显示数据行数
                    print(f"\n=== 文件已加载 {len(df)} 行数据 ===")

                    # 显示前20行数据
                    print("\n=== 数据预览（前20行）===")
                    pd.set_option('display.max_columns', None)  # 显示所有列
                    pd.set_option('display.width', None)  # 设置显示宽度
                    pd.set_option('display.max_colwidth', 30)  # 限制每列的宽度
                    print(df)

                    # 显示数据基本统计信息
                    print("\n=== 数据基本信息 ===")
                    print(df.info())

                    # 对于数值列，显示统计摘要
                    numeric_columns = df.select_dtypes(include=['number']).columns
                    if not numeric_columns.empty:
                        print("\n=== 数值列统计摘要 ===")
                        print(df[numeric_columns].describe())
                else:
                    print("错误：文件没有表头或格式不正确")
            else:
                print("错误：无法读取文件，可能是编码或格式问题")

    except Exception as e:
        print(f"读取文件时出错：{type(e).__name__} - {e}")
else:
    print("未选择任何文件")

# 暂停程序以查看输出
input("\n处理完成，按 Enter 键退出...")

# 销毁 Tkinter 窗口
root.destroy()