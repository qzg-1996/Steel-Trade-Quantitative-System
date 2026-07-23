@echo off
cd /d %~dp0
echo [Step 1/2] Installing components, first run takes 5-10 min ...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo Install failed, check network and retry.
    pause
    exit /b
)
echo [Step 2/2] Starting Web UI ...
echo Browser will open http://localhost:8501
streamlit run app.py --server.headless true
pause
