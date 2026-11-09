@echo off
rem Run the headless test suite in an isolated profile.
rem Pass a Blender executable as the first argument.
setlocal
set BLENDER=%~1
if "%BLENDER%"=="" set BLENDER=blender

set "PROFILE=%TEMP%\camera_preset_manager_tests"
if not exist "%PROFILE%\extensions" mkdir "%PROFILE%\extensions"
set "BLENDER_USER_RESOURCES=%PROFILE%"

"%BLENDER%" --background --factory-startup --python "%~dp0run_tests.py"
set CODE=%ERRORLEVEL%
echo.
echo Profile: %PROFILE%
echo Exit code: %CODE%
exit /b %CODE%
