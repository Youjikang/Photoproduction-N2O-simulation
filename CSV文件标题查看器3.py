import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import pandas as pd
import os
import numpy as np

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
            file_size_gb = file_size_mb / 1024  # 转换为 GB
            print(f"文件大小: {file_size_mb:.2f} MB ({file_size_gb:.2f} GB)")

            # 尝试读取 CSV 文件的表头
            print("正在读取文件头，请稍候...")
            encodings = ['utf-8', 'gbk', 'latin1']  # 常见编码
            df_header = None
            encoding_used = None

            for encoding in encodings:
                try:
                    # 只读取表头和几行样本数据
                    df_header = pd.read_csv(file_path, encoding=encoding, nrows=5)
                    encoding_used = encoding
                    print(f"成功使用编码: {encoding}")
                    break
                except Exception as e:
                    print(f"编码 {encoding} 失败: {type(e).__name__} - {e}")

            if df_header is not None:
                # 获取表头（列名）
                headers = df_header.columns.tolist()
                if headers:
                    print("\n=== CSV 文件的表头 ===")
                    for i, header in enumerate(headers, 1):
                        print(f"{i}. {header}")

                    # 显示样本数据
                    print("\n=== 数据预览（前5行）===")
                    pd.set_option('display.max_columns', None)  # 显示所有列
                    pd.set_option('display.width', None)  # 设置显示宽度
                    pd.set_option('display.max_colwidth', 30)  # 限制每列的宽度
                    print(df_header)

                    # 估计行数（这里无法准确获取，但可以给用户一个大致的信息）
                    print("\n注意：由于文件较大，无法直接计算总行数。")

                    # 检查指定的列是否存在
                    required_columns = ['year', 'month', 'depth', 'longitude', 'latitude']
                    missing_columns = [col for col in required_columns if col not in df_header.columns]

                    if missing_columns:
                        print(f"\n警告：以下列不存在: {', '.join(missing_columns)}")
                        print("请确认CSV文件包含所需列或检查列名是否正确。")
                    else:
                        # 创建查询功能
                        while True:
                            print("\n=== 查询特定数据 ===")
                            print("请输入查询参数 (留空表示不限制该条件):")

                            # 获取用户输入的查询条件
                            year_input = simpledialog.askstring("输入", "请输入年份 (如: 2020):", parent=root)
                            month_input = simpledialog.askstring("输入", "请输入月份 (1-12):", parent=root)
                            depth_input = simpledialog.askstring("输入", "请输入深度 (如: 10.5):", parent=root)
                            lon_input = simpledialog.askstring("输入", "请输入经度:", parent=root)
                            lat_input = simpledialog.askstring("输入", "请输入纬度:", parent=root)

                            # 如果所有条件都为空，提醒用户
                            if not any([year_input, month_input, depth_input, lon_input, lat_input]):
                                messagebox.showwarning("警告",
                                                       "所有条件都为空，这可能会尝试加载整个文件！\n对于大文件，这可能导致内存不足。",
                                                       parent=root)
                                continue_anyway = messagebox.askyesno("确认", "是否仍要继续？", parent=root)
                                if not continue_anyway:
                                    continue

                            # 打印输入的查询条件
                            print(f"\n查询条件:")
                            if year_input: print(f"年份: {year_input}")
                            if month_input: print(f"月份: {month_input}")
                            if depth_input: print(f"深度: {depth_input}")
                            if lon_input: print(f"经度: {lon_input}")
                            if lat_input: print(f"纬度: {lat_input}")

                            # 根据条件构建查询字符串
                            query_conditions = []

                            if year_input:
                                try:
                                    year_value = int(year_input)
                                    query_conditions.append(f"year == {year_value}")
                                except ValueError:
                                    print("警告: 年份必须为整数，忽略此条件")

                            if month_input:
                                try:
                                    month_value = int(month_input)
                                    query_conditions.append(f"month == {month_value}")
                                except ValueError:
                                    print("警告: 月份必须为整数，忽略此条件")

                            # 对浮点数条件，使用近似匹配
                            if depth_input:
                                try:
                                    depth_value = float(depth_input)
                                    # 使用范围查询来近似匹配浮点数
                                    tolerance = 0.001
                                    query_conditions.append(
                                        f"depth >= {depth_value - tolerance} and depth <= {depth_value + tolerance}")
                                except ValueError:
                                    print("警告: 深度必须为数字，忽略此条件")

                            if lon_input:
                                try:
                                    lon_value = float(lon_input)
                                    tolerance = 0.001
                                    query_conditions.append(
                                        f"longitude >= {lon_value - tolerance} and longitude <= {lon_value + tolerance}")
                                except ValueError:
                                    print("警告: 经度必须为数字，忽略此条件")

                            if lat_input:
                                try:
                                    lat_value = float(lat_input)
                                    tolerance = 0.001
                                    query_conditions.append(
                                        f"latitude >= {lat_value - tolerance} and latitude <= {lat_value + tolerance}")
                                except ValueError:
                                    print("警告: 纬度必须为数字，忽略此条件")

                            # 合并所有条件
                            query_string = " and ".join(query_conditions) if query_conditions else None

                            try:
                                print("\n开始查询，这可能需要一些时间...")

                                # 使用分批读取和过滤
                                chunksize = 100000  # 每次读取10万行
                                max_results = 1000  # 最多显示1000行结果
                                results = []
                                total_rows_processed = 0

                                for chunk in pd.read_csv(file_path, encoding=encoding_used, chunksize=chunksize):
                                    total_rows_processed += len(chunk)
                                    print(f"已处理 {total_rows_processed} 行...", end="\r")

                                    if query_string:
                                        filtered_chunk = chunk.query(query_string)
                                    else:
                                        filtered_chunk = chunk

                                    if not filtered_chunk.empty:
                                        results.append(filtered_chunk)
                                        # 如果结果已经足够多，可以提前停止
                                        if sum(len(df) for df in results) >= max_results:
                                            results[-1] = results[-1].head(
                                                max_results - sum(len(df) for df in results[:-1]))
                                            print(f"\n已达到最大结果数限制 ({max_results})，停止处理")
                                            break

                                # 合并所有结果
                                if results:
                                    final_result = pd.concat(results, ignore_index=True)
                                    print(
                                        f"\n=== 找到 {len(final_result)} 条匹配记录 (处理了 {total_rows_processed} 行) ===")
                                    print(final_result)

                                    # 询问是否导出结果
                                    export_option = simpledialog.askstring("导出", "是否导出结果? (y/n):", parent=root)
                                    if export_option and export_option.lower() == 'y':
                                        export_path = filedialog.asksaveasfilename(
                                            title="保存查询结果",
                                            defaultextension=".csv",
                                            filetypes=[("CSV files", "*.csv")]
                                        )
                                        if export_path:
                                            final_result.to_csv(export_path, index=False, encoding='utf-8')
                                            print(f"结果已保存到: {export_path}")
                                else:
                                    print("\n未找到匹配记录")

                            except Exception as e:
                                print(f"\n查询过程中出错: {type(e).__name__} - {e}")

                            # 询问是否继续查询
                            continue_option = simpledialog.askstring("继续", "是否继续查询? (y/n):", parent=root)
                            if not continue_option or continue_option.lower() != 'y':
                                break
                else:
                    print("错误：文件没有表头或格式不正确")
            else:
                print("错误：无法读取文件，可能是编码或格式问题")

    except Exception as e:
        print(f"读取文件时出错：{type(e).__name__} - {e}")
else:
    print("未选择任何文件")

# 销毁 Tkinter 窗口
root.destroy()