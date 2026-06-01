import pandas as pd
import numpy as np
import os
from pathlib import Path
import glob
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import sys

# 修正的波段定义
UVB_RANGE = (290, 315)  # 修正为290-315nm
UVA_RANGE = (315, 400)  # 保持315-400nm
BLUE_RANGE = (400, 490)  # 修正为蓝光400-490nm


def calculate_cumulative_energy(wavelengths, irradiance_data, wave_range):
    """
    计算指定波段的累积能量
    wavelengths: 波长数组
    irradiance_data: 光照强度数据 (mW/m²/nm)
    wave_range: 波段范围 (min_wl, max_wl)
    返回: 累积能量 (mW/m²)
    """
    # 找到波段范围内的波长索引
    mask = (wavelengths >= wave_range[0]) & (wavelengths <= wave_range[1])

    if not np.any(mask):
        return 0.0

    # 选择波段内的数据
    band_wavelengths = wavelengths[mask]
    band_irradiance = irradiance_data[mask]  # mW/m²/nm

    # 积分计算能量密度：∫ I(λ) dλ，单位 mW/m²
    # 使用梯形法则进行数值积分
    energy_density = np.trapz(band_irradiance, band_wavelengths)  # mW/m²

    return energy_density


def process_hourly_file_to_daily_energy(input_file_path, output_dir=None):
    """
    从hourly_spectra文件重新计算daily_cumulative_energy文件

    Args:
        input_file_path: hourly_spectra文件路径
        output_dir: 输出目录，如果为None则使用输入文件所在目录

    Returns:
        输出文件路径
    """
    print(f"正在处理文件: {input_file_path}")

    # 检查输入文件是否存在
    if not os.path.exists(input_file_path):
        raise FileNotFoundError(f"输入文件不存在: {input_file_path}")

    # 读取hourly数据
    print("正在读取hourly光谱数据...")
    hourly_df = pd.read_csv(input_file_path)

    print(f"数据形状: {hourly_df.shape}")
    print(f"列名前10个: {hourly_df.columns[:10].tolist()}")

    # 提取波长列（280到700nm）
    wavelength_columns = [str(wl) for wl in range(280, 701) if str(wl) in hourly_df.columns]
    wavelengths = np.array([int(col) for col in wavelength_columns])

    print(f"找到波长列数量: {len(wavelength_columns)}")
    print(f"波长范围: {wavelengths[0]}-{wavelengths[-1]}nm")

    # 验证必要的列存在
    required_cols = ['latitude', 'longitude', 'year', 'month', 'day', 'hour',
                     'cld_opd', 'cld_reff_original', 'cld_reff_constrained', 'ozone']
    missing_cols = [col for col in required_cols if col not in hourly_df.columns]
    if missing_cols:
        raise ValueError(f"缺少必要的列: {missing_cols}")

    # 自动识别年月日
    years = hourly_df['year'].unique()
    months = hourly_df['month'].unique()
    days = hourly_df['day'].unique()

    print(f"\n=== 数据时间范围 ===")
    print(f"年份: {sorted(years)}")
    print(f"月份: {sorted(months)}")
    print(f"天数: {sorted(days)}")

    # 按天分组处理
    daily_energy_results = []

    # 按照经纬度、年、月、日分组
    grouped = hourly_df.groupby(['latitude', 'longitude', 'year', 'month', 'day'])

    print(f"\n开始处理 {len(grouped)} 天的数据...")

    for (lat, lon, year, month, day), day_group in grouped:
        print(f"  处理: {year}-{month:02d}-{day:02d}, 位置: ({lat:.3f}, {lon:.3f})")

        # 获取该天的云和臭氧参数（使用第一条记录的参数）
        first_record = day_group.iloc[0]
        cld_opd = first_record['cld_opd']
        cld_reff_original = first_record['cld_reff_original']
        cld_reff_constrained = first_record['cld_reff_constrained']
        ozone = first_record['ozone']

        # 初始化日累积能量
        daily_uvb_energy = 0.0
        daily_uva_energy = 0.0
        daily_blue_energy = 0.0

        # 遍历该天的每小时数据
        for _, hour_row in day_group.iterrows():
            # 提取该小时的光谱数据
            hour_spectrum = hour_row[wavelength_columns].values

            # 检查是否为有效数据（非全零）
            if np.sum(hour_spectrum) > 0:
                # 计算该小时各波段的能量密度 (mW/m²)
                uvb_power = calculate_cumulative_energy(wavelengths, hour_spectrum, UVB_RANGE)
                uva_power = calculate_cumulative_energy(wavelengths, hour_spectrum, UVA_RANGE)
                blue_power = calculate_cumulative_energy(wavelengths, hour_spectrum, BLUE_RANGE)

                # 累积能量：每小时的能量密度 × 3600秒，转换为J/m²
                daily_uvb_energy += uvb_power * 3600 / 1000  # mW → W，然后 × 3600s = J/m²
                daily_uva_energy += uva_power * 3600 / 1000
                daily_blue_energy += blue_power * 3600 / 1000

        # 存储该天的累积能量结果
        daily_energy_results.append({
            'latitude': lat,
            'longitude': lon,
            'year': int(year),
            'month': int(month),
            'day': int(day),
            'daily_uvb_energy_J_m2': daily_uvb_energy,
            'daily_uva_energy_J_m2': daily_uva_energy,
            'daily_blue_energy_J_m2': daily_blue_energy,  # 修改为蓝光
            'cld_opd': cld_opd,
            'cld_reff_original': cld_reff_original,
            'cld_reff_constrained': cld_reff_constrained,
            'ozone': ozone
        })

        print(
            f"    UVB: {daily_uvb_energy:.2f} J/m², UVA: {daily_uva_energy:.2f} J/m², BLUE: {daily_blue_energy:.2f} J/m²")

    # 转换为DataFrame
    energy_df = pd.DataFrame(daily_energy_results)

    # 确定输出目录和文件名
    if output_dir is None:
        output_dir = os.path.dirname(input_file_path)

    # 完全基于数据内容生成输出文件名，不依赖输入文件名格式
    if not energy_df.empty:
        # 获取数据中的时间范围
        years = sorted(energy_df['year'].unique())
        months = sorted(energy_df['month'].unique())

        if len(years) == 1 and len(months) == 1:
            # 单一年月的数据
            year = years[0]
            month = months[0]
            output_filename = f'daily_cumulative_energy_{year}_{month:02d}_revised.csv'
        elif len(years) == 1 and len(months) > 1:
            # 单一年份，多个月份
            year = years[0]
            month_start = months[0]
            month_end = months[-1]
            output_filename = f'daily_cumulative_energy_{year}_{month_start:02d}to{month_end:02d}_revised.csv'
        else:
            # 跨年或复杂情况
            year_start, year_end = years[0], years[-1]
            month_start, month_end = months[0], months[-1]
            output_filename = f'daily_cumulative_energy_{year_start}_{month_start:02d}_to_{year_end}_{month_end:02d}_revised.csv'
    else:
        # 空数据的情况
        input_filename = os.path.splitext(os.path.basename(input_file_path))[0]
        output_filename = f'{input_filename}_daily_energy_revised.csv'

    output_file_path = os.path.join(output_dir, output_filename)

    # 保存结果
    energy_df.to_csv(output_file_path, index=False)

    print(f"\n=== 处理完成 ===")
    print(f"已保存修正波段的日累积能量数据: {output_file_path}")
    print(f"数据行数: {len(energy_df)}")

    # 显示统计信息
    if not energy_df.empty:
        print(f"\n=== 修正波段累积能量统计 ===")
        print(f"UVB能量 ({UVB_RANGE[0]}-{UVB_RANGE[1]}nm, J/m²): "
              f"平均={energy_df['daily_uvb_energy_J_m2'].mean():.2f}, "
              f"范围=[{energy_df['daily_uvb_energy_J_m2'].min():.2f}, {energy_df['daily_uvb_energy_J_m2'].max():.2f}]")
        print(f"UVA能量 ({UVA_RANGE[0]}-{UVA_RANGE[1]}nm, J/m²): "
              f"平均={energy_df['daily_uva_energy_J_m2'].mean():.2f}, "
              f"范围=[{energy_df['daily_uva_energy_J_m2'].min():.2f}, {energy_df['daily_uva_energy_J_m2'].max():.2f}]")
        print(f"BLUE能量 ({BLUE_RANGE[0]}-{BLUE_RANGE[1]}nm, J/m²): "
              f"平均={energy_df['daily_blue_energy_J_m2'].mean():.2f}, "
              f"范围=[{energy_df['daily_blue_energy_J_m2'].min():.2f}, {energy_df['daily_blue_energy_J_m2'].max():.2f}]")

        print(f"\n=== 云滴半径统计 ===")
        reff_original = energy_df['cld_reff_original']
        reff_constrained = energy_df['cld_reff_constrained']
        print(f"原始值范围: [{reff_original.min():.3f}, {reff_original.max():.3f}] μm")
        print(f"约束后范围: [{reff_constrained.min():.3f}, {reff_constrained.max():.3f}] μm")

    return output_file_path


def batch_process_hourly_files(input_directory, output_directory=None):
    """
    批量处理目录下的所有hourly_spectra文件

    Args:
        input_directory: 包含hourly_spectra文件的目录
        output_directory: 输出目录，如果为None则使用输入目录
    """
    input_dir = Path(input_directory)
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_directory}")

    # 查找所有hourly_spectra文件
    hourly_files = list(input_dir.glob("hourly_spectra_*.csv"))

    if not hourly_files:
        print(f"在目录 {input_directory} 中未找到hourly_spectra文件")
        return []

    print(f"找到 {len(hourly_files)} 个hourly_spectra文件:")
    for file in hourly_files:
        print(f"  - {file.name}")

    # 设置输出目录
    if output_directory is None:
        output_directory = input_directory
    else:
        os.makedirs(output_directory, exist_ok=True)

    # 批量处理
    processed_files = []
    for input_file in hourly_files:
        try:
            output_file = process_hourly_file_to_daily_energy(str(input_file), output_directory)
            processed_files.append(output_file)
            print(f"✓ 成功处理: {input_file.name}")
        except Exception as e:
            print(f"✗ 处理失败 {input_file.name}: {e}")

    print(f"\n批量处理完成，成功处理 {len(processed_files)} 个文件")
    return processed_files


def select_input_file():
    """选择输入文件的GUI函数"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 设置文件对话框
    file_path = filedialog.askopenfilename(
        title="选择hourly_spectra文件",
        filetypes=[
            ("CSV文件", "*.csv"),
            ("所有文件", "*.*")
        ],
        initialdir=os.getcwd()
    )

    root.destroy()
    return file_path


def select_output_directory():
    """选择输出目录的GUI函数"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 设置目录对话框
    dir_path = filedialog.askdirectory(
        title="选择输出文件夹",
        initialdir=os.getcwd()
    )

    root.destroy()
    return dir_path


def select_input_directory():
    """选择输入目录的GUI函数（用于批量处理）"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 设置目录对话框
    dir_path = filedialog.askdirectory(
        title="选择包含hourly_spectra文件的文件夹",
        initialdir=os.getcwd()
    )

    root.destroy()
    return dir_path


def show_processing_mode_dialog():
    """显示处理模式选择对话框"""
    root = tk.Tk()
    root.title("光谱数据处理工具")
    root.geometry("500x300")

    # 居中显示窗口
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (250)
    y = (root.winfo_screenheight() // 2) - (150)
    root.geometry(f"500x300+{x}+{y}")

    mode_var = tk.StringVar()

    # 标题
    tk.Label(root, text="光谱数据处理工具", font=("Arial", 16, "bold")).pack(pady=20)

    # 波段信息
    tk.Label(root, text=f"UVB: {UVB_RANGE[0]}-{UVB_RANGE[1]}nm").pack()
    tk.Label(root, text=f"UVA: {UVA_RANGE[0]}-{UVA_RANGE[1]}nm").pack()
    tk.Label(root, text=f"蓝光: {BLUE_RANGE[0]}-{BLUE_RANGE[1]}nm").pack(pady=(0, 20))

    # 选择模式
    tk.Label(root, text="请选择处理模式:", font=("Arial", 12)).pack(pady=10)

    # 按钮
    tk.Button(
        root,
        text="处理单个文件",
        command=lambda: [mode_var.set("single"), root.quit()],
        width=20,
        height=2
    ).pack(pady=5)

    tk.Button(
        root,
        text="批量处理文件夹",
        command=lambda: [mode_var.set("batch"), root.quit()],
        width=20,
        height=2
    ).pack(pady=5)

    tk.Button(
        root,
        text="退出",
        command=lambda: [mode_var.set("exit"), root.quit()],
        width=20
    ).pack(pady=15)

    root.mainloop()

    mode = mode_var.get()
    root.destroy()

    return mode


def main_gui():
    """主GUI函数"""
    print("=== 光谱数据处理工具 ===")
    print(f"波段定义:")
    print(f"  UVB: {UVB_RANGE[0]}-{UVB_RANGE[1]}nm")
    print(f"  UVA: {UVA_RANGE[0]}-{UVA_RANGE[1]}nm")
    print(f"  BLUE: {BLUE_RANGE[0]}-{BLUE_RANGE[1]}nm")
    print()

    try:
        # 显示模式选择对话框
        mode = show_processing_mode_dialog()

        if mode == "exit" or not mode:
            print("程序已退出")
            return

        elif mode == "single":
            print("=== 单文件处理模式 ===")

            # 选择输入文件
            print("请选择hourly_spectra文件...")
            input_file = select_input_file()

            if not input_file:
                print("未选择输入文件，程序已退出")
                return

            print(f"已选择输入文件: {input_file}")

            # 选择输出目录
            print("请选择输出文件夹...")
            output_dir = select_output_directory()

            if not output_dir:
                print("未选择输出目录，将使用输入文件所在目录")
                output_dir = None
            else:
                print(f"已选择输出目录: {output_dir}")

            # 处理文件
            try:
                output_file = process_hourly_file_to_daily_energy(input_file, output_dir)

                # 显示成功对话框
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo("处理完成", f"文件处理成功！\n\n输出文件: {os.path.basename(output_file)}")
                root.destroy()

            except Exception as e:
                print(f"处理失败: {e}")

                # 显示错误对话框
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("处理失败", f"文件处理失败！\n\n{str(e)}")
                root.destroy()

        elif mode == "batch":
            print("=== 批量处理模式 ===")

            # 选择输入目录
            print("请选择包含hourly_spectra文件的文件夹...")
            input_dir = select_input_directory()

            if not input_dir:
                print("未选择输入目录，程序已退出")
                return

            print(f"已选择输入目录: {input_dir}")

            # 选择输出目录
            print("请选择输出文件夹...")
            output_dir = select_output_directory()

            if not output_dir:
                print("未选择输出目录，将使用输入目录")
                output_dir = None
            else:
                print(f"已选择输出目录: {output_dir}")

            # 批量处理
            try:
                processed_files = batch_process_hourly_files(input_dir, output_dir)

                if processed_files:
                    success_msg = f"批量处理完成！\n\n成功处理 {len(processed_files)} 个文件"

                    # 显示成功对话框
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showinfo("批量处理完成", success_msg)
                    root.destroy()
                else:
                    # 显示警告对话框
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showwarning("批量处理完成", "没有找到可处理的文件")
                    root.destroy()

            except Exception as e:
                print(f"批量处理失败: {e}")

                # 显示错误对话框
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("批量处理失败", f"批量处理失败！\n\n{str(e)}")
                root.destroy()

    except Exception as e:
        print(f"程序运行出错: {e}")

        # 显示错误对话框
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("程序错误", f"程序运行出错！\n\n{str(e)}")
        root.destroy()


# 主程序
if __name__ == "__main__":
    # 检查是否有GUI环境
    try:
        import tkinter as tk

        # 测试是否可以创建Tk实例
        test_root = tk.Tk()
        test_root.withdraw()
        test_root.destroy()

        # 运行GUI版本
        main_gui()

    except Exception as e:
        print(f"无法启动GUI界面 ({e})，使用命令行模式...")

        # 命令行模式 - 原有的代码逻辑
        input_file = "hourly_spectra_2018_06.csv"  # 修改为您的实际路径

        if os.path.exists(input_file):
            print("=== 处理单个文件 ===")
            output_file = process_hourly_file_to_daily_energy(input_file)
            print(f"输出文件: {output_file}")
        else:
            print(f"文件不存在: {input_file}")
            print("请修改 input_file 变量为您的实际文件路径")

        print("\n=== 修正波段定义 ===")
        print(f"UVB: {UVB_RANGE[0]}-{UVB_RANGE[1]}nm")
        print(f"UVA: {UVA_RANGE[0]}-{UVA_RANGE[1]}nm")
        print(f"BLUE: {BLUE_RANGE[0]}-{BLUE_RANGE[1]}nm")