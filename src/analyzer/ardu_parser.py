import pandas as pd
import numpy as np
from pymavlink import mavutil
from .parser_base import LogParser


class ArduPilotParser(LogParser):
    """
    [子类] ArduPilot 二进制日志(.bin) 解析器
    继承自 LogParser，必须实现 load() 和 parse() 方法。
    """
    CUSTOM_MODE_MAP = {
            # Copter (旋翼机) 常用模式
            0: 'Stabilize',
            1: 'Acro',
            2: 'AltHold',
            3: 'Auto',
            4: 'Guided',
            5: 'Loiter',
            6: 'RTL',
            7: 'Circle',
            9: 'Land',
            11: 'Drift',
            13: 'Sport',
            14: 'Flip',
            15: 'AutoTune',
            16: 'PosHold',
            17: 'Brake',
            18: 'Throw',
            19: 'Avoid_ADSB',
            20: 'Guided_NoGPS',
            21: 'Smart_RTL',
            22: 'FlowHold',
            23: 'Follow',
            24: 'ZigZag',
            25: 'SystemID',
            27: 'Auto_RTL',
            28: 'Turtle',
            10: 'Auto', 
            12: 'Loiter', 
        }
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
         解析数据，支持 RATE (PID) 分析
        """
        if not hasattr(self, 'mlog'):
            return pd.DataFrame()

        data_list = []
        # [新增] 加入 MODE 消息
        target_types = ['ATT', 'GPS', 'VIBE', 'RATE', 'MODE']

        print(f"[Info] 开始解析数据，目标消息: {target_types} ...")

        while True:
            msg = self.mlog.recv_match(type=target_types, blocking=False)
            if msg is None:
                break

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
                row['clip_0'] = getattr(msg, 'Clip0', getattr(msg, 'Clipping0', 0))
                row['clip_1'] = getattr(msg, 'Clip1', getattr(msg, 'Clipping1', 0))
                row['clip_2'] = getattr(msg, 'Clip2', getattr(msg, 'Clipping2', 0))

            #  解析 RATE (角速度环)
            elif msg_type == 'RATE':
                # Roll 轴
                row['rate_roll'] = getattr(msg, 'R', getattr(msg, 'Roll', np.nan))
                row['rate_roll_des'] = getattr(msg, 'RDes', getattr(msg, 'DesRoll', np.nan))
                # Pitch 轴
                row['rate_pitch'] = getattr(msg, 'P', getattr(msg, 'Pitch', np.nan))
                row['rate_pitch_des'] = getattr(msg, 'PDes', getattr(msg, 'DesPitch', np.nan))
                # Yaw 轴
                row['rate_yaw'] = getattr(msg, 'Y', getattr(msg, 'Yaw', np.nan))
                row['rate_yaw_des'] = getattr(msg, 'YDes', getattr(msg, 'DesYaw', np.nan))
            #   解析MODE消息
            elif msg_type == 'MODE':
                # 1. 优先获取字符串形式的 Mode (新固件通常有)
                mode_name = getattr(msg, 'Mode', None)
                
                # 2. 如果没有，获取 ModeNum 并查表
                if mode_name is None:
                    mode_num = getattr(msg, 'ModeNum', None)
                    if mode_num is not None:
                        # 查我们的硬编码表
                        mode_name = self.CUSTOM_MODE_MAP.get(mode_num, f"Mode {mode_num}")
                    else:
                        mode_name = "Unknown"
                
                # 3. 统一转大写，确保匹配 app.py 里的颜色表
                # (例如 'Stabilize' -> 'STABILIZE')
                row['mode'] = str(mode_name).upper()

            data_list.append(row)

        print(f"[Info] 解析完成，共提取 {len(data_list)} 条记录。")
        df = pd.DataFrame(data_list)
        return df