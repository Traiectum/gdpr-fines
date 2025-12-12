@echo off
setlocal enabledelayedexpansion

cd /d C:\GDPR-Fines

set "LOG=C:\GDPR-Fines\run_update.log"
echo ================================ >> "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo Working dir: %CD% >> "%LOG%"

echo [STEP] Python start >> "%LOG%"
py fetch_et.py >> "%LOG%" 2>&1
echo [STEP] Python done, exit=%ERRORLEVEL% >> "%LOG%"

if not exist "gdpr_fines_quarterly_last4.csv" (
  echo ERROR: gdpr_fines_quarterly_last4.csv not created. >> "%LOG%"
  goto :END
)

echo [STEP] Copy to current start >> "%LOG%"
if not exist "current" mkdir "current"
copy /y "gdpr_fines_quarterly_last4.csv" "current\gdpr_fines_current.csv" >> "%LOG%" 2>&1
echo [STEP] Copy to current done, exit=%ERRORLEVEL% >> "%LOG%"

echo [STEP] Git start >> "%LOG%"
set "GIT=C:\Program Files\Git\bin\git.exe"
if not exist "%GIT%" set "GIT=git"

echo Git cmd: %GIT% >> "%LOG%"
"%GIT%" --version >> "%LOG%" 2>&1
echo [STEP] Git version done, exit=%ERRORLEVEL% >> "%LOG%"

echo [STEP] Repo check >> "%LOG%"
if not exist ".git" (
  echo ERROR: Not a git repo (missing .git). >> "%LOG%"
  goto :END
)

echo [STEP] git status BEFORE >> "%LOG%"
"%GIT%" status >> "%LOG%" 2>&1

echo [STEP] git add -A >> "%LOG%"
"%GIT%" add -A >> "%LOG%" 2>&1
echo [STEP] git add done, exit=%ERRORLEVEL% >> "%LOG%"

echo [STEP] git status AFTER add >> "%LOG%"
"%GIT%" status >> "%LOG%" 2>&1

echo [STEP] diff cached >> "%LOG%"
"%GIT%" diff --cached --quiet
set "DIFFCODE=%ERRORLEVEL%"
echo diff --cached exit code: !DIFFCODE! >> "%LOG%"

if "!DIFFCODE!"=="0" (
  echo No changes to commit. >> "%LOG%"
) else (
  echo [STEP] commit >> "%LOG%"
  "%GIT%" commit -m "Weekly update GDPR fines" >> "%LOG%" 2>&1
  echo Commit exit code: !ERRORLEVEL! >> "%LOG%"
)

echo [STEP] push >> "%LOG%"
"%GIT%" push >> "%LOG%" 2>&1
echo Push exit code: !ERRORLEVEL! >> "%LOG%"

:END
echo Done. >> "%LOG%"

REM Keep window open when double-clicking so you can see errors immediately
pause
endlocal
