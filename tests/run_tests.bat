@echo off
rem Run the headless test suite. Pass a Blender executable as the first argument.
setlocal
set BLENDER=%~1
if "%BLENDER%"=="" set BLENDER=blender

"%BLENDER%" --background --factory-startup --python "%~dp0run_tests.py"
set CODE=%ERRORLEVEL%
echo.
echo Exit code: %CODE%
exit /b %CODE%
