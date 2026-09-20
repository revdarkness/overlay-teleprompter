@echo off
title Overlay Teleprompter - Setup
echo.
echo  Creating your Teleprompter shortcuts...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Create-Shortcut.ps1"
