@echo off
cd /d "C:\Users\HP\Desktop\AI"
npm install docx --silent 2>&1
if errorlevel 1 (
    echo Failed to install docx
    exit /b 1
)
node build_roadmap.js
echo.
if exist "CS_AI_Engine_Startup_Roadmap.docx" (
    for %%F in ("CS_AI_Engine_Startup_Roadmap.docx") do (
        echo Document created successfully
        echo File size: %%~zF bytes
    )
) else (
    echo Failed to create document
    exit /b 1
)
