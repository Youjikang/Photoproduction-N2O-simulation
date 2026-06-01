import os
import xarray as xr
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
import glob
import re
from scipy.interpolate import RegularGridInterpolator, interp1d


def select_directory(title="选择文件夹"):
    """
    打开文件对话框让用户选择目录
    """
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 打开文件夹选择对话框
    directory = filedialog.askdirectory(title=title)

    # 如果用户取消选择，返回None
    if not directory:
        return None

    return directory


def process_nc_file_with_coords(input_file, coords_dir, output_dir, depth_interval=10,
                                output_format='csv', keep_nc=True, chunk_size=1000, target_vars=None):
    """
    处理单个NetCDF文件，使用坐标文件中的经纬度进行采样，并按照指定的深度间隔进行插值
    使用xarray的内置interp方法优化深度插值

    参数:
    input_file: str - 输入.nc文件路径
    coords_dir: str - 坐标文件目录
    output_dir: str - 输出目录
    depth_interval: float - 深度间隔（米）
    output_format: str - 输出格式 ('csv', 'netcdf' 或 'both')
    keep_nc: bool - 是否保留生成的netCDF文件
    chunk_size: int - 处理数据的块大小，用于控制内存使用
    target_vars: list - 需要处理的目标变量列表，默认为None（处理所有变量）

    返回:
    bool - 处理是否成功
    """
    try:
        print(f"\n处理文件: {os.path.basename(input_file)}")

        # 使用xarray打开nc文件，启用chunks选项以减少内存使用
        dataset = xr.open_dataset(input_file, chunks={'time': 'auto', 'depth': 'auto'})

        # 输出原始数据信息
        print("\n原始数据集信息:")
        print(f"维度: {dataset.dims}")

        # 检查深度信息
        has_depth = False
        if 'depth' in dataset.dims:
            has_depth = True
            orig_depths = dataset.depth.values
            print(f"深度范围: {orig_depths.min()} 至 {orig_depths.max()} 米")
            print(f"深度值数量: {len(orig_depths)}")

            # 基于用户指定的深度间隔创建新的深度层
            min_depth = np.floor(orig_depths.min() / depth_interval) * depth_interval
            max_depth = np.ceil(orig_depths.max() / depth_interval) * depth_interval
            new_depths = np.arange(min_depth, max_depth + depth_interval, depth_interval)
            print(f"将基于深度间隔 {depth_interval} 米创建 {len(new_depths)} 个新深度层")
            print(f"新深度范围: {new_depths.min()} 至 {new_depths.max()} 米")
        else:
            print("警告: 数据集中没有深度维度")
            new_depths = np.array([0])  # 如果没有深度维度，使用默认深度

        # 检查时间信息
        if 'time' in dataset.dims:
            # 将时间转换为datetime格式，但避免加载整个数组
            times = pd.to_datetime(dataset.time.values)
            print(f"时间范围: {times.min()} 到 {times.max()}")
            print(f"时间点数量: {len(times)}")

            # 提取年份信息
            years = np.unique([t.year for t in times])
            print(f"包含的年份: {years}")
        else:
            print("警告: 数据集中没有时间维度")
            years = [0]  # 如果没有时间维度，使用默认年份

        # 获取变量列表
        available_vars = list(dataset.data_vars)
        print(f"可用变量列表: {available_vars}")

        # 确定要处理的变量
        if target_vars is None:
            vars_to_process = available_vars
        else:
            # 过滤出存在于数据集中的目标变量
            vars_to_process = [var for var in target_vars if var in available_vars]
            if not vars_to_process:
                print(f"警告: 指定的目标变量 {target_vars} 在数据集中不存在!")
                print("将退出处理")
                return False

        print(f"将处理以下变量: {vars_to_process}")

        # 获取文件名（不包含路径和扩展名）
        base_filename = os.path.splitext(os.path.basename(input_file))[0]

        # 创建一个字典来存储每年的数据帧
        year_dfs = {year: [] for year in years}

        # 确定坐标文件，按年份匹配
        year_coords_files = {}
        for year in years:
            coords_pattern = f"filtered_{year}_filtered.csv"
            coords_file_path = os.path.join(coords_dir, coords_pattern)
            if os.path.exists(coords_file_path):
                year_coords_files[year] = coords_file_path
                print(f"找到{year}年的坐标文件: {coords_file_path}")
            else:
                # 找不到精确匹配的文件，尝试使用模糊匹配
                pattern = re.compile(f".*{year}.*\\.csv$")
                matching_files = [f for f in os.listdir(coords_dir) if pattern.match(f)]
                if matching_files:
                    year_coords_files[year] = os.path.join(coords_dir, matching_files[0])
                    print(f"使用模糊匹配找到{year}年的坐标文件: {matching_files[0]}")
                else:
                    print(f"警告: 找不到{year}年的坐标文件!")
                    # 可以在这里决定是跳过这一年，还是使用默认网格

        # 准备坐标数据
        year_coords = {}
        for year, coords_file in year_coords_files.items():
            try:
                coords_df = pd.read_csv(coords_file)
                # 检查是否有longitude和latitude列
                if 'longitude' in coords_df.columns and 'latitude' in coords_df.columns:
                    lon_col, lat_col = 'longitude', 'latitude'
                elif 'lon' in coords_df.columns and 'lat' in coords_df.columns:
                    lon_col, lat_col = 'lon', 'lat'
                else:
                    # 尝试找到可能的经纬度列
                    possible_lon_cols = [col for col in coords_df.columns if 'lon' in col.lower()]
                    possible_lat_cols = [col for col in coords_df.columns if 'lat' in col.lower()]

                    if possible_lon_cols and possible_lat_cols:
                        lon_col, lat_col = possible_lon_cols[0], possible_lat_cols[0]
                        print(f"使用推测的经纬度列: {lon_col}, {lat_col}")
                    else:
                        print(f"警告: 在{coords_file}中找不到经纬度列!")
                        continue

                # 获取唯一的经纬度坐标
                coords = coords_df[[lon_col, lat_col]].drop_duplicates().values
                year_coords[year] = coords
                print(f"从{coords_file}读取了{len(coords)}个唯一坐标点")
            except Exception as e:
                print(f"读取坐标文件{coords_file}时出错: {e}")
                continue

        # 确定nc文件中的经纬度变量名
        lon_name = 'longitude' if 'longitude' in dataset.dims else 'lon'
        lat_name = 'latitude' if 'latitude' in dataset.dims else 'lat'

        # 遍历时间维度，逐个时间点处理
        if 'time' in dataset.dims:
            for t_idx in range(len(times)):
                # 获取当前时间点
                current_time = times[t_idx]
                year = current_time.year
                month = current_time.month

                # 检查是否有该年份的坐标数据
                if year not in year_coords:
                    print(f"跳过时间点 {current_time}, 因为没有对应的坐标数据")
                    continue

                print(f"\n处理时间点: {current_time} ({t_idx + 1}/{len(times)})")

                try:
                    # 提取单个时间点的数据
                    time_slice = dataset.isel(time=t_idx)

                    # 获取网格经纬度数据
                    grid_lons = time_slice[lon_name].values
                    grid_lats = time_slice[lat_name].values

                    # 获取目标坐标点
                    target_coords = year_coords[year]

                    # 处理深度维度
                    if has_depth:
                        # 使用xarray的内置interp方法进行深度插值
                        # 这是关键优化点：一次性对所有深度进行插值而不是循环每个点
                        print("使用xarray的interp方法进行深度插值...")

                        # 创建插值后的数据集
                        interp_dataset = time_slice.interp(depth=new_depths, method='linear')

                        # 对每个深度层进行处理
                        for depth_idx, new_depth in enumerate(new_depths):
                            print(f"处理深度层 {new_depth:.1f} 米 ({depth_idx + 1}/{len(new_depths)})...")

                            # 创建数据字典，初始化坐标数据
                            data_rows = []

                            # 在特定深度处获取数据
                            depth_slice = interp_dataset.sel(depth=new_depth)

                            # 对每个变量进行处理
                            for var_name in vars_to_process:
                                if var_name in depth_slice:
                                    try:
                                        # 获取插值后的变量数据
                                        var_data = depth_slice[var_name].values

                                        # 使用scipy进行经纬度插值
                                        try:
                                            # 创建插值器（注意坐标顺序）
                                            interpolator = RegularGridInterpolator(
                                                (grid_lats, grid_lons),
                                                var_data,
                                                bounds_error=False,
                                                fill_value=np.nan
                                            )

                                            # 准备坐标点（注意坐标顺序：lat, lon）
                                            points = np.column_stack((target_coords[:, 1], target_coords[:, 0]))

                                            # 执行插值
                                            interpolated_values = interpolator(points)

                                            # 为每个坐标点创建一行数据
                                            for i, (lon, lat) in enumerate(target_coords):
                                                if i >= len(data_rows):
                                                    data_rows.append({
                                                        'year': year,
                                                        'month': month,
                                                        'depth': new_depth,
                                                        'longitude': lon,
                                                        'latitude': lat
                                                    })

                                                # 添加该变量的插值结果
                                                data_rows[i][var_name] = interpolated_values[i]
                                        except Exception as interp_error:
                                            print(
                                                f"经纬度插值变量 {var_name} 在深度 {new_depth} 米时出错: {interp_error}")
                                            continue
                                    except Exception as var_error:
                                        print(f"处理变量 {var_name} 在深度 {new_depth} 米时出错: {var_error}")
                                        continue

                            # 创建DataFrame并添加到对应年份的列表中
                            if data_rows:
                                temp_df = pd.DataFrame(data_rows)
                                temp_df = temp_df.dropna()  # 删除含NaN的行
                                year_dfs[year].append(temp_df)

                            # 清理临时对象，释放内存
                            del data_rows
                    else:
                        # 没有深度维度的处理
                        # 创建数据字典，初始化坐标数据
                        data_rows = []

                        # 对每个变量进行处理
                        for var_name in vars_to_process:
                            if var_name in time_slice:
                                # 获取变量数据
                                var_data = time_slice[var_name].values

                                # 使用scipy进行插值
                                try:
                                    interpolator = RegularGridInterpolator(
                                        (grid_lats, grid_lons),
                                        var_data,
                                        bounds_error=False,
                                        fill_value=np.nan
                                    )

                                    # 准备坐标点，注意坐标顺序 (lat, lon)
                                    points = np.column_stack((target_coords[:, 1], target_coords[:, 0]))

                                    # 执行插值
                                    interpolated_values = interpolator(points)

                                    # 为每个坐标点创建一行数据
                                    for i, (lon, lat) in enumerate(target_coords):
                                        if i >= len(data_rows):
                                            data_rows.append({
                                                'year': year,
                                                'month': month,
                                                'depth': 0,  # 默认深度为0
                                                'longitude': lon,
                                                'latitude': lat
                                            })

                                        # 添加该变量的插值结果
                                        data_rows[i][var_name] = interpolated_values[i]

                                except Exception as interp_error:
                                    print(f"插值变量 {var_name} 时出错: {interp_error}")
                                    continue

                        # 创建DataFrame并添加到对应年份的列表中
                        if data_rows:
                            temp_df = pd.DataFrame(data_rows)
                            temp_df = temp_df.dropna()  # 删除含NaN的行
                            year_dfs[year].append(temp_df)

                        # 清理临时对象，释放内存
                        del data_rows

                    # 检查是否需要定期保存数据，释放内存
                    # 如果某年的数据帧数量超过阈值，合并并保存
                    threshold = 10  # 可以根据实际情况调整
                    for y in year_dfs:
                        if len(year_dfs[y]) > threshold:
                            print(f"定期保存 {y} 年数据以释放内存...")
                            if year_dfs[y]:
                                # 合并数据帧
                                merged_df = pd.concat(year_dfs[y], ignore_index=True)

                                # 移除NaN值
                                merged_df = merged_df.dropna()

                                # 按年份保存CSV
                                year_csv_path = os.path.join(output_dir, f"{base_filename}_{y}_partial.csv")

                                # 如果文件已存在，追加模式写入，否则创建新文件
                                if os.path.exists(year_csv_path):
                                    merged_df.to_csv(year_csv_path, mode='a', header=False, index=False)
                                else:
                                    merged_df.to_csv(year_csv_path, index=False)

                                print(f"已保存 {y} 年部分数据至: {year_csv_path}")

                                # 清空该年的数据帧列表，释放内存
                                year_dfs[y] = []

                    # 清理本次迭代的临时变量
                    del time_slice
                    if has_depth:
                        del interp_dataset

                except Exception as time_error:
                    print(f"处理时间点 {current_time} 时出错: {time_error}")
                    continue

                # 显示进度
                if (t_idx + 1) % 5 == 0 or t_idx + 1 == len(times):
                    print(f"已处理 {t_idx + 1}/{len(times)} 个时间点")
        else:
            # 如果没有时间维度，处理整个数据集
            print("数据集没有时间维度，处理整个数据集...")
            year = 0  # 使用默认年份

            # 检查是否有该年份的坐标数据
            if year not in year_coords:
                print("警告: 没有找到默认年份的坐标数据，将跳过处理")
            else:
                # 获取网格经纬度数据
                grid_lons = dataset[lon_name].values
                grid_lats = dataset[lat_name].values

                # 获取目标坐标点
                target_coords = year_coords[year]

                # 处理每个新深度层
                if has_depth:
                    # 使用xarray的interp方法进行深度插值
                    print("使用xarray的interp方法进行深度插值...")
                    interp_dataset = dataset.interp(depth=new_depths, method='linear')

                    for depth_idx, new_depth in enumerate(new_depths):
                        print(f"处理深度层 {new_depth:.1f} 米 ({depth_idx + 1}/{len(new_depths)})...")

                        # 创建数据字典，初始化坐标数据
                        data_rows = []

                        # 获取特定深度的数据
                        depth_slice = interp_dataset.sel(depth=new_depth)

                        # 对每个变量进行处理
                        for var_name in vars_to_process:
                            if var_name in depth_slice:
                                try:
                                    # 获取变量数据
                                    var_data = depth_slice[var_name].values

                                    # 使用scipy进行经纬度插值
                                    interpolator = RegularGridInterpolator(
                                        (grid_lats, grid_lons),
                                        var_data,
                                        bounds_error=False,
                                        fill_value=np.nan
                                    )

                                    # 准备坐标点，注意坐标顺序 (lat, lon)
                                    points = np.column_stack((target_coords[:, 1], target_coords[:, 0]))

                                    # 执行插值
                                    interpolated_values = interpolator(points)

                                    # 为每个坐标点创建一行数据
                                    for i, (lon, lat) in enumerate(target_coords):
                                        if i >= len(data_rows):
                                            data_rows.append({
                                                'year': year,
                                                'month': 0,
                                                'depth': new_depth,
                                                'longitude': lon,
                                                'latitude': lat
                                            })

                                        # 添加该变量的插值结果
                                        data_rows[i][var_name] = interpolated_values[i]
                                except Exception as interp_error:
                                    print(f"插值变量 {var_name} 在深度 {new_depth} 米时出错: {interp_error}")
                                    continue

                        # 创建DataFrame并添加到对应年份的列表中
                        if data_rows:
                            temp_df = pd.DataFrame(data_rows)
                            temp_df = temp_df.dropna()  # 删除含NaN的行
                            year_dfs[year].append(temp_df)

                        # 清理临时对象，释放内存
                        del data_rows
                else:
                    # 没有深度维度
                    # 创建数据字典，初始化坐标数据
                    data_rows = []

                    # 对每个变量进行处理
                    for var_name in vars_to_process:
                        if var_name in dataset:
                            # 获取变量数据
                            var_data = dataset[var_name].values

                            # 使用scipy进行插值
                            try:
                                interpolator = RegularGridInterpolator(
                                    (grid_lats, grid_lons),
                                    var_data,
                                    bounds_error=False,
                                    fill_value=np.nan
                                )

                                # 准备坐标点，注意坐标顺序 (lat, lon)
                                points = np.column_stack((target_coords[:, 1], target_coords[:, 0]))

                                # 执行插值
                                interpolated_values = interpolator(points)

                                # 为每个坐标点创建一行数据
                                for i, (lon, lat) in enumerate(target_coords):
                                    if i >= len(data_rows):
                                        data_rows.append({
                                            'year': year,
                                            'month': 0,
                                            'depth': 0,
                                            'longitude': lon,
                                            'latitude': lat
                                        })

                                    # 添加该变量的插值结果
                                    data_rows[i][var_name] = interpolated_values[i]

                            except Exception as interp_error:
                                print(f"插值变量 {var_name} 时出错: {interp_error}")
                                continue

                    # 创建DataFrame并添加到对应年份的列表中
                    if data_rows:
                        temp_df = pd.DataFrame(data_rows)
                        temp_df = temp_df.dropna()  # 删除含NaN的行
                        year_dfs[year].append(temp_df)

                    # 清理临时对象，释放内存
                    del data_rows

        # 最终保存每年的数据
        print("\n最终保存每年数据...")
        for year, dfs in year_dfs.items():
            if dfs:  # 如果该年有数据
                try:
                    # 合并该年的所有数据帧
                    year_df = pd.concat(dfs, ignore_index=True)

                    # 移除NaN值
                    year_df = year_df.dropna()

                    # 生成该年的输出文件名
                    year_csv_path = os.path.join(output_dir, f"{base_filename}_{year}.csv")

                    # 如果存在部分文件，则需要合并
                    partial_path = os.path.join(output_dir, f"{base_filename}_{year}_partial.csv")
                    if os.path.exists(partial_path):
                        # 读取部分文件
                        partial_df = pd.read_csv(partial_path)

                        # 合并所有数据
                        full_df = pd.concat([partial_df, year_df], ignore_index=True)

                        # 保存完整数据
                        full_df.to_csv(year_csv_path, index=False)

                        # 删除部分文件
                        os.remove(partial_path)

                        print(f"{year}年数据已合并并保存至: {year_csv_path}")
                        print(f"记录数: {len(full_df)}")

                        # 清理
                        del partial_df, full_df
                    else:
                        # 直接保存数据
                        year_df.to_csv(year_csv_path, index=False)
                        print(f"{year}年数据已保存至: {year_csv_path}")
                        print(f"记录数: {len(year_df)}")

                    # 输出简要统计信息
                    if 'depth' in year_df.columns:
                        print(f"深度范围: {year_df['depth'].min()} 至 {year_df['depth'].max()} 米")
                    print(f"经度范围: {year_df['longitude'].min()} 至 {year_df['longitude'].max()}")
                    print(f"纬度范围: {year_df['latitude'].min()} 至 {year_df['latitude'].max()}")

                    # 清理，释放内存
                    del year_df

                except Exception as save_error:
                    print(f"保存{year}年数据时出错: {save_error}")

        # 如果需要保存为NetCDF格式
        if output_format in ['netcdf', 'both']:
            print("\n不支持将按坐标采样的数据保存为NetCDF格式")
            print("已跳过NetCDF输出")

        # 关闭数据集
        dataset.close()

        # 执行垃圾回收，释放内存
        import gc
        gc.collect()

        print("\n处理完成!")
        return True

    except Exception as e:
        print(f"处理文件 {input_file} 时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def batch_process_nc_files_with_coords(input_dir, coords_dir, output_dir, depth_interval=10,
                                       output_format='csv', keep_nc=True, chunk_size=1000, memory_threshold=70,
                                       target_vars=None):
    """
    批量处理NC文件，使用坐标文件中的坐标进行采样，并基于指定的深度间隔进行插值

    参数:
    input_dir: 输入NC文件目录
    coords_dir: 坐标文件目录
    output_dir: 输出目录
    depth_interval: 深度间隔（米）
    output_format: 输出格式
    keep_nc: 是否保留NetCDF文件
    chunk_size: 处理块大小
    memory_threshold: 内存使用阈值百分比
    target_vars: 需要处理的目标变量列表

    返回:
    成功处理的文件数量
    """
    # 获取所有.nc文件
    nc_files = glob.glob(os.path.join(input_dir, "*.nc"))

    if not nc_files:
        print("没有找到.nc文件")
        return 0

    print(f"找到 {len(nc_files)} 个.nc文件")

    # 获取所有坐标文件
    coords_files = glob.glob(os.path.join(coords_dir, "*.csv"))

    if not coords_files:
        print("警告: 坐标文件目录中没有找到.csv文件!")
        return 0

    print(f"找到 {len(coords_files)} 个坐标文件")

    # 创建输出目录（如果不存在）
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 初始化计数器
    success_count = 0
    fail_count = 0

    # 尝试导入psutil库以监控内存使用
    try:
        import psutil
        can_monitor_memory = True
    except ImportError:
        can_monitor_memory = False

    # 处理每个文件
    for i, nc_file in enumerate(nc_files):
        print(f"\n处理文件 {i + 1}/{len(nc_files)}: {os.path.basename(nc_file)}")

        # 检查内存使用情况
        if can_monitor_memory:
            memory_usage = psutil.virtual_memory().percent
            if memory_usage > memory_threshold:
                print(f"警告: 内存使用率 ({memory_usage}%) 超过阈值 ({memory_threshold}%)")
                print("建议手动释放内存或减小处理块大小")
                user_input = input("是否继续处理? (y/n): ").lower().strip()
                if user_input != 'y':
                    print("中断处理")
                    break

        # 处理文件
        success = process_nc_file_with_coords(
            nc_file,
            coords_dir,
            output_dir,
            depth_interval,
            output_format,
            keep_nc,
            chunk_size,
            target_vars
        )

        # 更新计数器
        if success:
            success_count += 1
        else:
            fail_count += 1

        # 处理完一个文件后，强制执行垃圾回收
        import gc
        gc.collect()

    # 打印总结
    print("\n处理完成！")
    print(f"成功处理: {success_count}/{len(nc_files)} 个文件")
    if fail_count > 0:
        print(f"处理失败: {fail_count}/{len(nc_files)} 个文件")

    return success_count


def main():
    """
    主函数，使用坐标文件进行采样，并基于用户指定的深度间隔进行插值
    """
    print("=" * 50)
    print("NetCDF文件处理与按坐标采样工具 (优化版)")
    print("=" * 50)

    # 选择输入目录
    print("\n请选择包含.nc文件的输入目录:")
    input_dir = select_directory("选择输入目录")
    if not input_dir:
        print("未选择输入目录，程序退出")
        return

    # 选择坐标文件目录
    print("\n请选择包含坐标CSV文件的目录:")
    coords_dir = select_directory("选择坐标文件目录")
    if not coords_dir:
        print("未选择坐标文件目录，程序退出")
        return

    # 选择输出目录
    print("\n请选择处理后文件的保存目录:")
    output_dir = select_directory("选择输出目录")
    if not output_dir:
        print("未选择输出目录，程序退出")
        return

    # 设置目标变量
    target_vars = ["no3", "o2", "po4", "si"]
    print(f"\n将处理以下变量: {target_vars}")

    # 设置重采样参数
    print("\n请设置采样参数:")

    # 深度间隔
    depth_interval_str = input("请输入深度间隔（米，默认为10）: ").strip()
    depth_interval = 10
    if depth_interval_str:
        try:
            depth_interval = float(depth_interval_str)
            if depth_interval <= 0:
                print("深度间隔必须大于0，将使用默认值10米")
                depth_interval = 10
        except ValueError:
            print("无效的输入，将使用默认值10米")

    print(f"将使用深度间隔: {depth_interval}米 进行插值生成新的深度层")

    # 输出格式
    format_options = {
        '1': 'csv',
        '2': 'netcdf',
        '3': 'both'
    }
    print("\n请选择输出格式:")
    print("1. 仅CSV (默认)")
    print("2. 仅NetCDF (注意: 坐标采样模式下不支持NetCDF输出)")
    print("3. CSV和NetCDF都输出 (注意: 坐标采样模式下不支持NetCDF输出)")

    format_choice = input("请输入选项编号 [1-3]: ").strip()
    output_format = format_options.get(format_choice, 'csv')

    # 是否保留中间NC文件
    if output_format != 'netcdf' and output_format != 'both':
        keep_nc_choice = input("\n是否保留生成的NetCDF文件? (y/n, 默认为n): ").lower().strip()
        keep_nc = keep_nc_choice == 'y'
    else:
        keep_nc = True

    # 高级设置 - 内存和性能优化
    print("\n高级设置 (内存和性能优化):")

    # 处理块大小
    chunk_size_str = input("请输入处理块大小 (默认为1000): ").strip()
    chunk_size = 1000
    if chunk_size_str:
        try:
            chunk_size = int(chunk_size_str)
            if chunk_size <= 0:
                print("处理块大小必须大于0，将使用默认值1000")
                chunk_size = 1000
        except ValueError:
            print("无效的输入，将使用默认值1000")

    # 内存使用阈值
    memory_threshold_str = input("请输入内存使用阈值百分比 (达到该值时暂停处理，默认为70): ").strip()
    memory_threshold = 70
    if memory_threshold_str:
        try:
            memory_threshold = float(memory_threshold_str)
            if memory_threshold <= 0 or memory_threshold > 95:
                print("内存阈值必须在0-95之间，将使用默认值70%")
                memory_threshold = 70
        except ValueError:
            print("无效的输入，将使用默认值70%")

    # 显示处理参数
    print("\n处理参数:")
    print(f"输入目录: {input_dir}")
    print(f"坐标文件目录: {coords_dir}")
    print(f"输出目录: {output_dir}")
    print(f"处理变量: {target_vars}")
    print(f"深度间隔: {depth_interval}米 (将用于生成新的深度层)")
    print(f"输出格式: {output_format}")
    if output_format != 'netcdf' and output_format != 'both':
        print(f"保留NetCDF文件: {'是' if keep_nc else '否'}")
    print(f"处理块大小: {chunk_size}")
    print(f"内存使用阈值: {memory_threshold}%")

    # 确认处理
    confirm = input("\n确认开始处理? (y/n): ").lower().strip()
    if confirm != 'y':
        print("已取消处理，程序退出")
        return

    # 检查内存监控库
    try:
        import psutil
        current_memory = psutil.virtual_memory().percent
        print(f"当前系统内存使用率: {current_memory}%")
    except ImportError:
        print("提示: 安装psutil库可以更好地监控内存使用情况")
        print("可以使用 pip install psutil 安装")

    # 开始批处理
    print("\n开始批量处理.nc文件，使用坐标文件进行采样...")
    processed_count = batch_process_nc_files_with_coords(
        input_dir,
        coords_dir,
        output_dir,
        depth_interval,
        output_format,
        keep_nc,
        chunk_size,
        memory_threshold,
        target_vars
    )

    if processed_count > 0:
        print(f"\n处理完成! 成功处理了 {processed_count} 个文件")
        print(f"处理后的文件保存在: {output_dir}")
    else:
        print("\n未能成功处理任何文件")


if __name__ == "__main__":
    main()