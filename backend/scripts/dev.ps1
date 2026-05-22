# 开发环境启动脚本（Windows PowerShell）
# 使用方式: .\scripts\dev.ps1

Set-Location $PSScriptRoot\..
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8800
