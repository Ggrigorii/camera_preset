@echo off
rem Validate and build the extension. Pass a Blender executable as the first argument.
setlocal
set BLENDER=%~1
if "%BLENDER%"=="" set BLENDER=blender

set ROOT=%~dp0..
echo Using: %BLENDER%

"%BLENDER%" --command extension validate "%ROOT%\camera_preset_manager" || goto :error
"%BLENDER%" --command extension build --source-dir "%ROOT%\camera_preset_manager" --output-dir "%ROOT%\dist" || goto :error

echo.
echo Built package is in %ROOT%\dist
exit /b 0

:error
echo Build failed.
exit /b 1
