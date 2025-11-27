import pandas as pd
import numpy as np
from pymavlink import mavutil
from .parser_base import LogParser


class ArduPilotParser(LogParser):
    """
    [子类] ArduPilot 二进制日志(.bin) 解析器
    继承自 LogParser，必须实现 load() 和 parse() 方法。
    """

    def load(self) -> bool:
        """
        实现基类的 load 方法：使用 mavutil 打开二进制文件
        """
        print(f"[Info] 正在打开日志文件: {self.file_path} ...")
        try:
            self.mlog = mavutil.mavlink_connection(self.file_path)
            return True
        except Exception as e:
            print(f"[Error] 无法打开文件: {e}")
            return False

    def parse(self) -> pd.DataFrame:
        """
        [增强版] 解析数据，增加容错处理
        """
        if not hasattr(self, 'mlog'):
            return pd.DataFrame()

        data_list = []
        target_types = ['ATT', 'GPS', 'VIBE']

        print(f"[Info] 开始解析数据，目标消息: {target_types} ...")

        while True:
            msg = self.mlog.recv_match(type=target_types, blocking=False)
            if msg is None:
                break

            # 安全获取时间戳
            timestamp = getattr(msg, 'TimeUS', 0) / 1e6
            msg_type = msg.get_type()

            row = {
                'timestamp': timestamp,
                'msg_type': msg_type,
            }

            if msg_type == 'ATT':
                row['roll'] = getattr(msg, 'Roll', np.nan)
                row['pitch'] = getattr(msg, 'Pitch', np.nan)
                row['yaw'] = getattr(msg, 'Yaw', np.nan)

            elif msg_type == 'GPS':
                row['lat'] = getattr(msg, 'Lat', np.nan)
                row['lon'] = getattr(msg, 'Lng', np.nan)
                row['alt'] = getattr(msg, 'Alt', np.nan)

            elif msg_type == 'VIBE':
                row['vibe_x'] = getattr(msg, 'VibeX', np.nan)
                row['vibe_y'] = getattr(msg, 'VibeY', np.nan)
                row['vibe_z'] = getattr(msg, 'VibeZ', np.nan)
                row['clip_0'] = getattr(msg, 'Clip0', getattr(msg, 'Clipping0', 0))  # 尝试两种命名
                row['clip_1'] = getattr(msg, 'Clip1', getattr(msg, 'Clipping1', 0))
                row['clip_2'] = getattr(msg, 'Clip2', getattr(msg, 'Clipping2', 0))

            data_list.append(row)

        print(f"[Info] 解析完成，共提取 {len(data_list)} 条记录。")

        df = pd.DataFrame(data_list)
        return df