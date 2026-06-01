import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog
import gc
import numpy as np
from tqdm import tqdm
import time


def select_input_folder():
    """选择包含CSV文件的输入文件夹"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    folder_path = filedialog.askdirectory(title="请选择包含CSV文件的输入文件夹")
    root.destroy()
    return folder_path


def select_output_folder():
    """选择输出文件夹"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    folder_path = filedialog.askdirectory(title="请选择输出文件夹")
    root.destroy()
    return folder_path


def convert_nitrite_unit(nitrite_umol_kg):
    """
    将nitrite从μmol/kg转换为mmol/m³
    公式: μmol/kg = mmol/m³ × 1000 / 1025
    反推: mmol/m³ = μmol/kg × 1025 / 1000
    """
    return nitrite_umol_kg * 1025 / 1000


def get_file_line_count(file_path):
    """快速估算文件行数用于进度显示"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f) - 1  # 减去标题行
    except:
        return None


def process_single_csv_optimized(file_path, output_folder):
    """
    优化版本的CSV文件处理函数
    使用向量化操作和pandas groupby提高性能
    """
    print(f"\n正在处理文件: {os.path.basename(file_path)}")

    # 获取文件名（不含扩展名）作为年份
    filename = os.path.splitext(os.path.basename(file_path))[0]

    # 获取文件总行数用于进度显示
    total_lines = get_file_line_count(file_path)
    if total_lines:
        print(f"文件总行数: {total_lines:,}")

    start_time = time.time()

    # 调整块大小以优化性能
    chunk_size = 50000  # 增加块大小
    processed_lines = 0
    all_results = []

    try:
        # 创建进度条
        pbar = tqdm(total=total_lines, desc="处理进度", unit="行") if total_lines else None

        # 逐块读取文件
        for chunk_num, chunk in enumerate(pd.read_csv(file_path, chunksize=chunk_size)):
            # 检查列名是否正确
            expected_columns = ['year', 'month', 'longitude', 'latitude', 'depth', 'nitrite_predicted', 'nitrate']
            if not all(col in chunk.columns for col in expected_columns):
                print(f"警告: 文件 {file_path} 的列名不匹配预期格式")
                print(f"实际列名: {list(chunk.columns)}")
                continue

            if chunk.empty:
                processed_lines += len(chunk)
                if pbar:
                    pbar.update(len(chunk))
                continue

            # 转换nitrite单位：从μmol/kg到mmol/m³ (向量化操作)
            chunk['nitrite_predicted'] = convert_nitrite_unit(chunk['nitrite_predicted'])

            # 创建位置键（向量化操作）
            chunk['location_key'] = (
                    chunk['longitude'].astype(str) + '_' +
                    chunk['latitude'].astype(str) + '_' +
                    chunk['depth'].astype(str)
            )

            # 按位置计算年平均值（跨月份平均）
            yearly_avg = chunk.groupby('location_key').agg({
                'year': 'first',
                'longitude': 'first',
                'latitude': 'first',
                'depth': 'first',
                'nitrite_predicted': 'mean',
                'nitrate': 'mean'
            }).reset_index()

            # 删除辅助列
            yearly_avg = yearly_avg.drop('location_key', axis=1)

            all_results.append(yearly_avg)

            processed_lines += len(chunk)
            if pbar:
                pbar.update(len(chunk))

            # 每处理10个块显示一次内存清理
            if (chunk_num + 1) % 10 == 0:
                gc.collect()

        if pbar:
            pbar.close()

    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {str(e)}")
        return

    # 合并所有结果
    if all_results:
        print("正在合并结果...")
        combined_df = pd.concat(all_results, ignore_index=True)

        # 对相同位置的数据再次求平均（如果有重叠）
        print("正在计算最终平均值...")
        final_result = combined_df.groupby(['longitude', 'latitude', 'depth']).agg({
            'year': 'first',
            'nitrite_predicted': 'mean',
            'nitrate': 'mean'
        }).reset_index()

        # 重新排列列的顺序
        final_result = final_result[['year', 'longitude', 'latitude', 'depth', 'nitrite_predicted', 'nitrate']]

        # 保存结果
        output_file = os.path.join(output_folder, f"{filename}_processed.csv")
        final_result.to_csv(output_file, index=False)

        # 计算处理时间
        elapsed_time = time.time() - start_time

        print(f"✅ 处理完成！")
        print(f"📁 结果保存到: {output_file}")
        print(f"📊 输出数据行数: {len(final_result):,}")
        print(f"⏱️  处理时间: {elapsed_time:.2f}秒")
        print(f"🚀 处理速度: {processed_lines / elapsed_time:.0f}行/秒")

    else:
        print(f"⚠️  警告: 文件 {file_path} 没有有效数据")

    # 清理内存
    del all_results
    gc.collect()


def main():
    """主函数"""
    print("=== 优化版 CSV文件处理程序 ===")
    print("🔄 程序会将nitrite_predicted从μmol/kg转换为mmol/m³")
    print("📐 转换公式：mmol/m³ = μmol/kg × 1025 / 1000")
    print("⚡ 使用向量化操作和优化算法提高处理速度")
    print()

    # 选择输入文件夹
    input_folder = select_input_folder()
    if not input_folder:
        print("❌ 未选择输入文件夹，程序退出")
        return

    print(f"📂 选择的输入文件夹: {input_folder}")

    # 选择输出文件夹
    print("\n请选择输出文件夹...")
    output_folder = select_output_folder()
    if not output_folder:
        print("❌ 未选择输出文件夹，程序退出")
        return

    print(f"📂 选择的输出文件夹: {output_folder}")

    # 确保输出文件夹存在
    os.makedirs(output_folder, exist_ok=True)

    # 获取所有CSV文件
    csv_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.csv')]

    if not csv_files:
        print("❌ 文件夹中没有找到CSV文件")
        return

    print(f"📋 找到 {len(csv_files)} 个CSV文件")

    # 计算总处理时间
    total_start_time = time.time()

    # 逐个处理CSV文件
    for i, csv_file in enumerate(csv_files, 1):
        print(f"\n{'=' * 60}")
        print(f"📊 总进度: {i}/{len(csv_files)} ({i / len(csv_files) * 100:.1f}%)")
        print(f"📄 当前文件: {csv_file}")

        file_path = os.path.join(input_folder, csv_file)

        try:
            process_single_csv_optimized(file_path, output_folder)
        except Exception as e:
            print(f"❌ 处理文件 {csv_file} 时出错: {str(e)}")
            continue

        # 强制垃圾回收
        gc.collect()

    # 计算总处理时间
    total_elapsed_time = time.time() - total_start_time

    print(f"\n{'=' * 60}")
    print(f"🎉 === 全部处理完成 ===")
    print(f"📂 所有结果保存在: {output_folder}")
    print(f"⏱️  总处理时间: {total_elapsed_time:.2f}秒 ({total_elapsed_time / 60:.1f}分钟)")
    print(f"📁 处理了 {len(csv_files)} 个文件")
    print(f"🚀 平均每个文件处理时间: {total_elapsed_time / len(csv_files):.2f}秒")


if __name__ == "__main__":
    main()