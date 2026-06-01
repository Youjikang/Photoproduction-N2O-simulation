import numpy as np
import pandas as pd
import os
import time
from scipy.interpolate import CubicSpline
from tkinter import Tk, filedialog
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys


def progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█'):
    """自定义进度条，不依赖tqdm"""
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        print()


def main():
    start_time = time.time()

    # 隐藏主窗口
    root = Tk()
    root.withdraw()

    # 选择输入文件夹
    input_folder = filedialog.askdirectory(title="选择含有CSV文件的输入文件夹")
    if not input_folder:
        print("未选择输入文件夹")
        return

    # 选择输出文件夹
    output_folder = filedialog.askdirectory(title="选择输出文件夹")
    if not output_folder:
        print("未选择输出文件夹")
        return

    # 获取输入文件夹中的所有CSV文件
    csv_files = [f for f in os.listdir(input_folder) if f.endswith('.csv')]

    if not csv_files:
        print("输入文件夹中没有CSV文件")
        return

    total_files = len(csv_files)
    print(f"找到{total_files}个CSV文件，开始处理...")

    # 已知的波长和对应的Kd列名
    wavelengths_known = [320, 340, 380, 412, 443, 490]
    kd_columns = ['Kd_320', 'Kd_340', 'Kd_380', 'Kd_412', 'Kd_443', 'Kd_490']

    # 定义需要外推的波长范围 (290–319nm) 和插值范围 (320–490nm)
    wavelengths_extrapolated = np.arange(290, 320)
    wavelengths_interpolated = np.arange(320, 491)
    wavelengths_full = np.concatenate([wavelengths_extrapolated, wavelengths_interpolated])

    # 设置批处理大小 - 每次处理一小批数据以减少内存使用
    batch_size = 100000  # 每批处理10万行，可以根据内存情况调整

    # 使用15个处理核心进行并行计算
    num_workers = 15
    print(f"使用{num_workers}个处理核心并行计算")
    print(f"批处理大小: {batch_size}行/批")

    # 显示初始进度条
    progress_bar(0, total_files, prefix='文件处理进度:', suffix='完成', length=50)

    processed_files = 0

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {}

        # 提交所有任务
        for csv_file in csv_files:
            input_path = os.path.join(input_folder, csv_file)
            year = os.path.splitext(csv_file)[0]  # 假设文件名是年份
            output_kd_path = os.path.join(output_folder, f"{year}_kd_spectra.csv")
            output_ag_path = os.path.join(output_folder, f"{year}_ag_spectra.csv")

            future = executor.submit(
                process_file_in_batches,
                input_path,
                output_kd_path,
                output_ag_path,
                kd_columns,
                wavelengths_known,
                wavelengths_extrapolated,
                wavelengths_interpolated,
                wavelengths_full,
                batch_size
            )
            futures[future] = csv_file

        # 收集结果并更新进度
        for future in as_completed(futures):
            csv_file = futures[future]
            try:
                rows_processed, processing_time = future.result()
                print(f"✅ {csv_file}: 处理了{rows_processed}行数据，耗时{processing_time:.2f}秒")
            except Exception as e:
                print(f"❌ {csv_file} 处理失败: {str(e)}")
                import traceback
                print(traceback.format_exc())

            # 更新进度条
            processed_files += 1
            progress_bar(processed_files, total_files, prefix='文件处理进度:', suffix='完成', length=50)

    end_time = time.time()
    total_time = end_time - start_time
    print(f"所有文件处理完成!")
    print(f"总耗时: {total_time:.2f}秒 (平均每个文件{total_time / len(csv_files):.2f}秒)")


def process_file_in_batches(input_path, output_kd_path, output_ag_path, kd_columns,
                            wavelengths_known, wavelengths_extrapolated,
                            wavelengths_interpolated, wavelengths_full, batch_size):
    """分批处理单个CSV文件，减少内存使用"""
    file_start_time = time.time()
    file_name = os.path.basename(input_path)

    # 首先计算总行数
    total_rows = sum(1 for _ in pd.read_csv(input_path, chunksize=batch_size))
    print(f"开始处理 {file_name}，估计共{total_rows * batch_size}行数据...")

    # 准备波长列名
    wavelength_cols = [str(w) for w in wavelengths_full]

    # 初始化结果文件，写入表头
    kd_header = ','.join(wavelength_cols)
    ag_header = ','.join(wavelength_cols)

    # 读取第一个块，获取所有列名
    first_chunk = next(pd.read_csv(input_path, chunksize=1))

    # 保留原始数据中的其他列名（非Kd列）
    other_columns = [col for col in first_chunk.columns if col not in kd_columns]

    if other_columns:
        kd_header += ',' + ','.join(other_columns)
        ag_header += ',' + ','.join(other_columns)

    with open(output_kd_path, 'w') as kd_file:
        kd_file.write(kd_header + '\n')

    with open(output_ag_path, 'w') as ag_file:
        ag_file.write(ag_header + '\n')

    # 分批读取和处理数据
    total_processed = 0

    for chunk_num, chunk in enumerate(pd.read_csv(input_path, chunksize=batch_size)):
        chunk_rows = len(chunk)
        total_processed += chunk_rows

        # 报告进度
        progress = total_processed / (total_rows * batch_size) * 100 if total_rows > 0 else 100
        print(f"  {file_name}: 正在处理第{chunk_num + 1}批 ({progress:.1f}%)...")

        # 处理当前块的数据
        kd_values = chunk[kd_columns].values
        kd320 = kd_values[:, 0]
        kd340 = kd_values[:, 1]

        # 计算SKd (向量化操作)
        skd = (np.log(kd340) - np.log(kd320)) / (340 - 320)

        # 逐行处理并直接写入文件，避免大数组
        with open(output_kd_path, 'a') as kd_file, open(output_ag_path, 'a') as ag_file:
            for i in range(chunk_rows):
                # 外推 290-319nm
                kd_extrapolated = extrapolate_kd(kd320[i], skd[i], wavelengths_extrapolated)

                # 立方插值 320-490nm
                kd_interpolated = compute_kd_spectrum(wavelengths_known, kd_values[i], wavelengths_interpolated)

                # 合并结果 (Kd)
                kd_spectrum = np.concatenate([kd_extrapolated, kd_interpolated])

                # 计算 ag 光谱 (290-490nm)
                ag_spectrum = compute_ag_spectrum(kd320[i], wavelengths_full)

                # 转换为字符串并写入文件
                kd_line = ','.join([str(x) for x in kd_spectrum])
                ag_line = ','.join([str(x) for x in ag_spectrum])

                # 添加其他列
                if other_columns:
                    other_values = ','.join([str(chunk.iloc[i][col]) for col in other_columns])
                    kd_line += ',' + other_values
                    ag_line += ',' + other_values

                kd_file.write(kd_line + '\n')
                ag_file.write(ag_line + '\n')

    file_end_time = time.time()
    processing_time = file_end_time - file_start_time

    return total_processed, processing_time


def extrapolate_kd(kd320, skd, wavelengths):
    """外推函数，用于290-319nm"""
    return kd320 * np.exp(skd * (wavelengths - 320))


def compute_kd_spectrum(wavelengths_known, kd_known, wavelengths_full):
    """插值函数，用于320-490nm (使用scipy的CubicSpline)"""
    cs = CubicSpline(wavelengths_known, kd_known)
    return cs(wavelengths_full)


def compute_ag_spectrum(kd320, wavelengths, sag=0.0194):
    """计算ag光谱的函数"""
    ag320 = 0.68 * kd320
    ag_spectrum = ag320 * np.exp(-sag * (wavelengths - 320))
    return ag_spectrum


if __name__ == "__main__":
    main()