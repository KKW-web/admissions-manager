@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "ADMISSIONS_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%ADMISSIONS_PY%" (
 "%ADMISSIONS_PY%" launch.py
 goto done
)
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
 py -3 launch.py
 goto done
)
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
 python launch.py
 goto done
)
echo Python 실행 환경을 찾지 못했습니다. Python 3.10 이상 설치가 필요합니다.
:done
if errorlevel 1 echo 실행이 중단되었습니다. 위 오류 내용을 확인하세요.
pause
