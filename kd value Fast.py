import numpy as np
import pandas as pd
import os
from tkinter import Tk, filedialog
from tqdm import tqdm

# 定义 SeaWiFS 传感器的四阶多项式系数
seaWiFS_coefficients = {
    'a0': -0.8515, 'a1': -1.8263, 'a2': 1.8714, 'a3': -2.4414, 'a4': -1.0690
}

# 定义 R(λ) 的均值和标准差（Kd < 0.32 和 Kd > 0.32）
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

# 定义 PC1 到 PC4 的系数（Kd < 0.32 和 Kd > 0.32）
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

# 定义 α, β, γ, δ, ε 的修正系数（Kd < 0.32 和 Kd > 0.32）
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


# 向量化处理函数 - 替代逐行处理
def calculate_kd_vectorized(df):
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

    # 对 Rrs(λ) 进行对数转换 - 向量化操作
    for band in ['412', '443', '490', '510', '555', '670']:
        column_name = f'Rrs_{band}'
        log_column_name = f'R_{band}'
        # 安全的对数变换
        df[log_column_name] = np.log(df[column_name].clip(lower=1e-10))

    # 创建两个掩码来分离高Kd和低Kd值的行
    low_kd_mask = df['NASA_Kd_490'] < 0.32
    high_kd_mask = ~low_kd_mask

    # 为低Kd和高Kd数据分别创建标准化X值
    for band in ['412', '443', '490', '510', '555', '670']:
        # 低Kd组的X值
        x_col = f'X_{band}'
        r_col = f'R_{band}'

        # 创建X列，初始化为NaN
        df[x_col] = np.nan

        # 为低Kd组计算X值
        mean_low = R_mean_std_low_kd[f'R_{band}']['mean']
        std_low = R_mean_std_low_kd[f'R_{band}']['std']
        df.loc[low_kd_mask, x_col] = (df.loc[low_kd_mask, r_col] - mean_low) / std_low

        # 为高Kd组计算X值
        mean_high = R_mean_std_high_kd[f'R_{band}']['mean']
        std_high = R_mean_std_high_kd[f'R_{band}']['std']
        df.loc[high_kd_mask, x_col] = (df.loc[high_kd_mask, r_col] - mean_high) / std_high

    # 为低Kd和高Kd分别计算主成分
    for pc in ['PC1', 'PC2', 'PC3', 'PC4']:
        # 创建PC列，初始化为NaN
        df[pc] = np.nan

        # 低Kd组的主成分
        df.loc[low_kd_mask, pc] = sum(e_coefficients_low_kd[pc][band] * df.loc[low_kd_mask, f'X_{band}']
                                      for band in ['412', '443', '490', '510', '555', '670'])

        # 高Kd组的主成分
        df.loc[high_kd_mask, pc] = sum(e_coefficients_high_kd[pc][band] * df.loc[high_kd_mask, f'X_{band}']
                                       for band in ['412', '443', '490', '510', '555', '670'])

    # 计算Kd值
    result_columns = []
    for kd_wavelength in ['320', '340', '380', '412', '443', '490']:
        ln_col = f'ln_Kd_{kd_wavelength}'
        kd_col = f'Kd_{kd_wavelength}'
        result_columns.append(kd_col)

        # 创建ln_Kd列，初始化为NaN
        df[ln_col] = np.nan

        # 低Kd组的ln_Kd计算
        coeffs_low = coefficients_Kd_low[f'Kd_{kd_wavelength}']
        df.loc[low_kd_mask, ln_col] = (
                coeffs_low['alpha'] +
                coeffs_low['beta'] * df.loc[low_kd_mask, 'PC1'] +
                coeffs_low['gamma'] * df.loc[low_kd_mask, 'PC2'] +
                coeffs_low['delta'] * df.loc[low_kd_mask, 'PC3'] +
                coeffs_low['epsilon'] * df.loc[low_kd_mask, 'PC4']
        )

        # 高Kd组的ln_Kd计算
        coeffs_high = coefficients_Kd_high[f'Kd_{kd_wavelength}']
        df.loc[high_kd_mask, ln_col] = (
                coeffs_high['alpha'] +
                coeffs_high['beta'] * df.loc[high_kd_mask, 'PC1'] +
                coeffs_high['gamma'] * df.loc[high_kd_mask, 'PC2'] +
                coeffs_high['delta'] * df.loc[high_kd_mask, 'PC3'] +
                coeffs_high['epsilon'] * df.loc[high_kd_mask, 'PC4']
        )

        # 计算最终的Kd值
        df[kd_col] = np.exp(df[ln_col])

    return df[result_columns]


# 分块处理函数
def process_in_chunks(file_path, chunk_size=10000):
    """以分块方式处理大型CSV文件"""
    # 获取文件总行数以显示进度
    total_rows = sum(1 for _ in open(file_path, 'r')) - 1  # 减去标题行

    # 设置结果数据框
    result_columns = [f'Kd_{wl}' for wl in ['320', '340', '380', '412', '443', '490']]
    all_results = pd.DataFrame(columns=result_columns)

    # 使用分块读取数据
    with tqdm(total=total_rows, desc="处理数据") as pbar:
        for chunk in pd.read_csv(file_path, chunksize=chunk_size):
            # 处理当前块
            result_chunk = calculate_kd_vectorized(chunk)

            # 合并结果
            all_results = pd.concat([all_results, result_chunk], ignore_index=True)

            # 更新进度条
            pbar.update(len(chunk))

    return all_results


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

    # 处理每个文件
    for idx, csv_file in enumerate(csv_files):
        input_path = os.path.join(input_dir, csv_file)
        print(f"\n处理文件 {idx + 1}/{len(csv_files)}: {csv_file}")

        # 确定文件大小以决定是否使用分块处理
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)

        if file_size_mb > 100:  # 如果文件大于100MB，使用分块处理
            print(f"文件大小: {file_size_mb:.2f} MB，使用分块处理")
            result = process_in_chunks(input_path)
        else:
            # 对于小文件，直接读取并处理
            print(f"文件大小: {file_size_mb:.2f} MB")
            df = pd.read_csv(input_path)
            print(f"文件行数: {len(df)}")
            result = calculate_kd_vectorized(df)
            del df  # 释放内存

        # 生成输出文件名
        output_filename = os.path.join(output_dir, f"{os.path.splitext(csv_file)[0]}_results.csv")

        # 保存结果到 CSV 文件
        result.to_csv(output_filename, index=False)
        print(f"结果已保存到：{output_filename}")

        # 释放内存
        del result
        import gc
        gc.collect()  # 强制垃圾回收

    print("\n所有文件处理完成！")


if __name__ == "__main__":
    process_csv_files()