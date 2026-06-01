import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import filedialog
from datetime import datetime


def select_file():
    """打开文件对话框让用户选择CSV文件"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 打开文件选择对话框
    file_path = filedialog.askopenfilename(
        title="选择CSV文件",
        filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
    )

    if not file_path:
        print("未选择文件，程序退出")
        return None

    return file_path


def select_output_directory():
    """打开文件对话框让用户选择输出目录"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 打开文件夹选择对话框
    output_dir = filedialog.askdirectory(title="选择报告保存位置")

    # 如果用户取消选择，则使用默认目录
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), "data_analysis_report")
        print(f"未选择目录，使用默认位置: {output_dir}")

    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def analyze_csv_data(csv_file_path, output_dir, chunk_size=1000000):
    """
    分析CSV文件的数据范围和统计信息

    参数:
    csv_file_path: CSV文件路径
    output_dir: 输出目录
    chunk_size: 分块读取大小，默认1百万行
    """
    start_time = datetime.now()
    print(f"开始分析CSV文件: {os.path.basename(csv_file_path)}")
    print(f"分析开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 创建报告文件
    base_filename = os.path.splitext(os.path.basename(csv_file_path))[0]
    report_file_path = os.path.join(output_dir, f"{base_filename}_analysis_report.txt")

    try:
        # 首先读取文件头，获取列名
        header_df = pd.read_csv(csv_file_path, nrows=0)
        columns = header_df.columns.tolist()
        print(f"文件列名: {columns}")

        # 初始化统计对象
        stats = {col: {
            'min': float('inf'),
            'max': float('-inf'),
            'mean': 0.0,
            'count': 0,
            'null_count': 0,
            'unique_values': set(),
            'histogram_data': []
        } for col in columns}

        # 特殊处理列
        numeric_cols = []
        categorical_cols = []
        coordinate_cols = ['longitude', 'latitude', 'depth']
        time_cols = ['year', 'month']
        data_cols = ['so', 'thetao']  # 盐度和温度数据列

        # 估计总行数
        file_size = os.path.getsize(csv_file_path)
        # 读取前1000行来估计每行平均大小
        sample_df = pd.read_csv(csv_file_path, nrows=1000)
        avg_row_size = file_size / len(sample_df) if len(sample_df) > 0 else 100
        estimated_rows = int(file_size / avg_row_size)

        print(f"估计文件总行数: {estimated_rows:,}")
        print(f"使用分块大小: {chunk_size:,}行")

        # 分块读取CSV文件
        chunks_total = (estimated_rows + chunk_size - 1) // chunk_size
        chunk_num = 0
        rows_processed = 0

        # 打开报告文件
        with open(report_file_path, 'w', encoding='utf-8') as report_file:
            report_file.write(f"CSV文件分析报告: {os.path.basename(csv_file_path)}\n")
            report_file.write(f"分析时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            report_file.write(f"估计文件总行数: {estimated_rows:,}\n\n")

            for chunk in pd.read_csv(csv_file_path, chunksize=chunk_size):
                chunk_start_time = datetime.now()
                chunk_num += 1
                chunk_rows = len(chunk)
                rows_processed += chunk_rows

                print(f"正在处理第{chunk_num}/{chunks_total}块 ({chunk_rows:,}行)...")

                # 对每列进行分析
                for col in columns:
                    if col not in chunk.columns:
                        continue

                    # 更新统计信息
                    col_data = chunk[col]
                    not_null_data = col_data.dropna()
                    stats[col]['null_count'] += col_data.isna().sum()
                    stats[col]['count'] += len(not_null_data)

                    if len(not_null_data) > 0:
                        # 数值型列
                        if np.issubdtype(col_data.dtype, np.number):
                            if col not in numeric_cols:
                                numeric_cols.append(col)

                            current_min = not_null_data.min()
                            current_max = not_null_data.max()
                            current_mean = not_null_data.mean()

                            stats[col]['min'] = min(stats[col]['min'], current_min)
                            stats[col]['max'] = max(stats[col]['max'], current_max)
                            stats[col]['mean'] = update_running_mean(
                                stats[col]['mean'],
                                current_mean,
                                stats[col]['count'] - len(not_null_data),
                                len(not_null_data)
                            )

                            # 收集直方图数据
                            if col in data_cols or col in coordinate_cols:
                                stats[col]['histogram_data'].extend(not_null_data.sample(
                                    min(10000, len(not_null_data)),
                                    random_state=42
                                ).tolist())

                        # 类别型列
                        else:
                            if col not in categorical_cols:
                                categorical_cols.append(col)

                            unique_vals = set(not_null_data.unique())
                            if len(stats[col]['unique_values']) < 1000 and len(unique_vals) < 1000:
                                stats[col]['unique_values'].update(unique_vals)

                chunk_time = (datetime.now() - chunk_start_time).total_seconds()
                chunk_speed = chunk_rows / chunk_time if chunk_time > 0 else 0

                print(f"已处理 {rows_processed:,}/{estimated_rows:,}行 ({rows_processed / estimated_rows * 100:.1f}%)")
                print(f"处理速度: {chunk_speed:.1f}行/秒")

                # 估计剩余时间
                if chunk_speed > 0:
                    remaining_rows = estimated_rows - rows_processed
                    est_remaining_seconds = remaining_rows / chunk_speed
                    est_completion = datetime.now() + pd.Timedelta(seconds=est_remaining_seconds)
                    print(f"预计剩余时间: {format_time_delta(est_remaining_seconds)}")
                    print(f"预计完成时间: {est_completion.strftime('%Y-%m-%d %H:%M:%S')}")

            # 写入报告
            report_file.write("==== 列属性摘要 ====\n")
            report_file.write(f"总行数: {rows_processed:,}\n")
            report_file.write(f"数值型列: {', '.join(numeric_cols)}\n")
            report_file.write(f"类别型列: {', '.join(categorical_cols)}\n\n")

            report_file.write("==== 详细列统计信息 ====\n\n")

            # 生成每列的统计报告
            for col in columns:
                report_file.write(f"列名: {col}\n")
                report_file.write(f"数据类型: {'数值型' if col in numeric_cols else '类别型'}\n")
                report_file.write(f"非空值数量: {stats[col]['count']:,}\n")
                report_file.write(f"空值数量: {stats[col]['null_count']:,}\n")

                if col in numeric_cols:
                    # 修复无限值
                    if stats[col]['min'] == float('inf'):
                        stats[col]['min'] = "未知"
                    if stats[col]['max'] == float('-inf'):
                        stats[col]['max'] = "未知"

                    report_file.write(f"最小值: {stats[col]['min']}\n")
                    report_file.write(f"最大值: {stats[col]['max']}\n")
                    report_file.write(f"平均值: {stats[col]['mean']}\n")

                if col in categorical_cols and len(stats[col]['unique_values']) < 100:
                    unique_values_list = sorted(list(stats[col]['unique_values']))
                    report_file.write(f"唯一值 ({len(unique_values_list)}个): {unique_values_list}\n")

                report_file.write("\n")

            # 生成数据图表
            try:
                print("正在生成数据可视化图表...")
                charts_dir = os.path.join(output_dir, f"{base_filename}_charts")
                os.makedirs(charts_dir, exist_ok=True)

                # 为特定列生成直方图
                for col in numeric_cols:
                    if len(stats[col]['histogram_data']) > 0:
                        plt.figure(figsize=(10, 6))
                        plt.hist(stats[col]['histogram_data'], bins=50, alpha=0.7)
                        plt.title(f'{col} 分布')
                        plt.xlabel(col)
                        plt.ylabel('频率')
                        plt.grid(True, alpha=0.3)
                        chart_path = os.path.join(charts_dir, f"{col}_histogram.png")
                        plt.savefig(chart_path)
                        plt.close()
                        report_file.write(f"{col} 分布图: {chart_path}\n")

                # 如果有经纬度数据，生成散点图
                if 'longitude' in numeric_cols and 'latitude' in numeric_cols:
                    if (len(stats['longitude']['histogram_data']) > 0 and
                            len(stats['latitude']['histogram_data']) > 0):
                        # 从采样数据中获取匹配的索引
                        sample_size = min(
                            len(stats['longitude']['histogram_data']),
                            len(stats['latitude']['histogram_data']),
                            10000  # 最多1万个点以避免过度绘图
                        )

                        plt.figure(figsize=(12, 6))
                        plt.scatter(
                            stats['longitude']['histogram_data'][:sample_size],
                            stats['latitude']['histogram_data'][:sample_size],
                            s=5, alpha=0.5
                        )
                        plt.title('地理分布散点图')
                        plt.xlabel('经度')
                        plt.ylabel('纬度')
                        plt.grid(True, alpha=0.3)
                        chart_path = os.path.join(charts_dir, "geo_distribution.png")
                        plt.savefig(chart_path)
                        plt.close()
                        report_file.write(f"地理分布散点图: {chart_path}\n")

                report_file.write("\n生成的所有图表保存在目录: " + charts_dir + "\n")
            except Exception as e:
                report_file.write(f"\n生成图表时出错: {e}\n")
                print(f"生成图表时出错: {e}")

        # 创建HTML报告（可选）
        try:
            html_report_path = os.path.join(output_dir, f"{base_filename}_analysis_report.html")
            generate_html_report(stats, columns, numeric_cols, categorical_cols, html_report_path, base_filename,
                                 charts_dir)
            print(f"HTML报告已生成: {html_report_path}")
        except Exception as e:
            print(f"生成HTML报告时出错: {e}")

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        print("\n=== 分析完成 ===")
        print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总耗时: {format_time_delta(total_time)}")
        print(f"分析报告已保存至: {report_file_path}")

        return report_file_path

    except Exception as e:
        print(f"分析CSV文件时出错: {e}")
        import traceback
        traceback.print_exc()
        return None


def update_running_mean(current_mean, new_mean, current_count, new_count):
    """更新运行平均值"""
    if current_count == 0:
        return new_mean
    if new_count == 0:
        return current_mean

    total_count = current_count + new_count
    updated_mean = (current_mean * current_count + new_mean * new_count) / total_count
    return updated_mean


def format_time_delta(seconds):
    """将秒转换为更易读的时间格式"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"


def generate_html_report(stats, columns, numeric_cols, categorical_cols, html_path, base_filename, charts_dir):
    """生成HTML格式的分析报告"""
    with open(html_path, 'w', encoding='utf-8') as html_file:
        html_file.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>数据分析报告 - {base_filename}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ text-align: left; padding: 12px; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .chart-container {{ margin: 20px 0; }}
        .chart {{ max-width: 100%; border: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>CSV数据分析报告</h1>
    <h2>文件: {base_filename}</h2>
    <p>分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <h2>列属性摘要</h2>
    <table border="1">
        <tr>
            <th>类型</th>
            <th>列名</th>
        </tr>
        <tr>
            <td>数值型列</td>
            <td>{', '.join(numeric_cols)}</td>
        </tr>
        <tr>
            <td>类别型列</td>
            <td>{', '.join(categorical_cols)}</td>
        </tr>
    </table>

    <h2>详细列统计</h2>
""")

        # 添加每列的详细统计信息
        for col in columns:
            html_file.write(f"""
    <h3>列: {col}</h3>
    <table border="1">
        <tr>
            <th>属性</th>
            <th>值</th>
        </tr>
        <tr>
            <td>数据类型</td>
            <td>{'数值型' if col in numeric_cols else '类别型'}</td>
        </tr>
        <tr>
            <td>非空值数量</td>
            <td>{stats[col]['count']:,}</td>
        </tr>
        <tr>
            <td>空值数量</td>
            <td>{stats[col]['null_count']:,}</td>
        </tr>
""")

            if col in numeric_cols:
                html_file.write(f"""
        <tr>
            <td>最小值</td>
            <td>{stats[col]['min']}</td>
        </tr>
        <tr>
            <td>最大值</td>
            <td>{stats[col]['max']}</td>
        </tr>
        <tr>
            <td>平均值</td>
            <td>{stats[col]['mean']}</td>
        </tr>
""")

            if col in categorical_cols and len(stats[col]['unique_values']) < 50:
                unique_values_list = sorted(list(stats[col]['unique_values']))
                html_file.write(f"""
        <tr>
            <td>唯一值 ({len(unique_values_list)}个)</td>
            <td>{str(unique_values_list)}</td>
        </tr>
""")

            html_file.write("    </table>\n")

            # 添加直方图（如果有）
            if col in numeric_cols and os.path.exists(os.path.join(charts_dir, f"{col}_histogram.png")):
                html_file.write(f"""
    <div class="chart-container">
        <h4>{col} 分布</h4>
        <img src="{base_filename}_charts/{col}_histogram.png" alt="{col} 分布" class="chart">
    </div>
""")

        # 添加地理分布图（如果有）
        geo_chart_path = os.path.join(charts_dir, "geo_distribution.png")
        if os.path.exists(geo_chart_path):
            html_file.write(f"""
    <div class="chart-container">
        <h4>地理分布</h4>
        <img src="{base_filename}_charts/geo_distribution.png" alt="地理分布" class="chart">
    </div>
""")

        html_file.write("""
</body>
</html>
""")


def main():
    print("欢迎使用CSV数据范围分析工具")
    print("=" * 50)

    # 选择CSV文件
    csv_file_path = select_file()
    if csv_file_path is None:
        return

    print(f"已选择文件: {csv_file_path}")

    # 选择输出目录
    output_dir = select_output_directory()
    print(f"分析报告将保存至: {output_dir}")

    # 设置分块大小
    chunk_size = 1000000  # 默认100万行
    custom_chunk = input(f"设置分块大小（默认{chunk_size:,}行）? (y/n): ").lower().strip()

    if custom_chunk == 'y':
        try:
            chunk_size = int(input("请输入分块大小（行数）: ").replace(',', ''))
            if chunk_size <= 0:
                print(f"无效的分块大小，使用默认值{chunk_size:,}行")
                chunk_size = 1000000
        except ValueError:
            print(f"输入无效，使用默认分块大小{chunk_size:,}行")

    print(f"使用分块大小: {chunk_size:,}行")

    # 开始分析
    report_file_path = analyze_csv_data(csv_file_path, output_dir, chunk_size)

    if report_file_path:
        print(f"\n分析完成! 报告已保存至: {report_file_path}")
        print("同时也生成了HTML格式的报告和数据可视化图表。")
    else:
        print("\n分析失败，未能生成报告")


if __name__ == "__main__":
    main()