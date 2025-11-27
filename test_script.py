import os
import sys
sys.path.append(os.getcwd())

from src.analyzer.ardu_parser import ArduPilotParser


def test_parsing():
    log_file = "data/log100.bin"
    if not os.path.exists(log_file):
        print(f"错误: 找不到文件 {log_file}")
        print("请在 data/ 目录下放入一个 .bin 文件，并修改 test_script.py 中的文件名。")
        return
    print("------- 开始测试 -------")
    parser = ArduPilotParser(log_file)
    try:
        df = parser.get_dataframe()
    except Exception as e:
        print(f" 解析过程中出错: {e}")
        return
    if not df.empty:
        print("\n测试成功！成功读取数据。")
        print("数据预览 (前 5 行):")
        print(df.head())

        print("\n数据统计:")
        print(f"总行数: {len(df)}")
        print(f"包含的消息类型: {df['msg_type'].unique()}")

        if 'roll' in df.columns:
            print(f"Roll 平均值: {df['roll'].mean():.2f} deg")
    else:
        print("警告: 数据为空，可能日志中没有 ATT 或 GPS 消息。")


if __name__ == "__main__":
    test_parsing()