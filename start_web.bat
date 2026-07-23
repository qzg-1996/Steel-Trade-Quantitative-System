@echo off
cd /d %~dp0
echo Starting Steel Quant Web UI ...
echo Browser will open http://localhost:8501
streamlit run app.py --server.headless true
pause
