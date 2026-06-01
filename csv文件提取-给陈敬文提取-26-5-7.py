import os
import pandas as pd
from tkinter import Tk
from tkinter.filedialog import askopenfilename, askdirectory
from tkinter.messagebox import showinfo, showerror
from tqdm import tqdm


def count_csv_rows(file_path):
    """
    统计 CSV 总行数，用于显示进度。
    减 1 是因为第一行通常是表头。
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f) - 1


def extract_columns_from_csv():
    columns_to_extract = [
        "G2year",
        "G2month",
        "G2day",
        "G2hour",
        "G2minute",
        "G2latitude",
        "G2longitude",
        "G2depth",
        "G2temperature",
        "G2phosphate",
        "G2toc",
        "G2don",
        "G2chla",
        "G2oxygen"
    ]

    root = Tk()
    root.withdraw()

    csv_file = askopenfilename(
        title="请选择 CSV 文件",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )

    if not csv_file:
        showerror("错误", "没有选择 CSV 文件")
        return

    output_folder = askdirectory(title="请选择输出文件夹")

    if not output_folder:
        showerror("错误", "没有选择输出文件夹")
        return

    input_filename = os.path.splitext(os.path.basename(csv_file))[0]
    output_file = os.path.join(output_folder, f"{input_filename}_extracted.csv")

    try:
        print("正在统计文件行数，请稍等...")
        total_rows = count_csv_rows(csv_file)

        print(f"总数据行数：{total_rows}")
        print("开始提取列...")

        chunk_size = 100000
        first_chunk = True

        progress_bar = tqdm(total=total_rows, unit="行")

        for chunk in pd.read_csv(
            csv_file,
            usecols=columns_to_extract,
            chunksize=chunk_size,
            low_memory=False
        ):
            chunk.to_csv(
                output_file,
                mode="w" if first_chunk else "a",
                index=False,
                header=first_chunk,
                encoding="utf-8-sig"
            )

            progress_bar.update(len(chunk))
            first_chunk = False

        progress_bar.close()

        showinfo("完成", f"列提取完成！\n文件已保存到：\n{output_file}")

    except ValueError as e:
        showerror(
            "错误",
            "CSV 文件中可能缺少指定列。\n\n"
            f"详细错误：\n{e}"
        )

    except Exception as e:
        showerror("错误", f"处理文件时出错：\n{e}")


if __name__ == "__main__":
    extract_columns_from_csv()