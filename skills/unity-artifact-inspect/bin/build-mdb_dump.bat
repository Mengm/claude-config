@echo off
REM Build unity_lmdb_dump.exe from Unity's vendored OpenLDAP LMDB sources.
REM Output: %~dp0unity_lmdb_dump.exe
REM
REM Requires MSVC. Run from any cmd; this script sources vcvars64.bat itself.

setlocal
set "VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
set "SRC=F:\jnunity-2022-310\External\LMDB"
set "OUT=%~dp0"

if not exist "%VCVARS%" (
  echo ERROR: vcvars64.bat not found at "%VCVARS%"
  echo Edit this script to point at your MSVC install.
  exit /b 1
)
if not exist "%SRC%\mdb.c" (
  echo ERROR: LMDB sources not found at "%SRC%"
  exit /b 1
)

call "%VCVARS%" >nul || ( echo vcvars64 failed & exit /b 1 )

pushd "%OUT%"

echo Building unity_lmdb_dump.exe...
cl /nologo /O2 /MT /W2 /D_CRT_SECURE_NO_WARNINGS /Fe:unity_lmdb_dump.exe ^
   /I"%SRC%" ^
   unity_lmdb_dump.c "%SRC%\mdb.c" "%SRC%\midl.c" ^
   ntdll.lib advapi32.lib /link /INCREMENTAL:NO
if errorlevel 1 ( echo build failed & popd & exit /b 1 )

del /q *.obj 2>nul

echo.
echo Built:
dir /b unity_lmdb_dump.exe

popd
endlocal
