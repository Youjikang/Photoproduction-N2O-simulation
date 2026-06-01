import numpy as np
import pandas as pd
import os
from tkinter import Tk, filedialog
from tqdm import tqdm

# 定义 SeaWiFS 传感器的四阶多项式系数 (unchanged)
seaWiFS_coefficients = {
    'a0': -0.8515,
    'a1': -1.8263,
    'a2': 1.8714,
    'a3': -2.4414,
    'a4': -1.0690
}

# 定义 R(λ) 的均值和标准差（Kd < 0.32 和 Kd > 0.32） (unchanged)
R_mean_std_low_kd = {
    'R_412': {'mean': -5.3340, 'std': 0.8637},
    'R_443': {'mean': -5.2589, 'std': 0.7808},
    'R_490': {'mean': -5.0970, 'std': 0.7268},
    'R_510': {'mean': -5.2474, 'std': 0.7483},
    'R_555': {'mean': -5.5939, 'std': 0.8208},
    'R_670': {'mean': -7.9649, 'std': 0.8836}
}

R_mean_std_high_kd = {
    'R_412': {'mean': -6.8156, 'std': 1.0703},
    'R_443': {'mean': -6.3098, 'std': 0.9956},
    'R_490': {'mean': -5.6367, 'std': 0.8839},
    'R_510': {'mean': -5.4596, 'std': 0.8599},
    'R_555': {'mean': -5.0692, 'std': 0.7490},
    'R_670': {'mean': -5.9379, 'std': 0.7485}
}

# 定义 PC1 到 PC4 的系数（Kd < 0.32 和 Kd > 0.32） (unchanged)
e_coefficients_low_kd = {
    'PC1': {'412': -0.3976, '443': -0.4237, '490': -0.4521, '510': -0.4540, '555': -0.4159, '670': -0.2809},
    'PC2': {'412': 0.4481, '443': 0.3497, '490': 0.1303, '510': -0.0670, '555': -0.3652, '670': -0.7226},
    'PC3': {'412': 0.3990, '443': 0.2370, '490': -0.1326, '510': -0.3724, '555': -0.4920, '670': 0.6215},
    'PC4': {'412': 0.5829, '443': -0.2240, '490': -0.5733, '510': -0.1354, '555': 0.5045, '670': -0.0928}
}

e_coefficients_high_kd = {
    'PC1': {'412': -0.4019, '443': -0.4224, '490': -0.4295, '510': -0.4297, '555': -0.4240, '670': -0.3333},
    'PC2': {'412': -0.4536, '443': -0.2541, '490': -0.0825, '510': -0.0403, '555': 0.1504, '670': 0.8358},
    'PC3': {'412': 0.5303, '443': 0.2160, '490': -0.1431, '510': -0.3003, '555': -0.6103, '670': 0.4347},
    'PC4': {'412': -0.4941, '443': 0.2907, '490': 0.4526, '510': 0.3252, '555': -0.6005, '670': -0.0113}
}

# 定义 α, β, γ, δ, ε 的修正系数（Kd < 0.32 和 Kd > 0.32） (unchanged)
coefficients_Kd_low = {
    'Kd_320': {'alpha': -0.7327, 'beta': 0.0980, 'gamma': -0.5928, 'delta': -0.5230, 'epsilon': -1.1130},
    'Kd_340': {'alpha': -1.0625, 'beta': 0.0855, 'gamma': -0.6301, 'delta': -0.4996, 'epsilon': -0.8653},
    'Kd_380': {'alpha': -1.6508, 'beta': 0.0485, 'gamma': -0.6565, 'delta': -0.4154, 'epsilon': -0.4186},
    'Kd_412': {'alpha': -1.9638, 'beta': 0.0240, 'gamma': -0.6550, 'delta': -0.3240, 'epsilon': 0.1644},
    'Kd_443': {'alpha': -2.1846, 'beta': 0.0088, 'gamma': -0.6256, 'delta': -0.2368, 'epsilon': 0.6171},
    'Kd_490': {'alpha': -2.4894, 'beta': -0.0025, 'gamma': -0.5574, 'delta': -0.0733, 'epsilon': 0.6902}
}

coefficients_Kd_high = {
    'Kd_320': {'alpha': 1.7574, 'beta': 0.1253, 'gamma': 1.0342, 'delta': -0.3073, 'epsilon': 0.8648},
    'Kd_340': {'alpha': 1.4696, 'beta': 0.1181, 'gamma': 0.9701, 'delta': -0.1030, 'epsilon': 0.6973},
    'Kd_380': {'alpha': 0.9983, 'beta': 0.1117, 'gamma': 0.9816, 'delta': 0.1098, 'epsilon': 0.5601},
    'Kd_412': {'alpha': 0.6930, 'beta': 0.1200, 'gamma': 0.9512, 'delta': 0.3410, 'epsilon': 0.0220},
    'Kd_443': {'alpha': 0.4314, 'beta': 0.1130, 'gamma': 0.9268, 'delta': 0.4504, 'epsilon': -0.2891},
    'Kd_490': {'alpha': 0.0530, 'beta': 0.0927, 'gamma': 0.9158, 'delta': 0.5754, 'epsilon': -0.3118}
}


# 逐行处理数据的函数，添加行计数
def calculate_kd_for_row(row, row_counter, total_rows):
    global last_printed
    if row_counter is None or total_rows is None:
        raise ValueError("row_counter and total_rows must be provided")

    # 更新行计数
    row_counter[0] += 1
    current_row = row_counter[0]

    # 每处理100行打印一次进度
    if current_row % 100 == 0 or current_row == total_rows:
        print(f"当前文件已处理 {current_row}/{total_rows} 行")

    if row['NASA_Kd_490'] < 0.32:
        mean_std = R_mean_std_low_kd
        e_coefficients = e_coefficients_low_kd
        coefficients_Kd = coefficients_Kd_low
    else:
        mean_std = R_mean_std_high_kd
        e_coefficients = e_coefficients_high_kd
        coefficients_Kd = coefficients_Kd_high

    # 对 Rrs(λ) 进行对数转换
    for band in ['412', '443', '490', '510', '555', '670']:
        column_name = f'Rrs_{band}'
        log_column_name = f'R_{band}'
        value = row[column_name]
        row[log_column_name] = np.log(value) if value > 0 else np.nan

    # 计算 X(λ)
    for band, params in mean_std.items():
        x_column_name = f'X_{band.split("_")[1]}'
        row[x_column_name] = (row[f'R_{band.split("_")[1]}'] - params['mean']) / params['std']

    # 计算 PC1 到 PC4
    for pc in ['PC1', 'PC2', 'PC3', 'PC4']:
        row[pc] = (e_coefficients[pc]['412'] * row['X_412'] +
                   e_coefficients[pc]['443'] * row['X_443'] +
                   e_coefficients[pc]['490'] * row['X_490'] +
                   e_coefficients[pc]['510'] * row['X_510'] +
                   e_coefficients[pc]['555'] * row['X_555'] +
                   e_coefficients[pc]['670'] * row['X_670'])

    # 计算 ln[Kd(λ)] 和 Kd(λ)
    for kd_key, coeffs in coefficients_Kd.items():
        ln_column = f'ln_Kd_{kd_key.split("_")[1]}'
        row[ln_column] = (coeffs['alpha'] +
                          coeffs['beta'] * row['PC1'] +
                          coeffs['gamma'] * row['PC2'] +
                          coeffs['delta'] * row['PC3'] +
                          coeffs['epsilon'] * row['PC4'])
        row[f'Kd_{kd_key.split("_")[1]}'] = np.exp(row[ln_column])

    return row


# 主函数：选择文件夹并处理所有 CSV 文件
def process_csv_files():
    # 创建 Tkinter 根窗口（隐藏主窗口）
    root = Tk()
    root.withdraw()  # 隐藏主窗口

    # 选择输入文件夹
    input_dir = filedialog.askdirectory(title="请选择包含 CSV 文件的输入文件夹")
    if not input_dir:
        print("未选择输入文件夹，程序退出。")
        return

    # 选择输出文件夹
    output_dir = filedialog.askdirectory(title="请选择输出文件夹")
    if not output_dir:
        print("未选择输出文件夹，程序退出。")
        return

    # 确保输出文件夹存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 遍历输入文件夹中的所有 CSV 文件
    csv_files = [f for f in os.listdir(input_dir) if f.endswith('.csv')]
    if not csv_files:
        print("输入文件夹中没有 CSV 文件。")
        return

    print(f"找到 {len(csv_files)} 个 CSV 文件，将依次处理...")

    # 使用 tqdm 显示文件处理进度
    for idx, csv_file in enumerate(tqdm(csv_files, desc="处理文件")):
        input_path = os.path.join(input_dir, csv_file)
        print(f"\n处理文件 {idx + 1}/{len(csv_files)}: {csv_file}")

        # 读取 CSV 文件
        df = pd.read_csv(input_path)

        print(f"文件行数: {len(df)}")

        # 初始化行计数器
        row_counter = [0]  # 使用列表来使计数器在函数内可变

        # 计算 Rrs 蓝绿波段的比值
        df['log_Rrs_ratio'] = np.log10(df['Rrs_490'] / df['Rrs_555'])

        # 计算 log10(Kbio(490)) 和 Kbio(490)
        df['log_Kbio_490'] = (seaWiFS_coefficients['a0'] +
                              seaWiFS_coefficients['a1'] * df['log_Rrs_ratio'] +
                              seaWiFS_coefficients['a2'] * df['log_Rrs_ratio'] ** 2 +
                              seaWiFS_coefficients['a3'] * df['log_Rrs_ratio'] ** 3 +
                              seaWiFS_coefficients['a4'] * df['log_Rrs_ratio'] ** 4)

        df['Kbio_490'] = 10 ** df['log_Kbio_490']
        df['NASA_Kd_490'] = df['Kbio_490'] + 0.0166

        # 应用计算函数，并传递行计数器和总行数
        total_rows = len(df)
        df = df.apply(lambda row: calculate_kd_for_row(row, row_counter, total_rows), axis=1)

        # 选择需要保存的列
        result_columns = [f'Kd_{wl}' for wl in ['320', '340', '380', '412', '443', '490']]
        result = df[result_columns]

        # 生成输出文件名
        output_filename = os.path.join(output_dir, f"{os.path.splitext(csv_file)[0]}_results.csv")

        # 保存结果到 CSV 文件
        result.to_csv(output_filename, index=False)
        print(f"结果已保存到：{output_filename}")

        # 释放内存，删除临时变量
        del df
        del result
        import gc
        gc.collect()  # 强制垃圾回收

    print("\n所有文件处理完成！")


if __name__ == "__main__":
    process_csv_files()