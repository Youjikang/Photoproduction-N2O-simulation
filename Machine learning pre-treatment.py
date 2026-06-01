import os
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt


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
        # 读取数据 - 根据您的文件格式调整参数
        # 这里假设是CSV格式，但您可能需要针对其他格式进行修改
        df = pd.read_csv(file_path)

        # 检查是否存在所有所需的列
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            print(f"警告: {file_path}中缺少以下列: {missing_columns}")
            return None

        # 只选择所需的列
        df = df[required_columns]

        return df

    except Exception as e:
        print(f"加载{file_path}时出错: {e}")
        return None


def process_data_for_year(seawifs_file, modis_file, required_params, output_dir):
    """
    处理特定年份的SeaWiFS和MODIS匹配数据文件，仅保存过滤后的单独文件

    参数:
        seawifs_file (str): SeaWiFS数据文件的路径
        modis_file (str): MODIS数据文件的路径
        required_params (list): 所需参数/列的列表
        output_dir (str): 保存处理后数据的目录

    返回:
        tuple: (matched_points_count, success_flag)
    """
    year = get_year_from_filename(seawifs_file)
    print(f"正在处理{year}年的数据")

    # 从两个来源加载数据
    print(f"  [1/6] 加载SeaWiFS数据: {os.path.basename(seawifs_file)}")
    seawifs_data = load_data(seawifs_file, required_params)

    print(f"  [2/6] 加载MODIS数据: {os.path.basename(modis_file)}")
    modis_data = load_data(modis_file, required_params)

    if seawifs_data is None or modis_data is None:
        print(f"无法加载{year}年的数据")
        return 0, False

    # 添加来源标识符
    print(f"  [3/6] 添加数据源标识")
    seawifs_data['source'] = 'SeaWiFS'
    modis_data['source'] = 'MODIS'
    print(f"      SeaWiFS数据: {len(seawifs_data)}行")
    print(f"      MODIS数据: {len(modis_data)}行")

    # 为每个经纬度对创建唯一键以进行匹配
    # 舍入到特定精度以处理浮点比较问题
    print(f"  [4/6] 创建坐标匹配键")
    precision = 5  # 根据数据的分辨率调整
    seawifs_data['coord_key'] = seawifs_data.apply(
        lambda row: f"{round(row['latitude'], precision)}_{round(row['longitude'], precision)}",
        axis=1
    )
    modis_data['coord_key'] = modis_data.apply(
        lambda row: f"{round(row['latitude'], precision)}_{round(row['longitude'], precision)}",
        axis=1
    )

    # 查找共同坐标
    print(f"  [5/6] 查找共同坐标")
    common_coords = set(seawifs_data['coord_key']).intersection(set(modis_data['coord_key']))
    print(f"      {year}年找到{len(common_coords)}个共同坐标")

    if len(common_coords) == 0:
        print(f"      {year}年未找到共同坐标，放弃处理")
        return 0, False

    # 过滤数据以仅保留共同坐标
    print(f"  [6/6] 过滤数据仅保留共同坐标并保存")
    seawifs_filtered = seawifs_data[seawifs_data['coord_key'].isin(common_coords)]
    modis_filtered = modis_data[modis_data['coord_key'].isin(common_coords)]
    print(f"      过滤后SeaWiFS数据: {len(seawifs_filtered)}行")
    print(f"      过滤后MODIS数据: {len(modis_filtered)}行")

    # 移除不需要的列并保存过滤后的单独文件
    seawifs_filtered = seawifs_filtered.drop(['source', 'coord_key'], axis=1)
    modis_filtered = modis_filtered.drop(['source', 'coord_key'], axis=1)

    seawifs_output = os.path.join(output_dir, f"seawifs_filtered_{year}.csv")
    modis_output = os.path.join(output_dir, f"modis_filtered_{year}.csv")
    seawifs_filtered.to_csv(seawifs_output, index=False)
    modis_filtered.to_csv(modis_output, index=False)
    print(f"      已保存过滤后的SeaWiFS数据到: {seawifs_output}")
    print(f"      已保存过滤后的MODIS数据到: {modis_output}")

    return len(common_coords), True


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

    # 处理每一年
    successful_years = []
    total_years = len(common_years)

    for index, year in enumerate(sorted(common_years), 1):
        print(f"\n--- 处理进度: {index}/{total_years} ({index / total_years * 100:.1f}%) ---")
        print(f"开始处理 {year} 年的数据 ({index}/{total_years})")

        seawifs_file = seawifs_years[year]
        modis_file = modis_years[year]

        matched_count, success = process_data_for_year(seawifs_file, modis_file, required_params, output_dir)
        if success:
            successful_years.append(year)
            print(f"✓ {year}年处理成功")
        else:
            print(f"✗ {year}年处理失败")

    print(f"成功处理了{len(successful_years)}个年份: {successful_years}")


if __name__ == "__main__":
    main()