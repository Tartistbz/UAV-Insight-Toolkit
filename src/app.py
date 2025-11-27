import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys
import tempfile
import shutil

# --- 路径黑魔法 (适配 IDE 和 EXE) ---
if getattr(sys, 'frozen', False):
    # 如果是打包后的 exe，根目录应该是 exe 所在的文件夹
    # 这样用户只要在 exe 旁边建一个 data 文件夹，程序就能读到
    base_dir = os.path.dirname(sys.executable)
    # 临时解压目录 (用于寻找内部的 analyzer 包)
    internal_root = sys._MEIPASS
    sys.path.append(os.path.join(internal_root, 'src')) # 确保能 import
else:
    # 正常 IDE 运行
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(base_dir)

from src.analyzer.ardu_parser import ArduPilotParser

# --- 页面配置 ---
st.set_page_config(
    page_title="UAV Insight Toolkit",
    page_icon="✈️",
    layout="wide"
)

# --- 侧边栏逻辑 ---
st.sidebar.title("✈️ UAV Log Analysis")

# 方式 1: 直接上传
uploaded_file = st.sidebar.file_uploader("📂 方法一: 点击上传日志 (.bin)", type=["bin"])

# 方式 2: 扫描 exe 旁边的 data 文件夹
st.sidebar.markdown("---")
st.sidebar.markdown("📂 **方法二: 选择 data/ 目录下的文件**")

data_dir = os.path.join(base_dir, 'data')
if not os.path.exists(data_dir):
    log_files = []
else:
    log_files = [f for f in os.listdir(data_dir) if f.endswith('.bin')]

selected_from_folder = st.sidebar.selectbox(
    "从列表中选择:",
    options=log_files,
    index=0 if log_files else None,
    help="请在 exe 文件旁边新建一个名为 data 的文件夹，放入日志后重启软件即可看到。"
)

# --- 统一文件入口逻辑 ---
target_path = None

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        target_path = tmp_file.name
    st.sidebar.success(f"已加载上传文件: {uploaded_file.name}")

elif selected_from_folder:
    target_path = os.path.join(data_dir, selected_from_folder)
# --- 主界面 ---
st.title("无人机飞行数据分析看板")

if target_path:
    st.write(f"正在分析日志 ...")


    # 1. 解析数据
    # 使用缓存装饰器，避免每次刷新页面都重新读文件
    @st.cache_data
    def load_data(path):
        parser = ArduPilotParser(path)
        return parser.get_dataframe()


    try:
        df_raw = load_data(target_path)

        if df_raw.empty:
            st.error("日志解析为空，请检查文件内容。")
        else:
            # --- 2. 数据清洗  ---
            # 使用前向填充 (ffill) 填补 NaN，让 GPS 和 ATT 数据在时间轴上对齐
            df_clean = df_raw.set_index('timestamp').ffill().reset_index()
            # 模拟 GLOBAL_POSITION_INT 的 relative_alt 计算
            if 'alt' in df_clean.columns:
                # 1. 找到起飞点的海拔 (Home Altitude)
                home_alt = df_clean['alt'].iloc[:50].mean()

                # 2. 计算相对高度 (单位: 米)
                df_clean['relative_alt'] = df_clean['alt'] - home_alt
            else:
                df_clean['relative_alt'] = 0
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("飞行时长", f"{df_clean['timestamp'].max() - df_clean['timestamp'].min():.1f} s")
            with col2:
                max_alt = df_clean['alt'].max() if 'alt' in df_clean else 0
                st.metric("最大高度 (Rel)", f"{max_alt:.1f} m")
            with col3:
                st.metric("数据点总数", len(df_clean))

            # --- 4. 绘图区域 ---
            tab1, tab2, tab3 = st.tabs(["📈 姿态分析", "🌍 3D 轨迹", "⚠️ 震动诊断"])

            with tab1:
                st.subheader("姿态响应分析 (Attitude)")
                if 'roll' in df_clean.columns:
                    fig_att = px.line(
                        df_clean,
                        x='timestamp',
                        y=['roll', 'pitch'],
                        labels={'value': '角度 (deg)', 'timestamp': '时间 (s)'}
                    )
                    st.plotly_chart(fig_att, use_container_width=True)
                else:
                    st.warning("未检测到姿态数据")

            with tab2:
                st.subheader("3D 飞行轨迹 (Relative Alt)")
                if 'lat' in df_clean.columns and 'lon' in df_clean.columns:
                    # 降采样防止卡顿
                    df_traj = df_clean.iloc[::10, :]
                    fig_traj = px.scatter_3d(
                        df_traj,
                        x='lat', y='lon', z='relative_alt',
                        color='relative_alt',
                        size_max=5,
                        opacity=0.7
                    )
                    st.plotly_chart(fig_traj, use_container_width=True)
                else:
                    st.warning("未检测到 GPS 数据")

            with tab3:
                st.subheader("机身震动水平 (Vibration Levels)")

                # 只有当 clip_0 在列名中时，才去计算 max()，否则会报 KeyError
                has_vibe_data = 'vibe_x' in df_clean.columns
                has_clip_data = 'clip_0' in df_clean.columns

                if has_vibe_data:
                    st.markdown("""
                    **判断标准 (参考 ArduPilot Wiki):**
                    - ✅ **正常:** < 15 m/s²
                    - ⚠️ **警告:** 15 - 30 m/s²
                    - ❌ **危险:** > 30 m/s²
                    """)

                    # 1. 绘制震动曲线
                    fig_vibe = px.line(
                        df_clean,
                        x='timestamp',
                        y=['vibe_x', 'vibe_y', 'vibe_z'],
                        title="三轴震动均值",
                        labels={'value': '震动值 (m/s²)', 'timestamp': '时间 (s)'}
                    )
                    fig_vibe.add_hline(y=30, line_dash="dash", line_color="red", annotation_text="危险阈值")
                    fig_vibe.add_hline(y=15, line_dash="dash", line_color="orange", annotation_text="警告阈值")
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
                    st.warning("⚠️ 当前日志未包含震动数据 (VIBE 消息)。可能是飞控参数 LOG_BITMASK 未开启震动记录。")

    except Exception as e:
        st.error(f"解析出错: {e}")
        st.code(str(e))

else:
    st.info("请在左侧选择一个日志文件开始分析。")