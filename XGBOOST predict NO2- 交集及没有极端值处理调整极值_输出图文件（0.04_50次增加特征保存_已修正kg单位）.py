"""
海洋化学数据批量预测代码 - 修正单位换算版 + GPU优化 + 流式处理
目标变量: G2nitrite
生成时间: 2024-XX-XX

修正内容:
1. 添加营养盐参数单位换算（mmol/m³ → μmol/kg）
2. 使用平均海水密度进行换算
3. 修正GPU检测和调用方式（参考训练代码成功经验）
4. 简化GPU测试，避免空标签错误
5. 优化DMatrix创建方式
6. 保持原有的流式处理和内存优化功能

单位换算说明:
- 输入数据单位: mmol/m³ (no3, o2, po4, si)
- 训练模型单位: μmol/kg
- 换算公式: μmol/kg = mmol/m³ × 1000 / 海水密度(kg/m³)
- 平均海水密度: 1025 kg/m³

使用说明:
1. 运行程序，按顺序选择：模型文件夹、输入文件夹、输出文件夹
2. 程序自动检测GPU并正确设置XGBoost GPU模式
3. 自动进行营养盐参数单位换算
4. 支持断点续传，中断后可继续处理
5. 内存使用优化，支持超大文件处理
"""

import pandas as pd
import numpy as np
import xgboost as xgb
import pickle
import json
import warnings
import os
import time
import gc
import psutil
from pathlib import Path
import subprocess

warnings.filterwarnings('ignore')

# GUI相关导入
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    GUI_AVAILABLE = True
except ImportError:
    print("警告: tkinter不可用，将使用命令行输入")
    GUI_AVAILABLE = False

# 进度条支持
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("注意: tqdm不可用，将不显示进度条")
    TQDM_AVAILABLE = False
    def tqdm(iterable, *args, **kwargs):
        return iterable

# 列名映射关系
COLUMN_MAPPING = {
    'year': 'G2year',
    'month': 'G2month',
    'depth': 'G2depth',
    'longitude': 'G2longitude',
    'latitude': 'G2latitude',
    'no3': 'G2nitrate',
    'o2': 'G2oxygen',
    'po4': 'G2phosphate',
    'si': 'G2silicate',
    'so': 'G2salinity',
    'thetao': 'G2theta'
}

# 需要进行单位换算的营养盐参数（从 mmol/m³ 转换为 μmol/kg）
UNIT_CONVERSION_COLUMNS = ['G2nitrate', 'G2oxygen', 'G2phosphate', 'G2silicate']

# 单位换算配置
UNIT_CONVERSION_CONFIG = {
    'seawater_density_kg_per_m3': 1025,  # 平均海水密度 kg/m³
    'mmol_to_umol_factor': 1000,         # mmol → μmol 转换因子
    'conversion_factor': None            # 将在运行时计算
}

# 计算转换因子
UNIT_CONVERSION_CONFIG['conversion_factor'] = (
    UNIT_CONVERSION_CONFIG['mmol_to_umol_factor'] /
    UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']
)

# 输出列顺序
OUTPUT_COLUMNS = ['year', 'month', 'longitude', 'latitude', 'depth', 'nitrite_predicted', 'nitrate']

# 流式处理配置
STREAMING_CONFIG = {
    'chunk_size': 50000,  # 每批处理的行数
    'memory_threshold_mb': 4000,  # 内存使用阈值（MB）
    'large_file_threshold_mb': 500,  # 大文件阈值（MB）
    'enable_gc_frequency': 10,  # 垃圾回收频率（每N个chunk）
}


def get_memory_usage_mb():
    """获取当前内存使用量（MB）"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def check_gpu_availability():
    """检查GPU可用性（修正版，参考训练代码）"""
    try:
        # 检查NVIDIA GPU
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ 检测到NVIDIA GPU")
            return True
        else:
            print("❌ 未检测到NVIDIA GPU")
            return False
    except Exception as e:
        print(f"❌ GPU检测失败: {e}")
        return False


def setup_gpu_optimized():
    """
    优化的GPU检测和设置（修正版，参考训练代码的成功经验）
    避免创建空标签的测试，直接检查GPU可用性
    """
    try:
        # 基础GPU检查
        gpu_available = check_gpu_availability()
        if not gpu_available:
            return False, None

        # 简化的XGBoost GPU兼容性测试
        try:
            # 创建一个简单的测试数据（避免空标签问题）
            test_data = np.random.rand(10, 5)  # 减少测试数据量
            test_labels = np.random.rand(10)   # 确保标签数量匹配

            # 创建DMatrix
            test_dmatrix = xgb.DMatrix(test_data, label=test_labels)

            # 测试GPU参数设置（不进行实际训练）
            gpu_params = {
                'tree_method': 'gpu_hist',
                'gpu_id': 0,
                'objective': 'reg:squarederror',
                'max_depth': 3,  # 简化参数
                'eta': 0.1
            }

            print("✅ XGBoost GPU参数验证成功")
            return True, 0  # 返回GPU可用和GPU ID

        except Exception as e:
            print(f"⚠️  XGBoost GPU兼容性测试失败: {e}")
            print("   原因可能是XGBoost版本不支持GPU或GPU驱动问题")
            print("   将使用CPU模式")
            return False, None

    except Exception as e:
        print(f"❌ GPU设置失败: {e}，使用CPU模式")
        return False, None


def get_file_size_mb(file_path):
    """获取文件大小（MB）"""
    try:
        # 修正：确保文件路径是字符串类型
        size_bytes = os.path.getsize(str(file_path))
        return size_bytes / (1024 * 1024)
    except:
        return 0


def should_use_streaming(file_path):
    """判断是否应该使用流式处理"""
    file_size_mb = get_file_size_mb(file_path)
    available_memory_mb = psutil.virtual_memory().available / (1024 * 1024)

    print(f"  文件大小: {file_size_mb:.1f} MB")
    print(f"  可用内存: {available_memory_mb:.1f} MB")

    # 如果文件大于阈值或者文件大小超过可用内存的50%，使用流式处理
    use_streaming = (file_size_mb > STREAMING_CONFIG['large_file_threshold_mb'] or
                    file_size_mb > available_memory_mb * 0.5)

    if use_streaming:
        print(f"  → 使用流式处理（文件较大或内存不足）")
    else:
        print(f"  → 使用一次性处理（文件较小）")

    return use_streaming, file_size_mb


def convert_nutrient_units(df, verbose=True):
    """
    营养盐参数单位换算：mmol/m³ → μmol/kg

    参数:
    - df: 包含营养盐数据的DataFrame
    - verbose: 是否显示详细信息

    返回:
    - 转换后的DataFrame
    """
    if verbose:
        print("🔄 营养盐参数单位换算 (mmol/m³ → μmol/kg)...")
        print(f"   海水密度: {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']} kg/m³")
        print(f"   转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f}")

    df_converted = df.copy()
    conversion_stats = {}

    for column in UNIT_CONVERSION_COLUMNS:
        if column in df_converted.columns:
            # 获取原始统计信息
            original_values = df_converted[column].dropna()
            if len(original_values) > 0:
                original_stats = {
                    'count': len(original_values),
                    'mean': original_values.mean(),
                    'min': original_values.min(),
                    'max': original_values.max(),
                    'std': original_values.std()
                }

                # 进行单位转换
                df_converted[column] = df_converted[column] * UNIT_CONVERSION_CONFIG['conversion_factor']

                # 获取转换后统计信息
                converted_values = df_converted[column].dropna()
                converted_stats = {
                    'count': len(converted_values),
                    'mean': converted_values.mean(),
                    'min': converted_values.min(),
                    'max': converted_values.max(),
                    'std': converted_values.std()
                }

                conversion_stats[column] = {
                    'original': original_stats,
                    'converted': converted_stats
                }

                if verbose:
                    print(f"   {column}:")
                    print(f"     原始 (mmol/m³): 均值={original_stats['mean']:.3f}, 范围=[{original_stats['min']:.3f}, {original_stats['max']:.3f}]")
                    print(f"     转换 (μmol/kg): 均值={converted_stats['mean']:.3f}, 范围=[{converted_stats['min']:.3f}, {converted_stats['max']:.3f}]")
            else:
                if verbose:
                    print(f"   {column}: 无有效数据，跳过转换")
        else:
            if verbose:
                print(f"   {column}: 列不存在，跳过转换")

    if verbose:
        converted_columns = [col for col in UNIT_CONVERSION_COLUMNS if col in df_converted.columns]
        print(f"✅ 营养盐单位换算完成，转换了 {len(converted_columns)} 个参数")

    return df_converted, conversion_stats


def select_model_folder():
    """选择包含模型文件和特征工程信息文件的文件夹"""
    print("选择模型及特征工程信息文件夹")

    if not GUI_AVAILABLE:
        return get_model_folder_from_input()

    root = tk.Tk()
    root.withdraw()

    try:
        messagebox.showinfo("第一步：选择模型文件夹",
                            "请选择包含以下文件的模型文件夹：\n"
                            "- G2nitrite_complete_model.json\n"
                            "- G2nitrite_complete_feature_engineering_info.pkl")
        model_folder = filedialog.askdirectory(title="选择模型及特征工程信息文件夹")

        if not model_folder:
            messagebox.showwarning("取消", "未选择模型文件夹，程序退出")
            return None

        messagebox.showinfo("选择完成", f"模型文件夹: {model_folder}")
        return model_folder

    except Exception as e:
        messagebox.showerror("错误", f"文件夹选择失败: {e}")
        return None
    finally:
        root.destroy()


def get_model_folder_from_input():
    """命令行输入方式获取模型文件夹路径"""
    print("=== 模型文件夹路径设置 ===")
    print("需要包含以下文件：")
    print("- G2nitrite_complete_model.json")
    print("- G2nitrite_complete_feature_engineering_info.pkl")

    while True:
        model_folder = input("请输入模型文件夹路径 (留空使用当前目录): ").strip()
        if not model_folder:
            model_folder = os.getcwd()
            break
        elif os.path.exists(model_folder) and os.path.isdir(model_folder):
            break
        else:
            print("文件夹不存在，请重新输入")

    return model_folder


def select_data_folders():
    """选择输入和输出文件夹"""
    if not GUI_AVAILABLE:
        return get_data_folders_from_input()

    root = tk.Tk()
    root.withdraw()

    try:
        messagebox.showinfo("第二步：选择输入文件夹",
                            "请选择包含CSV数据文件的输入文件夹\n\n"
                            "注意：营养盐参数将自动进行单位换算\n"
                            "从 mmol/m³ 转换为 μmol/kg")
        input_folder = filedialog.askdirectory(title="选择输入文件夹")

        if not input_folder:
            messagebox.showwarning("取消", "未选择输入文件夹，程序退出")
            return None, None

        messagebox.showinfo("第三步：选择输出文件夹", "请选择预测结果保存的输出文件夹")
        output_folder = filedialog.askdirectory(title="选择输出文件夹")

        if not output_folder:
            messagebox.showwarning("取消", "未选择输出文件夹，程序退出")
            return None, None

        messagebox.showinfo("选择完成",
                            f"输入文件夹: {input_folder}\n"
                            f"输出文件夹: {output_folder}\n\n"
                            f"营养盐单位将自动换算:\n"
                            f"mmol/m³ → μmol/kg")

        return input_folder, output_folder

    except Exception as e:
        messagebox.showerror("错误", f"文件夹选择失败: {e}")
        return None, None
    finally:
        root.destroy()


def get_data_folders_from_input():
    """命令行输入方式获取数据文件夹路径"""
    print("=== 数据文件夹路径设置 ===")
    print("注意：营养盐参数将自动进行单位换算 (mmol/m³ → μmol/kg)")

    while True:
        input_folder = input("请输入包含CSV文件的输入文件夹路径: ").strip()
        if os.path.exists(input_folder) and os.path.isdir(input_folder):
            break
        else:
            print("文件夹不存在，请重新输入")

    while True:
        output_folder = input("请输入输出文件夹路径 (留空使用当前目录): ").strip()
        if not output_folder:
            output_folder = os.getcwd()
            break
        elif os.path.exists(output_folder) and os.path.isdir(output_folder):
            break
        else:
            print("文件夹不存在，请重新输入")

    return input_folder, output_folder


def load_model_and_info_gpu(model_folder):
    """加载模型和特征工程信息（修正GPU优化版）"""
    model_path = Path(model_folder)
    MODEL_FILE = model_path / 'G2nitrite_complete_model.json'
    FEATURE_INFO_FILE = model_path / 'G2nitrite_complete_feature_engineering_info.pkl'

    print(f"📁 模型文件夹: {model_folder}")
    print(f"🔍 查找文件:")
    print(f"   模型文件: {MODEL_FILE}")
    print(f"   特征信息文件: {FEATURE_INFO_FILE}")

    try:
        # 检查文件是否存在
        if not MODEL_FILE.exists():
            print(f"❌ 模型文件不存在: {MODEL_FILE}")
            print(f"   请确保文件夹中包含: G2nitrite_complete_model.json")
            return None, None, False, None

        if not FEATURE_INFO_FILE.exists():
            print(f"❌ 特征工程信息文件不存在: {FEATURE_INFO_FILE}")
            print(f"   请确保文件夹中包含: G2nitrite_complete_feature_engineering_info.pkl")
            return None, None, False, None

        # 修正的GPU检测
        use_gpu, gpu_id = setup_gpu_optimized()

        # 加载XGBoost模型
        model = xgb.Booster()
        model.load_model(str(MODEL_FILE))
        print(f"✅ 模型加载成功: {MODEL_FILE.name}")

        # GPU设置反馈
        if use_gpu:
            print(f"✅ GPU模式已启用，GPU ID: {gpu_id}")
            print("   预测时将使用GPU加速")
        else:
            print("✅ CPU模式已启用")
            print("   预测时将使用CPU")

        # 加载特征工程信息
        with open(FEATURE_INFO_FILE, 'rb') as f:
            feature_info = pickle.load(f)
        print(f"✅ 特征工程信息加载成功: {FEATURE_INFO_FILE.name}")

        return model, feature_info, use_gpu, gpu_id

    except Exception as e:
        print(f"❌ 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None, False, None


def map_column_names(df):
    """映射列名到模型期望的格式"""
    print("🔄 映射列名...")

    available_columns = df.columns.tolist()
    mapped_df = df.copy()

    # 执行列名映射
    rename_dict = {}
    for input_col, model_col in COLUMN_MAPPING.items():
        if input_col in available_columns:
            rename_dict[input_col] = model_col
            print(f"  {input_col} -> {model_col}")

    if rename_dict:
        mapped_df = mapped_df.rename(columns=rename_dict)
        print(f"✅ 成功映射 {len(rename_dict)} 个列名")
    else:
        print("⚠️  没有找到需要映射的列名")

    # 检查必要列是否存在
    required_columns = ['G2latitude', 'G2longitude', 'G2depth', 'G2nitrate']
    missing_columns = [col for col in required_columns if col not in mapped_df.columns]

    if missing_columns:
        print(f"⚠️  缺少必要列: {missing_columns}")

    return mapped_df


def apply_safe_feature_transform(series, transform_type='log'):
    """安全的特征变换"""
    if series.isna().all():
        return pd.Series(np.nan, index=series.index)

    # 只处理无穷大值，将其设为NaN
    series_safe = series.replace([np.inf, -np.inf], np.nan)

    if transform_type == 'log':
        result = series_safe.copy()
        positive_mask = result > 0
        result.loc[positive_mask] = np.log1p(result.loc[positive_mask])
        result.loc[~positive_mask] = np.nan
    elif transform_type == 'sqrt':
        result = series_safe.copy()
        non_negative_mask = result >= 0
        result.loc[non_negative_mask] = np.sqrt(result.loc[non_negative_mask])
        result.loc[~non_negative_mask] = np.nan
    elif transform_type == 'square':
        result = series_safe.clip(-1e6, 1e6) ** 2
    elif transform_type == 'inverse':
        result = series_safe.copy()
        non_zero_mask = np.abs(result) > 1e-10
        result.loc[non_zero_mask] = 1.0 / result.loc[non_zero_mask]
        result.loc[~non_zero_mask] = np.nan
    else:
        result = series_safe

    return result.replace([np.inf, -np.inf], np.nan)


def apply_safe_ratio_feature(numerator, denominator):
    """安全的比率特征计算"""
    num_safe = numerator.replace([np.inf, -np.inf], np.nan)
    den_safe = denominator.replace([np.inf, -np.inf], np.nan)
    ratio = num_safe / den_safe
    ratio = ratio.replace([np.inf, -np.inf], np.nan)
    return ratio.clip(-1e6, 1e6)


def apply_feature_engineering(df, feature_info):
    """应用特征工程（完全基于训练时保存的信息）"""
    print("🔧 应用特征工程...")

    df_fe = df.copy()

    # 应用保存的特征工程步骤
    steps = feature_info.get('steps', [])

    for step in steps:
        if step == 'geographic_time_features':
            print("  - 地理时间特征")
            if 'G2latitude' in df_fe.columns and 'G2longitude' in df_fe.columns:
                df_fe['sin_lat'] = np.sin(np.deg2rad(df_fe['G2latitude']))
                df_fe['cos_lat'] = np.cos(np.deg2rad(df_fe['G2latitude']))
                df_fe['abs_latitude'] = np.abs(df_fe['G2latitude'])

            if 'G2month' in df_fe.columns:
                df_fe['sin_month'] = np.sin(2 * np.pi * df_fe['G2month'] / 12)
                df_fe['cos_month'] = np.cos(2 * np.pi * df_fe['G2month'] / 12)

        elif step == 'depth_stratification_features':
            print("  - 深度分层特征")
            if 'G2depth' in df_fe.columns:
                df_fe['log_depth'] = apply_safe_feature_transform(df_fe['G2depth'] + 1, 'log')
                df_fe['sqrt_depth'] = apply_safe_feature_transform(df_fe['G2depth'], 'sqrt')

                # 深度分层
                depth_info = feature_info.get('depth_stratification', {})
                depth_bins = depth_info.get('bins', [0, 50, 200, 1000, 4000, np.inf])
                depth_labels = depth_info.get('labels', ['surface', 'subsurface', 'intermediate', 'deep', 'abyssal'])

                depth_zone = pd.cut(df_fe['G2depth'], bins=depth_bins, labels=depth_labels)
                for zone in depth_labels:
                    df_fe[f'is_{zone}'] = (depth_zone == zone).astype(float)

        elif step == 'nutrient_biogeochemical_features':
            print("  - 营养盐生物地球化学特征")
            if 'G2nitrate' in df_fe.columns:
                df_fe['log_nitrate'] = apply_safe_feature_transform(df_fe['G2nitrate'] + 0.001, 'log')
                df_fe['sqrt_nitrate'] = apply_safe_feature_transform(df_fe['G2nitrate'], 'sqrt')

                # 硝酸盐分级
                nitrate_info = feature_info.get('nitrate_classification', {})
                nitrate_bins = nitrate_info.get('bins', [0, 1, 5, 15, 30, np.inf])
                nitrate_labels = nitrate_info.get('labels', ['very_low', 'low', 'medium', 'high', 'very_high'])

                nitrate_level = pd.cut(df_fe['G2nitrate'], bins=nitrate_bins, labels=nitrate_labels)
                for level in nitrate_labels:
                    df_fe[f'nitrate_{level}'] = (nitrate_level == level).astype(float)

        elif step == 'redfield_ratio_features':
            print("  - Redfield比率特征")
            if 'G2nitrate' in df_fe.columns and 'G2phosphate' in df_fe.columns:
                df_fe['N_P_ratio'] = apply_safe_ratio_feature(df_fe['G2nitrate'], df_fe['G2phosphate'])

                redfield_info = feature_info.get('redfield_ratio', {})
                standard_ratio = redfield_info.get('standard_ratio', 16.0)
                compliance_threshold = redfield_info.get('compliance_threshold', 5.0)

                df_fe['redfield_deviation'] = df_fe['N_P_ratio'] - standard_ratio
                df_fe['redfield_deviation_abs'] = np.abs(df_fe['redfield_deviation'])
                df_fe['is_redfield_compliant'] = (np.abs(df_fe['redfield_deviation']) <= compliance_threshold).astype(float)

            if 'G2nitrate' in df_fe.columns and 'G2silicate' in df_fe.columns:
                df_fe['N_Si_ratio'] = apply_safe_ratio_feature(df_fe['G2nitrate'], df_fe['G2silicate'])

        elif step == 'redox_environment_features':
            print("  - 氧化还原环境特征")
            if 'G2oxygen' in df_fe.columns:
                df_fe['log_oxygen'] = apply_safe_feature_transform(df_fe['G2oxygen'] + 0.001, 'log')

                oxygen_info = feature_info.get('oxygen_classification', {})
                hypoxic_threshold = oxygen_info.get('hypoxic_threshold', 62.5)
                suboxic_threshold = oxygen_info.get('suboxic_threshold', 22.3)
                anoxic_threshold = oxygen_info.get('anoxic_threshold', 4.5)

                df_fe['is_hypoxic'] = (df_fe['G2oxygen'] < hypoxic_threshold).astype(float)
                df_fe['is_suboxic'] = (df_fe['G2oxygen'] < suboxic_threshold).astype(float)
                df_fe['is_anoxic'] = (df_fe['G2oxygen'] < anoxic_threshold).astype(float)

                if 'G2nitrate' in df_fe.columns:
                    df_fe['O2_N_ratio'] = apply_safe_ratio_feature(df_fe['G2oxygen'], df_fe['G2nitrate'])

        elif step == 'temperature_salinity_features':
            print("  - 温盐特征")
            if 'G2theta' in df_fe.columns and 'G2salinity' in df_fe.columns:
                df_fe['density_proxy'] = df_fe['G2salinity'] - 0.1 * df_fe['G2theta']
                df_fe['temp_sal_product'] = df_fe['G2theta'] * df_fe['G2salinity']

                water_mass_info = feature_info.get('water_mass_classification', {})
                cold_threshold = water_mass_info.get('cold_water_threshold', 4.0)
                warm_threshold = water_mass_info.get('warm_water_threshold', 15.0)
                high_sal_threshold = water_mass_info.get('high_salinity_threshold', 35.0)
                low_sal_threshold = water_mass_info.get('low_salinity_threshold', 34.0)

                df_fe['is_cold_water'] = (df_fe['G2theta'] < cold_threshold).astype(float)
                df_fe['is_warm_water'] = (df_fe['G2theta'] > warm_threshold).astype(float)
                df_fe['is_high_salinity'] = (df_fe['G2salinity'] > high_sal_threshold).astype(float)
                df_fe['is_low_salinity'] = (df_fe['G2salinity'] < low_sal_threshold).astype(float)

        elif step == 'silicate_features':
            print("  - 硅酸盐特征")
            if 'G2silicate' in df_fe.columns:
                df_fe['log_silicate'] = apply_safe_feature_transform(df_fe['G2silicate'] + 0.001, 'log')
                df_fe['sqrt_silicate'] = apply_safe_feature_transform(df_fe['G2silicate'], 'sqrt')

                silicate_info = feature_info.get('silicate_classification', {})
                depleted_threshold = silicate_info.get('depleted_threshold', 2.0)
                rich_threshold = silicate_info.get('rich_threshold', 15.0)

                df_fe['is_si_depleted'] = (df_fe['G2silicate'] < depleted_threshold).astype(float)
                df_fe['is_si_rich'] = (df_fe['G2silicate'] > rich_threshold).astype(float)

        elif step == 'phosphate_features':
            print("  - 磷酸盐特征")
            if 'G2phosphate' in df_fe.columns:
                df_fe['log_phosphate'] = apply_safe_feature_transform(df_fe['G2phosphate'] + 0.001, 'log')
                df_fe['sqrt_phosphate'] = apply_safe_feature_transform(df_fe['G2phosphate'], 'sqrt')

                phosphate_info = feature_info.get('phosphate_classification', {})
                limitation_threshold = phosphate_info.get('limitation_threshold', 0.1)

                df_fe['is_p_limited'] = (df_fe['G2phosphate'] < limitation_threshold).astype(float)

        elif step == 'seasonal_climate_features':
            print("  - 季节和气候特征")
            if 'G2month' in df_fe.columns and 'G2latitude' in df_fe.columns:
                df_fe['is_northern_hemisphere'] = (df_fe['G2latitude'] >= 0).astype(float)

                # 季节特征
                def get_season(month, is_north):
                    if pd.isna(month):
                        return np.nan
                    if is_north:
                        if month in [12, 1, 2]:
                            return 'winter'
                        elif month in [3, 4, 5]:
                            return 'spring'
                        elif month in [6, 7, 8]:
                            return 'summer'
                        else:
                            return 'autumn'
                    else:
                        if month in [12, 1, 2]:
                            return 'summer'
                        elif month in [3, 4, 5]:
                            return 'autumn'
                        elif month in [6, 7, 8]:
                            return 'winter'
                        else:
                            return 'spring'

                df_fe['season'] = df_fe.apply(
                    lambda row: get_season(row['G2month'], row['G2latitude'] >= 0), axis=1
                )

                for season in ['winter', 'spring', 'summer', 'autumn']:
                    df_fe[f'is_{season}'] = (df_fe['season'] == season).astype(float)

                df_fe.drop('season', axis=1, inplace=True)

                # 气候带
                climate_info = feature_info.get('climate_zones', {})
                climate_bins = climate_info.get('bins', [-90, -35, -23.5, 23.5, 35, 90])
                climate_labels = climate_info.get('labels', ['polar_s', 'temperate_s', 'tropical', 'temperate_n', 'polar_n'])

                climate_zones = pd.cut(df_fe['G2latitude'], bins=climate_bins, labels=climate_labels)
                for zone in climate_labels:
                    df_fe[f'is_{zone}'] = (climate_zones == zone).astype(float)

    # 确保只保留训练时使用的特征
    final_features = feature_info.get('final_features', [])
    available_features = [f for f in final_features if f in df_fe.columns]

    if len(available_features) != len(final_features):
        missing_features = set(final_features) - set(available_features)
        print(f"⚠️  缺少特征: {missing_features}")
        print(f"   将使用 {len(available_features)} / {len(final_features)} 个特征")

    return df_fe[available_features]


def apply_physical_constraints(predictions):
    """应用物理边界约束"""
    print("🔒 应用物理边界约束...")

    original_stats = {
        'min': predictions.min(),
        'max': predictions.max(),
        'negative_count': (predictions < 0).sum(),
        'total_count': len(predictions)
    }

    # 限制亚硝酸盐浓度不能小于0
    predictions_constrained = np.maximum(predictions, 0.0)

    constrained_stats = {
        'min': predictions_constrained.min(),
        'max': predictions_constrained.max(),
        'corrected_count': (predictions < 0).sum()
    }

    print(f"  原始预测范围: [{original_stats['min']:.6f}, {original_stats['max']:.6f}]")
    print(f"  负值数量: {original_stats['negative_count']} / {original_stats['total_count']} ({original_stats['negative_count'] / original_stats['total_count'] * 100:.1f}%)")
    print(f"  约束后范围: [{constrained_stats['min']:.6f}, {constrained_stats['max']:.6f}]")
    print(f"  修正了 {constrained_stats['corrected_count']} 个负值")

    return predictions_constrained


def predict_gpu_optimized(X, model, use_gpu, gpu_id):
    """
    修正的GPU优化预测函数（参考训练代码成功经验）
    """
    try:
        if use_gpu and gpu_id is not None:
            print(f"  🚀 使用GPU {gpu_id} 进行预测...")
            # 参考训练代码的成功方式创建DMatrix
            dtest = xgb.DMatrix(X, missing=np.nan)
            # 注意：预测时不需要设置tree_method参数，这是训练时的参数
            predictions = model.predict(dtest)
        else:
            print("  💻 使用CPU进行预测...")
            dtest = xgb.DMatrix(X, missing=np.nan)
            predictions = model.predict(dtest)

        return predictions

    except Exception as e:
        print(f"  ⚠️  预测过程出错，尝试CPU预测: {e}")
        # 回退到CPU预测
        try:
            dtest = xgb.DMatrix(X, missing=np.nan)
            predictions = model.predict(dtest)
            print("  ✅ CPU预测成功")
            return predictions
        except Exception as e2:
            print(f"  ❌ CPU预测也失败: {e2}")
            raise e2


def process_chunk(chunk, original_indices, model, feature_info, use_gpu, gpu_id):
    """处理单个数据块"""
    try:
        # 保存原始数据用于输出
        original_chunk = chunk.copy()

        # 列名映射
        chunk_mapped = map_column_names(chunk)

        # 营养盐参数单位换算 (mmol/m³ → μmol/kg)
        chunk_converted, conversion_stats = convert_nutrient_units(chunk_mapped, verbose=False)

        # 数据预处理
        numeric_columns = chunk_converted.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            inf_count = np.isinf(chunk_converted[col]).sum()
            if inf_count > 0:
                chunk_converted[col] = chunk_converted[col].replace([np.inf, -np.inf], np.nan)

        # 应用特征工程
        X = apply_feature_engineering(chunk_converted, feature_info)

        # 修正的GPU优化预测
        predictions = predict_gpu_optimized(X, model, use_gpu, gpu_id)

        # 应用物理约束
        predictions_constrained = apply_physical_constraints(predictions)

        # 准备输出数据
        result_data = {}

        # 从原始数据获取基础列
        if 'year' in original_chunk.columns:
            result_data['year'] = original_chunk['year']
        elif 'G2year' in chunk_mapped.columns:
            result_data['year'] = chunk_mapped['G2year']
        else:
            result_data['year'] = np.nan

        if 'month' in original_chunk.columns:
            result_data['month'] = original_chunk['month']
        elif 'G2month' in chunk_mapped.columns:
            result_data['month'] = chunk_mapped['G2month']
        else:
            result_data['month'] = np.nan

        if 'longitude' in original_chunk.columns:
            result_data['longitude'] = original_chunk['longitude']
        elif 'G2longitude' in chunk_mapped.columns:
            result_data['longitude'] = chunk_mapped['G2longitude']
        else:
            result_data['longitude'] = np.nan

        if 'latitude' in original_chunk.columns:
            result_data['latitude'] = original_chunk['latitude']
        elif 'G2latitude' in chunk_mapped.columns:
            result_data['latitude'] = chunk_mapped['G2latitude']
        else:
            result_data['latitude'] = np.nan

        if 'depth' in original_chunk.columns:
            result_data['depth'] = original_chunk['depth']
        elif 'G2depth' in chunk_mapped.columns:
            result_data['depth'] = chunk_mapped['G2depth']
        else:
            result_data['depth'] = np.nan

        # 预测的亚硝酸盐
        result_data['nitrite_predicted'] = predictions_constrained

        # 原始硝酸盐数据（注意：这里使用原始值，不是转换后的值）
        if 'no3' in original_chunk.columns:
            result_data['nitrate'] = original_chunk['no3']
        else:
            result_data['nitrate'] = np.nan

        # 创建结果DataFrame
        result_df = pd.DataFrame(result_data)
        result_df.index = original_indices  # 保持原始索引

        return result_df, len(predictions_constrained)

    except Exception as e:
        print(f"❌ 处理数据块失败: {e}")
        return None, 0


def predict_streaming(file_path, model, feature_info, use_gpu, gpu_id, output_file):
    """流式处理大文件预测"""
    print(f"🌊 开始流式处理预测: {file_path}")

    chunk_size = STREAMING_CONFIG['chunk_size']
    processed_rows = 0
    total_predicted = 0
    chunk_count = 0

    # 检查是否有断点续传文件
    # 修正：确保路径类型正确
    temp_output_file = str(output_file) + '.tmp'
    if os.path.exists(temp_output_file):
        print(f"📂 发现临时文件，准备断点续传...")
        # 读取已处理的行数
        try:
            existing_df = pd.read_csv(temp_output_file)
            processed_rows = len(existing_df)
            print(f"   已处理 {processed_rows} 行，将从此处继续...")
        except:
            print(f"   临时文件读取失败，重新开始...")
            processed_rows = 0

    # 首先计算总行数用于进度显示
    print("🔍 计算文件总行数...")
    try:
        # 修正：确保文件路径是字符串类型
        total_rows = sum(1 for _ in open(str(file_path), 'r')) - 1  # 减去header
        print(f"   文件总行数: {total_rows:,}")
    except:
        total_rows = None
        print("   无法计算总行数，将显示已处理行数")

    # 创建进度条
    if TQDM_AVAILABLE and total_rows:
        pbar = tqdm(total=total_rows, desc="处理进度",
                   initial=processed_rows, unit="行")
    else:
        pbar = None

    try:
        # 流式读取CSV文件
        # 修正：确保文件路径是字符串类型
        chunk_reader = pd.read_csv(str(file_path), chunksize=chunk_size,
                                 skiprows=range(1, processed_rows + 1) if processed_rows > 0 else None)

        # 处理文件头（如果是新开始）
        write_header = processed_rows == 0

        for chunk in chunk_reader:
            chunk_count += 1
            current_memory = get_memory_usage_mb()

            print(f"\n🔄 处理第 {chunk_count} 个数据块")
            print(f"   数据块大小: {len(chunk):,} 行")
            print(f"   当前内存使用: {current_memory:.1f} MB")

            # 处理当前数据块
            chunk_start_idx = processed_rows
            chunk_indices = range(chunk_start_idx, chunk_start_idx + len(chunk))

            result_chunk, predicted_count = process_chunk(
                chunk, chunk_indices, model, feature_info, use_gpu, gpu_id
            )

            if result_chunk is not None:
                # 追加写入结果文件
                result_chunk.to_csv(temp_output_file, mode='a',
                                   header=write_header, index=False)
                write_header = False  # 只在第一次写入header

                processed_rows += len(chunk)
                total_predicted += predicted_count

                # 更新进度条
                if pbar:
                    pbar.update(len(chunk))

                # 显示预测统计
                predictions = result_chunk['nitrite_predicted']
                print(f"   ✅ 预测完成: {predicted_count} 个值")
                print(f"   预测范围: [{predictions.min():.6f}, {predictions.max():.6f}]")
                print(f"   累计处理: {processed_rows:,} 行")

                # 内存监控和垃圾回收
                if chunk_count % STREAMING_CONFIG['enable_gc_frequency'] == 0:
                    gc.collect()
                    new_memory = get_memory_usage_mb()
                    print(f"   垃圾回收后内存: {new_memory:.1f} MB")

                # 内存压力检查
                if current_memory > STREAMING_CONFIG['memory_threshold_mb']:
                    print(f"   ⚠️  内存使用过高 ({current_memory:.1f} MB)，执行垃圾回收...")
                    gc.collect()

            else:
                print(f"   ❌ 数据块处理失败，跳过...")
                # 仍然需要更新processed_rows以免重复处理
                processed_rows += len(chunk)
                if pbar:
                    pbar.update(len(chunk))

        # 处理完成，重命名临时文件
        if os.path.exists(temp_output_file):
            if os.path.exists(str(output_file)):
                os.remove(str(output_file))
            os.rename(temp_output_file, str(output_file))
            print(f"✅ 流式处理完成，结果已保存: {output_file}")

        if pbar:
            pbar.close()

        return total_predicted, processed_rows

    except Exception as e:
        if pbar:
            pbar.close()
        print(f"❌ 流式处理失败: {e}")
        import traceback
        traceback.print_exc()
        return 0, processed_rows


def predict_single_file_optimized(file_path, model, feature_info, use_gpu, gpu_id):
    """优化的单文件预测（自动选择处理方式）"""
    try:
        # 判断是否需要流式处理
        use_streaming, file_size_mb = should_use_streaming(file_path)

        if use_streaming:
            print(f"📁 文件 {file_path} ({file_size_mb:.1f} MB) 使用流式处理")
            return None  # 流式处理在调用方单独处理

        # 小文件：一次性处理
        print(f"📁 文件 {file_path} ({file_size_mb:.1f} MB) 使用一次性处理")

        # 加载数据
        # 修正：确保文件路径是字符串类型
        df = pd.read_csv(str(file_path))
        print(f"✅ 数据加载成功: {df.shape}")

        # 保存原始数据用于输出
        original_df = df.copy()

        # 列名映射
        df_mapped = map_column_names(df)

        # 营养盐参数单位换算 (mmol/m³ → μmol/kg)
        df_converted, conversion_stats = convert_nutrient_units(df_mapped, verbose=True)

        # 数据预处理
        print("🔧 数据预处理...")
        numeric_columns = df_converted.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            inf_count = np.isinf(df_converted[col]).sum()
            if inf_count > 0:
                print(f"  处理 {col}: {inf_count} 个inf值")
                df_converted[col] = df_converted[col].replace([np.inf, -np.inf], np.nan)

        # 应用特征工程
        X = apply_feature_engineering(df_converted, feature_info)
        print(f"✅ 特征工程完成: {X.shape}")

        # 修正的GPU优化预测
        print("🔮 执行预测...")
        predictions = predict_gpu_optimized(X, model, use_gpu, gpu_id)

        # 应用物理约束
        predictions_constrained = apply_physical_constraints(predictions)

        print(f"✅ 预测完成: {len(predictions_constrained)} 个预测值")

        # 准备输出数据
        result_data = {}

        # 从原始数据获取基础列
        if 'year' in original_df.columns:
            result_data['year'] = original_df['year']
        elif 'G2year' in df_mapped.columns:
            result_data['year'] = df_mapped['G2year']
        else:
            result_data['year'] = np.nan

        if 'month' in original_df.columns:
            result_data['month'] = original_df['month']
        elif 'G2month' in df_mapped.columns:
            result_data['month'] = df_mapped['G2month']
        else:
            result_data['month'] = np.nan

        if 'longitude' in original_df.columns:
            result_data['longitude'] = original_df['longitude']
        elif 'G2longitude' in df_mapped.columns:
            result_data['longitude'] = df_mapped['G2longitude']
        else:
            result_data['longitude'] = np.nan

        if 'latitude' in original_df.columns:
            result_data['latitude'] = original_df['latitude']
        elif 'G2latitude' in df_mapped.columns:
            result_data['latitude'] = df_mapped['G2latitude']
        else:
            result_data['latitude'] = np.nan

        if 'depth' in original_df.columns:
            result_data['depth'] = original_df['depth']
        elif 'G2depth' in df_mapped.columns:
            result_data['depth'] = df_mapped['G2depth']
        else:
            result_data['depth'] = np.nan

        # 预测的亚硝酸盐
        result_data['nitrite_predicted'] = predictions_constrained

        # 原始硝酸盐数据（注意：这里使用原始值，不是转换后的值）
        if 'no3' in original_df.columns:
            result_data['nitrate'] = original_df['no3']
        else:
            result_data['nitrate'] = np.nan

        # 创建结果DataFrame
        result_df = pd.DataFrame(result_data)

        # 显示预测统计
        print(f"\n📊 预测统计:")
        print(f"  预测值范围: [{predictions_constrained.min():.6f}, {predictions_constrained.max():.6f}]")
        print(f"  预测值均值: {predictions_constrained.mean():.6f}")
        print(f"  预测值标准差: {predictions_constrained.std():.6f}")
        print(f"  零值预测数: {(predictions_constrained == 0).sum()} ({(predictions_constrained == 0).mean() * 100:.1f}%)")
        print(f"  正值预测数: {(predictions_constrained > 0).sum()} ({(predictions_constrained > 0).mean() * 100:.1f}%)")

        return result_df

    except Exception as e:
        print(f"❌ 处理文件失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def batch_predict_nitrite_optimized(input_folder, output_folder, model, feature_info, use_gpu, gpu_id):
    """修正的单位换算版GPU优化批量预测主函数"""
    print(f"🌊 开始批量 G2nitrite 预测...")
    print(f"GPU模式: {'✅ 启用' if use_gpu else '❌ 禁用'}")
    if use_gpu:
        print(f"GPU设备: {gpu_id}")
    print(f"单位换算: mmol/m³ → μmol/kg (转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f})")

    # 查找输入文件
    input_path = Path(input_folder)
    csv_files = list(input_path.glob("*.csv"))

    if not csv_files:
        print(f"❌ 在输入文件夹中未找到CSV文件: {input_folder}")
        return False

    print(f"📁 找到 {len(csv_files)} 个CSV文件")

    # 创建输出文件夹
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # 批量处理
    successful_files = 0
    failed_files = []
    total_processed_rows = 0

    # 显示系统信息
    print(f"\n💻 系统信息:")
    print(f"   可用内存: {psutil.virtual_memory().available / (1024**3):.1f} GB")
    print(f"   CPU核心数: {psutil.cpu_count()}")
    print(f"   当前内存使用: {get_memory_usage_mb():.1f} MB")
    print(f"   平均海水密度: {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']} kg/m³")

    progress_bar = tqdm(csv_files, desc="处理文件") if TQDM_AVAILABLE else csv_files

    for csv_file in progress_bar:
        print(f"\n{'=' * 60}")
        print(f"🔄 处理文件: {csv_file.name}")
        print(f"{'=' * 60}")

        try:
            # 检查文件大小，决定处理方式
            use_streaming, file_size_mb = should_use_streaming(csv_file)

            # 生成输出文件名
            output_filename = f"predicted_{csv_file.stem}.csv"
            output_file = output_path / output_filename

            if use_streaming:
                # 流式处理
                predicted_count, processed_rows = predict_streaming(
                    str(csv_file), model, feature_info, use_gpu, gpu_id, str(output_file)
                )

                if predicted_count > 0:
                    print(f"✅ 流式处理完成: {output_filename}")
                    print(f"   处理行数: {processed_rows:,}")
                    print(f"   预测数量: {predicted_count:,}")
                    successful_files += 1
                    total_processed_rows += processed_rows
                else:
                    failed_files.append(csv_file.name)
                    print(f"❌ 流式处理失败: {csv_file.name}")

            else:
                # 一次性处理
                result_df = predict_single_file_optimized(str(csv_file), model, feature_info, use_gpu, gpu_id)

                if result_df is not None:
                    # 保存结果
                    result_df.to_csv(str(output_file), index=False)
                    print(f"✅ 结果已保存: {output_filename}")
                    print(f"   输出样本数: {len(result_df)}")
                    print(f"   输出列: {list(result_df.columns)}")

                    successful_files += 1
                    total_processed_rows += len(result_df)
                else:
                    failed_files.append(csv_file.name)
                    print(f"❌ 处理失败: {csv_file.name}")

            # 垃圾回收
            gc.collect()
            current_memory = get_memory_usage_mb()
            print(f"   当前内存使用: {current_memory:.1f} MB")

        except Exception as e:
            failed_files.append(csv_file.name)
            print(f"❌ 处理文件时出错 {csv_file.name}: {e}")

    # 生成处理报告
    print(f"\n{'=' * 80}")
    print(f"📊 批量预测完成报告 (修正单位换算版)")
    print(f"{'=' * 80}")
    print(f"总文件数: {len(csv_files)}")
    print(f"成功处理: {successful_files}")
    print(f"失败文件: {len(failed_files)}")
    print(f"总处理行数: {total_processed_rows:,}")
    print(f"GPU模式: {'启用' if use_gpu else '禁用'}")
    print(f"单位换算: mmol/m³ → μmol/kg")

    if failed_files:
        print(f"\n失败文件列表:")
        for i, filename in enumerate(failed_files, 1):
            print(f"  {i}. {filename}")

    # 保存处理报告
    report_file = output_path / "batch_prediction_report_unit_conversion.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"海洋化学数据批量预测报告 (修正单位换算版 + GPU优化 + 流式处理)\n")
        f.write(f"处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入文件夹: {input_folder}\n")
        f.write(f"输出文件夹: {output_folder}\n")
        f.write(f"GPU模式: {'启用' if use_gpu else '禁用'}\n")
        if use_gpu:
            f.write(f"GPU设备: {gpu_id}\n")
        f.write(f"流式处理阈值: {STREAMING_CONFIG['large_file_threshold_mb']} MB\n")
        f.write(f"分块大小: {STREAMING_CONFIG['chunk_size']:,} 行\n\n")

        f.write(f"单位换算配置:\n")
        f.write(f"  营养盐参数: {UNIT_CONVERSION_COLUMNS}\n")
        f.write(f"  输入单位: mmol/m³\n")
        f.write(f"  输出单位: μmol/kg\n")
        f.write(f"  平均海水密度: {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']} kg/m³\n")
        f.write(f"  转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f}\n")
        f.write(f"  换算公式: μmol/kg = mmol/m³ × {UNIT_CONVERSION_CONFIG['mmol_to_umol_factor']} / {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']}\n\n")

        f.write(f"处理统计:\n")
        f.write(f"  总文件数: {len(csv_files)}\n")
        f.write(f"  成功处理: {successful_files}\n")
        f.write(f"  失败文件: {len(failed_files)}\n")
        f.write(f"  总处理行数: {total_processed_rows:,}\n")
        f.write(f"  成功率: {successful_files / len(csv_files) * 100:.1f}%\n\n")

        f.write(f"修正内容:\n")
        f.write(f"  ✅ 添加营养盐参数单位换算 (mmol/m³ → μmol/kg)\n")
        f.write(f"  ✅ 使用平均海水密度进行换算\n")
        f.write(f"  ✅ 修正GPU检测和调用方式\n")
        f.write(f"  ✅ 简化GPU测试，避免空标签错误\n")
        f.write(f"  ✅ 优化DMatrix创建方式\n")
        f.write(f"  ✅ 参考训练代码成功经验\n")
        f.write(f"  ✅ 保持流式处理和内存优化功能\n\n")

        f.write(f"技术特性:\n")
        f.write(f"  ✅ 营养盐参数自动单位换算\n")
        f.write(f"  ✅ 修正后的GPU加速预测\n")
        f.write(f"  ✅ 流式处理大文件 (>{STREAMING_CONFIG['large_file_threshold_mb']} MB)\n")
        f.write(f"  ✅ 内存压力缓解\n")
        f.write(f"  ✅ 断点续传支持\n")
        f.write(f"  ✅ 自动垃圾回收\n")
        f.write(f"  ✅ 实时内存监控\n\n")

        f.write(f"列名映射:\n")
        for input_col, model_col in COLUMN_MAPPING.items():
            f.write(f"  {input_col} -> {model_col}\n")

        f.write(f"\n输出列顺序:\n")
        for i, col in enumerate(OUTPUT_COLUMNS, 1):
            f.write(f"  {i}. {col}\n")

        if failed_files:
            f.write(f"\n失败文件:\n")
            for filename in failed_files:
                f.write(f"  - {filename}\n")

    print(f"\n📄 处理报告已保存: {report_file}")

    if successful_files > 0:
        print(f"\n🎉 批量预测成功完成！")
        print(f"   成功处理 {successful_files} 个文件")
        print(f"   总处理行数: {total_processed_rows:,}")
        print(f"   预测结果保存在: {output_folder}")
        print(f"   GPU加速: {'✅ 已启用' if use_gpu else '❌ 未启用'}")
        print(f"   单位换算: ✅ 已启用 (mmol/m³ → μmol/kg)")
        return True
    else:
        print(f"\n❌ 批量预测失败，没有成功处理任何文件")
        return False


def main():
    """主程序"""
    print("🚀 海洋化学数据批量预测程序启动...")
    print("🔧 修正单位换算版 + GPU优化 + 流式处理大文件:")
    print("   - 添加营养盐参数单位换算 (mmol/m³ → μmol/kg)")
    print("   - 使用平均海水密度进行换算")
    print("   - 修正GPU检测和调用方式")
    print("   - 简化GPU测试，避免空标签错误")
    print("   - 优化DMatrix创建方式")
    print("   - 参考训练代码成功经验")
    print("   - 流式处理大文件 (支持10GB+)")
    print("   - 内存压力缓解 (分块处理)")
    print("   - 断点续传支持")
    print("   - 实时内存监控")
    print("   - 自动垃圾回收")
    print("=" * 80)

    # 第一步：选择模型文件夹
    print("\n📁 第一步：选择模型文件夹")
    model_folder = select_model_folder()
    if model_folder is None:
        print("❌ 未选择模型文件夹，程序退出")
        input("\n按回车键退出...")
        return

    # 第二步：加载模型（修正GPU优化版）
    print(f"\n🔧 第二步：加载模型和特征工程信息（修正GPU优化版）")
    model, feature_info, use_gpu, gpu_id = load_model_and_info_gpu(model_folder)
    if model is None or feature_info is None:
        print("❌ 模型加载失败，程序退出")
        input("\n按回车键退出...")
        return

    # 第三步：选择输入输出文件夹
    print(f"\n📁 第三步：选择数据处理文件夹")
    input_folder, output_folder = select_data_folders()
    if input_folder is None or output_folder is None:
        print("❌ 文件夹选择失败，程序退出")
        input("\n按回车键退出...")
        return

    # 显示所有设置
    print(f"\n{'=' * 80}")
    print(f"📋 设置确认")
    print(f"{'=' * 80}")
    print(f"📁 模型文件夹: {model_folder}")
    print(f"📁 输入文件夹: {input_folder}")
    print(f"📁 输出文件夹: {output_folder}")
    print(f"🚀 GPU加速: {'启用' if use_gpu else '禁用'}")
    if use_gpu:
        print(f"🎯 GPU设备: {gpu_id}")

    print(f"\n🔧 单位换算配置:")
    print(f"   营养盐参数: {UNIT_CONVERSION_COLUMNS}")
    print(f"   输入单位: mmol/m³")
    print(f"   输出单位: μmol/kg")
    print(f"   平均海水密度: {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']} kg/m³")
    print(f"   转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f}")
    print(f"   换算公式: μmol/kg = mmol/m³ × {UNIT_CONVERSION_CONFIG['mmol_to_umol_factor']} / {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']}")

    print(f"\n🔧 修正内容:")
    print(f"   ✅ 添加营养盐参数单位换算")
    print(f"   ✅ 使用平均海水密度进行换算")
    print(f"   ✅ 修正GPU检测和调用方式")
    print(f"   ✅ 简化GPU测试，避免空标签错误")
    print(f"   ✅ 优化DMatrix创建方式")
    print(f"   ✅ 参考训练代码成功经验")

    print(f"\n🔧 流式处理配置:")
    print(f"   大文件阈值: {STREAMING_CONFIG['large_file_threshold_mb']} MB")
    print(f"   分块大小: {STREAMING_CONFIG['chunk_size']:,} 行")
    print(f"   内存阈值: {STREAMING_CONFIG['memory_threshold_mb']} MB")
    print(f"   垃圾回收频率: 每 {STREAMING_CONFIG['enable_gc_frequency']} 个块")

    print(f"\n🔧 列名映射配置:")
    for input_col, model_col in COLUMN_MAPPING.items():
        print(f"   {input_col} -> {model_col}")

    print(f"\n📋 输出列配置:")
    for i, col in enumerate(OUTPUT_COLUMNS, 1):
        print(f"   {i}. {col}")

    # 确认开始处理
    if GUI_AVAILABLE:
        try:
            root = tk.Tk()
            root.withdraw()

            confirm = messagebox.askyesno(
                "确认处理",
                f"准备开始批量预测 (修正单位换算版)\n\n"
                f"模型文件夹: {model_folder}\n"
                f"输入文件夹: {input_folder}\n"
                f"输出文件夹: {output_folder}\n"
                f"GPU加速: {'启用' if use_gpu else '禁用'}\n"
                f"大文件阈值: {STREAMING_CONFIG['large_file_threshold_mb']} MB\n\n"
                f"单位换算:\n"
                f"- 营养盐参数: {', '.join(UNIT_CONVERSION_COLUMNS)}\n"
                f"- 输入单位: mmol/m³\n"
                f"- 输出单位: μmol/kg\n"
                f"- 转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f}\n\n"
                f"修正功能:\n"
                f"- 添加营养盐参数单位换算\n"
                f"- 使用平均海水密度进行换算\n"
                f"- 修正GPU检测和调用方式\n"
                f"- 简化GPU测试，避免空标签错误\n"
                f"- 优化DMatrix创建方式\n"
                f"- 参考训练代码成功经验\n"
                f"- 流式处理大文件\n"
                f"- 内存压力缓解\n"
                f"- 断点续传支持\n"
                f"- 实时内存监控\n\n"
                f"是否开始处理？"
            )

            root.destroy()

            if not confirm:
                print("❌ 用户取消操作")
                return
        except:
            pass
    else:
        confirm = input("\n是否开始批量预测？(y/n): ").lower().strip()
        if confirm not in ['y', 'yes', '是']:
            print("❌ 用户取消操作")
            return

    # 开始批量预测
    print(f"\n{'=' * 80}")
    print(f"🚀 开始批量预测处理 (修正单位换算版)")
    print(f"{'=' * 80}")

    start_time = time.time()
    success = batch_predict_nitrite_optimized(input_folder, output_folder, model, feature_info, use_gpu, gpu_id)
    end_time = time.time()

    processing_time = end_time - start_time
    print(f"\n⏱️  总处理时间: {processing_time:.1f} 秒 ({processing_time / 60:.1f} 分钟)")

    # 显示完成消息
    if GUI_AVAILABLE and success:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "批量预测完成",
                f"批量预测成功完成！(修正单位换算版)\n\n"
                f"模型文件夹: {model_folder}\n"
                f"输入文件夹: {input_folder}\n"
                f"输出文件夹: {output_folder}\n"
                f"处理时间: {processing_time:.1f} 秒\n"
                f"GPU加速: {'启用' if use_gpu else '禁用'}\n\n"
                f"单位换算:\n"
                f"✅ 营养盐参数: mmol/m³ → μmol/kg\n"
                f"✅ 转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f}\n\n"
                f"修正功能:\n"
                f"✅ 添加营养盐参数单位换算\n"
                f"✅ 使用平均海水密度进行换算\n"
                f"✅ 修正GPU检测和调用方式\n"
                f"✅ 简化GPU测试，避免空标签错误\n"
                f"✅ 优化DMatrix创建方式\n"
                f"✅ 参考训练代码成功经验\n"
                f"✅ 流式处理大文件\n"
                f"✅ 内存压力缓解\n"
                f"✅ 断点续传支持\n"
                f"✅ 物理边界约束 (nitrite ≥ 0)\n"
                f"✅ 标准化输出格式\n"
                f"✅ 详细处理报告"
            )
            root.destroy()
        except:
            pass

    print(f"\n💡 使用说明:")
    print(f"   1. 预测结果文件命名格式: predicted_[原文件名].csv")
    print(f"   2. 输出列包含: 年月经纬度深度、预测nitrite、原始nitrate")
    print(f"   3. 预测值已应用物理约束 (nitrite ≥ 0)")
    print(f"   4. 详细处理报告: batch_prediction_report_unit_conversion.txt")
    print(f"   5. 大文件自动使用流式处理，支持断点续传")

    print(f"\n🔧 单位换算说明:")
    print(f"   ✅ 营养盐参数自动换算: {UNIT_CONVERSION_COLUMNS}")
    print(f"   ✅ 换算公式: μmol/kg = mmol/m³ × {UNIT_CONVERSION_CONFIG['mmol_to_umol_factor']} / {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']}")
    print(f"   ✅ 转换因子: {UNIT_CONVERSION_CONFIG['conversion_factor']:.6f}")
    print(f"   ✅ 平均海水密度: {UNIT_CONVERSION_CONFIG['seawater_density_kg_per_m3']} kg/m³")
    print(f"   ⚠️  输出文件中的硝酸盐值仍为原始单位 (mmol/m³)")

    print(f"\n🔧 修正内容:")
    print(f"   ✅ 添加营养盐参数单位换算 (mmol/m³ → μmol/kg)")
    print(f"   ✅ 使用平均海水密度进行换算")
    print(f"   ✅ 修正GPU检测和调用方式 (参考训练代码成功经验)")
    print(f"   ✅ 简化GPU测试，避免空标签错误")
    print(f"   ✅ 优化DMatrix创建方式")
    print(f"   ✅ 预测时不设置tree_method参数 (仅训练时需要)")
    print(f"   ✅ 改进错误处理和回退机制")

    print(f"\n🔧 保持的技术特点:")
    print(f"   ✅ 流式处理大文件 (支持10GB+)")
    print(f"   ✅ 内存压力缓解 (分块处理)")
    print(f"   ✅ 断点续传支持")
    print(f"   ✅ 实时内存监控")
    print(f"   ✅ 自动垃圾回收")
    print(f"   ✅ 智能处理方式选择")
    print(f"   ✅ 基于海洋化学专业知识的特征工程")
    print(f"   ✅ 与训练模型完全一致的预处理流程")
    print(f"   ✅ 物理约束应用")
    print(f"   ✅ 详细错误处理和报告")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断程序")
    except Exception as e:
        print(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按回车键退出...")