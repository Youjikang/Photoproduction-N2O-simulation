import os
import tkinter as tk
from tkinter import filedialog, messagebox
import csv
import io


def merge_csv_files():
    """
    使用流式处理方式合并两个大型CSV文件，保持极低的内存占用
    """
    # 创建tkinter根窗口（但不显示）
    root = tk.Tk()
    root.withdraw()

    # 请用户选择第一个CSV文件
    print("请选择第一个CSV文件...")
    file1 = filedialog.askopenfilename(title="选择第一个CSV文件", filetypes=[("CSV files", "*.csv")])
    if not file1:
        print("未选择文件，程序退出")
        return

    # 请用户选择第二个CSV文件
    print("请选择第二个CSV文件...")
    file2 = filedialog.askopenfilename(title="选择第二个CSV文件", filetypes=[("CSV files", "*.csv")])
    if not file2:
        print("未选择第二个文件，程序退出")
        return

    try:
        # 分析文件格式（仅使用文件的少量采样）
        print(f"正在分析文件 {os.path.basename(file1)} 的格式...")
        encoding1, delimiter1, quotechar1, has_header1 = analyze_csv_format(file1)
        print(f"文件1格式: 分隔符='{delimiter1}', 引号='{quotechar1}', 编码='{encoding1}', 有表头={has_header1}")

        print(f"正在分析文件 {os.path.basename(file2)} 的格式...")
        encoding2, delimiter2, quotechar2, has_header2 = analyze_csv_format(file2)
        print(f"文件2格式: 分隔符='{delimiter2}', 引号='{quotechar2}', 编码='{encoding2}', 有表头={has_header2}")

        # 选择使用哪个文件的格式
        if delimiter1 != delimiter2 or quotechar1 != quotechar2 or encoding1 != encoding2:
            print("两个文件的格式不完全一致，将使用第一个文件的格式")

        output_delimiter = delimiter1
        output_quotechar = quotechar1
        output_encoding = encoding1

        # 获取表头和列信息，不读取整个文件
        print("正在获取文件表头信息...")
        header1, first_data_row1 = get_header_info(file1, encoding1, delimiter1, quotechar1, has_header1)
        header2, first_data_row2 = get_header_info(file2, encoding2, delimiter2, quotechar2, has_header2)

        # 决定最终使用的表头
        if has_header1 and has_header2 and header1 != header2:
            print("警告: 两个CSV文件的列名不完全相同")
            print(f"文件1列名: {header1}")
            print(f"文件2列名: {header2}")

            # 询问用户如何处理
            answer = messagebox.askyesno("列名不匹配",
                                         "两个CSV文件的列名不完全相同。\n是否只合并共有的列？\n\n选择'是'只合并共有列\n选择'否'将使用所有列（文件2会根据文件1的列顺序调整）")

            if answer:
                # 只保留共有列
                common_columns = list(set(header1) & set(header2))
                output_header = common_columns

                # 获取每个文件中共有列的索引
                indices1 = [header1.index(col) for col in common_columns]
                indices2 = [header2.index(col) for col in common_columns]

                print(f"只合并共有列: {common_columns}")
            else:
                # 使用所有列（以第一个文件的列为基准）
                output_header = header1
                indices1 = list(range(len(header1)))

                # 为第二个文件创建映射关系
                indices2 = []
                for col in header1:
                    if col in header2:
                        indices2.append(header2.index(col))
                    else:
                        # 如果第二个文件没有这一列，使用-1表示需要填充空值
                        indices2.append(-1)

                print(f"使用文件1的所有列: {header1}")
        else:
            # 如果表头一致或者只有一个文件有表头
            if has_header1:
                output_header = header1
            elif has_header2:
                output_header = header2
            else:
                # 两个文件都没有表头，使用第一行的列数创建一个数字表头
                col_count = max(len(first_data_row1), len(first_data_row2))
                output_header = [f"Column{i + 1}" for i in range(col_count)]

            # 默认使用所有列
            indices1 = list(range(len(output_header)))
            indices2 = list(range(len(output_header)))

        # 请用户选择保存位置和文件名
        print("请选择保存位置...")
        output_file = filedialog.asksaveasfilename(
            title="保存合并后的CSV文件",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )

        if not output_file:
            print("未指定保存文件，程序退出")
            return

        # 使用流式处理方式合并文件
        print(f"正在合并文件到 {output_file}...")
        with open(output_file, 'w', encoding=output_encoding, newline='') as out_file:
            writer = csv.writer(out_file, delimiter=output_delimiter, quotechar=output_quotechar,
                                quoting=csv.QUOTE_MINIMAL)

            # 写入表头
            writer.writerow(output_header)

            # 流式处理第一个文件
            row_count1 = stream_process_file(file1, writer, encoding1, delimiter1, quotechar1,
                                             has_header1, indices1, output_header)
            print(f"已处理文件1的 {row_count1} 行数据")

            # 流式处理第二个文件
            row_count2 = stream_process_file(file2, writer, encoding2, delimiter2, quotechar2,
                                             has_header2, indices2, output_header)
            print(f"已处理文件2的 {row_count2} 行数据")

        # 计算文件大小
        file1_size = os.path.getsize(file1) / (1024 * 1024)  # MB
        file2_size = os.path.getsize(file2) / (1024 * 1024)  # MB
        output_size = os.path.getsize(output_file) / (1024 * 1024)  # MB

        total_rows = row_count1 + row_count2 + 1  # +1 表示表头

        print(f"合并完成！")
        print(f"原始文件大小: 文件1 = {file1_size:.2f} MB, 文件2 = {file2_size:.2f} MB")
        print(f"合并后文件大小: {output_size:.2f} MB")

        messagebox.showinfo(
            "完成",
            f"文件合并成功!\n\n"
            f"共 {total_rows} 行数据\n"
            f"原始文件: {file1_size:.2f} MB + {file2_size:.2f} MB = {file1_size + file2_size:.2f} MB\n"
            f"合并后: {output_size:.2f} MB\n"
            f"已保存至: {output_file}"
        )

    except Exception as e:
        messagebox.showerror("错误", f"合并过程中出现错误:\n{str(e)}")
        print(f"错误: {str(e)}")
        # 打印详细的错误追踪
        import traceback
        traceback.print_exc()


def analyze_csv_format(file_path, sample_size=100):
    """
    分析CSV文件格式，只读取少量样本
    返回: 编码, 分隔符, 引号字符, 是否有表头
    """
    # 先检测编码
    encoding = detect_encoding(file_path)

    # 使用不同的分隔符尝试
    possible_delimiters = [',', ';', '\t', '|']
    possible_quotechars = ['"', "'"]

    best_delimiter = ','  # 默认分隔符
    best_quotechar = '"'  # 默认引号
    max_fields = 0
    sample_rows = []

    # 尝试不同的分隔符和引号组合，仅读取少量行进行分析
    for delimiter in possible_delimiters:
        for quotechar in possible_quotechars:
            try:
                with open(file_path, 'r', encoding=encoding, newline='') as f:
                    sample_content = ''.join([f.readline() for _ in range(min(sample_size, 100))])

                # 使用字符串IO避免再次打开文件
                sample_file = io.StringIO(sample_content)
                reader = csv.reader(sample_file, delimiter=delimiter, quotechar=quotechar)
                rows = list(reader)

                # 检查是否读取到了内容
                if not rows:
                    continue

                # 检查字段数量
                field_counts = [len(row) for row in rows if row]
                if not field_counts:
                    continue

                # 一致性检查
                most_common_count = max(set(field_counts), key=field_counts.count)
                consistent_rows = [row for row in rows if len(row) == most_common_count]

                # 如果一致的行太少，可能不是正确的分隔符
                if len(consistent_rows) < len(rows) * 0.8:
                    continue

                # 如果字段数量比当前最大值多，更新最佳选择
                if most_common_count > max_fields and len(consistent_rows) > 1:
                    max_fields = most_common_count
                    best_delimiter = delimiter
                    best_quotechar = quotechar
                    sample_rows = consistent_rows[:min(10, len(consistent_rows))]
            except Exception:
                continue

    # 检测是否有表头
    has_header = False
    if len(sample_rows) >= 2:
        has_header = detect_header(sample_rows)

    return encoding, best_delimiter, best_quotechar, has_header


def get_header_info(file_path, encoding, delimiter, quotechar, has_header):
    """
    获取文件的表头信息，只读取文件的前几行
    返回: 表头列表, 第一行数据
    """
    with open(file_path, 'r', encoding=encoding, newline='') as f:
        reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)

        if has_header:
            header = next(reader)
            try:
                first_data_row = next(reader)
            except StopIteration:
                first_data_row = []
        else:
            try:
                first_data_row = next(reader)
                header = [f"Column{i + 1}" for i in range(len(first_data_row))]
            except StopIteration:
                first_data_row = []
                header = []

    return header, first_data_row


def stream_process_file(file_path, writer, encoding, delimiter, quotechar, has_header, indices, output_header):
    """
    流式处理CSV文件，逐行读取并写入，保持低内存占用
    返回: 处理的行数
    """
    row_count = 0
    with open(file_path, 'r', encoding=encoding, newline='') as f:
        reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)

        # 如果有表头，跳过第一行
        if has_header:
            next(reader)

        # 逐行处理
        for row in reader:
            row_count += 1

            # 处理行数据
            if row:
                if len(indices) == len(output_header):  # 正常映射
                    output_row = []
                    for i in indices:
                        if i >= 0 and i < len(row):
                            output_row.append(row[i])
                        else:
                            output_row.append('')
                else:  # 简单复制
                    output_row = row

                writer.writerow(output_row)

            # 每处理10000行显示进度
            if row_count % 10000 == 0:
                print(f"已处理 {row_count} 行...")

    return row_count


def detect_header(rows):
    """检测数据是否有表头"""
    if len(rows) < 2:
        return False

    # 简单启发式方法
    first_row = rows[0]
    other_rows = rows[1:]

    # 检查第一行和其他行的数字比例
    is_number = lambda x: x.replace('.', '', 1).replace('-', '', 1).isdigit() if isinstance(x, str) else False

    first_row_num_count = sum(1 for cell in first_row if is_number(cell))
    first_row_num_ratio = first_row_num_count / len(first_row) if first_row else 0

    other_rows_num_count = sum(sum(1 for cell in row if is_number(cell)) for row in other_rows)
    other_rows_num_ratio = other_rows_num_count / (len(other_rows) * len(first_row)) if other_rows and first_row else 0

    # 如果第一行几乎没有数字，但其他行有明显比例的数字，可能是表头
    if first_row_num_ratio < 0.1 and other_rows_num_ratio > 0.3:
        return True

    # 如果第一行的数字比例明显低于其他行，可能是表头
    if first_row_num_ratio < other_rows_num_ratio * 0.5:
        return True

    return False


def detect_encoding(file_path):
    """检测文件编码（只读取文件的前4KB）"""
    # 读取文件的前4KB用于检测
    with open(file_path, 'rb') as f:
        raw_data = f.read(4096)

    # 尝试常见编码
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'ascii', 'iso-8859-1']

    # 先尝试用chardet库检测
    try:
        import chardet
        result = chardet.detect(raw_data)
        if result['confidence'] > 0.7:
            return result['encoding']
    except ImportError:
        print("未安装chardet库，将使用备选方法检测编码")
    except Exception as e:
        print(f"使用chardet检测编码时出错: {str(e)}")

    # 如果chardet不可用或失败，尝试手动检测
    for enc in encodings:
        try:
            raw_data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue

    # 默认返回
    return 'utf-8'


if __name__ == "__main__":
    # 检查是否安装了chardet库
    try:
        import chardet
    except ImportError:
        print("提示: 未检测到chardet库，建议安装以获得更好的编码检测能力")
        print("可通过命令安装: pip install chardet")

    merge_csv_files()