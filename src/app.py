import streamlit as st
import plotly.express as px
import os
import sys
import tempfile
import time
from zai import ZhipuAiClient
if getattr(sys, 'frozen', False):
    # 如果是打包后的 exe，根目录应该是 exe 所在的文件夹
    base_dir = os.path.dirname(sys.executable)
    # 临时解压目录 (用于寻找内部的 analyzer 包)
    internal_root = sys._MEIPASS
    sys.path.append(os.path.join(internal_root, 'src'))
else:
    # 正常 IDE 运行
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(base_dir)
from analyzer.ardu_parser import ArduPilotParser
from analyzer.px4_parser import PX4Parser

MODE_COLORS = {
    # --- 通用 / ArduPilot 常用 ---
    'Stabilize': 'rgba(255, 165, 0, 0.1)',   # Orange (手动增稳)
    'Loiter': 'rgba(0, 0, 255, 0.1)',        # Blue (定点)
    'PosHold': 'rgba(0, 0, 255, 0.1)',       # Blue (定点)
    'AltHold': 'rgba(0, 255, 255, 0.1)',     # Cyan (定高)
    'Auto': 'rgba(0, 255, 0, 0.1)',          # Green (自动任务)
    'RTL': 'rgba(255, 0, 0, 0.1)',           # Red (返航)
    'Land': 'rgba(255, 0, 0, 0.1)',          # Red (降落)
    'Guided': 'rgba(255, 0, 255, 0.1)',      # Magenta (引导/电脑控制)
    'Manual': 'rgba(128, 128, 128, 0.1)',    # Grey (纯手动)
    'Acro': 'rgba(255, 255, 0, 0.1)',        # Yellow (特技)
    'Drift': 'rgba(255, 255, 0, 0.1)',       # Yellow
    'Sport': 'rgba(255, 255, 0, 0.1)',       # Yellow
    'Brake': 'rgba(255, 0, 0, 0.1)',         # Red
    'Throw': 'rgba(255, 165, 0, 0.1)',       # Orange

    # --- PX4 特有模式补充 ---
    'Mission': 'rgba(0, 255, 0, 0.1)',       # Green (对应 Auto)
    'Offboard': 'rgba(255, 0, 255, 0.1)',    # Magenta (对应 Guided)
    'Stabilized': 'rgba(255, 165, 0, 0.1)',  # Orange (对应 Stabilize)
    'Position': 'rgba(0, 0, 255, 0.1)',      # Blue (对应 PosHold)
    'Takeoff': 'rgba(255, 165, 0, 0.1)',     # Orange (起飞阶段)
    'Hold': 'rgba(0, 0, 255, 0.1)',          # Blue (保持)
    'Follow': 'rgba(0, 255, 255, 0.1)',      # Cyan (跟随)
    'Precland': 'rgba(255, 0, 0, 0.1)',      # Red (精密降落)
    'Orbit': 'rgba(255, 0, 255, 0.1)',       # Magenta (盘旋)
    'Descend': 'rgba(255, 0, 0, 0.2)',       # Red (下降/故障保护)
    'Rattitude': 'rgba(255, 165, 0, 0.1)',   # Orange
    'Termination': 'rgba(0, 0, 0, 0.5)',     # Black (停机)
}
# --- 页面配置 ---
st.set_page_config(
    page_title="UAV Insight Toolkit",
    page_icon="✈️",
    layout="wide"
)

# ---  AI 侧边栏配置逻辑 ---
st.sidebar.title("✈️ UAV Log Analysis")


# 1. 定义弹窗函数 (使用 @st.dialog 装饰器 - Streamlit 1.34+)
@st.dialog("🚫 API Key 验证失败")
def show_error_dialog(error_type, error_msg):
    st.error(f"错误类型: {error_type}")
    st.markdown(f"**详细信息:**\n\n{error_msg}")
    st.info("请检查 Key 是否复制完整，或网络是否通畅。")
    if st.button("知道了"):
        st.rerun()


def get_raw_curve(df, col_name):
    """
    只保留数值发生变化的时刻，消除 ffill 带来的'阶梯/方波'效应
    """
    # 1. 计算差分，找出值发生变化的行
    # fillna(1) 是为了保留第一个点 (diff是NaN)
    mask = df[col_name].diff().fillna(1) != 0
    return df[mask]

# 2. 定义验证函数
def verify_key(key):
    """验证 Key 的格式和有效性"""
    key = key.strip()

    # 检查 1: 是否为空
    if not key:
        return False, "EmptyError", "输入框是空的！请粘贴您的 API Key。"

    # 检查 2: 格式 (智谱Key通常较长且包含点号)
    if len(key) < 20:
        return False, "FormatError", "Key 的长度似乎不够，您可能只复制了一部分。"

    # 检查 3: 尝试建立一个真实的连接 (轻量级测试)
    try:
        # 尝试初始化客户端 (不消耗 token，只检查连通性)
        client = ZhipuAiClient(api_key=key)
        # 这里我们不做实际请求，只要 Client 初始化没报错，格式基本是对的
        return True, "Success", key
    except Exception as e:
        return False, "ConnectionError", f"SDK 初始化失败: {str(e)}"

def add_flight_mode_background(fig, df):
    """
    给 Plotly 图表添加飞行模式背景色块 (智能兼容 ArduPilot 和 PX4)
    """
    if 'mode' not in df.columns:
        return fig
    
    # --- 1. 定义翻译字典 ---
    # ArduCopter 标准映射
    MAP_ARDU = {
        0: 'Stabilize', 1: 'Acro', 2: 'AltHold', 3: 'Auto',
        4: 'Guided', 5: 'Loiter', 6: 'RTL', 7: 'Circle',
        9: 'Land', 11: 'Drift', 13: 'Sport', 14: 'Flip',
        15: 'AutoTune', 16: 'PosHold', 17: 'Brake', 18: 'Throw',
        19: 'Avoid_ADSB', 20: 'Guided_NoGPS', 21: 'Smart_RTL',
        22: 'FlowHold', 23: 'Follow',24: 'ZigZag',25: 'SystemID',  
        27: 'Auto_RTL',
        28: 'Turtle'    
    }
    
    # PX4 标准映射 (基于 vehicle_status.nav_state)
    MAP_PX4 = {
            0: 'Manual',  1: 'AltHold',  2: 'PosHold', 3: 'Mission', 4: 'Loiter', 
            5: 'RTL', 6: 'Acro', 7: 'Offboard',8: 'Stabilized',  9: 'Rattitude',
            10: 'Takeoff',  11: 'Land',12: 'Descend', 13: 'Termination',14: 'Follow',   
            15: 'Precland',16: 'Orbit', 17: 'Takeoff',18: 'Land',19: 'Follow', 20: 'Precland',  
            22: 'Orbit'      
        }

    # --- 2. 智能切换字典 ---
    # 默认用 Ardu
    mode_map = MAP_ARDU
    # 如果检测到 firmware 列是 PX4，则切换到 PX4 字典
    if 'firmware' in df.columns and df['firmware'].iloc[0] == 'PX4':
        mode_map = MAP_PX4

    # --- 3. 数据处理 ---
    df_mode = df[['timestamp', 'mode']].dropna().reset_index(drop=True)
    if df_mode.empty:
        return fig

    df_mode['mode_group'] = (df_mode['mode'] != df_mode['mode'].shift()).cumsum()
    groups = df_mode.groupby('mode_group')
    
    for _, group in groups:
        start_t = group['timestamp'].min()
        end_t = group['timestamp'].max()
        raw_val = group['mode'].iloc[0]
        
        # --- 4. 数字转名字 ---
        try:
            mode_id = int(float(raw_val))
            mode_name = mode_map.get(mode_id, f"Mode {mode_id}")
        except:
            mode_name = str(raw_val).strip()

        # --- 5. 颜色匹配 ---
        # 优先全字匹配
        color = MODE_COLORS.get(mode_name, None)
        
        # 其次首字母大写匹配
        if color is None:
            color = MODE_COLORS.get(mode_name.capitalize(), None)
            
        if color is None:
            up_name = mode_name.upper()
            if 'MANUAL' in up_name: color = MODE_COLORS.get('Manual')
            elif 'MISSION' in up_name: color = MODE_COLORS.get('Auto')     # 绿色
            elif 'OFFBOARD' in up_name: color = MODE_COLORS.get('Guided')   # 粉/紫色
            elif 'POSITION' in up_name: color = MODE_COLORS.get('PosHold')  # 蓝色
            elif 'STABILIZED' in up_name: color = MODE_COLORS.get('Stabilize')
            elif 'RTL' in up_name or 'RETURN' in up_name: color = MODE_COLORS.get('RTL')
            elif 'LAND' in up_name: color = MODE_COLORS.get('Land')
            else:
                color = 'rgba(200, 200, 200, 0.1)' # 实在找不到就灰色

        # --- 6. 绘图 ---
        fig.add_vrect(
            x0=start_t, x1=end_t,
            fillcolor=color,
            opacity=1,
            layer="below",
            line_width=0,
            annotation_text=mode_name,
            annotation_position="top left",
            annotation_font_size=12,
            annotation_font_color="black"
        )
    return fig
    """
    给 Plotly 图表添加飞行模式背景色块 (内置数字转名字映射)
    """
    if 'mode' not in df.columns:
        return fig
    
    # --- 1. 定义数字到名字的映射表 (ArduCopter 标准) ---
    MODE_MAPPING = {
        0: 'Stabilize', 1: 'Acro', 2: 'AltHold', 3: 'Auto',
        4: 'Guided', 5: 'Loiter', 6: 'RTL', 7: 'Circle',
        9: 'Land', 11: 'Drift', 13: 'Sport', 14: 'Flip',
        15: 'AutoTune', 16: 'PosHold', 17: 'Brake', 18: 'Throw',
        19: 'Avoid_ADSB', 20: 'Guided_NoGPS', 21: 'Smart_RTL',
        22: 'FlowHold', 23: 'Follow',24: 'ZigZag',25: 'SystemID',  
        27: 'Auto_RTL',28: 'Turtle'    
    }

    # 提取模式并清洗
    df_mode = df[['timestamp', 'mode']].dropna().reset_index(drop=True)
    if df_mode.empty:
        return fig

    # 2. 分段
    df_mode['mode_group'] = (df_mode['mode'] != df_mode['mode'].shift()).cumsum()
    groups = df_mode.groupby('mode_group')
    
    for _, group in groups:
        start_t = group['timestamp'].min()
        end_t = group['timestamp'].max()
        
        # --- 3. 核心修复：把数字转成名字 ---
        raw_val = group['mode'].iloc[0]
        
        # 尝试转成整数去查表
        try:
            mode_id = int(float(raw_val)) # 处理可能出现的 "4.0" 字符串
            # 查表，查不到就显示 "Mode 4"
            mode_name = MODE_MAPPING.get(mode_id, f"Mode {mode_id}") 
        except:
            # 如果本身就是字符串名字，就直接用
            mode_name = str(raw_val).strip()

        # --- 4. 匹配颜色 ---
        color_key = mode_name.capitalize() 
        
        # 备选颜色逻辑：如果字典里没有，但名字里带关键字，也给颜色
        color = MODE_COLORS.get(mode_name, None) # 先精准匹配
        if color is None:
            color = MODE_COLORS.get(color_key, 'rgba(200, 200, 200, 0.1)') # 再首字母大写匹配
        
        # --- 5. 绘图 ---
        fig.add_vrect(
            x0=start_t, x1=end_t,
            fillcolor=color,
            opacity=1,
            layer="below",
            line_width=0,
            annotation_text=mode_name,     # 这里会显示 "Guided" 而不是 "4"
            annotation_position="top left",
            annotation_font_size=12,
            annotation_font_color="black"  # 黑色字体
        )
    return fig
    """
    给 Plotly 图表添加飞行模式背景色块
    """
    if 'mode' not in df.columns:
            return fig
        
    # --- 1. 定义数字到名字的映射表 (ArduCopter 标准) ---
    # 如果你是固定翼或小车，这个表可能需要微调，但 4 和 9 通常是通用的
    MODE_MAPPING = {
        0: 'Stabilize', 1: 'Acro', 2: 'AltHold', 3: 'Auto',
        4: 'Guided', 5: 'Loiter', 6: 'RTL', 7: 'Circle',
        9: 'Land', 11: 'Drift', 13: 'Sport', 14: 'Flip',
        15: 'AutoTune', 16: 'PosHold', 17: 'Brake', 18: 'Throw',
        20: 'Guided_NoGPS', 21: 'Smart_RTL'
    }
    
    # 1. 提取模式并清洗
    df_mode = df[['timestamp', 'mode']].dropna().reset_index(drop=True)
    if df_mode.empty:
        return fig

    # [调试] 在侧边栏显示我们解析到了哪些模式，帮你找原因
    # 这样你就能看到是 "STABILIZE" 还是 "0" 还是 "Unknown"
    with st.sidebar.expander("🛠️ 调试: 飞行模式列表"):
        unique_modes = df_mode['mode'].unique()
        st.write(unique_modes)

    # 2. 分段
    df_mode['mode_group'] = (df_mode['mode'] != df_mode['mode'].shift()).cumsum()
    groups = df_mode.groupby('mode_group')
    
    for _, group in groups:
        start_t = group['timestamp'].min()
        end_t = group['timestamp'].max()
        # 确保转大写，去除空格
        raw_mode = str(group['mode'].iloc[0]).strip()

        # 如果你的 MODE_COLORS 里的 key 是 "Stabilize" 这种首字母大写的：
        mode_name = raw_mode.capitalize()
        
        # 获取颜色，默认灰色
        color = MODE_COLORS.get(mode_name, 'rgba(200, 200, 200, 0.1)')
        
        # 3. 添加背景矩形
        fig.add_vrect(
            x0=start_t, x1=end_t,
            fillcolor=color,
            opacity=1,
            layer="below",
            line_width=0,
            # 强制显示文字
            annotation_text="TEST-" + mode_name,
            annotation_position="top left", # 尝试放在左上角
            annotation_font_size=12,
            annotation_font_color="black"   # 强制黑色字体，防止灰色背景看不清
        )
    return fig

# 3. AI 配置区域
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 AI 配置")

# 使用 st.form 隔离输入框，回车不会刷新
with st.sidebar.form(key="apikey_form"):
    # 从 session_state 获取默认值
    default_val = st.session_state.get("zhipu_api_key", "")

    user_input_key = st.text_input(
        "🔑 请输入/粘贴 GLM API Key",
        value=default_val,
        type="password",
        help="粘贴后请点击下方的确认按钮"
    )

    # 确认按钮
    submit_button = st.form_submit_button("✅ 确认并验证 Key")

# 处理按钮点击逻辑
if submit_button:
    is_valid, err_type, result = verify_key(user_input_key)

    if is_valid:
        st.session_state.zhipu_api_key = result
        st.sidebar.success("🎉 验证成功！Key 已保存。")
        time.sleep(0.5)
        st.rerun()
    else:
        show_error_dialog(err_type, result)

# 获取最终可用的 Key
api_key = st.session_state.get("zhipu_api_key", "")

# 显示当前状态
if api_key:
    st.sidebar.caption(f"当前状态: ✅ 已加载 (尾号 {api_key[-4:]})")
else:
    st.sidebar.caption("当前状态: ⚪ 未配置")

# --- 日志文件选择逻辑 ---
st.sidebar.markdown("---")
st.sidebar.subheader("📂 日志加载")

# 方式 1: 直接上传
uploaded_file = st.sidebar.file_uploader("点击上传日志 (.bin / .ulg)", type=["bin", "ulg"])

# 方式 2: 扫描 exe 旁边的 data 文件夹
st.sidebar.markdown("**或选择 data/ 目录下的文件:**")
data_dir = os.path.join(base_dir, 'data')
if not os.path.exists(data_dir):
    log_files = []
else:
    log_files = [f for f in os.listdir(data_dir) if f.endswith('.bin') or f.endswith('.ulg')]

selected_from_folder = st.sidebar.selectbox(
    "从列表中选择:",
    options=log_files,
    index=0 if log_files else None,
    label_visibility="collapsed"
)

# --- 统一文件入口逻辑 ---
target_path = None

if uploaded_file is not None:
    # 动态获取原始文件的后缀名 (.bin 或 .ulg)
    # 这样 load_data 才能正确识别并调用 PX4Parser
    file_ext = os.path.splitext(uploaded_file.name)[1]

    # 默认兜底
    if not file_ext:
        file_ext = ".bin"

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        target_path = tmp_file.name
    st.sidebar.success(f"已加载: {uploaded_file.name}")

elif selected_from_folder:
    target_path = os.path.join(data_dir, selected_from_folder)


# --- 主界面 ---
st.title("无人机飞行数据分析看板")

if target_path:
    st.write(f"正在分析日志 ...")


    # 1. 解析数据函数
    @st.cache_data
    def load_data(path):
        if path.endswith('.ulg'):
            parser = PX4Parser(path)
            df = parser.get_dataframe()
            # [关键] 强制打上 PX4 标签，后续绘图函数会根据这个标签切换字典
            df['firmware'] = 'PX4' 
        else:
            parser = ArduPilotParser(path)
            df = parser.get_dataframe()
            # [关键] 打上 Ardu 标签
            df['firmware'] = 'Ardu'
        return df


    def generate_ai_prompt(df):
            """
            不再只按时间间隔采样，而是优先保留：模式切换点、震动峰值点、姿态误差峰值点。
            """
            # --- 1. 准备映射字典 ---
            # ArduPilot
            MAP_ARDU = {
                0: 'Stabilize', 1: 'Acro', 2: 'AltHold', 3: 'Auto', 4: 'Guided', 
                5: 'Loiter', 6: 'RTL', 7: 'Circle', 9: 'Land', 
                16: 'PosHold', 17: 'Brake', 21: 'Smart_RTL', 23: 'Follow'
            }
            # PX4
            MAP_PX4 = {
                0: 'Manual',  1: 'AltHold',  2: 'PosHold', 3: 'Mission', 4: 'Loiter', 
                5: 'RTL', 6: 'Acro', 7: 'Offboard',8: 'Stabilized',  9: 'Rattitude',
                10: 'Takeoff',  11: 'Land',12: 'Descend', 13: 'Termination',14: 'Follow',   
                15: 'Precland',16: 'Orbit', 17: 'Takeoff',18: 'Land',19: 'Follow', 20: 'Precland',  
                22: 'Orbit'   
            }

            # 确定固件类型
            is_px4 = False
            if 'firmware' in df.columns and df['firmware'].iloc[0] == 'PX4':
                is_px4 = True
            
            target_map = MAP_PX4 if is_px4 else MAP_ARDU

            # --- 2. 智能关键帧抽取 (Smart Resampling) ---
            # 目标：凑够约 30-40 行数据
            indices = set()
            
            # A. 必选：模式切换的时刻 (Mode Switches)
            # shift(1) 比较前后两行，不一样的就是切换点
            mode_change_indices = df.index[df['mode'] != df['mode'].shift(1)].tolist()
            indices.update(mode_change_indices)
            # B. 必选：震动最大的前 3 个时刻 (Vibration Peaks)
            if 'vibe_x' in df:
                vibe_peak_indices = df['vibe_x'].nlargest(3).index.tolist()
                indices.update(vibe_peak_indices)
            # C. 必选：姿态误差最大的前 3 个时刻 (PID Error Peaks)
            # 如果有期望值和实际值，计算差值并找最大
            if 'rate_roll' in df and 'rate_roll_des' in df:
                # 计算临时的误差列
                err_series = (df['rate_roll_des'] - df['rate_roll']).abs()
                err_peak_indices = err_series.nlargest(3).index.tolist()
                indices.update(err_peak_indices)
            # D. 补充：基础时间轴 (Base Timeline)
            # 为了保持时间连贯性，无论发生什么，每隔 5% 的进度取一个点
            step = max(1, len(df) // 15) # 约取 15 个均匀点
            uniform_indices = df.iloc[::step].index.tolist()
            indices.update(uniform_indices)
            # E. 必选：起飞和结束
            indices.add(df.index[0])
            indices.add(df.index[-1])
            # --- 3. 整理采样数据 ---
            # 将所有索引排序，去除重复，提取数据
            sorted_indices = sorted(list(indices))
            sampled_df = df.loc[sorted_indices].copy()
            # 计算相对时间
            start_time = df['timestamp'].min()
            sampled_df['t_rel'] = sampled_df['timestamp'] - start_time
            # --- 4. 生成文本报告 ---
            duration = df['timestamp'].max() - df['timestamp'].min()
            max_alt = df['relative_alt'].max() if 'relative_alt' in df else 0
            summary = "【1. 飞行概况】\n"
            summary += f"- 固件: {'PX4' if is_px4 else 'ArduPilot'}\n"
            summary += f"- 时长: {duration:.1f}s | 高度: {max_alt:.1f}m\n"
            
            if 'vibe_x' in df:
                max_v = df['vibe_x'].max()
                summary += f"- 最大震动: {max_v:.2f} (阈值30)\n"

            summary += "\n【2. 关键事件快照 (智能抽取)】\n"
            summary += "说明: 此表已自动筛选出 [模式切换]、[最大震动]、[最大误差] 的时刻。\n"
            summary += "Time(s) | Mode       | Alt(m) | Roll(°) | Vibe(m/s²) | Event/Reason\n"
            summary += "--------|------------|--------|---------|------------|-------------\n"

            last_mode = None
            
            for idx, row in sampled_df.iterrows():
                # A. 基础数据格式化
                t = f"{row['t_rel']:.1f}"
                
                # 模式名解析
                raw_mode = row['mode']
                try:
                    mode_id = int(float(raw_mode))
                    mode_str = target_map.get(mode_id, f"M{mode_id}")
                except:
                    mode_str = str(raw_mode).strip()
                mode_disp = mode_str[:8].ljust(10)
                
                alt = f"{row['relative_alt']:.1f}".rjust(6) if 'relative_alt' in row else "   0.0"
                roll = f"{row['roll']:.1f}".rjust(7) if 'roll' in row else "    0.0"
                vibe = f"{row['vibe_x']:.1f}".rjust(10) if 'vibe_x' in row else "       0.0"
                
                # B. 智能标注原因 (为什么这一行被选进来了？)
                reasons = []
                
                # 原因1: 模式切换
                if last_mode is not None and mode_str != last_mode:
                    reasons.append(f"🔄Switch")
                last_mode = mode_str
                
                # 原因2: 震动过大 (例如超过25) 或 接近全场最大值
                if 'vibe_x' in df:
                    if row['vibe_x'] > 25: reasons.append("⚠️HighVibe")
                    # 如果这个点的索引在刚才计算的震动峰值列表里
                    if idx in vibe_peak_indices: reasons.append("📈MaxVibe")

                # 原因3: 误差过大 (如果刚才算了误差)
                if 'rate_roll' in df and idx in err_peak_indices:
                    reasons.append("❌MaxErr")

                # 如果没特殊原因，就是时间轴采样
                event_mark = " ".join(reasons) if reasons else "⏱️Timer"

                summary += f"{t.ljust(7)} | {mode_disp} | {alt} | {roll} | {vibe} | {event_mark}\n"

            return summary


    try:
        df_raw = load_data(target_path)

        if df_raw.empty:
            st.error("日志解析为空，请检查文件内容。")
        else:
            # --- 2. 数据清洗 ---
            df_clean = df_raw.set_index('timestamp').ffill().reset_index()
            if 'alt' in df_clean.columns:
                home_alt = df_clean['alt'].iloc[:50].mean()
                df_clean['relative_alt'] = df_clean['alt'] - home_alt

            elif 'loc_z' in df_clean.columns:
                start_z = df_clean['loc_z'].iloc[:50].mean()
                df_clean['relative_alt'] = -(df_clean['loc_z'] - start_z)

            else:
                df_clean['relative_alt'] = 0

            # --- 3. 关键指标 ---
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("飞行时长", f"{df_clean['timestamp'].max() - df_clean['timestamp'].min():.1f} s")
            with col2:
                max_rel_alt = df_clean['relative_alt'].max()
                st.metric("最大相对高度", f"{max_rel_alt:.1f} m")
            with col3:
                st.metric("数据点总数", len(df_clean))

            # --- 4. 绘图区域 ---
            tab1, tab2, tab3, tab4 = st.tabs(["📈 姿态分析", "🌍 3D 轨迹", "⚠️ 震动诊断", "🔧 PID 调优"])
            with tab1:
                st.subheader("姿态响应分析 (Attitude)")
                if 'roll' in df_clean.columns:
                    fig_att = px.line(
                        df_clean,
                        x='timestamp',
                        y=['roll', 'pitch'],
                        labels={'value': '角度 (deg)', 'timestamp': '时间 (s)'}
                    )
                    add_flight_mode_background(fig_att, df_clean)
                    st.plotly_chart(fig_att, use_container_width=True)
                else:
                    st.warning("未检测到姿态数据")

                    # --- [更新] Tab 2: 定位综合分析 ---
            with tab2:
                # 逻辑: 优先画 GPS，如果没有 GPS 但有局部位置(光流/IMU)，则画局部轨迹
                st.subheader("1. 3D 飞行轨迹")
                if 'lat' in df_clean.columns and 'lon' in df_clean.columns:
                    st.caption("数据源: Global GPS (WGS84)")
                    df_traj = df_clean.iloc[::10, :]
                    fig_traj = px.scatter_3d(
                        df_traj,
                        x='lat', y='lon', z='relative_alt',
                        color='relative_alt',
                        size_max=5, opacity=0.7,
                        title="GPS 3D 轨迹",
                        height=800
                    )
                    st.plotly_chart(fig_traj, use_container_width=True)
                elif 'loc_x' in df_clean.columns and 'loc_y' in df_clean.columns:
                    st.caption("数据源: Local Position NED (Local Frame)")
                    st.info("💡 未检测到 GPS，正在显示基于 NED 坐标系的局部轨迹 (例如光流/视觉定位)。")

                    df_traj = df_clean.iloc[::10, :]
                    # 绘制局部轨迹
                    fig_traj = px.scatter_3d(
                        df_traj,
                        x='loc_x', y='loc_y', z='relative_alt',
                        color='relative_alt',
                        size_max=5, opacity=0.7,
                        title="Local NED 轨迹 (无 GPS)",
                        height=800
                    )
                    st.plotly_chart(fig_traj, use_container_width=True)

                else:
                    st.warning("⚠️ 未检测到位置数据 (GPS 或 Local Position)。无法绘制轨迹。")

                # --- 第二部分: 光流传感器分析 ---
                st.markdown("---")  # 分割线
                st.subheader("2. 光流/室内定位分析 (Optical Flow)")

                # 检查是否存在光流数据 (基于 px4_parser 解析的字段)
                if 'flow_quality' in df_clean.columns:

                    # 布局：左边看质量，右边看流量
                    col_flow_1, col_flow_2 = st.columns(2)

                    with col_flow_1:
                        st.markdown("**信号质量 (Quality)**")
                        st.caption("范围 0-255。低于 100 通常无法定点。")

                        # [修改] 使用去重后的数据画图
                        df_qual_raw = get_raw_curve(df_clean, 'flow_quality')

                        fig_qual = px.line(
                            df_qual_raw, x='timestamp', y='flow_quality',
                            title="Optical Flow Quality",
                            labels={'flow_quality': '质量值'}
                        )
                        fig_qual.add_hline(y=100, line_dash="dash", line_color="orange",
                                           annotation_text="可用阈值 (100)")
                        st.plotly_chart(fig_qual, use_container_width=True)

                    with col_flow_2:
                        st.markdown("**累计流量 (Integrated Flow)**")
                        st.caption("单位: rad。用于判断水平移动趋势。")

                        flow_cols = [c for c in ['flow_x', 'flow_y'] if c in df_clean.columns]
                        if flow_cols:
                            # [修改] 对每一列分别处理可能会麻烦，这里直接对 flow_x 去重采样即可
                            # 因为 flow_x 和 flow_y 通常是同时更新的
                            df_flow_raw = get_raw_curve(df_clean, 'flow_x')

                            fig_flow = px.line(
                                df_flow_raw, x='timestamp', y=flow_cols,
                                title="Flow Integral X/Y",
                                labels={'value': '累计流量 (rad)'}
                            )
                            st.plotly_chart(fig_flow, use_container_width=True)
                        else:
                            st.info("未检测到流量数据")
                else:
                    # 如果不是 PX4 光流日志，显示提示信息
                    st.info(
                        "ℹ️ 当前日志未检测到光流数据 (Optical Flow)")
            with tab3:
                st.subheader("机身震动水平 (Vibration Levels)")
                has_vibe_data = 'vibe_x' in df_clean.columns
                has_clip_data = 'clip_0' in df_clean.columns

                if has_vibe_data:
                    st.markdown("""
                    **判断标准 (参考 ArduPilot Wiki):**
                    - ✅ **正常:** < 15 m/s²
                    - ⚠️ **警告:** 15 - 30 m/s²
                    - ❌ **危险:** > 30 m/s²
                    """)

                    fig_vibe = px.line(
                        df_clean,
                        x='timestamp',
                        y=['vibe_x', 'vibe_y', 'vibe_z'],
                        title="三轴震动均值",
                        labels={'value': '震动值 (m/s²)', 'timestamp': '时间 (s)'}
                    )
                    fig_vibe.add_hline(y=30, line_dash="dash", line_color="red", annotation_text="危险阈值")
                    fig_vibe.add_hline(y=15, line_dash="dash", line_color="orange", annotation_text="警告阈值")
                    add_flight_mode_background(fig_vibe, df_clean)
                    st.plotly_chart(fig_vibe, use_container_width=True)

                    if has_clip_data:
                        cols = ['clip_0', 'clip_1', 'clip_2']
                        valid_cols = [c for c in cols if c in df_clean.columns]
                        if valid_cols:
                            total_clips = df_clean[valid_cols].max().sum()
                            if total_clips > 0:
                                st.error(f"🚨 检测到传感器削顶 (Clipping): {total_clips} 次。建议检查减震。")
                            else:
                                st.success("✅ 传感器工作正常，未检测到削顶 (No Clipping)。")
                    else:
                        st.info("ℹ️ 当前日志不包含 Clipping 记录字段。")
                else:
                    st.warning("⚠️ 当前日志未包含震动数据 (VIBE 消息)。")
            with tab4:
                st.subheader("角速度响应分析 (Rate Controller)")

                # 检查是否有数据
                if 'rate_roll' in df_clean.columns:
                    st.markdown("""
                    **如何分析：**
                    - 🔴 **红色线 (Desired):** 飞控“想要”达到的转速。
                    - 🔵 **蓝色线 (Actual):** 无人机“实际”的转速。
                    - **完美状态：** 红蓝两线完全重合。
                    - **滞后：** 蓝线总是在红线后面 -> 需增大 P 或 I。
                    - **震荡：** 蓝线在红线上下剧烈抖动 -> 需减小 P 或 D。
                    """)

                    # 1. 选择轴向 (Radio Button)
                    axis = st.radio("选择分析轴向:", ["Roll (横滚)", "Pitch (俯仰)", "Yaw (航向)"], horizontal=True)

                    # 2. 准备绘图数据
                    if "Roll" in axis:
                        y_cols = ['rate_roll_des', 'rate_roll']
                        title = "Roll Rate: Desired vs Actual"
                        # 计算当前轴的误差
                        mae = (df_clean['rate_roll_des'] - df_clean['rate_roll']).abs().mean()
                    elif "Pitch" in axis:
                        y_cols = ['rate_pitch_des', 'rate_pitch']
                        title = "Pitch Rate: Desired vs Actual"
                        mae = (df_clean['rate_pitch_des'] - df_clean['rate_pitch']).abs().mean()
                    else:
                        y_cols = ['rate_yaw_des', 'rate_yaw']
                        title = "Yaw Rate: Desired vs Actual"
                        mae = (df_clean['rate_yaw_des'] - df_clean['rate_yaw']).abs().mean()

                    # 显示误差指标
                    st.metric(f"{axis.split()[0]} 平均跟踪误差 (MAE)", f"{mae:.2f} deg/s")

                    # 3. 绘制交互式图表
                    # 这里的技巧是指定颜色 map，让 Desired 永远是红色，Actual 永远是蓝色
                    color_map = {y_cols[0]: 'red', y_cols[1]: 'blue'}

                    fig_pid = px.line(
                        df_clean,
                        x='timestamp',
                        y=y_cols,
                        title=title,
                        color_discrete_map=color_map,  # 固定颜色
                        labels={'value': '角速度 (deg/s)', 'timestamp': '时间 (s)', 'variable': '信号'}
                    )

                    # 允许局部缩放
                    fig_pid.update_traces(line=dict(width=1.5))
                    add_flight_mode_background(fig_pid, df_clean)
                    st.plotly_chart(fig_pid, use_container_width=True)

                else:
                    st.warning("⚠️ 当前日志未包含 RATE 消息。请检查飞控参数 LOG_BITMASK。")
            # --- [AI 智能分析模块] ---
            st.markdown("---")
            st.subheader("🤖 AI 飞行诊断 (Powered by GLM-4.5)")

            col_ai_1, col_ai_2 = st.columns([1, 2])

            with col_ai_1:
                st.info("📊 **发送给 AI 的数据摘要:**")
                prompt_summary = generate_ai_prompt(df_clean)
                st.code(prompt_summary, language="text")

            with col_ai_2:
                if st.button("🚀 开始 AI 诊断"):
                    if not api_key:
                        st.error("请先在侧边栏配置并验证 API Key！")
                    else:
                        try:
                            # 1. 占位符策略：先创建一个空容器
                            response_container = st.empty()
                            response_container.info("🧠 GLM-4.5 正在阅读时序数据并进行推理，请稍候...")

                            client = ZhipuAiClient(api_key=api_key)

                            messages = [
                                {"role": "system",
                                 "content": """你是一位专业的无人机飞控专家。用户会提供一份包含“统计摘要”和“时序趋势快照”的飞行数据。
                                    请基于这些数据进行深度推理，而不仅仅是复述数字。
                                    分析要求：
                                    1. **结合时空上下文**：分析震动峰值发生的时间点。
                                    2. **关联分析**：观察“飞行趋势快照”，看震动变大时，姿态（Roll）或高度（Alt）是否有剧烈变化？
                                    3. **给出专业判断**。
                                    请输出格式清晰的诊断报告。"""},
                                {"role": "user", "content": prompt_summary}
                            ]

                            full_response = ""

                            # 3. 发起请求
                            response = client.chat.completions.create(
                                model="glm-4.5-flash",
                                messages=messages,
                                thinking={
                                    "type": "disabled",  # bu启用深度思考模式
                                },
                                stream=True,
                                max_tokens=4096,
                                temperature=0.7
                            )

                            # 4. 流式接收
                            for chunk in response:
                                if chunk.choices and chunk.choices[0].delta.content:
                                    content = chunk.choices[0].delta.content
                                    full_response += content
                                    response_container.markdown(full_response + "▌")

                            response_container.markdown(full_response)

                        except Exception as e:
                            response_container.error(f"AI 分析请求失败: {e}")

    except Exception as e:
        st.error(f"解析出错: {e}")
        st.code(str(e))

else:
    st.info("请在左侧选择一个日志文件开始分析。")