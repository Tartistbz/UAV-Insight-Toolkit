
# 🚁 UAV Insight Toolkit (AI-Powered)

![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![AI](https://img.shields.io/badge/AI-GLM--4.5-purple)
![Framework](https://img.shields.io/badge/Framework-Streamlit-red)

**UAV Insight Toolkit** is a comprehensive, open-source telemetry analysis and visualization platform designed for PX4 and ArduPilot drones. Built with Python and MAVLink, it bridges the gap between raw binary logs and actionable flight insights.

> **Core Value:** Provides engineers with an interactive dashboard to diagnose vibration issues, PID performance, and 3D flight trajectories instantly—now powered by **GLM-4.5 AI** for automated diagnostics.

## 📸 Dashboard Preview

![Dashboard Demo](assets/demo_screenshot.png)

## ✨ Key Features

### 🤖 AI Smart Diagnostics (AI Copilot)
* **Powered by GLM-4.5:** Integrated with ZhipuAI's latest Large Language Model via `zai-sdk` for real-time inference.
* **Time-Series Analysis:** Automatically downsamples flight logs to extract vibration peaks, altitude shifts, and attitude errors, generating a context-aware diagnostic report.
* **One-Click Checkup:** Automatically identifies issues like "Frame Resonance," "PID Oscillation," and "Sensor Clipping."

### 🔧 PID Tuning Analysis (Rate Controller)
* **Desired vs. Actual:** Overlays **Desired Rate** (Red) and **Actual Rate** (Blue) curves for Roll, Pitch, and Yaw axes.
* **Quantified Metrics:** Automatically calculates Mean Absolute Error (MAE) to quantify tracking performance.

### 📊 Multi-Dimensional Visualization
* **Interactive 3D Replay:** Visualizes flight paths with relative altitude encoding using Plotly 3D engines.
* **Vibration & Clipping:** Auto-detects dangerous vibration levels (>30m/s²) and counts sensor clipping events.

### ⚡ Modern Engineering Experience
* **Drag & Drop Upload:** Supports direct file uploads via the web UI or local scanning of the `data/` directory (EXE compatible).
* **Secure Configuration:** Built-in API Key validation with secure storage (session-based or local file), ensuring keys are never exposed.

## 🛠️ Tech Stack

* **Core Logic:** Python 3.9, Pymavlink (MAVLink Protocol Handling)
* **AI Engine:** ZhipuAI GLM-4.5-Flash (via `zai-sdk`)
* **Data Processing:** Pandas (Time-series alignment & forward-fill algorithms)
* **Visualization:** Streamlit (Web UI), Plotly (Interactive Charts)

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone [https://github.com/Tartistbz/UAV-Insight-Toolkit.git](https://github.com/Tartistbz/UAV-Insight-Toolkit.git)
cd UAV-Insight-Toolkit

# Create virtual environment (Recommended)
conda create -n uav-env python=3.9
conda activate uav-env

# Install dependencies
pip install -r requirements.txt
```

### 2. AI Configuration (Optional)

To use the AI Diagnostics feature, you need a ZhipuAI API Key.

1. Get your key from the [ZhipuAI Open Platform](https://bigmodel.cn/).
2. **Method A (GUI):** Enter the key in the sidebar and click "Verify".
3. **Method B (File):** Create a file named `apikey.txt` in the root directory and paste your key there (this file is Git-ignored).

### 3. Usage

Run the dashboard:

Bash

```
streamlit run src/app.py
```

The app will launch at `http://localhost:8501`. You can then drag and drop your `.bin` log files to start analysis.

## 📂 Project Structure

Plaintext

```
UAV-Insight-Toolkit/
├── data/               # Log storage (Git-ignored)
├── src/
│   ├── analyzer/       # Core Parsing Logic
│   │   ├── parser_base.py   # Abstract Base Class
│   │   └── ardu_parser.py   # ArduPilot Implementation
│   └── app.py          # Streamlit Dashboard Entry
├── requirements.txt    # Dependency Management
└── README.md           # Documentation
```

## 📝 Roadmap

- [x] Basic .bin Log Parsing
- [x] Attitude & 3D Trajectory Visualization
- [x] Vibration Level Diagnostics & Clipping Detection
- [x] **PID Analysis (Rate Roll/Pitch/Yaw)**
- [x] **AI Smart Diagnostics (GLM-4.5 Integration)**
- [x] File Upload & EXE Path Compatibility
- [ ] Export to CSV/MAT format
- [ ] PX4 .ulg Support

## 🤝 Contribution

Contributions are welcome! Please fork the repository and submit a Pull Request.

## 📄 License

Distributed under the GNU General Public License v3.0. See `LICENSE` for more information.