import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
from pathlib import Path


def select_csv_file():
    """弹出窗口选择CSV文件"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 弹出文件选择对话框
    file_path = filedialog.askopenfilename(
        title="选择CSV文件",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )

    root.destroy()
    return file_path


def get_file_line_count(file_path):
    """快速获取文件行数（不包括表头）"""
    try:
        print("正在统计文件行数...")
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            line_count = sum(1 for _ in f) - 1  # 减1是因为不包括表头
        return line_count
    except:
        try:
            # 尝试其他编码
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                line_count = sum(1 for _ in f) - 1
            return line_count
        except:
            return None


def get_row_range(max_rows=None):
    """输入要查看的行范围"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    try:
        # 显示文件信息
        info_msg = "请输入起始行号 (从1开始)"
        if max_rows:
            info_msg += f"\n文件总行数: {max_rows}"

        # 获取起始行
        start_row = simpledialog.askinteger(
            "输入行范围",
            info_msg,
            minvalue=1,
            maxvalue=max_rows if max_rows else None
        )

        if start_row is None:  # 用户取消
            root.destroy()
            return None, None

        # 获取结束行
        end_info = f"请输入结束行号 (起始行: {start_row})"
        if max_rows:
            end_info += f"\n最大行号: {max_rows}"

        end_row = simpledialog.askinteger(
            "输入行范围",
            end_info,
            minvalue=start_row,
            maxvalue=max_rows if max_rows else None
        )

        if end_row is None:  # 用户取消
            root.destroy()
            return None, None

        root.destroy()
        return start_row, end_row

    except Exception as e:
        messagebox.showerror("错误", f"输入有误: {str(e)}")
        root.destroy()
        return None, None


def read_csv_chunk(file_path, start_row, end_row, max_display_rows=50):
    """高效读取CSV文件的指定行范围"""
    try:
        print(f"正在读取第 {start_row} 到 {end_row} 行...")

        # 计算需要跳过的行数和需要读取的行数
        skip_rows = start_row - 1  # pandas的skiprows不包括表头
        nrows = end_row - start_row + 1

        # 如果需要显示的行数太多，限制显示数量
        display_rows = min(nrows, max_display_rows)

        # 首先读取表头
        header_df = pd.read_csv(file_path, nrows=0)
        print("\n表头:")
        for i, col in enumerate(header_df.columns, 1):
            print(f"  {i}. {col}")
        print("-" * 50)

        # 读取指定行范围的数据
        if skip_rows > 0:
            df = pd.read_csv(file_path, skiprows=range(1, skip_rows + 1), nrows=nrows)
        else:
            df = pd.read_csv(file_path, nrows=nrows)

        # 显示文件信息
        print(f"\n文件路径: {file_path}")
        print(f"请求查看行范围: {start_row} - {end_row} ({nrows} 行)")
        print(f"实际读取行数: {len(df)}")

        if len(df) == 0:
            print("警告: 没有读取到数据，可能超出文件范围")
            return

        # 显示数据
        if nrows <= max_display_rows:
            print(f"\n第 {start_row} 到 {end_row} 行的数据:")
            print(df.to_string(index=False))
        else:
            print(f"\n数据量较大，仅显示前 {display_rows} 行:")
            print(df.head(display_rows).to_string(index=False))
            print(f"\n... (还有 {nrows - display_rows} 行未显示)")

            # 询问是否查看更多
            show_more = input(f"\n是否要显示所有 {nrows} 行数据？(y/n): ").lower()
            if show_more == 'y':
                print(f"\n完整数据 (第 {start_row} 到 {end_row} 行):")
                print(df.to_string(index=False))

        # 显示基本统计信息
        print(f"\n数据统计:")
        print(f"  列数: {len(df.columns)}")
        print(f"  行数: {len(df)}")

        # 可选：保存到文件
        if len(df) > 0:
            save_option = input(f"\n是否要将这些数据保存到新的CSV文件？(y/n): ").lower()
            if save_option == 'y':
                output_file = f"selected_rows_{start_row}_to_{end_row}.csv"
                df.to_csv(output_file, index=False)
                print(f"数据已保存到: {output_file}")

    except FileNotFoundError:
        print(f"错误: 找不到文件 {file_path}")
    except pd.errors.EmptyDataError:
        print("错误: CSV文件为空")
    except pd.errors.ParserError as e:
        print(f"错误: CSV文件解析失败 - {str(e)}")
    except MemoryError:
        print("错误: 内存不足，无法读取如此大的数据范围")
        print("建议: 减少查看的行数范围")
    except Exception as e:
        print(f"错误: {str(e)}")


def main():
    """主函数"""
    print("CSV文件查看器 (优化版)")
    print("=" * 40)

    # 选择CSV文件
    file_path = select_csv_file()
    if not file_path:
        print("未选择文件，程序退出")
        return

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        return

    # 显示文件大小
    file_size = Path(file_path).stat().st_size
    print(f"文件大小: {file_size / (1024 * 1024):.2f} MB")

    # 快速统计行数
    total_rows = get_file_line_count(file_path)
    if total_rows:
        print(f"文件总行数: {total_rows:,}")
    else:
        print("无法快速统计行数")

    # 获取行范围
    start_row, end_row = get_row_range(total_rows)
    if start_row is None or end_row is None:
        print("未输入有效行范围，程序退出")
        return

    # 检查行范围合理性
    if total_rows and start_row > total_rows:
        print(f"错误: 起始行 {start_row:,} 超出文件总行数 {total_rows:,}")
        return

    if total_rows and end_row > total_rows:
        print(f"警告: 结束行 {end_row:,} 超出文件总行数 {total_rows:,}")
        print(f"将自动调整为最大行数 {total_rows:,}")
        end_row = total_rows

    # 检查查看范围是否过大
    range_size = end_row - start_row + 1
    if range_size > 10000:
        confirm = input(f"警告: 您要查看 {range_size:,} 行数据，这可能很慢。是否继续？(y/n): ").lower()
        if confirm != 'y':
            print("操作已取消")
            return

    # 读取和显示CSV文件
    read_csv_chunk(file_path, start_row, end_row)


if __name__ == "__main__":
    main()