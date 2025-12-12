@echo off
setlocal

cd /d C:\GDPR-Fines

REM Logfile
set LOG=C:\GDPR-Fines\run_update.log
echo ================================ >> "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo Working dir: %CD% >> "%LOG%"

REM --- Python ---
set "PY=C:\Users\hidde\AppData\Local\Microsoft\WindowsApps\python.exe"
echo Python: %PY% >> "%LOG%"
"%PY%" fetch_et.py >> "%LOG%" 2>&1
echo Python exit code: %ERRORLEVEL% >> "%LOG%"

REM --- Git ---
set GIT="C:\Program Files\Git\bin\git.exe"
if exist %GIT% (
  echo Git: %GIT% >> "%LOG%"
) else (
  echo Git not found at %GIT% >> "%LOG%"
  echo Trying git from PATH... >> "%LOG%"
  set GIT=git
)

%GIT% --version >> "%LOG%" 2>&1

%GIT% status >> "%LOG%" 2>&1
%GIT% add gdpr_fines_quarterly_last4.csv >> "%LOG%" 2>&1

REM Commit only if there are changes
%GIT% diff --cached --quiet
if %ERRORLEVEL%==0 (
  echo No changes to commit. >> "%LOG%"
) else (
  %GIT% commit -m "Weekly update GDPR fines" >> "%LOG%" 2>&1
  echo Commit exit code: %ERRORLEVEL% >> "%LOG%"
)

%GIT% push >> "%LOG%" 2>&1
echo Push exit code: %ERRORLEVEL% >> "%LOG%"

echo Done. >> "%LOG%"
endlocal
