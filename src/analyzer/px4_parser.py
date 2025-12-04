import pandas as pd
import numpy as np
from pyulog import ULog
from .parser_base import LogParser


class PX4Parser(LogParser):
    """
    [子类] PX4 ULog (.ulg) 解析器 (全功能版)
    支持: 姿态, GPS, 局部位置, PID, 光流, 震动(计算), 削顶, 飞行模式
    """

    def load(self) -> bool:
        print(f"[Info] 正在加载 PX4 ULog 文件: {self.file_path} ...")
        try:
            self.ulog = ULog(self.file_path)
            return True
        except Exception as e:
            print(f"[Error] 无法打开 ULog 文件: {e}")
            return False

    def parse(self) -> pd.DataFrame:
        if not hasattr(self, 'ulog'):
            return pd.DataFrame()

        # 1. 话题配置
        topics_config = {
            'vehicle_attitude': ['timestamp', 'q[0]', 'q[1]', 'q[2]', 'q[3]'],
            'vehicle_gps_position': ['timestamp', 'lat', 'lon', 'alt'],
            'vehicle_local_position': ['timestamp', 'x', 'y', 'z'],
            'vehicle_angular_velocity': ['timestamp', 'xyz[0]', 'xyz[1]', 'xyz[2]'],
            'vehicle_rates_setpoint': ['timestamp', 'roll', 'pitch', 'yaw'],

            # [新增] 飞行模式源数据 (PX4 中模式存储在 vehicle_status 的 nav_state 字段)
            'vehicle_status': ['timestamp', 'nav_state'],

            # [新增] 震动源数据: 原始加速度
            'sensor_combined': ['timestamp', 'accelerometer_m_s2[0]', 'accelerometer_m_s2[1]', 'accelerometer_m_s2[2]'],

            # [新增] 削顶状态
            'vehicle_imu_status': ['timestamp', 'accel_clipping[0]', 'accel_clipping[1]', 'accel_clipping[2]'],
        }

        # 动态检测光流
        available_topics = {t.name for t in self.ulog.data_list}
        flow_topic = None
        if 'vehicle_optical_flow' in available_topics:
            flow_topic = 'vehicle_optical_flow'
        elif 'optical_flow' in available_topics:
            flow_topic = 'optical_flow'

        flow_field_map = {}
        if flow_topic:
            try:
                ds = self.ulog.get_dataset(flow_topic)
                fields = ds.data.keys()
                if 'pixel_flow[0]' in fields:
                    flow_field_map = {'pixel_flow[0]': 'flow_x', 'pixel_flow[1]': 'flow_y'}
                elif 'pixel_flow_x_integral' in fields:
                    flow_field_map = {'pixel_flow_x_integral': 'flow_x', 'pixel_flow_y_integral': 'flow_y'}
                elif 'integrated_x' in fields:
                    flow_field_map = {'integrated_x': 'flow_x', 'integrated_y': 'flow_y'}

                if 'quality' in fields: flow_field_map['quality'] = 'flow_quality'
                if flow_field_map: topics_config[flow_topic] = ['timestamp'] + list(flow_field_map.keys())
            except:
                pass

        # 2. 提取数据
        dfs = {}
        for topic, fields in topics_config.items():
            try:
                data = self.ulog.get_dataset(topic)
                df_temp = pd.DataFrame(data.data)
                df_temp['timestamp'] /= 1e6  # us -> s

                # [新增] 特殊处理: 重命名 nav_state 为 mode
                if topic == 'vehicle_status':
                    df_temp = df_temp.rename(columns={'nav_state': 'mode'})

                if topic == flow_topic:
                    df_temp = df_temp.rename(columns=flow_field_map)
                    cols = ['timestamp'] + list(flow_field_map.values())
                    df_temp = df_temp[[c for c in cols if c in df_temp.columns]]

                # 兼容 IMU Clipping 字段名
                if topic == 'vehicle_imu_status':
                    if 'accel_clipping[0]' not in df_temp.columns and 'accel_clipping' in df_temp.columns:
                        df_temp['accel_clipping[0]'] = df_temp['accel_clipping']
                        df_temp['accel_clipping[1]'] = 0
                        df_temp['accel_clipping[2]'] = 0

                dfs[topic] = df_temp
            except:
                continue

        if not dfs or 'vehicle_attitude' not in dfs:
            return pd.DataFrame()

        # 3. 对齐合并
        main_df = dfs['vehicle_attitude'].sort_values('timestamp')

        # 姿态解算
        w, x, y, z = main_df['q[0]'], main_df['q[1]'], main_df['q[2]'], main_df['q[3]']
        main_df['roll'] = np.degrees(np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
        main_df['pitch'] = np.degrees(np.arcsin(np.clip(2 * (w * y - z * x), -1, 1)))
        main_df['yaw'] = np.degrees(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
        main_df = main_df[['timestamp', 'roll', 'pitch', 'yaw']]
        
        # [新增] 合并飞行模式 (Mode)
        if 'vehicle_status' in dfs:
            # 使用 nearest 匹配，因为模式切换频率比姿态低得多
            main_df = pd.merge_asof(main_df, dfs['vehicle_status'][['timestamp', 'mode']], on='timestamp')

        # 合并 GPS
        if 'vehicle_gps_position' in dfs:
            gps = dfs['vehicle_gps_position']
            gps['lat'] /= 1e7
            gps['lon'] /= 1e7
            gps['alt'] /= 1e3
            main_df = pd.merge_asof(main_df, gps[['timestamp', 'lat', 'lon', 'alt']], on='timestamp')

        # 合并局部位置
        if 'vehicle_local_position' in dfs:
            loc = dfs['vehicle_local_position'].rename(columns={'x': 'loc_x', 'y': 'loc_y', 'z': 'loc_z'})
            main_df = pd.merge_asof(main_df, loc[['timestamp', 'loc_x', 'loc_y', 'loc_z']], on='timestamp')

        # 合并 PID
        if 'vehicle_angular_velocity' in dfs and 'vehicle_rates_setpoint' in dfs:
            act = dfs['vehicle_angular_velocity']
            des = dfs['vehicle_rates_setpoint'].rename(
                columns={'roll': 'rate_roll_des', 'pitch': 'rate_pitch_des', 'yaw': 'rate_yaw_des'})
            for col in ['xyz[0]', 'xyz[1]', 'xyz[2]']: act[col] = np.degrees(act[col])
            for col in ['rate_roll_des', 'rate_pitch_des', 'rate_yaw_des']: des[col] = np.degrees(des[col])

            main_df = pd.merge_asof(main_df, act.rename(
                columns={'xyz[0]': 'rate_roll', 'xyz[1]': 'rate_pitch', 'xyz[2]': 'rate_yaw'})[
                ['timestamp', 'rate_roll', 'rate_pitch', 'rate_yaw']], on='timestamp')
            main_df = pd.merge_asof(main_df, des[['timestamp', 'rate_roll_des', 'rate_pitch_des', 'rate_yaw_des']],
                                    on='timestamp')

        # 合并光流
        if flow_topic in dfs:
            main_df = pd.merge_asof(main_df, dfs[flow_topic], on='timestamp')

        # [关键] 计算震动 (Vibration)
        if 'sensor_combined' in dfs:
            acc = dfs['sensor_combined']
            window_size = 25
            acc['vibe_x'] = acc['accelerometer_m_s2[0]'].rolling(window_size).std().fillna(0)
            acc['vibe_y'] = acc['accelerometer_m_s2[1]'].rolling(window_size).std().fillna(0)
            acc['vibe_z'] = acc['accelerometer_m_s2[2]'].rolling(window_size).std().fillna(0)
            main_df = pd.merge_asof(main_df, acc[['timestamp', 'vibe_x', 'vibe_y', 'vibe_z']], on='timestamp')

        # [关键] 合并削顶 (Clipping)
        if 'vehicle_imu_status' in dfs:
            clip = dfs['vehicle_imu_status']
            clip_cols_map = {}
            if 'accel_clipping[0]' in clip.columns:
                clip_cols_map = {'accel_clipping[0]': 'clip_0', 'accel_clipping[1]': 'clip_1',
                                 'accel_clipping[2]': 'clip_2'}

            if clip_cols_map:
                clip = clip.rename(columns=clip_cols_map)
                main_df = pd.merge_asof(main_df, clip[['timestamp', 'clip_0', 'clip_1', 'clip_2']], on='timestamp')

        return main_df