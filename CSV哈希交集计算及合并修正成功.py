#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import multiprocessing as mp
import time
from datetime import datetime
import gc
import logging
from tqdm import tqdm
import hashlib
import psutil
import tempfile
import shutil
import warnings
from functools import partial
import threading
import queue
import subprocess
import csv
from pathlib import Path
import re
import sys
import heapq
import io
import concurrent.futures

# 忽略警告
warnings.filterwarnings('ignore')

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局配置，优化版
CONFIG = {
    'max_workers': 3,  # 从5减少到3，降低并发内存使用
    'memory_limit_percent': 80,  # 从90%降低到80%
    'chunk_size': 100000,  # 从50000增加到100000，提高批处理效率
    'use_external_sort': False,  # Windows环境下禁用外部排序
    'temp_dir': None,  # 临时目录，将动态设置
    'max_open_files': 50,  # 从100减少到50
    'keep_temp_files': True,  # 保留临时文件（不自动清除）
    'ssd_optimized': True,  # SSD优化开关
    'sort_chunk_size': 5000000,  # 排序块大小
    'buffer_size': 16 * 1024 * 1024,  # 从4MB增加到16MB，提高IO性能
    'parallel_sort': False,  # 禁用并行排序以避免嵌套进程问题
    'parallel_sort_workers': 2,  # 从4减少到2
    'hash_group_digits': 2,  # 哈希分组数量，从1位增加到2位
    'use_parallel_filter': True,  # 启用并行筛选
    'use_threaded_io': True,  # 启用多线程IO
    'batch_buffer_limit': 200000,  # 批量写入缓冲区大小
    'show_progress_bar': True  # 显示进度条
}


# 内存监控函数
def memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / 1024 / 1024  # MB


# 获取系统可用内存
def get_available_memory():
    return psutil.virtual_memory().available / (1024 * 1024)  # MB


# 检查内存状态，如果超过阈值则强制垃圾回收
def check_memory(threshold_percent=None, critical_percent=95, force_gc=True):
    """
    检查内存状态，如果超过阈值则执行优化措施
    """
    if threshold_percent is None:
        threshold_percent = CONFIG['memory_limit_percent']

    # 获取当前内存使用情况
    current_percent = psutil.virtual_memory().percent

    # 如果超过紧急阈值，采取紧急措施
    if current_percent > critical_percent:
        logger.warning(f"内存使用率 {current_percent}% 超过紧急阈值 {critical_percent}%，执行紧急优化")

        # 1. 强制多次垃圾回收
        for _ in range(3):
            gc.collect()

        # 2. 尝试清理Python对象缓存
        gc.collect(0)  # 收集第0代对象
        gc.collect(1)  # 收集第1代对象
        gc.collect(2)  # 收集第2代对象

        # 3. 建议系统回收内存（不一定所有系统都支持）
        try:
            import ctypes
            libc = ctypes.CDLL('libc.so.6')
            libc.malloc_trim(0)
        except:
            pass

        return True

    # 如果超过常规阈值执行常规优化
    elif current_percent > threshold_percent:
        logger.warning(f"内存使用率 {current_percent}% 超过阈值 {threshold_percent}%，执行优化")

        # 执行垃圾回收
        if force_gc:
            gc.collect()

        return True

    return False


# 统一的哈希值计算函数
def calculate_hash(month, longitude, latitude, depth):
    """统一的哈希值计算函数，确保所有计算方式一致"""
    # 转换为浮点数确保类型一致
    longitude_float = float(longitude)
    latitude_float = float(latitude)
    depth_float = float(depth)

    # 使用固定精度格式化
    longitude_str = f"{round(longitude_float, 4):.4f}"
    latitude_str = f"{round(latitude_float, 4):.4f}"
    depth_str = f"{round(depth_float, 2):.2f}"

    identifier = f"{month}_{longitude_str}_{latitude_str}_{depth_str}"
    return identifier, hashlib.md5(identifier.encode()).hexdigest()


# 创建临时文件目录
def create_temp_dir(base_dir=None, prefix="ocean_data_"):
    """
    创建临时文件目录
    base_dir: 基础目录，如果指定则在此目录下创建临时文件夹
    prefix: 临时文件夹前缀
    """
    if base_dir and os.path.exists(base_dir):
        # 如果指定了基础目录，在该目录下创建带时间戳的子文件夹
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = os.path.join(base_dir, f"{prefix}{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
    else:
        # 否则使用系统临时目录
        temp_dir = tempfile.mkdtemp(prefix=prefix)

    logger.info(f"创建临时目录: {temp_dir}")

    # 设置环境变量和Python临时目录
    try:
        tempfile.tempdir = temp_dir
        os.environ['TMPDIR'] = temp_dir  # Unix/Linux
        os.environ['TEMP'] = temp_dir  # Windows
        os.environ['TMP'] = temp_dir  # Windows替代变量
        logger.info(f"已设置临时目录环境变量为: {temp_dir}")
    except Exception as e:
        logger.warning(f"设置临时目录环境变量失败: {str(e)}")

    return temp_dir


# 清理临时文件目录
def cleanup_temp_dir(temp_dir):
    """
    清理临时文件目录
    temp_dir: 临时目录路径
    """
    # 如果设置了保留临时文件，则不清除
    if CONFIG.get('keep_temp_files', True):
        logger.info(f"保留临时目录: {temp_dir}")
        return

    # 否则清除临时目录
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"清理临时目录: {temp_dir}")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {str(e)}")


# 分块读取CSV文件的行数，针对Windows优化
def count_csv_lines(file_path):
    try:
        # Windows系统直接使用手动计数方法
        if os.name == 'nt':
            logger.info(f"开始手动计数文件行数: {file_path}")
            count = 0
            with open(file_path, 'r', buffering=CONFIG['buffer_size']) as f:
                for _ in f:
                    count += 1
                    if count % 1000000 == 0:
                        logger.info(f"已计数 {count} 行...")
            logger.info(f"文件 {file_path} 包含 {count} 行")
            return count
        # 非Windows系统尝试使用wc命令
        else:
            try:
                result = subprocess.run(['wc', '-l', file_path],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        timeout=30)
                if result.returncode == 0:
                    count = int(result.stdout.strip().split()[0])
                    logger.info(f"使用wc命令计数: {file_path} 包含 {count} 行")
                    return count
            except:
                pass

        # 如果wc命令失败，使用手动计数方法
        logger.info(f"开始手动计数文件行数: {file_path}")
        count = 0
        # 使用更大的缓冲区提高SSD读取性能
        with open(file_path, 'r', buffering=CONFIG['buffer_size']) as f:
            for _ in f:
                count += 1
                if count % 1000000 == 0:
                    logger.info(f"已计数 {count} 行...")

        logger.info(f"文件 {file_path} 包含 {count} 行")
        return count
    except Exception as e:
        logger.error(f"计数行数出错: {str(e)}")
        # 返回一个估计值
        file_size = os.path.getsize(file_path)
        # 假设每行平均200字节
        estimated_lines = file_size // 200
        logger.warning(f"使用估计值: {estimated_lines} 行")
        return estimated_lines


# 修改：使用最小内存快速创建哈希值集合 - 优化版本，统一舍入处理
def extract_hashes_from_csv(file_path, temp_dir, columns=None):
    """
    从CSV文件中提取经纬度、深度、月份组合的哈希值
    使用最小内存占用的方式 - 优化版本，确保与calculate_hash函数一致的舍入规则
    """
    logger.info(f"从文件提取哈希值: {os.path.basename(file_path)}")

    # 验证输入文件
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到输入文件: {file_path}")

    # 验证临时目录
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir, exist_ok=True)

    # 确保所有临时操作使用指定目录
    current_tempdir = tempfile.gettempdir()
    if current_tempdir != temp_dir:
        logger.warning(f"当前临时目录({current_tempdir})与指定临时目录({temp_dir})不一致，尝试修正")
        tempfile.tempdir = temp_dir
        os.environ['TMPDIR'] = temp_dir  # Unix/Linux
        os.environ['TEMP'] = temp_dir  # Windows
        os.environ['TMP'] = temp_dir  # Windows替代变量

    # 创建输出文件 - 明确使用指定的临时目录
    hash_file = os.path.join(temp_dir, f"hashes_{os.path.basename(file_path)}.txt")
    logger.info(f"哈希值将保存至: {hash_file}")

    # 打开输入和输出文件
    total_rows = 0
    chunk_size = CONFIG['chunk_size']

    try:
        # 获取文件总行数
        file_size = os.path.getsize(file_path)
        estimated_lines = file_size // 200  # 估计总行数（每行约200字节）

        # 使用tqdm进度条显示进度
        if CONFIG['show_progress_bar']:
            with open(hash_file, 'w', buffering=CONFIG['buffer_size']) as out_file:
                reader = pd.read_csv(file_path, chunksize=chunk_size, usecols=columns)
                progress_bar = tqdm(total=estimated_lines, desc=f"提取哈希值: {os.path.basename(file_path)}")

                for chunk in reader:
                    # 关键修改：确保与calculate_hash完全一致的处理方式
                    # 1. 转换为字符串前先分别舍入到指定精度（不是连续两次）
                    chunk['longitude_rounded'] = chunk['longitude'].apply(lambda x: round(float(x), 4))
                    chunk['latitude_rounded'] = chunk['latitude'].apply(lambda x: round(float(x), 4))
                    chunk['depth_rounded'] = chunk['depth'].apply(lambda x: round(float(x), 2))

                    # 2. 使用与calculate_hash相同的格式化方式
                    chunk['longitude_str'] = chunk['longitude_rounded'].apply(lambda x: f"{x:.4f}")
                    chunk['latitude_str'] = chunk['latitude_rounded'].apply(lambda x: f"{x:.4f}")
                    chunk['depth_str'] = chunk['depth_rounded'].apply(lambda x: f"{x:.2f}")

                    # 3. 构建标识符和计算哈希值
                    chunk['identifier'] = (
                            chunk['month'].astype(str) + '_' +
                            chunk['longitude_str'] + '_' +
                            chunk['latitude_str'] + '_' +
                            chunk['depth_str']
                    )

                    # 计算哈希值
                    for identifier in chunk['identifier']:
                        hash_value = hashlib.md5(identifier.encode()).hexdigest()
                        out_file.write(f"{hash_value}\n")

                    total_rows += len(chunk)
                    progress_bar.update(len(chunk))

                    # 检查并释放内存
                    if total_rows % (chunk_size * 10) == 0:
                        check_memory()
                        gc.collect()

                    # 清除chunk引用，减少内存占用
                    del chunk

                progress_bar.close()
        else:
            # 不显示进度条的版本
            with open(hash_file, 'w', buffering=CONFIG['buffer_size']) as out_file:
                reader = pd.read_csv(file_path, chunksize=chunk_size, usecols=columns)

                for i, chunk in enumerate(reader):
                    # 关键修改：确保与calculate_hash完全一致的处理方式
                    # 1. 转换为字符串前先分别舍入到指定精度（不是连续两次）
                    chunk['longitude_rounded'] = chunk['longitude'].apply(lambda x: round(float(x), 4))
                    chunk['latitude_rounded'] = chunk['latitude'].apply(lambda x: round(float(x), 4))
                    chunk['depth_rounded'] = chunk['depth'].apply(lambda x: round(float(x), 2))

                    # 2. 使用与calculate_hash相同的格式化方式
                    chunk['longitude_str'] = chunk['longitude_rounded'].apply(lambda x: f"{x:.4f}")
                    chunk['latitude_str'] = chunk['latitude_rounded'].apply(lambda x: f"{x:.4f}")
                    chunk['depth_str'] = chunk['depth_rounded'].apply(lambda x: f"{x:.2f}")

                    # 3. 构建标识符和计算哈希值
                    chunk['identifier'] = (
                            chunk['month'].astype(str) + '_' +
                            chunk['longitude_str'] + '_' +
                            chunk['latitude_str'] + '_' +
                            chunk['depth_str']
                    )

                    # 计算哈希值
                    for identifier in chunk['identifier']:
                        hash_value = hashlib.md5(identifier.encode()).hexdigest()
                        out_file.write(f"{hash_value}\n")

                    total_rows += len(chunk)

                    if i % 10 == 0:
                        logger.info(f"已处理 {total_rows} 行...")
                        # 检查并释放内存
                        check_memory()
                        # 增加显式垃圾回收频率
                        gc.collect()

                    # 清除chunk引用，减少内存占用
                    del chunk
                    gc.collect()

    except Exception as e:
        logger.error(f"提取哈希值时出错: {str(e)}")
        raise

    logger.info(f"完成哈希值提取，共处理 {total_rows} 行，结果保存至: {hash_file}")
    return hash_file, total_rows


# 并行排序一个文件块
def parallel_sort_chunk(file_chunk, temp_file):
    """并行对一个文件块进行排序"""
    lines = [line.strip() for line in file_chunk if line.strip()]
    lines.sort()

    with open(temp_file, 'w', buffering=CONFIG['buffer_size']) as f:
        for line in lines:
            f.write(f"{line}\n")

    return temp_file


# 修复4: 添加进程类型检查，修改sort_large_file函数以使用线程池
def sort_large_file(input_file, output_file, chunk_size=None):
    """
    对大文件进行外部排序 - SSD优化版
    使用分块读取、内存排序、多路归并的方法
    修复了Windows环境下的进程创建问题和嵌套进程问题
    使用线程池而非进程池提高Windows系统性能
    """
    if chunk_size is None:
        chunk_size = CONFIG['sort_chunk_size']

    # 检查是否在子进程中运行
    is_subprocess = mp.current_process().name != 'MainProcess'

    # 临时文件目录
    temp_dir = os.path.dirname(output_file)
    temp_files = []

    try:
        # 步骤1: 分块读取并排序
        logger.info(f"对文件 {os.path.basename(input_file)} 进行分块排序...")

        # 计算文件总行数（估计值）
        file_size = os.path.getsize(input_file)
        # 假设每行平均30字节，估算总行数和块数
        est_total_lines = file_size // 30
        est_chunks = est_total_lines // chunk_size + 1

        logger.info(f"估计文件含有约 {est_total_lines} 行，将分为约 {est_chunks} 个块")

        # 分块读取、排序、写入临时文件
        chunk_count = 0

        # SSD优化: 使用更大的块和缓冲区
        if CONFIG['ssd_optimized']:
            # 使用较大的缓冲区读取文件
            with open(input_file, 'r', buffering=CONFIG['buffer_size']) as f:
                lines = []

                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)

                    if len(lines) >= chunk_size:
                        # 修改: 使用线程池而非进程池，Windows下也可并行
                        parallel_sort_enabled = (CONFIG['parallel_sort'] and
                                                 CONFIG['parallel_sort_workers'] > 1 and
                                                 not is_subprocess and
                                                 len(lines) > 100000)

                        if parallel_sort_enabled:
                            # 并行排序 - 使用线程池，在Windows上也能高效运行
                            logger.info(f"线程池并行排序块 {chunk_count}...")

                            # 将行数据分成几个子块
                            worker_count = CONFIG['parallel_sort_workers']
                            sub_chunks = [[] for _ in range(worker_count)]

                            # 平均分配行到子块
                            for idx, line in enumerate(lines):
                                sub_chunks[idx % worker_count].append(line)

                            # 创建临时文件路径
                            sub_temp_files = [
                                os.path.join(temp_dir, f"temp_sorted_subchunk_{chunk_count}_{i}.txt")
                                for i in range(worker_count)
                            ]

                            # 使用线程池进行并行排序 - 在Windows上也能高效运行
                            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                                futures = []
                                for i, sub_chunk in enumerate(sub_chunks):
                                    futures.append(
                                        executor.submit(
                                            parallel_sort_chunk,
                                            sub_chunk, sub_temp_files[i]
                                        )
                                    )

                                # 收集结果
                                sub_temp_files = [future.result() for future in futures]

                            # 归并排序的子块
                            merged_temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{chunk_count}.txt")
                            merge_sorted_files(sub_temp_files, merged_temp_file)

                            # 清理子块临时文件
                            for sub_file in sub_temp_files:
                                if os.path.exists(sub_file):
                                    os.remove(sub_file)

                            temp_files.append(merged_temp_file)

                        else:
                            # 串行排序 - 在子进程中使用
                            lines.sort()

                            # 写入临时文件
                            temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{chunk_count}.txt")
                            with open(temp_file, 'w', buffering=CONFIG['buffer_size']) as temp_f:
                                for sorted_line in lines:
                                    temp_f.write(f"{sorted_line}\n")

                            temp_files.append(temp_file)

                        chunk_count += 1

                        # 清空内存
                        lines = []

                        # 强制垃圾回收
                        gc.collect()

                        if chunk_count % 10 == 0:
                            logger.info(f"已处理 {chunk_count} 个块...")

                # 处理最后一个不完整的块
                if lines:
                    # 对于最后一块，也使用相同的并行/串行策略
                    parallel_sort_enabled = (CONFIG['parallel_sort'] and
                                             CONFIG['parallel_sort_workers'] > 1 and
                                             not is_subprocess and
                                             len(lines) > 100000)

                    if parallel_sort_enabled:
                        # 对最后一块使用线程池并行排序
                        logger.info(f"线程池并行排序最后一块 {chunk_count}...")

                        worker_count = CONFIG['parallel_sort_workers']
                        sub_chunks = [[] for _ in range(worker_count)]

                        for idx, line in enumerate(lines):
                            sub_chunks[idx % worker_count].append(line)

                        sub_temp_files = [
                            os.path.join(temp_dir, f"temp_sorted_subchunk_{chunk_count}_{i}.txt")
                            for i in range(worker_count)
                        ]

                        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                            futures = []
                            for i, sub_chunk in enumerate(sub_chunks):
                                futures.append(
                                    executor.submit(
                                        parallel_sort_chunk,
                                        sub_chunk, sub_temp_files[i]
                                    )
                                )

                            sub_temp_files = [future.result() for future in futures]

                        merged_temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{chunk_count}.txt")
                        merge_sorted_files(sub_temp_files, merged_temp_file)

                        for sub_file in sub_temp_files:
                            if os.path.exists(sub_file):
                                os.remove(sub_file)

                        temp_files.append(merged_temp_file)
                    else:
                        # 串行排序
                        lines.sort()

                        temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{chunk_count}.txt")
                        with open(temp_file, 'w', buffering=CONFIG['buffer_size']) as temp_f:
                            for sorted_line in lines:
                                temp_f.write(f"{sorted_line}\n")

                        temp_files.append(temp_file)

                    chunk_count += 1

        else:
            # 原始实现，不使用SSD优化
            with open(input_file, 'r') as f:
                lines = []

                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)

                    if len(lines) >= chunk_size:
                        # 排序当前块
                        lines.sort()

                        # 写入临时文件
                        temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{chunk_count}.txt")
                        with open(temp_file, 'w') as temp_f:
                            for sorted_line in lines:
                                temp_f.write(f"{sorted_line}\n")

                        temp_files.append(temp_file)
                        chunk_count += 1

                        # 清空内存
                        lines = []

                        # 强制垃圾回收
                        gc.collect()

                        if chunk_count % 10 == 0:
                            logger.info(f"已处理 {chunk_count} 个块...")

                # 处理最后一个不完整的块
                if lines:
                    lines.sort()

                    temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{chunk_count}.txt")
                    with open(temp_file, 'w') as temp_f:
                        for sorted_line in lines:
                            temp_f.write(f"{sorted_line}\n")

                    temp_files.append(temp_file)
                    chunk_count += 1

        logger.info(f"分块排序完成，共 {chunk_count} 个排序块")

        # 步骤2: 归并排序块
        if len(temp_files) == 1:
            # 只有一个块，直接重命名
            shutil.move(temp_files[0], output_file)
        else:
            # 多路归并
            logger.info("执行多路归并...")
            merge_sorted_files(temp_files, output_file)

        logger.info(f"文件排序完成: {os.path.basename(output_file)}")

    finally:
        # 清理临时文件
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

        # 强制垃圾回收
        gc.collect()


# 归并多个排序文件 - SSD优化版
def merge_sorted_files(input_files, output_file):
    """
    归并多个已排序的文件 - SSD优化版
    使用小根堆进行多路归并，利用大缓冲区提高SSD性能
    """
    import heapq

    # SSD优化：减少打开文件数量，分批次归并
    max_open_files = min(CONFIG['max_open_files'], 20)  # SSD可以适当增加同时打开的文件数

    if len(input_files) <= max_open_files:
        # 一次性归并所有文件
        _merge_files_batch(input_files, output_file)
    else:
        # 分批次归并
        logger.info(f"文件数量({len(input_files)})超过最大同时打开文件数({max_open_files})，进行分批归并")

        batch_size = max_open_files - 1  # 留一个文件句柄给输出文件
        batches = []

        # 分批归并
        for i in range(0, len(input_files), batch_size):
            batch = input_files[i:i + batch_size]

            # 创建临时输出文件
            temp_output = f"{output_file}_batch_{i // batch_size}.tmp"
            _merge_files_batch(batch, temp_output)

            batches.append(temp_output)

        # 归并临时文件
        logger.info(f"归并 {len(batches)} 个批次文件...")
        _merge_files_batch(batches, output_file)

        # 清理临时批次文件
        for batch_file in batches:
            if os.path.exists(batch_file):
                os.remove(batch_file)


# 内部函数：归并一批排序文件
def _merge_files_batch(input_files, output_file):
    """归并一批排序文件"""
    # 打开所有输入文件
    file_handlers = []
    for i, f_path in enumerate(input_files):
        try:
            # SSD优化：使用大缓冲区
            fh = open(f_path, 'r', buffering=CONFIG['buffer_size'])
            file_handlers.append(fh)
        except Exception as e:
            logger.error(f"打开文件失败: {f_path}, 错误: {str(e)}")
            # 关闭已打开的文件
            for h in file_handlers:
                h.close()
            raise

    try:
        # SSD优化：使用大缓冲区
        with open(output_file, 'w', buffering=CONFIG['buffer_size']) as out_f:
            # 初始化小根堆
            heap = []
            for i, fh in enumerate(file_handlers):
                line = fh.readline().strip()
                if line:
                    # 使用(值, 文件索引)的形式加入堆
                    heapq.heappush(heap, (line, i))

            # 前一个写入的值，用于去重
            prev_val = None
            # 计数器，用于显示进度
            merged_count = 0

            # 归并过程
            while heap:
                # 取出最小值
                val, file_idx = heapq.heappop(heap)

                # 去重
                if val != prev_val:
                    out_f.write(f"{val}\n")
                    prev_val = val
                    merged_count += 1

                    # 显示进度
                    if merged_count % 10000000 == 0:  # 每合并1000万行显示一次
                        logger.info(f"已归并 {merged_count} 行...")

                # 从相应文件读取下一行
                line = file_handlers[file_idx].readline().strip()
                if line:
                    heapq.heappush(heap, (line, file_idx))

            logger.info(f"归并完成，共 {merged_count} 行")

    finally:
        # 关闭所有文件
        for fh in file_handlers:
            fh.close()


# 使用归并算法查找两个已排序文件的交集 - SSD优化版
def merge_find_intersection(sorted_file1, sorted_file2, output_file):
    """
    使用归并算法查找两个已排序文件的交集 - SSD优化版
    这是一种极低内存占用的方法，针对SSD进行了优化
    """
    try:
        # SSD优化：使用大缓冲区
        with open(sorted_file1, 'r', buffering=CONFIG['buffer_size']) as f1, \
                open(sorted_file2, 'r', buffering=CONFIG['buffer_size']) as f2, \
                open(output_file, 'w', buffering=CONFIG['buffer_size']) as out:

            line1 = f1.readline().strip()
            line2 = f2.readline().strip()

            count = 0

            # SSD优化：批量处理，减少IO操作次数
            output_buffer = []
            buffer_size = 200000  # 从100000增加到200000，减少IO操作

            while line1 and line2:
                if line1 == line2:
                    # 找到交集元素，加入缓冲区
                    output_buffer.append(line1)
                    count += 1

                    # 如果缓冲区满了，批量写入
                    if len(output_buffer) >= buffer_size:
                        out.write('\n'.join(output_buffer) + '\n')
                        output_buffer = []
                        logger.info(f"已找到 {count} 个交集...")

                    line1 = f1.readline().strip()
                    line2 = f2.readline().strip()
                elif line1 < line2:
                    line1 = f1.readline().strip()
                else:
                    line2 = f2.readline().strip()

            # 写入剩余的缓冲区内容
            if output_buffer:
                out.write('\n'.join(output_buffer) + '\n')

            logger.info(f"交集查找完成，共 {count} 个交集")
            return count

    except Exception as e:
        logger.error(f"归并查找交集出错: {str(e)}")
        raise


# 改进后的哈希交集查找函数 - 针对Windows优化
def find_hash_intersection(hash_file1, hash_file2, output_file, use_external_sort=None):
    """在两个哈希文件之间查找交集，使用针对SSD优化的极低内存方法"""
    logger.info(f"查找哈希交集: {os.path.basename(hash_file1)} 和 {os.path.basename(hash_file2)}")

    # 验证输入文件
    if not os.path.exists(hash_file1):
        raise FileNotFoundError(f"找不到哈希文件1: {hash_file1}")
    if not os.path.exists(hash_file2):
        raise FileNotFoundError(f"找不到哈希文件2: {hash_file2}")

    # 验证输出目录
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 在Windows环境下禁用外部排序
    if use_external_sort is None:
        use_external_sort = CONFIG['use_external_sort'] and os.name != 'nt'

    # Linux系统下尝试使用外部命令
    if use_external_sort and os.name != 'nt':
        try:
            # 使用外部排序首先对文件进行排序 (Linux系统)
            sorted_file1 = hash_file1 + ".sorted"
            sorted_file2 = hash_file2 + ".sorted"

            logger.info("使用外部排序...")
            # SSD优化：增加排序缓冲区
            sort_buffer = "4G"  # 4GB排序缓冲区
            subprocess.run(['sort', '-S', sort_buffer, '-u', '-o', sorted_file1, hash_file1], check=True)
            subprocess.run(['sort', '-S', sort_buffer, '-u', '-o', sorted_file2, hash_file2], check=True)

            # 使用comm命令找交集 (效率更高)
            logger.info("找交集...")
            with open(output_file, 'w') as out:
                subprocess.run(['comm', '-1', '-2', sorted_file1, sorted_file2],
                               stdout=out, check=True)

            # 清理临时文件
            os.remove(sorted_file1)
            os.remove(sorted_file2)

            # 计算交集大小
            count = sum(1 for _ in open(output_file))
            logger.info(f"发现 {count} 个共有哈希值")
            return count

        except Exception as e:
            logger.warning(f"外部排序方法失败: {str(e)}，使用分块处理方法")

    # ---- SSD优化: 使用针对SSD优化的分块哈希集处理方法 ----
    logger.info("使用SSD优化的磁盘分块处理方法查找交集...")

    # 临时文件准备
    temp_dir = os.path.dirname(output_file)
    sorted_file1 = os.path.join(temp_dir, f"sorted_{os.path.basename(hash_file1)}")
    sorted_file2 = os.path.join(temp_dir, f"sorted_{os.path.basename(hash_file2)}")

    try:
        # 步骤1: 对两个哈希文件进行排序 (SSD优化的外部排序)
        logger.info("步骤1: 对哈希文件进行排序...")
        sort_large_file(hash_file1, sorted_file1, CONFIG['sort_chunk_size'])
        sort_large_file(hash_file2, sorted_file2, CONFIG['sort_chunk_size'])

        # 步骤2: 使用SSD优化的归并算法找出交集
        logger.info("步骤2: 使用SSD优化的归并算法找出交集...")
        count = merge_find_intersection(sorted_file1, sorted_file2, output_file)

        # 清理临时排序文件
        if os.path.exists(sorted_file1):
            os.remove(sorted_file1)
        if os.path.exists(sorted_file2):
            os.remove(sorted_file2)

        logger.info(f"发现 {count} 个共有哈希值")
        return count

    except Exception as e:
        logger.error(f"分块处理交集查找出错: {str(e)}")

        # 确保清理临时文件
        if os.path.exists(sorted_file1):
            os.remove(sorted_file1)
        if os.path.exists(sorted_file2):
            os.remove(sorted_file2)

        # 如果分块处理失败，尝试最后的备用方法
        logger.warning("尝试使用SSD优化的备用方法...")

        # 最后的备用方法：使用分块哈希表
        return disk_based_intersection_ssd(hash_file1, hash_file2, output_file)


# 使用SSD优化的磁盘哈希表的备用方法
def disk_based_intersection_ssd(hash_file1, hash_file2, output_file):
    """
    使用基于磁盘的哈希表查找交集，针对SSD进行了优化
    当所有其他方法都失败时的备用方法
    """
    logger.info("使用SSD优化的磁盘哈希表查找交集...")

    # 创建临时哈希表文件
    temp_dir = os.path.dirname(output_file)
    hash_table_file = os.path.join(temp_dir, "temp_hash_table.txt")

    try:
        # 步骤1: 确定哪个文件更小，优先加载较小的文件到内存
        size1 = os.path.getsize(hash_file1)
        size2 = os.path.getsize(hash_file2)

        if size1 <= size2:
            smaller_file = hash_file1
            larger_file = hash_file2
        else:
            smaller_file = hash_file2
            larger_file = hash_file1

        logger.info(
            f"选择较小的文件 ({os.path.basename(smaller_file)}, {size1 if size1 <= size2 else size2} 字节) 加载到内存")

        # 步骤2: 将较小文件的哈希值加载到内存
        # SSD优化：分批读取文件到内存，避免一次性加载过大文件
        hash_set = set()
        batch_size = 1000000  # 每次读取100万行
        lines_read = 0

        with open(smaller_file, 'r', buffering=CONFIG['buffer_size']) as f:
            batch = []
            for line in f:
                hash_val = line.strip()
                if hash_val:
                    batch.append(hash_val)

                if len(batch) >= batch_size:
                    hash_set.update(batch)
                    lines_read += len(batch)
                    logger.info(f"已读取 {lines_read} 个哈希值")
                    batch = []
                    # 检查内存
                    check_memory()
                    # 强制垃圾回收
                    gc.collect()

            # 处理最后一批
            if batch:
                hash_set.update(batch)
                lines_read += len(batch)

        logger.info(f"已加载 {len(hash_set)} 个哈希值到内存")

        # 步骤3: 流式处理较大的文件并查找交集
        logger.info("查找交集...")

        count = 0
        # SSD优化：使用更大的缓冲区和批量写入
        output_buffer = []
        buffer_size = 200000  # 从100000增加到200000，减少IO操作

        with open(larger_file, 'r', buffering=CONFIG['buffer_size']) as f, \
                open(output_file, 'w', buffering=CONFIG['buffer_size']) as out:

            for line in f:
                hash_val = line.strip()
                if hash_val and hash_val in hash_set:
                    output_buffer.append(hash_val)
                    count += 1

                    # 如果缓冲区满了，批量写入
                    if len(output_buffer) >= buffer_size:
                        out.write('\n'.join(output_buffer) + '\n')
                        output_buffer = []
                        logger.info(f"已找到 {count} 个交集...")
                        # 检查内存
                        check_memory()

            # 写入剩余的缓冲区内容
            if output_buffer:
                out.write('\n'.join(output_buffer) + '\n')

        logger.info(f"找到 {count} 个共有哈希值")
        return count

    finally:
        # 清理临时文件
        if os.path.exists(hash_table_file):
            os.remove(hash_table_file)
        # 强制垃圾回收
        gc.collect()


# 多线程读取哈希文件的辅助函数
def read_hash_groups_thread(file_path, group_queue, group_digits):
    """
    多线程读取哈希文件并按前缀分组
    将分组结果放入队列中
    """
    # 创建分组字典
    hash_groups = {}
    lines_read = 0

    # 打开文件并分组
    with open(file_path, 'r', buffering=CONFIG['buffer_size']) as f:
        for line in f:
            hash_val = line.strip()
            if hash_val:
                # 获取前N位作为分组键
                group_key = hash_val[:group_digits]

                # 添加到相应分组
                if group_key not in hash_groups:
                    hash_groups[group_key] = set()
                hash_groups[group_key].add(hash_val)

                lines_read += 1

                # 定期将已经填充的组放入队列
                if lines_read % 1000000 == 0:
                    # 将已经达到一定大小的组放入队列
                    keys_to_remove = []
                    for key, values in hash_groups.items():
                        if len(values) >= 10000:  # 组大小阈值
                            group_queue.put((key, values))
                            keys_to_remove.append(key)

                    # 从字典中移除已处理的组
                    for key in keys_to_remove:
                        del hash_groups[key]

                    logger.info(f"已读取 {lines_read} 个哈希值")

    # 将剩余的所有组放入队列
    for key, values in hash_groups.items():
        group_queue.put((key, values))

    # 放入结束标记
    group_queue.put(None)
    logger.info(f"完成哈希文件读取，共 {lines_read} 行")


# 多线程读取哈希文件线程函数
def read_hash_file_thread(file_path, result_queue, batch_size=1000000):
    """多线程读取哈希文件"""
    try:
        with open(file_path, 'r', buffering=CONFIG['buffer_size']) as f:
            batch = []
            for line in f:
                hash_val = line.strip()
                if hash_val:
                    batch.append(hash_val)

                if len(batch) >= batch_size:
                    result_queue.put(batch)
                    batch = []

            # 处理最后一批
            if batch:
                result_queue.put(batch)

        # 放入结束标记
        result_queue.put(None)

    except Exception as e:
        logger.error(f"读取哈希文件线程出错: {str(e)}")
        # 确保放入结束标记
        result_queue.put(None)


# 将原来的实现重命名，保留为备用 - 优化版
def filter_csv_by_hashes_original(input_file, hash_file, output_file, columns=None):
    """
    原始的哈希值筛选实现，用于处理较小的哈希文件
    优化版本: 增加进度显示和多线程读取，确保与提取阶段哈希计算一致
    """
    logger.info(f"根据哈希值筛选文件: {os.path.basename(input_file)}")

    # 验证输入文件
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"找不到输入CSV文件: {input_file}")
    if not os.path.exists(hash_file):
        raise FileNotFoundError(f"找不到哈希文件: {hash_file}")

    # 验证输出目录
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 读取哈希值 - 使用多线程或直接读取
    hash_set = set()
    if CONFIG['use_threaded_io']:
        # 多线程版本
        logger.info("使用多线程读取哈希值...")
        hash_queue = queue.Queue(maxsize=10)  # 限制队列大小以控制内存使用
        read_thread = threading.Thread(target=read_hash_file_thread,
                                       args=(hash_file, hash_queue))
        read_thread.daemon = True
        read_thread.start()

        total_hash_count = 0
        # 从队列中获取批次数据
        while True:
            batch = hash_queue.get()
            if batch is None:  # 结束标记
                break

            hash_set.update(batch)
            total_hash_count += len(batch)

            if total_hash_count % 1000000 == 0:
                logger.info(f"已读取 {total_hash_count} 个哈希值")
                # 检查内存
                check_memory()

        # 等待线程结束
        read_thread.join()
    else:
        # 直接读取版本
        batch_size = 1000000  # 每次读取100万行
        lines_read = 0

        with open(hash_file, 'r', buffering=CONFIG['buffer_size']) as f:
            batch = []
            for line in f:
                hash_val = line.strip()
                if hash_val:
                    batch.append(hash_val)

                if len(batch) >= batch_size:
                    hash_set.update(batch)
                    lines_read += len(batch)
                    logger.info(f"已读取 {lines_read} 个哈希值")
                    batch = []
                    # 检查内存
                    check_memory()
                    # 强制垃圾回收
                    gc.collect()

            # 处理最后一批
            if batch:
                hash_set.update(batch)
                lines_read += len(batch)

    logger.info(f"共读取 {len(hash_set)} 个哈希值")

    # 使用原生CSV模块替代pandas的to_csv进行写入
    import csv

    # 首先读取CSV头部获取列名
    with open(input_file, 'r', newline='', buffering=CONFIG['buffer_size']) as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)  # 获取标题行

    # 确定所需列的索引
    if columns:
        # 获取指定列在原始CSV中的索引位置
        col_indices = {col: header.index(col) for col in columns if col in header}
    else:
        # 使用所有列
        col_indices = {col: i for i, col in enumerate(header)}

    # 创建用于输出的新标题
    output_header = header.copy()

    # 如果标题中没有identifier和hash，则添加
    if 'identifier' not in output_header:
        output_header.append('identifier')
    if 'hash' not in output_header:
        output_header.append('hash')

    # 创建CSV写入器和输出文件
    with open(output_file, 'w', newline='', buffering=CONFIG['buffer_size']) as outfile:
        writer = csv.writer(outfile)
        writer.writerow(output_header)  # 写入标题行

        # 获取identifier和hash在输出标题中的位置
        identifier_idx = output_header.index('identifier')
        hash_idx = output_header.index('hash')

        # 初始化计数器和缓冲区
        total_filtered = 0
        buffer_rows = []
        buffer_limit = CONFIG['batch_buffer_limit']  # 提高批量写入阈值

        # 获取文件总行数（估计值）
        file_size = os.path.getsize(input_file)
        est_total_lines = file_size // 200  # 假设每行平均200字节

        # 打开输入文件进行处理
        with open(input_file, 'r', newline='', buffering=CONFIG['buffer_size']) as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # 跳过标题行

            # 使用tqdm显示进度条
            if CONFIG['show_progress_bar']:
                with tqdm(total=est_total_lines, desc=f"筛选CSV") as pbar:
                    for i, row in enumerate(reader):
                        # 提取和处理标识信息
                        try:
                            # 确保可以找到所需列
                            if 'month' not in header or 'longitude' not in header or 'latitude' not in header or 'depth' not in header:
                                logger.warning(f"CSV 文件缺少必要的列: month, longitude, latitude, 或 depth")
                                continue

                            month_idx = header.index('month')
                            lon_idx = header.index('longitude')
                            lat_idx = header.index('latitude')
                            depth_idx = header.index('depth')

                            # 确保有足够的列
                            if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                                logger.warning(f"第 {i + 2} 行数据不完整，跳过")
                                continue

                            month = row[month_idx]
                            longitude = row[lon_idx]
                            latitude = row[lat_idx]
                            depth = row[depth_idx]

                            # 修改：使用统一哈希计算函数，确保与提取阶段一致
                            identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

                            # 检查哈希值是否在集合中
                            if hash_value in hash_set:
                                # 创建新行，新行长度应与输出标题长度相同
                                new_row = row.copy()

                                # 确保新行长度与输出标题匹配
                                while len(new_row) < len(output_header):
                                    new_row.append('')

                                # 设置identifier和hash值
                                new_row[identifier_idx] = identifier
                                new_row[hash_idx] = hash_value

                                buffer_rows.append(new_row)
                                total_filtered += 1

                                # 当缓冲区达到阈值时批量写入
                                if len(buffer_rows) >= buffer_limit:
                                    writer.writerows(buffer_rows)
                                    buffer_rows = []

                                    # 更新进度条
                                    pbar.set_postfix({"保留": total_filtered})

                        except Exception as e:
                            logger.warning(f"处理第 {i + 2} 行时出错: {str(e)}")
                            continue

                        # 周期性垃圾回收
                        if i % 1000000 == 0:
                            gc.collect()

                        # 更新进度条 - 每10000行更新一次
                        if i % 10000 == 0:
                            pbar.update(10000)

                    # 写入剩余的缓冲行
                    if buffer_rows:
                        writer.writerows(buffer_rows)
            else:
                # 不使用进度条的版本
                for i, row in enumerate(reader):
                    # 提取和处理标识信息
                    try:
                        # 确保可以找到所需列
                        if 'month' not in header or 'longitude' not in header or 'latitude' not in header or 'depth' not in header:
                            logger.warning(f"CSV 文件缺少必要的列: month, longitude, latitude, 或 depth")
                            continue

                        month_idx = header.index('month')
                        lon_idx = header.index('longitude')
                        lat_idx = header.index('latitude')
                        depth_idx = header.index('depth')

                        # 确保有足够的列
                        if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                            logger.warning(f"第 {i + 2} 行数据不完整，跳过")
                            continue

                        month = row[month_idx]
                        longitude = row[lon_idx]
                        latitude = row[lat_idx]
                        depth = row[depth_idx]

                        # 修改：使用统一哈希计算函数，确保与提取阶段一致
                        identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

                        # 检查哈希值是否在集合中
                        if hash_value in hash_set:
                            # 创建新行，新行长度应与输出标题长度相同
                            new_row = row.copy()

                            # 确保新行长度与输出标题匹配
                            while len(new_row) < len(output_header):
                                new_row.append('')

                            # 设置identifier和hash值
                            new_row[identifier_idx] = identifier
                            new_row[hash_idx] = hash_value

                            buffer_rows.append(new_row)
                            total_filtered += 1

                            # 当缓冲区达到阈值时批量写入
                            if len(buffer_rows) >= buffer_limit:
                                writer.writerows(buffer_rows)
                                buffer_rows = []

                                # 显示进度
                                if total_filtered % 1000000 == 0:
                                    logger.info(f"已筛选 {total_filtered} 行")

                                # 内存管理
                                check_memory()

                    except Exception as e:
                        logger.warning(f"处理第 {i + 2} 行时出错: {str(e)}")
                        continue

                    # 周期性垃圾回收
                    if i % 1000000 == 0:
                        gc.collect()

                    # 显示进度
                    if i % 1000000 == 0:
                        logger.info(f"已处理 {i} 行，保留 {total_filtered} 行")

                # 写入剩余的缓冲行
                if buffer_rows:
                    writer.writerows(buffer_rows)

    logger.info(f"筛选完成，保留 {total_filtered} 行")
    return total_filtered


# 新增：基于哈希分组的筛选函数，用于处理大文件
def filter_csv_by_hash_groups(input_file, hash_file, output_file, columns=None):
    """
    使用哈希分组的方法筛选大型CSV文件
    修改以确保与提取阶段使用相同的哈希计算方法
    """
    logger.info(f"使用哈希分组方法筛选文件: {os.path.basename(input_file)}")

    # 验证输入文件
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"找不到输入CSV文件: {input_file}")
    if not os.path.exists(hash_file):
        raise FileNotFoundError(f"找不到哈希文件: {hash_file}")

    # 验证输出目录
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 读取哈希值集合
    hash_set = set()
    with open(hash_file, 'r', buffering=CONFIG['buffer_size']) as f:
        for line in f:
            hash_val = line.strip()
            if hash_val:
                hash_set.add(hash_val)

    logger.info(f"已加载 {len(hash_set)} 个哈希值到内存")

    # 读取哈希值集合
    hash_set = set()
    with open(hash_file, 'r', buffering=CONFIG['buffer_size']) as f:
        for line in f:
            hash_val = line.strip()
            if hash_val:
                hash_set.add(hash_val)

    logger.info(f"已加载 {len(hash_set)} 个哈希值到内存")

    # 读取CSV头并准备输出
    with open(input_file, 'r', newline='', buffering=CONFIG['buffer_size']) as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)  # 获取标题行

    # 创建用于输出的新标题
    output_header = header.copy()

    # 如果标题中没有identifier和hash，则添加
    if 'identifier' not in output_header:
        output_header.append('identifier')
    if 'hash' not in output_header:
        output_header.append('hash')

    # 创建CSV写入器和输出文件
    with open(output_file, 'w', newline='', buffering=CONFIG['buffer_size']) as outfile:
        writer = csv.writer(outfile)
        writer.writerow(output_header)  # 写入标题行

        # 批量读取和处理
        total_filtered = 0
        buffer_rows = []
        buffer_limit = CONFIG['batch_buffer_limit']

        # 获取文件总行数（估计值）
        file_size = os.path.getsize(input_file)
        est_total_lines = file_size // 200  # 假设每行平均200字节

        # 获取关键列的索引
        month_idx = header.index('month') if 'month' in header else -1
        lon_idx = header.index('longitude') if 'longitude' in header else -1
        lat_idx = header.index('latitude') if 'latitude' in header else -1
        depth_idx = header.index('depth') if 'depth' in header else -1

        # 检查是否有所需的列
        if -1 in [month_idx, lon_idx, lat_idx, depth_idx]:
            raise ValueError("CSV文件缺少必要的列: month, longitude, latitude, 或 depth")

        # 获取identifier和hash在输出标题中的位置
        identifier_idx = output_header.index('identifier')
        hash_idx = output_header.index('hash')

        # 处理输入文件
        with open(input_file, 'r', newline='', buffering=CONFIG['buffer_size']) as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # 跳过标题行

            if CONFIG['show_progress_bar']:
                with tqdm(total=est_total_lines, desc=f"筛选CSV") as pbar:
                    # 批量读取行
                    batch_rows = []
                    batch_size = 10000  # 每批处理的行数

                    for i, row in enumerate(reader):
                        batch_rows.append(row)

                        if len(batch_rows) >= batch_size:
                            # 处理一批数据
                            for row in batch_rows:
                                try:
                                    # 确保有足够的列
                                    if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                                        continue

                                    month = row[month_idx]
                                    longitude = row[lon_idx]
                                    latitude = row[lat_idx]
                                    depth = row[depth_idx]

                                    # 使用统一的哈希计算函数
                                    identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

                                    # 检查哈希值是否在集合中
                                    if hash_value in hash_set:
                                        # 创建新行
                                        new_row = row.copy()

                                        # 确保新行长度与输出标题匹配
                                        while len(new_row) < len(output_header):
                                            new_row.append('')

                                        # 设置identifier和hash值
                                        new_row[identifier_idx] = identifier
                                        new_row[hash_idx] = hash_value

                                        buffer_rows.append(new_row)
                                        total_filtered += 1

                                        # 当缓冲区达到阈值时批量写入
                                        if len(buffer_rows) >= buffer_limit:
                                            writer.writerows(buffer_rows)
                                            buffer_rows = []

                                            # 更新进度条
                                            pbar.set_postfix({"保留": total_filtered})
                                except Exception as e:
                                    logger.warning(f"处理行时出错: {str(e)}")
                                    continue

                            # 更新进度条
                            pbar.update(len(batch_rows))

                            # 清空批次
                            batch_rows = []

                        # 内存管理
                        if i % 1000000 == 0:
                            gc.collect()

                    # 处理最后一批
                    if batch_rows:
                        for row in batch_rows:
                            try:
                                # 确保有足够的列
                                if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                                    continue

                                month = row[month_idx]
                                longitude = row[lon_idx]
                                latitude = row[lat_idx]
                                depth = row[depth_idx]

                                # 使用统一的哈希计算函数
                                identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

                                # 检查哈希值是否在集合中
                                if hash_value in hash_set:
                                    # 创建新行
                                    new_row = row.copy()

                                    # 确保新行长度与输出标题匹配
                                    while len(new_row) < len(output_header):
                                        new_row.append('')

                                    # 设置identifier和hash值
                                    new_row[identifier_idx] = identifier
                                    new_row[hash_idx] = hash_value

                                    buffer_rows.append(new_row)
                                    total_filtered += 1
                            except Exception as e:
                                logger.warning(f"处理行时出错: {str(e)}")
                                continue

                        # 更新进度条
                        pbar.update(len(batch_rows))

                    # 写入剩余的缓冲行
                    if buffer_rows:
                        writer.writerows(buffer_rows)
            else:
                # 不使用进度条的版本
                # 批量读取行
                batch_rows = []
                batch_size = 10000  # 每批处理的行数

                for i, row in enumerate(reader):
                    batch_rows.append(row)

                    if len(batch_rows) >= batch_size:
                        # 处理一批数据
                        for row in batch_rows:
                            try:
                                # 确保有足够的列
                                if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                                    continue

                                month = row[month_idx]
                                longitude = row[lon_idx]
                                latitude = row[lat_idx]
                                depth = row[depth_idx]

                                # 使用统一的哈希计算函数
                                identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

                                # 检查哈希值是否在集合中
                                if hash_value in hash_set:
                                    # 创建新行
                                    new_row = row.copy()

                                    # 确保新行长度与输出标题匹配
                                    while len(new_row) < len(output_header):
                                        new_row.append('')

                                    # 设置identifier和hash值
                                    new_row[identifier_idx] = identifier
                                    new_row[hash_idx] = hash_value

                                    buffer_rows.append(new_row)
                                    total_filtered += 1

                                    # 当缓冲区达到阈值时批量写入
                                    if len(buffer_rows) >= buffer_limit:
                                        writer.writerows(buffer_rows)
                                        buffer_rows = []

                                        # 显示进度
                                        if total_filtered % 1000000 == 0:
                                            logger.info(f"已筛选 {total_filtered} 行")

                                        # 内存管理
                                        check_memory()
                            except Exception as e:
                                logger.warning(f"处理行时出错: {str(e)}")
                                continue

                        # 显示进度
                        if i % 1000000 == 0:
                            logger.info(f"已处理 {i} 行，保留 {total_filtered} 行")

                        # 清空批次
                        batch_rows = []

                        # 内存管理
                        if i % 1000000 == 0:
                            gc.collect()

                # 处理最后一批
                if batch_rows:
                    for row in batch_rows:
                        try:
                            # 确保有足够的列
                            if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                                continue

                            month = row[month_idx]
                            longitude = row[lon_idx]
                            latitude = row[lat_idx]
                            depth = row[depth_idx]

                            # 使用统一的哈希计算函数
                            identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

                            # 检查哈希值是否在集合中
                            if hash_value in hash_set:
                                # 创建新行
                                new_row = row.copy()

                                # 确保新行长度与输出标题匹配
                                while len(new_row) < len(output_header):
                                    new_row.append('')

                                # 设置identifier和hash值
                                new_row[identifier_idx] = identifier
                                new_row[hash_idx] = hash_value

                                buffer_rows.append(new_row)
                                total_filtered += 1
                        except Exception as e:
                            logger.warning(f"处理行时出错: {str(e)}")
                            continue

                # 写入剩余的缓冲行
                if buffer_rows:
                    writer.writerows(buffer_rows)

    logger.info(f"筛选完成，保留 {total_filtered} 行")
    return total_filtered


# 辅助函数：处理一个批次的数据 - 优化版
def process_batch(rows, headers, hash_set, header, group_digits=None):
    """
    处理一个批次的数据，返回筛选后的行 - 优化版
    使用与extract_hashes_from_csv相同的哈希计算方法
    """
    # 初始化筛选后的行
    filtered_rows = []

    # 获取关键列的索引
    month_idx = headers.index('month') if 'month' in headers else -1
    lon_idx = headers.index('longitude') if 'longitude' in headers else -1
    lat_idx = headers.index('latitude') if 'latitude' in headers else -1
    depth_idx = headers.index('depth') if 'depth' in headers else -1

    # 获取输出标题中identifier和hash的位置
    identifier_idx = header.index('identifier') if 'identifier' in header else -1
    hash_idx = header.index('hash') if 'hash' in header else -1

    if identifier_idx == -1:
        header.append('identifier')
        identifier_idx = header.index('identifier')

    if hash_idx == -1:
        header.append('hash')
        hash_idx = header.index('hash')

    # 检查是否有所需的列
    if -1 in [month_idx, lon_idx, lat_idx, depth_idx]:
        logger.warning("缺少必要的列: month, longitude, latitude, 或 depth")
        return filtered_rows

    # 处理每一行
    for row in rows:
        try:
            if len(row) <= max(month_idx, lon_idx, lat_idx, depth_idx):
                continue

            month = row[month_idx]
            longitude = row[lon_idx]
            latitude = row[lat_idx]
            depth = row[depth_idx]

            # 使用统一的哈希计算函数
            identifier, hash_value = calculate_hash(month, longitude, latitude, depth)

            # 检查哈希值是否在集合中
            if hash_value in hash_set:
                # 创建新行，包含原始数据、标识符和哈希值
                new_row = row.copy()

                # 确保新行长度与输出标题匹配
                while len(new_row) < len(header):
                    new_row.append('')

                # 设置identifier和hash值
                new_row[identifier_idx] = identifier
                new_row[hash_idx] = hash_value

                filtered_rows.append(new_row)
        except Exception as e:
            logger.warning(f"处理行时出错: {str(e)}")
            continue

    return filtered_rows


def merge_filtered_csv(bgc_file, phy_file, output_file, year):
    """
    使用排序+归并方法合并两个已经过哈希筛选的CSV文件，内存占用极低
    """
    logger.info(f"使用排序+归并方法合并筛选后的文件 ({year}年)")

    # 验证输入文件
    if not os.path.exists(bgc_file):
        raise FileNotFoundError(f"找不到筛选后的营养盐文件: {bgc_file}")
    if not os.path.exists(phy_file):
        raise FileNotFoundError(f"找不到筛选后的物理参数文件: {phy_file}")

    # 验证输出目录
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 步骤1: 按identifier对文件排序
    temp_dir = os.path.dirname(output_file)
    sorted_bgc_file = os.path.join(temp_dir, f"sorted_bgc_{year}.csv")
    sorted_phy_file = os.path.join(temp_dir, f"sorted_phy_{year}.csv")

    logger.info("步骤1: 对两个文件按identifier排序")
    sort_csv_by_identifier(bgc_file, sorted_bgc_file)
    sort_csv_by_identifier(phy_file, sorted_phy_file)

    # 读取两个文件的标题行
    with open(sorted_bgc_file, 'r', newline='', buffering=CONFIG['buffer_size']) as bgc_f:
        bgc_reader = csv.reader(bgc_f)
        bgc_header = next(bgc_reader)

    with open(sorted_phy_file, 'r', newline='', buffering=CONFIG['buffer_size']) as phy_f:
        phy_reader = csv.reader(phy_f)
        phy_header = next(phy_reader)

    # 查找identifier列的索引
    try:
        bgc_id_idx = bgc_header.index('identifier')
        phy_id_idx = phy_header.index('identifier')
    except ValueError:
        logger.error("找不到identifier列，无法合并")
        raise ValueError("找不到identifier列，无法合并")

    # 找出列的索引位置
    bgc_indices = {}
    phy_indices = {}

    # 基本字段
    base_fields = ['month', 'depth', 'longitude', 'latitude']
    for field in base_fields:
        if field in bgc_header:
            bgc_indices[field] = bgc_header.index(field)
        if field in phy_header:
            phy_indices[field] = phy_header.index(field)

    # BGC特定字段
    bgc_specific = ['no3', 'o2', 'po4', 'si']
    for field in bgc_specific:
        if field in bgc_header:
            bgc_indices[field] = bgc_header.index(field)

    # PHY特定字段
    phy_specific = ['so', 'thetao']
    for field in phy_specific:
        if field in phy_header:
            phy_indices[field] = phy_header.index(field)

    # 定义合并后的列名
    merged_columns = ['year', 'month', 'depth', 'longitude', 'latitude', 'no3', 'o2', 'po4', 'si', 'so', 'thetao']

    # 步骤2: 使用归并算法合并两个已排序文件
    logger.info("步骤2: 使用归并算法合并文件")

    # 打开文件进行归并
    with open(sorted_bgc_file, 'r', newline='', buffering=CONFIG['buffer_size']) as bgc_f, \
            open(sorted_phy_file, 'r', newline='', buffering=CONFIG['buffer_size']) as phy_f, \
            open(output_file, 'w', newline='', buffering=CONFIG['buffer_size']) as out_f:

        # 设置CSV读写器
        bgc_reader = csv.reader(bgc_f)
        phy_reader = csv.reader(phy_f)
        writer = csv.writer(out_f)

        # 跳过标题行（已经读取过）
        next(bgc_reader)
        next(phy_reader)

        # 写入合并后的标题
        writer.writerow(merged_columns)

        # 读取第一行数据
        try:
            bgc_row = next(bgc_reader)
            bgc_id = bgc_row[bgc_id_idx] if bgc_row and len(bgc_row) > bgc_id_idx else None
        except StopIteration:
            bgc_row = None
            bgc_id = None

        try:
            phy_row = next(phy_reader)
            phy_id = phy_row[phy_id_idx] if phy_row and len(phy_row) > phy_id_idx else None
        except StopIteration:
            phy_row = None
            phy_id = None

        # 设置缓冲区
        merged_buffer = []
        buffer_size = CONFIG['batch_buffer_limit']
        total_merged = 0

        # 归并过程
        while bgc_row and phy_row:
            # 如果标识符相等，合并并写入
            if bgc_id == phy_id:
                try:
                    # 构建合并行
                    merged_row = [
                        year,  # 年份
                        int(bgc_row[bgc_indices['month']]),  # 月份
                        float(bgc_row[bgc_indices['depth']]),  # 深度
                        float(bgc_row[bgc_indices['longitude']]),  # 经度
                        float(bgc_row[bgc_indices['latitude']]),  # 纬度
                        float(bgc_row[bgc_indices['no3']]),  # no3
                        float(bgc_row[bgc_indices['o2']]),  # o2
                        float(bgc_row[bgc_indices['po4']]),  # po4
                        float(bgc_row[bgc_indices['si']]),  # si
                        float(phy_row[phy_indices['so']]),  # so
                        float(phy_row[phy_indices['thetao']])  # thetao
                    ]

                    # 添加到缓冲区
                    merged_buffer.append(merged_row)
                    total_merged += 1

                    # 当缓冲区达到阈值时批量写入
                    if len(merged_buffer) >= buffer_size:
                        writer.writerows(merged_buffer)
                        merged_buffer = []

                        # 显示进度
                        if total_merged % 1000000 == 0:  # 每合并100万行显示一次
                            logger.info(f"已合并 {total_merged} 行...")
                            # 检查内存
                            check_memory()
                            # 强制垃圾回收
                            gc.collect()
                except Exception as e:
                    logger.warning(f"合并行时出错: {str(e)}")

                # 两个文件都前进一行
                try:
                    bgc_row = next(bgc_reader)
                    bgc_id = bgc_row[bgc_id_idx] if bgc_row and len(bgc_row) > bgc_id_idx else None
                except StopIteration:
                    bgc_row = None
                    bgc_id = None

                try:
                    phy_row = next(phy_reader)
                    phy_id = phy_row[phy_id_idx] if phy_row and len(phy_row) > phy_id_idx else None
                except StopIteration:
                    phy_row = None
                    phy_id = None

            # 如果bgc标识符小于phy标识符，bgc前进一行
            elif bgc_id < phy_id:
                try:
                    bgc_row = next(bgc_reader)
                    bgc_id = bgc_row[bgc_id_idx] if bgc_row and len(bgc_row) > bgc_id_idx else None
                except StopIteration:
                    bgc_row = None
                    bgc_id = None

            # 如果bgc标识符大于phy标识符，phy前进一行
            else:
                try:
                    phy_row = next(phy_reader)
                    phy_id = phy_row[phy_id_idx] if phy_row and len(phy_row) > phy_id_idx else None
                except StopIteration:
                    phy_row = None
                    phy_id = None

        # 写入剩余的缓冲行
        if merged_buffer:
            writer.writerows(merged_buffer)

    # 清理临时文件
    try:
        os.remove(sorted_bgc_file)
        os.remove(sorted_phy_file)
    except Exception as e:
        logger.warning(f"清理临时文件失败: {str(e)}")

    logger.info(f"合并完成，共合并 {total_merged} 行")
    return total_merged


def sort_csv_by_identifier(input_file, output_file):
    """对CSV文件按identifier列排序"""
    logger.info(f"对文件 {os.path.basename(input_file)} 按identifier排序")

    # 读取CSV头
    with open(input_file, 'r', newline='', buffering=CONFIG['buffer_size']) as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)

    # 查找identifier列的索引
    try:
        id_idx = header.index('identifier')
    except ValueError:
        logger.error("找不到identifier列，无法排序")
        raise ValueError("找不到identifier列，无法排序")

    # 创建临时目录
    temp_dir = os.path.dirname(output_file)
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir, exist_ok=True)

    # 分块读取、排序、写入临时文件
    temp_files = []
    chunk_size = CONFIG['chunk_size']
    current_chunk = []
    total_rows = 0

    with open(input_file, 'r', newline='', buffering=CONFIG['buffer_size']) as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # 跳过标题行

        for row in reader:
            if len(row) <= id_idx:
                continue  # 跳过不完整的行

            current_chunk.append((row[id_idx], row))
            total_rows += 1

            if len(current_chunk) >= chunk_size:
                # 排序当前块
                current_chunk.sort(key=lambda x: x[0])

                # 写入临时文件
                temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{len(temp_files)}.csv")
                with open(temp_file, 'w', newline='', buffering=CONFIG['buffer_size']) as tempfile:
                    writer = csv.writer(tempfile)
                    for _, row in current_chunk:
                        writer.writerow(row)

                temp_files.append(temp_file)
                current_chunk = []

                # 强制垃圾回收
                gc.collect()

        # 处理最后一个不完整的块
        if current_chunk:
            current_chunk.sort(key=lambda x: x[0])

            temp_file = os.path.join(temp_dir, f"temp_sorted_chunk_{len(temp_files)}.csv")
            with open(temp_file, 'w', newline='', buffering=CONFIG['buffer_size']) as tempfile:
                writer = csv.writer(tempfile)
                for _, row in current_chunk:
                    writer.writerow(row)

            temp_files.append(temp_file)

    logger.info(f"排序分块完成，共 {len(temp_files)} 个排序块，总计 {total_rows} 行")

    # 多路归并排序
    with open(output_file, 'w', newline='', buffering=CONFIG['buffer_size']) as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)  # 写入标题行

        # 打开所有临时文件
        file_handlers = []
        readers = []
        heap = []

        for i, f_path in enumerate(temp_files):
            fh = open(f_path, 'r', newline='', buffering=CONFIG['buffer_size'])
            file_handlers.append(fh)
            readers.append(csv.reader(fh))

            # 读取第一行
            try:
                row = next(readers[i])
                if row and len(row) > id_idx:
                    # 加入堆 (标识符, 行索引, 行内容)
                    heapq.heappush(heap, (row[id_idx], i, row))
            except StopIteration:
                pass

        # 归并
        try:
            while heap:
                # 取出最小值
                _, file_idx, row = heapq.heappop(heap)

                # 写入输出文件
                writer.writerow(row)

                # 从相应文件读取下一行
                try:
                    next_row = next(readers[file_idx])
                    if next_row and len(next_row) > id_idx:
                        heapq.heappush(heap, (next_row[id_idx], file_idx, next_row))
                except StopIteration:
                    pass
        finally:
            # 关闭所有文件
            for fh in file_handlers:
                fh.close()

        # 清理临时文件
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except:
                pass

    logger.info(f"文件排序完成: {os.path.basename(output_file)}")
    return output_file

# 按年份对文件分组
def group_files_by_year(bgc_dir, phy_dir):
    bgc_files = [f for f in os.listdir(bgc_dir) if f.endswith('.csv')]
    phy_files = [f for f in os.listdir(phy_dir) if f.endswith('.csv')]

    bgc_by_year = {}
    for file in bgc_files:
        year = extract_year_from_filename(file)
        if year:
            bgc_by_year[year] = os.path.join(bgc_dir, file)

    phy_by_year = {}
    for file in phy_files:
        year = extract_year_from_filename(file)
        if year:
            phy_by_year[year] = os.path.join(phy_dir, file)

    # 找出两个目录共有的年份
    common_years = set(bgc_by_year.keys()) & set(phy_by_year.keys())

    year_file_pairs = {}
    for year in common_years:
        year_file_pairs[year] = (bgc_by_year[year], phy_by_year[year])

    return year_file_pairs


# 提取年份从文件名
def extract_year_from_filename(filename):
    # 从文件名末尾找到年份，假设格式为 _YYYY_
    parts = filename.split('_')
    for part in parts:
        if part.isdigit() and len(part) == 4:
            try:
                year = int(part)
                if 1900 <= year <= 2100:  # 合理的年份范围
                    return year
            except ValueError:
                continue
    return None


# 新增: 使用配置调用处理函数的包装函数
def process_year_data_with_config(year, bgc_file, phy_file, output_dir, year_config):
    """包装函数，使用特定配置调用处理函数"""
    # 暂时替换全局配置
    old_config = CONFIG.copy()

    # 替换全局配置
    for key, value in year_config.items():
        CONFIG[key] = value

    try:
        # 调用原函数
        return process_year_data(year, bgc_file, phy_file, output_dir)
    finally:
        # 恢复原始配置 (虽然在子进程中其实不必要，但为了安全和一致性)
        for key, value in old_config.items():
            CONFIG[key] = value


# 修改: 改进process_year_data函数，支持根据配置选择筛选方法
def process_year_data(year, bgc_file, phy_file, output_dir):
    """
    使用极低内存方法处理一年的数据 - 优化版
    支持根据配置选择合适的筛选方法
    """
    logger.info(f"开始处理 {year} 年的数据")
    start_time = time.time()

    # 获取当前进程ID
    pid = os.getpid()
    logger.info(f"进程 ID: {pid}，处理年份: {year}")

    # 使用配置中已设置的临时目录，无需再创建子目录
    local_temp_dir = CONFIG['temp_dir']
    logger.info(f"年份 {year} 使用临时目录: {local_temp_dir}")

    # 将此临时目录设置为进程的临时目录
    tempfile.tempdir = local_temp_dir
    os.environ['TMPDIR'] = local_temp_dir
    os.environ['TEMP'] = local_temp_dir
    os.environ['TMP'] = local_temp_dir
    logger.info(f"已设置进程临时目录环境变量为: {local_temp_dir}")

    try:
        # 确保输入文件存在
        if not os.path.exists(bgc_file):
            raise FileNotFoundError(f"找不到营养盐数据文件: {bgc_file}")
        if not os.path.exists(phy_file):
            raise FileNotFoundError(f"找不到物理参数数据文件: {phy_file}")

        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # 营养盐数据列
        bgc_columns = ['year', 'month', 'depth', 'longitude', 'latitude', 'no3', 'o2', 'po4', 'si']
        # 物理参数列
        phy_columns = ['year', 'month', 'depth', 'longitude', 'latitude', 'so', 'thetao']

        # 第一步：提取两个文件的哈希值
        logger.info(f"第一步：提取哈希值（{year}年）")
        bgc_hash_file, bgc_total = extract_hashes_from_csv(bgc_file, local_temp_dir, bgc_columns)
        gc.collect()  # 在两次大操作之间强制进行垃圾回收
        phy_hash_file, phy_total = extract_hashes_from_csv(phy_file, local_temp_dir, phy_columns)
        gc.collect()  # 再次强制回收

        # 第二步：找到哈希值交集
        logger.info(f"第二步：查找哈希值交集（{year}年）")
        common_hash_file = os.path.join(local_temp_dir, f"common_hashes_{year}.txt")
        common_count = find_hash_intersection(bgc_hash_file, phy_hash_file, common_hash_file)
        gc.collect()  # 强制回收

        # 记录剔除的数据量
        bgc_removed = bgc_total - common_count
        phy_removed = phy_total - common_count

        # 检查是否有共有哈希值
        if common_count == 0:
            logger.warning(f"{year}年没有找到共有的经纬度点！")
            return {
                'year': year,
                'bgc_total': bgc_total,
                'phy_total': phy_total,
                'bgc_removed': bgc_removed,
                'phy_removed': phy_removed,
                'merged_count': 0,
                'warning': "没有找到共有的经纬度点"
            }

        # 第三步：根据哈希值筛选两个文件
        logger.info(f"第三步：根据哈希值筛选数据（{year}年）")
        filtered_bgc_file = os.path.join(local_temp_dir, f"filtered_bgc_{year}.csv")
        filtered_phy_file = os.path.join(local_temp_dir, f"filtered_phy_{year}.csv")

        # 修改: 根据配置、进程类型和文件大小选择筛选方法
        is_subprocess = mp.current_process().name != 'MainProcess'
        use_parallel = CONFIG['use_parallel_filter'] and not is_subprocess
        large_file_threshold = 10 * 1024 * 1024  # 10MB以上视为大文件

        # 检查文件大小，决定使用哪种筛选方法
        bgc_file_size = os.path.getsize(bgc_file)
        phy_file_size = os.path.getsize(phy_file)

        # 营养盐文件筛选
        if bgc_file_size > large_file_threshold and use_parallel:
            logger.info(f"使用基于哈希分组的方法筛选营养盐大文件 ({bgc_file_size / 1024 / 1024:.2f}MB)")
            bgc_filtered_count = filter_csv_by_hash_groups(bgc_file, common_hash_file, filtered_bgc_file, bgc_columns)
        else:
            logger.info(f"使用原始方法筛选营养盐文件 ({bgc_file_size / 1024 / 1024:.2f}MB)")
            bgc_filtered_count = filter_csv_by_hashes_original(bgc_file, common_hash_file, filtered_bgc_file,
                                                               bgc_columns)
        gc.collect()  # 强制回收

        # 物理参数文件筛选
        if phy_file_size > large_file_threshold and use_parallel:
            logger.info(f"使用基于哈希分组的方法筛选物理参数大文件 ({phy_file_size / 1024 / 1024:.2f}MB)")
            phy_filtered_count = filter_csv_by_hash_groups(phy_file, common_hash_file, filtered_phy_file, phy_columns)
        else:
            logger.info(f"使用原始方法筛选物理参数文件 ({phy_file_size / 1024 / 1024:.2f}MB)")
            phy_filtered_count = filter_csv_by_hashes_original(phy_file, common_hash_file, filtered_phy_file,
                                                               phy_columns)
        gc.collect()  # 强制回收

        # 第四步：合并筛选后的数据
        logger.info(f"第四步：合并筛选后的数据（{year}年）")
        output_file = os.path.join(output_dir, f"merged_data_{year}.csv")
        merged_count = merge_filtered_csv(filtered_bgc_file, filtered_phy_file, output_file, year)
        gc.collect()  # 强制回收

        # 第五步：生成处理报告
        processing_time = time.time() - start_time
        mem_usage = memory_usage()

        report = f"""
    处理年份: {year}
    ------------------------------
    原始数据:
        营养盐数据: {bgc_total} 行
        物理参数数据: {phy_total} 行

    经纬度筛选:
        找到共有经纬度点: {common_count} 个
        剔除的营养盐数据: {bgc_removed} 行
        剔除的物理参数数据: {phy_removed} 行

    筛选后数据:
        营养盐数据: {bgc_filtered_count} 行
        物理参数数据: {phy_filtered_count} 行

    最终合并数据: {merged_count} 行
    ------------------------------
    处理耗时: {processing_time:.2f} 秒
    内存峰值使用: {mem_usage:.2f} MB
    临时文件目录: {local_temp_dir}
    SSD优化: {'启用' if CONFIG['ssd_optimized'] else '禁用'}
    并行排序: {'启用' if CONFIG['parallel_sort'] else '禁用'}
    使用并行筛选: {'启用' if use_parallel else '禁用'}
            """

        report_file = os.path.join(output_dir, f"report_{year}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"{year} 年数据处理完成，输出文件: {output_file}")
        logger.info(f"{year} 年处理报告已保存至: {report_file}")

        # 返回处理结果摘要
        return {
            'year': year,
            'bgc_total': bgc_total,
            'phy_total': phy_total,
            'bgc_removed': bgc_removed,
            'phy_removed': phy_removed,
            'merged_count': merged_count,
            'processing_time': processing_time,
            'temp_dir': local_temp_dir
        }

    except Exception as e:
        logger.error(f"处理 {year} 年数据时出错: {str(e)}")
        # 将异常重新抛出，以便上层捕获
        raise

    finally:
        # 根据配置决定是否清理年份临时目录
        if not CONFIG.get('keep_temp_files', True):
            try:
                shutil.rmtree(local_temp_dir)
                logger.info(f"清理年份临时目录: {local_temp_dir}")
            except Exception as e:
                logger.warning(f"清理年份临时目录失败: {str(e)}")


# 主界面类
class OceanDataProcessor:
    def __init__(self, root):
        self.root = root
        self.bgc_dir = ""
        self.phy_dir = ""
        self.output_dir = ""
        self.year_file_pairs = {}
        self.setup_ui()

    def setup_ui(self):
        """设置用户界面"""
        self.root.title("海洋数据筛选与合并工具")
        self.root.geometry("800x900")  # 显著增加高度和宽度，确保所有内容可见
        self.root.minsize(800, 900)

        # 创建主滚动框架
        self.main_canvas = tk.Canvas(self.root)
        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.main_canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.main_canvas.configure(yscrollcommand=scrollbar.set)
        self.main_canvas.bind('<Configure>',
                              lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox('all')))

        # 创建内部框架放置所有控件
        main_frame = tk.Frame(self.main_canvas)
        self.main_canvas.create_window((0, 0), window=main_frame, anchor='nw')

        # 标题
        title_label = tk.Label(main_frame, text="海洋数据筛选与合并工具", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)

        # 目录选择区域 - 添加更清晰的分隔
        dirs_frame = tk.LabelFrame(main_frame, text="目录设置", padx=10, pady=10)
        dirs_frame.pack(fill="x", padx=20, pady=10)

        # 输出目录
        output_frame = tk.Frame(dirs_frame)
        output_frame.pack(fill="x", pady=5)
        tk.Label(output_frame, text="输出目录:", width=15, anchor='w').pack(side="left")
        self.output_entry = tk.Entry(output_frame)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(output_frame, text="浏览...", command=self.select_output_dir).pack(side="right")

        # 营养盐数据目录
        bgc_frame = tk.Frame(dirs_frame)
        bgc_frame.pack(fill="x", pady=5)
        tk.Label(bgc_frame, text="营养盐数据目录:", width=15, anchor='w').pack(side="left")
        self.bgc_entry = tk.Entry(bgc_frame)
        self.bgc_entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(bgc_frame, text="浏览...", command=self.select_bgc_dir).pack(side="right")

        # 物理参数数据目录
        phy_frame = tk.Frame(dirs_frame)
        phy_frame.pack(fill="x", pady=5)
        tk.Label(phy_frame, text="物理参数数据目录:", width=15, anchor='w').pack(side="left")
        self.phy_entry = tk.Entry(phy_frame)
        self.phy_entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(phy_frame, text="浏览...", command=self.select_phy_dir).pack(side="right")

        # 配置区域 - 使用网格布局提高紧凑性
        config_frame = tk.LabelFrame(main_frame, text="处理配置", padx=10, pady=10)
        config_frame.pack(fill="x", padx=20, pady=10)

        # 使用网格布局放置配置项，每行两列
        row = 0

        # CPU核心数
        tk.Label(config_frame, text="并行处理年份数:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        cpu_var_frame = tk.Frame(config_frame)
        self.cpu_var = tk.IntVar(value=CONFIG['max_workers'])
        max_cores = min(mp.cpu_count(), 4)
        cpu_options = list(range(1, max_cores + 1))
        self.cpu_menu = tk.OptionMenu(cpu_var_frame, self.cpu_var, *cpu_options)
        self.cpu_menu.pack(side='right')
        cpu_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 内存限制
        row += 1
        tk.Label(config_frame, text="内存使用限制:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        mem_var_frame = tk.Frame(config_frame)
        self.mem_var = tk.IntVar(value=CONFIG['memory_limit_percent'])
        mem_options = [30, 40, 50, 60, 70, 80, 90]
        self.mem_menu = tk.OptionMenu(mem_var_frame, self.mem_var, *mem_options)
        self.mem_menu.pack(side='right')
        tk.Label(mem_var_frame, text="%").pack(side='right')
        mem_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 数据块大小
        row += 1
        tk.Label(config_frame, text="数据块大小:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        chunk_var_frame = tk.Frame(config_frame)
        self.chunk_var = tk.IntVar(value=CONFIG['chunk_size'])
        chunk_options = [10000, 20000, 50000, 100000, 200000]
        self.chunk_menu = tk.OptionMenu(chunk_var_frame, self.chunk_var, *chunk_options)
        self.chunk_menu.pack(side='right')
        tk.Label(chunk_var_frame, text="行").pack(side='right')
        chunk_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 排序块大小
        row += 1
        tk.Label(config_frame, text="排序块大小:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        sort_chunk_var_frame = tk.Frame(config_frame)
        self.sort_chunk_var = tk.IntVar(value=CONFIG['sort_chunk_size'])
        sort_chunk_options = [1000000, 2000000, 5000000, 10000000]
        self.sort_chunk_menu = tk.OptionMenu(sort_chunk_var_frame, self.sort_chunk_var, *sort_chunk_options)
        self.sort_chunk_menu.pack(side='right')
        tk.Label(sort_chunk_var_frame, text="行").pack(side='right')
        sort_chunk_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 缓冲区大小
        row += 1
        tk.Label(config_frame, text="IO缓冲区大小:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        buffer_var_frame = tk.Frame(config_frame)
        self.buffer_var = tk.IntVar(value=CONFIG['buffer_size'] // (1024 * 1024))
        buffer_options = [1, 2, 4, 8, 16, 32]
        self.buffer_menu = tk.OptionMenu(buffer_var_frame, self.buffer_var, *buffer_options)
        self.buffer_menu.pack(side='right')
        tk.Label(buffer_var_frame, text="MB").pack(side='right')
        buffer_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 批量写入缓冲区大小
        row += 1
        tk.Label(config_frame, text="批量写入缓冲大小:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        batch_buffer_var_frame = tk.Frame(config_frame)
        self.batch_buffer_var = tk.IntVar(value=CONFIG['batch_buffer_limit'])
        batch_buffer_options = [50000, 100000, 200000, 500000]
        self.batch_buffer_menu = tk.OptionMenu(batch_buffer_var_frame, self.batch_buffer_var, *batch_buffer_options)
        self.batch_buffer_menu.pack(side='right')
        tk.Label(batch_buffer_var_frame, text="行").pack(side='right')
        batch_buffer_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 哈希分组位数
        row += 1
        tk.Label(config_frame, text="哈希分组位数:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        hash_group_var_frame = tk.Frame(config_frame)
        self.hash_group_var = tk.IntVar(value=CONFIG['hash_group_digits'])
        hash_group_options = [1, 2, 3]
        self.hash_group_menu = tk.OptionMenu(hash_group_var_frame, self.hash_group_var, *hash_group_options)
        self.hash_group_menu.pack(side='right')
        tk.Label(hash_group_var_frame, text="位").pack(side='right')
        hash_group_var_frame.grid(row=row, column=1, sticky='e', padx=5, pady=5)

        # 临时文件位置
        row += 1
        tk.Label(config_frame, text="临时文件位置:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        temp_var_frame = tk.Frame(config_frame)
        default_temp_dir = os.path.join(os.getcwd(), "temp")
        self.temp_var = tk.StringVar(value=default_temp_dir)
        self.temp_entry = tk.Entry(config_frame, textvariable=self.temp_var, width=30)
        self.temp_entry.grid(row=row, column=1, sticky='w', padx=5, pady=5)
        tk.Button(config_frame, text="浏览...", command=self.select_temp_dir).grid(row=row, column=1, sticky='e',
                                                                                   padx=5, pady=5)

        # 高级选项区域 - 使用Checkbutton网格布局
        options_frame = tk.LabelFrame(main_frame, text="高级选项", padx=10, pady=10)
        options_frame.pack(fill="x", padx=20, pady=10)

        # 使用网格布局放置高级选项，每行两列
        row = 0

        # SSD优化选项
        tk.Label(options_frame, text="SSD优化:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self.ssd_var = tk.BooleanVar(value=CONFIG['ssd_optimized'])
        self.ssd_check = tk.Checkbutton(options_frame, variable=self.ssd_var)
        self.ssd_check.grid(row=row, column=1, sticky='w', padx=5, pady=5)

        # 并行排序选项
        row += 1
        tk.Label(options_frame, text="并行排序:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self.parallel_sort_var = tk.BooleanVar(value=CONFIG['parallel_sort'])
        self.parallel_sort_check = tk.Checkbutton(options_frame, variable=self.parallel_sort_var)
        # 移除Windows禁用，改为说明使用线程池
        if os.name == 'nt':
            tk.Label(options_frame, text="(Windows使用线程池)", font=("Arial", 7)).grid(row=row, column=1, sticky='e',
                                                                                        padx=5, pady=5)
        self.parallel_sort_check.grid(row=row, column=1, sticky='w', padx=5, pady=5)

        # 保留临时文件选项
        row += 1
        tk.Label(options_frame, text="保留临时文件:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self.keep_temp_var = tk.BooleanVar(value=CONFIG['keep_temp_files'])
        self.keep_temp_check = tk.Checkbutton(options_frame, variable=self.keep_temp_var)
        self.keep_temp_check.grid(row=row, column=1, sticky='w', padx=5, pady=5)

        # 使用多线程IO选项
        row += 1
        tk.Label(options_frame, text="使用多线程IO:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self.threaded_io_var = tk.BooleanVar(value=CONFIG['use_threaded_io'])
        self.threaded_io_check = tk.Checkbutton(options_frame, variable=self.threaded_io_var)
        self.threaded_io_check.grid(row=row, column=1, sticky='w', padx=5, pady=5)

        # 使用并行筛选选项
        row += 1
        tk.Label(options_frame, text="使用并行筛选:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self.parallel_filter_var = tk.BooleanVar(value=CONFIG['use_parallel_filter'])
        self.parallel_filter_check = tk.Checkbutton(options_frame, variable=self.parallel_filter_var)
        self.parallel_filter_check.grid(row=row, column=1, sticky='w', padx=5, pady=5)

        # 显示进度条选项
        row += 1
        tk.Label(options_frame, text="显示详细进度条:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        self.progress_bar_var = tk.BooleanVar(value=CONFIG['show_progress_bar'])
        self.progress_bar_check = tk.Checkbutton(options_frame, variable=self.progress_bar_var)
        self.progress_bar_check.grid(row=row, column=1, sticky='w', padx=5, pady=5)

        # 处理按钮 - 明显的开始处理按钮，固定在底部
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill="x", padx=20, pady=20)

        # 创建一个固定高度的容器，确保按钮不会被挤压
        self.start_button = tk.Button(button_frame, text="开始处理", command=self.start_processing,
                                      width=20, height=2, font=("Arial", 12, "bold"), bg="#4CAF50", fg="white")
        self.start_button.pack(side="top", pady=10)

        self.cancel_button = tk.Button(button_frame, text="取消处理", command=self.cancel_processing,
                                       width=20, height=2, font=("Arial", 12), state="disabled")
        self.cancel_button.pack(side="top", pady=5)

        # 日志区域
        log_frame = tk.LabelFrame(main_frame, text="处理日志", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.log_text = tk.Text(log_frame, height=8, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 添加日志处理器
        self.setup_log_handler()

        # 进度条
        progress_frame = tk.Frame(main_frame)
        progress_frame.pack(fill="x", padx=20, pady=10)

        self.progress_label = tk.Label(progress_frame, text="准备就绪")
        self.progress_label.pack(anchor="w")

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x")

        # 状态栏 - 固定在窗口底部
        self.status_var = tk.StringVar(value="就绪")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor="w")
        status_bar.pack(side="bottom", fill="x")

        # 确保滚动区域更新
        main_frame.update_idletasks()
        self.main_canvas.config(scrollregion=self.main_canvas.bbox("all"))

        # 处理线程
        self.processing_thread = None
        self.cancel_flag = False

    def setup_log_handler(self):
        """设置日志处理器，将日志输出到文本框"""

        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                logging.Handler.__init__(self)
                self.text_widget = text_widget

            def emit(self, record):
                msg = self.format(record) + '\n'

                def append():
                    self.text_widget.insert(tk.END, msg)
                    self.text_widget.see(tk.END)

                self.text_widget.after(0, append)

        text_handler = TextHandler(self.log_text)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        text_handler.setFormatter(formatter)
        logger.addHandler(text_handler)

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = filedialog.askdirectory(title="选择输出目录")
        if dir_path:
            self.output_dir = dir_path
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, dir_path)

    def select_bgc_dir(self):
        """选择营养盐数据目录"""
        dir_path = filedialog.askdirectory(title="选择营养盐数据目录")
        if dir_path:
            self.bgc_dir = dir_path
            self.bgc_entry.delete(0, tk.END)
            self.bgc_entry.insert(0, dir_path)

    def select_phy_dir(self):
        """选择物理参数数据目录"""
        dir_path = filedialog.askdirectory(title="选择物理参数数据目录")
        if dir_path:
            self.phy_dir = dir_path
            self.phy_entry.delete(0, tk.END)
            self.phy_entry.insert(0, dir_path)

    def select_temp_dir(self):
        """选择临时文件目录"""
        dir_path = filedialog.askdirectory(title="选择临时文件目录")
        if dir_path:
            self.temp_var.set(dir_path)

    def start_processing(self):
        """开始处理数据"""
        # 检查目录是否已选择
        if not self.output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return

        if not self.bgc_dir:
            messagebox.showerror("错误", "请选择营养盐数据目录")
            return

        if not self.phy_dir:
            messagebox.showerror("错误", "请选择物理参数数据目录")
            return

        # 更新配置
        CONFIG['max_workers'] = self.cpu_var.get()
        CONFIG['memory_limit_percent'] = self.mem_var.get()
        CONFIG['chunk_size'] = self.chunk_var.get()
        CONFIG['keep_temp_files'] = self.keep_temp_var.get()
        CONFIG['sort_chunk_size'] = self.sort_chunk_var.get()
        CONFIG['buffer_size'] = self.buffer_var.get() * 1024 * 1024  # 将MB转换为字节
        CONFIG['batch_buffer_limit'] = self.batch_buffer_var.get()
        CONFIG['hash_group_digits'] = self.hash_group_var.get()
        CONFIG['ssd_optimized'] = self.ssd_var.get()
        CONFIG['use_threaded_io'] = self.threaded_io_var.get()
        CONFIG['use_parallel_filter'] = self.parallel_filter_var.get()
        CONFIG['show_progress_bar'] = self.progress_bar_var.get()
        CONFIG['parallel_sort'] = self.parallel_sort_var.get()  # 简化，不需要Windows禁用

        # 在Windows上始终禁用并行排序
        if os.name == 'nt':
            CONFIG['parallel_sort'] = False
        else:
            CONFIG['parallel_sort'] = self.parallel_sort_var.get()

        # 设置临时目录 - 确保总是正确创建
        temp_dir = self.temp_var.get()
        if temp_dir:
            # 如果目录不存在，创建它
            if not os.path.exists(temp_dir):
                try:
                    os.makedirs(temp_dir, exist_ok=True)
                    logger.info(f"创建临时目录: {temp_dir}")
                except Exception as e:
                    # 如果创建失败，提示用户并使用默认临时目录
                    logger.warning(f"创建临时目录失败: {str(e)}，使用系统临时目录")
                    messagebox.showwarning("警告", f"创建临时目录失败: {str(e)}\n将使用系统临时目录")
                    temp_dir = None
        else:
            # 如果用户未指定，则使用当前目录下的temp子目录
            temp_dir = os.path.join(os.getcwd(), "temp")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)
            logger.info(f"未指定临时目录，使用默认临时目录: {temp_dir}")

        # 更新全局配置
        CONFIG['temp_dir'] = temp_dir
        logger.info(f"设置全局临时目录: {CONFIG['temp_dir']}")
        logger.info(f"临时文件保留设置: {'保留' if CONFIG['keep_temp_files'] else '清除'}")
        logger.info(f"SSD优化设置: {'启用' if CONFIG['ssd_optimized'] else '禁用'}")
        logger.info(f"并行排序设置: {'启用' if CONFIG['parallel_sort'] else '禁用'}")
        logger.info(f"使用多线程IO: {'启用' if CONFIG['use_threaded_io'] else '禁用'}")
        logger.info(f"使用并行筛选: {'启用' if CONFIG['use_parallel_filter'] else '禁用'}")
        logger.info(f"显示详细进度条: {'启用' if CONFIG['show_progress_bar'] else '禁用'}")

        # 设置默认临时目录
        if temp_dir:
            try:
                # 设置Python临时文件系统的默认目录
                tempfile.tempdir = temp_dir
                # 设置环境变量，影响其他可能使用临时目录的库
                os.environ['TMPDIR'] = temp_dir  # Unix/Linux
                os.environ['TEMP'] = temp_dir  # Windows
                os.environ['TMP'] = temp_dir  # Windows替代变量
                logger.info(f"已设置系统临时目录环境变量为: {temp_dir}")

                # SSD优化：预热临时目录
                if CONFIG['ssd_optimized']:
                    logger.info(f"预热SSD临时目录...")
                    # 创建一个小文件来预热SSD缓存
                    warmup_file = os.path.join(temp_dir, "warmup.txt")
                    with open(warmup_file, 'w') as f:
                        f.write("SSD预热文件\n" * 1000)
                    # 读取预热文件
                    with open(warmup_file, 'r') as f:
                        _ = f.read()
                    # 删除预热文件
                    os.remove(warmup_file)
                    logger.info(f"SSD预热完成")

            except Exception as e:
                logger.warning(f"设置临时目录环境变量失败: {str(e)}")

        # 查找匹配的年份
        self.year_file_pairs = group_files_by_year(self.bgc_dir, self.phy_dir)

        if not self.year_file_pairs:
            messagebox.showerror("错误", "未找到匹配的年份数据文件")
            return

        # 显示找到的年份
        years_str = ", ".join(str(year) for year in sorted(self.year_file_pairs.keys()))
        logger.info(f"找到 {len(self.year_file_pairs)} 个年份的匹配数据: {years_str}")

        # 更新UI状态
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.status_var.set("处理中...")
        self.cancel_flag = False

        # 在新线程中运行处理逻辑
        self.processing_thread = threading.Thread(target=self.process_data)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def cancel_processing(self):
        """取消处理"""
        if messagebox.askyesno("确认", "确定要取消处理吗？"):
            self.cancel_flag = True
            self.status_var.set("正在取消...")
            logger.info("用户取消处理")

    def process_data(self):
        """处理数据的线程函数 - 修改版，解决临时目录问题"""
        global_temp_dir = CONFIG['temp_dir']  # 主进程中的临时目录

        try:
            start_time = time.time()

            # 创建总体报告
            overall_report = "海洋数据筛选与合并总体报告\n"
            overall_report += f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            overall_report += f"处理配置:\n"
            overall_report += f"  并行处理年份数: {CONFIG['max_workers']}\n"
            overall_report += f"  内存使用限制: {CONFIG['memory_limit_percent']}%\n"
            overall_report += f"  数据块大小: {CONFIG['chunk_size']} 行\n"
            overall_report += f"  临时文件保留设置: {'保留' if CONFIG['keep_temp_files'] else '清除'}\n"
            overall_report += f"  临时文件目录: {CONFIG['temp_dir']}\n"
            overall_report += f"  SSD优化: {'启用' if CONFIG['ssd_optimized'] else '禁用'}\n"
            overall_report += f"  排序块大小: {CONFIG['sort_chunk_size']} 行\n"
            overall_report += f"  IO缓冲区大小: {CONFIG['buffer_size'] // (1024 * 1024)} MB\n"
            overall_report += f"  批量写入缓冲区大小: {CONFIG['batch_buffer_limit']} 行\n"
            overall_report += f"  哈希分组位数: {CONFIG['hash_group_digits']} 位\n"
            overall_report += f"  并行排序: {'启用' if CONFIG['parallel_sort'] else '禁用'}\n"
            overall_report += f"  使用多线程IO: {'启用' if CONFIG['use_threaded_io'] else '禁用'}\n"
            overall_report += f"  使用并行筛选: {'启用' if CONFIG['use_parallel_filter'] else '禁用'}\n"
            overall_report += f"  显示详细进度条: {'启用' if CONFIG['show_progress_bar'] else '禁用'}\n"
            overall_report += f"  运行环境: {'Windows' if os.name == 'nt' else 'Linux/Unix'}\n"
            overall_report += f"找到 {len(self.year_file_pairs)} 个年份的匹配数据\n\n"
            overall_report += "-" * 50 + "\n\n"

            # 准备要处理的年份
            years = sorted(self.year_file_pairs.keys())
            total_years = len(years)

            # 更新进度
            self.progress_var.set(0)
            self.progress_label.config(text=f"总进度: 0/{total_years}")

            # 处理结果
            results = []

            # 使用进程池，不再使用初始化器
            if os.name == 'nt':
                # Windows平台需要使用spawn方法
                ctx = mp.get_context('spawn')
                pool = ctx.Pool(processes=CONFIG['max_workers'])  # 移除初始化器
                logger.info("Windows环境: 使用spawn方法创建进程池")
            else:
                # Linux/Unix平台
                pool = mp.Pool(processes=CONFIG['max_workers'])  # 移除初始化器
                logger.info("非Windows环境: 使用默认方法创建进程池")

            try:
                # 提交任务
                futures = []
                for year in years:
                    if self.cancel_flag:
                        break

                    bgc_file, phy_file = self.year_file_pairs[year]

                    # 验证输入文件
                    if not os.path.exists(bgc_file):
                        logger.error(f"找不到营养盐数据文件: {bgc_file}")
                        continue
                    if not os.path.exists(phy_file):
                        logger.error(f"找不到物理参数数据文件: {phy_file}")
                        continue

                    # 为每个年份创建独立的临时目录
                    year_temp_dir = os.path.join(global_temp_dir, f"ocean_data_{year}")
                    if not os.path.exists(year_temp_dir):
                        os.makedirs(year_temp_dir, exist_ok=True)
                    logger.info(f"为 {year} 年创建独立临时目录: {year_temp_dir}")

                    # 创建年份特定的配置副本
                    year_config = CONFIG.copy()
                    year_config['temp_dir'] = year_temp_dir  # 使用年份特定的临时目录

                    futures.append(
                        pool.apply_async(
                            process_year_data_with_config,  # 使用新函数传递配置
                            (year, bgc_file, phy_file, self.output_dir, year_config)
                        )
                    )

                # 收集结果
                for i, future in enumerate(futures):
                    if self.cancel_flag:
                        break

                    try:
                        result = future.get()
                        results.append(result)

                        # 更新进度
                        self.progress_var.set((i + 1) / total_years * 100)
                        self.progress_label.config(text=f"总进度: {i + 1}/{total_years}")

                        # 更新状态
                        self.status_var.set(f"已处理 {i + 1}/{total_years} 年份")

                        logger.info(f"完成处理 {result['year']} 年数据")

                        # 强制回收
                        gc.collect()
                    except Exception as e:
                        logger.error(f"处理年份数据时出错: {str(e)}")
                        results.append({
                            'year': years[i],
                            'error': str(e)
                        })
            finally:
                # 确保进程池关闭
                pool.close()
                pool.join()

            # 处理被取消
            if self.cancel_flag:
                logger.info("处理已被用户取消")
                self.status_var.set("处理已取消")

                # 恢复UI状态
                self.root.after(0, self.reset_ui)
                return

            # 更新总体报告
            for result in results:
                if 'error' in result:
                    overall_report += f"年份: {result['year']} - 处理失败: {result['error']}\n\n"
                else:
                    overall_report += f"年份: {result['year']}\n"
                    overall_report += f"  营养盐数据: 原始 {result['bgc_total']} 行, 剔除 {result['bgc_removed']} 行\n"
                    overall_report += f"  物理参数数据: 原始 {result['phy_total']} 行, 剔除 {result['phy_removed']} 行\n"
                    overall_report += f"  最终合并数据: {result['merged_count']} 行\n"
                    if 'processing_time' in result:
                        overall_report += f"  处理耗时: {result['processing_time']:.2f} 秒\n"
                    if 'temp_dir' in result:
                        overall_report += f"  临时文件目录: {result['temp_dir']}\n"
                    overall_report += "\n"

            # 添加总处理时间
            total_time = time.time() - start_time
            overall_report += f"\n总处理耗时: {total_time:.2f} 秒\n"

            # 保存总体报告
            overall_report_path = os.path.join(self.output_dir, "overall_report.txt")
            with open(overall_report_path, 'w', encoding='utf-8') as f:
                f.write(overall_report)

            logger.info(f"总体报告已保存至: {overall_report_path}")

            # 显示完成消息
            self.root.after(0, lambda: messagebox.showinfo("完成",
                                                           f"数据处理完成，总体报告已保存至:\n{overall_report_path}"))

            # 更新状态
            self.status_var.set("处理完成")

        except Exception as e:
            logger.error(f"处理过程中发生错误: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"处理过程中发生错误: {str(e)}"))
            self.status_var.set("处理出错")

        finally:
            # 清理主进程的临时目录 - 只有当配置为不保留临时文件时才清除
            if global_temp_dir and os.path.exists(global_temp_dir) and not CONFIG.get('keep_temp_files', True):
                try:
                    cleanup_temp_dir(global_temp_dir)
                except Exception as e:
                    logger.warning(f"清理全局临时目录失败: {str(e)}")

            # 恢复UI状态
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        """重置UI状态"""
        self.start_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        self.progress_var.set(0)
        self.progress_label.config(text="准备就绪")

# 主函数
def main():
    # Windows多进程需要添加freeze_support调用
    if os.name == 'nt':
        mp.freeze_support()

    root = tk.Tk()
    # 设置窗口图标
    try:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocean_icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except:
        pass  # 如果没有图标文件或其他错误，忽略

    app = OceanDataProcessor(root)

    # 使窗口在屏幕中央显示
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')

    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"程序发生错误: {str(e)}")
        messagebox.showerror("错误", f"程序发生错误: {str(e)}")