import os
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt
from concurrent.futures import ProcessPoolExecutor
import multiprocessing


def select_folder(title):
    """
    打开对话框选择文件夹

    参数:
        title (str): 对话框窗口的标题

    返回:
        str: 选择的文件夹路径
    """
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    folder_path = filedialog.askdirectory(title=title)
    root.destroy()
    return folder_path


def get_year_from_filename(filename):
    """
    从文件名中提取年份

    参数:
        filename (str): 文件名

    返回:
        str: 从文件名中提取的年份
    """
    # 获取文件名（不含路径）
    base_name = os.path.basename(filename)
    # 提取文件名前四个字符作为年份
    year = base_name[:4]
    return year


def load_data(file_path, required_columns):
    """
    从文件加载数据并选择所需的列

    参数:
        file_path (str): 数据文件的路径
        required_columns (list): 要提取的列的列表

    返回:
        pd.DataFrame: 包含所需列的DataFrame
    """
    try:
        # 使用更高效的方式读取CSV，只读取需要的列
        df = pd.read_csv(file_path, usecols=required_columns)
        return df
    except Exception as e:
        print(f"加载{file_path}时出错: {e}")
        return None


def process_data_for_year(year_data):
    """
    处理特定年份的SeaWiFS和MODIS匹配数据文件，保存按SeaWiFS顺序排列的数据

    参数:
        year_data (tuple): (year, seawifs_file, modis_file, required_params, output_dir)

    返回:
        tuple: (year, matched_points_count, success_flag, year_sea_df, year_modis_df)
    """
    year, seawifs_file, modis_file, required_params, output_dir = year_data
    print(f"正在处理{year}年的数据")

    # 从两个来源加载数据
    print(f"  [1/4] 加载SeaWiFS数据: {os.path.basename(seawifs_file)}")
    seawifs_data = load_data(seawifs_file, required_params)

    print(f"  [2/4] 加载MODIS数据: {os.path.basename(modis_file)}")
    modis_data = load_data(modis_file, required_params)

    if seawifs_data is None or modis_data is None:
        print(f"无法加载{year}年的数据")
        return year, 0, False, None, None

    # 添加来源标识符
    seawifs_data['source'] = 'SeaWiFS'
    modis_data['source'] = 'MODIS'
    print(f"  [3/4] 数据加载完成 - SeaWiFS: {len(seawifs_data)}行, MODIS: {len(modis_data)}行")

    # 为坐标创建键 - 使用更高效的向量化操作
    precision = 5  # 根据数据的分辨率调整
    seawifs_data['latitude_rounded'] = np.round(seawifs_data['latitude'], precision)
    seawifs_data['longitude_rounded'] = np.round(seawifs_data['longitude'], precision)
    modis_data['latitude_rounded'] = np.round(modis_data['latitude'], precision)
    modis_data['longitude_rounded'] = np.round(modis_data['longitude'], precision)

    # 使用merge而不是循环来匹配坐标点
    print(f"  [4/4] 合并匹配坐标和保存数据")
    merged_data = pd.merge(
        seawifs_data,
        modis_data,
        on=['latitude_rounded', 'longitude_rounded'],
        suffixes=('_seawifs', '_modis')
    )

    common_coords_count = len(merged_data)
    print(f"      {year}年找到{common_coords_count}个共同坐标")

    if common_coords_count == 0:
        print(f"      {year}年未找到共同坐标，放弃处理")
        return year, 0, False, None, None

    # 准备输出的DataFrame
    # 为SeaWiFS数据准备列
    sea_output_columns = []
    for col in required_params:
        if col in seawifs_data.columns:  # 确保列存在
            sea_output_columns.append(f"{col}_seawifs")

    # 为MODIS数据准备列
    modis_output_columns = []
    for col in required_params:
        if col in modis_data.columns:  # 确保列存在
            modis_output_columns.append(f"{col}_modis")

    # 准备输出
    seawifs_output = merged_data[sea_output_columns].copy()
    seawifs_output.columns = [col.replace('_seawifs', '') for col in sea_output_columns]

    modis_output = merged_data[modis_output_columns].copy()
    modis_output.columns = [col.replace('_modis', '') for col in modis_output_columns]

    # 保存排序后的单独文件
    seawifs_output_path = os.path.join(output_dir, f"seawifs_filtered_{year}.csv")
    modis_output_path = os.path.join(output_dir, f"modis_filtered_{year}.csv")
    seawifs_output.to_csv(seawifs_output_path, index=False)
    modis_output.to_csv(modis_output_path, index=False)

    print(f"      已保存排序后的SeaWiFS数据到: {seawifs_output_path}")
    print(f"      已保存排序后的MODIS数据到: {modis_output_path}")

    # 为最终合并准备数据框
    # 1. SeaWiFS数据 - 添加SEA_前缀到所有列
    year_sea_df = seawifs_output.copy()
    sea_cols_mapping = {}
    for col in year_sea_df.columns:
        if col.startswith('Rrs_'):
            sea_cols_mapping[col] = f"SEA_{col}"
    year_sea_df = year_sea_df.rename(columns=sea_cols_mapping)

    # 2. MODIS数据 - 添加MODIS_前缀到所有列
    year_modis_df = modis_output.copy()
    modis_cols_mapping = {}
    for col in year_modis_df.columns:
        if col.startswith('Rrs_'):
            modis_cols_mapping[col] = f"MODIS_{col}"
    year_modis_df = year_modis_df.rename(columns=modis_cols_mapping)

    # 添加年份
    year_sea_df['year'] = year
    year_modis_df['year'] = year

    return year, common_coords_count, True, year_sea_df, year_modis_df


def combine_all_years_data(results, output_dir):
    """
    合并所有年份的数据并保存

    参数:
        results (list): 处理结果列表，每项为(year, matched_count, success, year_sea_df, year_modis_df)
        output_dir (str): 保存合并数据的目录
    """
    print("合并所有年份的数据...")
    all_seawifs = []
    all_modis = []
    all_combined = []
    successful_years = []

    for year, matched_count, success, year_sea_df, year_modis_df in sorted(results, key=lambda x: x[0]):
        if not success or year_sea_df is None or year_modis_df is None:
            continue

        successful_years.append(year)
        all_seawifs.append(year_sea_df)
        all_modis.append(year_modis_df)

        # 对于合并文件，我们需要添加前缀区分两个数据源的所有列
        # 为SeaWiFS添加前缀
        sea_df_with_prefix = year_sea_df.copy()
        # 先为已经添加了前缀的Rrs列创建列名映射（避免重复添加前缀）
        sea_cols_mapping = {}
        for col in sea_df_with_prefix.columns:
            if not col.startswith('SEA_'):
                sea_cols_mapping[col] = f'SEA_{col}'
        # 重命名列
        sea_df_with_prefix = sea_df_with_prefix.rename(columns=sea_cols_mapping)

        # 为MODIS添加前缀
        modis_df_with_prefix = year_modis_df.copy()
        # 先为已经添加了前缀的Rrs列创建列名映射
        modis_cols_mapping = {}
        for col in modis_df_with_prefix.columns:
            if not col.startswith('MODIS_'):
                modis_cols_mapping[col] = f'MODIS_{col}'
        # 重命名列
        modis_df_with_prefix = modis_df_with_prefix.rename(columns=modis_cols_mapping)

        # 确保两个数据框有相同的行
        if len(sea_df_with_prefix) == len(modis_df_with_prefix):
            # 合并同一年份的数据
            combined = pd.concat([sea_df_with_prefix, modis_df_with_prefix], axis=1)
            all_combined.append(combined)

    print(f"成功处理了{len(successful_years)}个年份: {successful_years}")

    # 合并所有年份的数据
    if all_seawifs:
        all_seawifs_df = pd.concat(all_seawifs, ignore_index=True)
        all_seawifs_output = os.path.join(output_dir, "all_years_seawifs_filtered.csv")
        all_seawifs_df.to_csv(all_seawifs_output, index=False)
        print(f"已保存所有年份SeaWiFS数据到: {all_seawifs_output}")

    if all_modis:
        all_modis_df = pd.concat(all_modis, ignore_index=True)
        all_modis_output = os.path.join(output_dir, "all_years_modis_filtered.csv")
        all_modis_df.to_csv(all_modis_output, index=False)
        print(f"已保存所有年份MODIS数据到: {all_modis_output}")

    if all_combined:
        all_combined_df = pd.concat(all_combined, ignore_index=True)

        # 移除可能的重复列（在合并过程中可能会出现）
        all_cols = list(all_combined_df.columns)
        duplicate_cols = [col for col in all_cols if all_cols.count(col) > 1]
        for col in duplicate_cols:
            # 找到所有重复列的索引
            indices = [i for i, x in enumerate(all_cols) if x == col]
            # 保留第一个，删除其余的
            for idx in indices[1:]:
                all_cols[idx] = None
        # 删除None值
        all_cols = [col for col in all_cols if col is not None]
        all_combined_df = all_combined_df[all_cols]

        all_combined_output = os.path.join(output_dir, "all_years_combined.csv")
        all_combined_df.to_csv(all_combined_output, index=False)
        print(f"已保存所有年份合并数据到: {all_combined_output}")


def main():
    print("选择SeaWiFS_Rrs数据文件夹...")
    seawifs_dir = select_folder("选择SeaWiFS_Rrs数据文件夹")
    if not seawifs_dir:
        print("未选择SeaWiFS_Rrs的文件夹。退出程序。")
        return

    print("选择MODIS_Rrs数据文件夹...")
    modis_dir = select_folder("选择MODIS_Rrs数据文件夹")
    if not modis_dir:
        print("未选择MODIS_Rrs的文件夹。退出程序。")
        return

    print("选择输出数据文件夹...")
    output_dir = select_folder("选择输出数据文件夹")
    if not output_dir:
        print("未选择输出文件夹。退出程序。")
        return

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 所需参数
    required_params = ['Rrs_412', 'Rrs_443', 'Rrs_490', 'Rrs_510', 'Rrs_555',
                       'Rrs_670', 'latitude', 'longitude', 'year']

    # 获取每个来源的文件列表
    print("正在扫描文件...")
    seawifs_files = [os.path.join(seawifs_dir, f) for f in os.listdir(seawifs_dir)
                     if os.path.isfile(os.path.join(seawifs_dir, f))]
    modis_files = [os.path.join(modis_dir, f) for f in os.listdir(modis_dir)
                   if os.path.isfile(os.path.join(modis_dir, f))]
    print(f"找到 {len(seawifs_files)} 个SeaWiFS文件和 {len(modis_files)} 个MODIS文件")

    # 将文件映射到年份
    print("正在映射文件到年份...")
    seawifs_years = {get_year_from_filename(f): f for f in seawifs_files}
    modis_years = {get_year_from_filename(f): f for f in modis_files}
    print(f"SeaWiFS识别了 {len(seawifs_years)} 个年份，MODIS识别了 {len(modis_years)} 个年份")

    # 查找共同年份
    common_years = set(seawifs_years.keys()).intersection(set(modis_years.keys()))
    print(f"找到{len(common_years)}个共同年份: {sorted(common_years)}")

    # 准备多进程处理
    year_data_list = []
    for year in sorted(common_years):
        year_data_list.append((year, seawifs_years[year], modis_years[year], required_params, output_dir))

    # 使用多进程处理数据
    max_workers = max(1, min(multiprocessing.cpu_count() - 1, len(common_years)))
    print(f"使用{max_workers}个CPU核心并行处理数据...")

    results = []
    # 多进程处理
    if max_workers > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_data_for_year, year_data_list))
    else:
        # 如果只有一个可用核心，则使用串行处理
        for year_data in year_data_list:
            results.append(process_data_for_year(year_data))

    # 合并并保存所有年份的数据
    combine_all_years_data(results, output_dir)
    print("所有数据处理完成！")


if __name__ == "__main__":
    main()