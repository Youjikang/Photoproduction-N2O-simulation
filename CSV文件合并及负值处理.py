import os
import pandas as pd
import tkinter as tk
from tkinter import filedialog


# 选择文件夹路径
def select_folder():
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title="请选择存储年份文件夹的目录")


# 选择保存路径
def select_save_folder():
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title="请选择保存合并 CSV 文件的目录")


# **逐个年份合并 CSV 并保留数据精度**
def merge_csv_by_year(folder_path, save_folder):
    for year_folder in os.listdir(folder_path):
        year_folder_path = os.path.join(folder_path, year_folder)

        if os.path.isdir(year_folder_path):  # 确保是文件夹
            save_path = os.path.join(save_folder, f"{year_folder}_merged.csv")  # 按年份保存文件
            first_file = True  # 标记是否是第一个文件

            for file_name in os.listdir(year_folder_path):
                if file_name.endswith('.csv'):
                    file_path = os.path.join(year_folder_path, file_name)

                    # **检查文件是否为空**
                    if os.path.getsize(file_path) == 0:
                        print(f"⚠️ {file_path} 是空文件，已跳过！")
                        continue

                    try:
                        # **逐块读取，减少内存使用**
                        chunk_iter = pd.read_csv(file_path, dtype=str, chunksize=100000)
                        for chunk in chunk_iter:
                            if '.geo' in chunk.columns:
                                chunk = chunk.drop(columns=['.geo'])  # 删除 `.geo` 列

                            # **转换数据类型，保持数据有效位数**
                            for col in chunk.columns:
                                try:
                                    chunk[col] = pd.to_numeric(chunk[col])
                                except ValueError:
                                    pass  # 忽略转换错误，保持原始数据格式

                            # **增量写入 CSV，避免一次性加载所有数据**
                            chunk.to_csv(save_path, mode='a', index=False, header=first_file, float_format="%.6f")
                            first_file = False  # 之后的文件不再写入 header

                    except pd.errors.EmptyDataError:
                        print(f"❌ 错误: {file_path} 为空，已跳过！")
                    except pd.errors.ParserError:
                        print(f"❌ 错误: {file_path} 格式损坏，已跳过！")

            print(f"✅ {year_folder} 年数据合并完成，已保存到: {save_path}")


# **处理 CSV 文件，去除负值**
def process_csv_files(save_folder):
    for file_name in os.listdir(save_folder):
        if file_name.endswith('_merged.csv'):
            file_path = os.path.join(save_folder, file_name)
            filtered_save_path = file_path.replace("_merged.csv", "_filtered.csv")  # 生成新文件名

            try:
                df_iter = pd.read_csv(file_path, chunksize=100000)  # **逐块读取**
                first_chunk = True

                for chunk in df_iter:
                    # **检查并去除负值**
                    columns_to_check = ['Rrs_412', 'Rrs_443', 'Rrs_490', 'Rrs_510', 'Rrs_555', 'Rrs_670']
                    for column in columns_to_check:
                        if column in chunk.columns:
                            chunk = chunk[chunk[column] >= 0]

                    # **增量写入**
                    chunk.to_csv(filtered_save_path, mode='a', index=False, header=first_chunk, float_format="%.6f")
                    first_chunk = False

                print(f"✅ 处理后的文件已保存到: {filtered_save_path}")

                # **删除原始未去负值的文件**
                os.remove(file_path)
                print(f"🗑️ 已删除未去负值的文件: {file_path}")

            except Exception as e:
                print(f"❌ 处理 {file_path} 过程中发生错误: {e}")


# **主逻辑**
folder_path = select_folder()
if folder_path:
    save_folder = select_save_folder()
    if save_folder:
        merge_csv_by_year(folder_path, save_folder)  # **逐个年份合并**
        process_csv_files(save_folder)  # **处理负值并删除未处理的文件**
    else:
        print("⚠️ 未选择保存文件的目录，程序退出。")
else:
    print("⚠️ 未选择文件夹，程序退出。")
