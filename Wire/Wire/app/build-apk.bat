@echo off
setlocal
cd /d "%~dp0"
echo.
echo === Wire: build Android APK (hybrid app) ===
echo Needs: Node 18+, JDK 17 and the Android SDK (ANDROID_HOME set).

where node >nul 2>nul || ( echo Node.js not found - install from https://nodejs.org & pause & exit /b 1 )
where java >nul 2>nul || ( echo JDK 17 not found - install it and set JAVA_HOME & pause & exit /b 1 )
if not defined ANDROID_HOME if not defined ANDROID_SDK_ROOT ( echo Set ANDROID_HOME to your Android SDK folder & pause & exit /b 1 )

if not exist ".env.production" (
  echo.
  set /p WIRE_URL=Your Render API address, e.g. https://wire-api.onrender.com : 
  echo %WIRE_URL%| findstr /b /i "https://" >nul || ( echo The address must start with https:// & pause & exit /b 1 )
  >".env.production" echo VITE_API_URL=%WIRE_URL%
)

call npm install || ( echo npm install failed & pause & exit /b 1 )
call npm run build || ( echo web build failed & pause & exit /b 1 )

if not exist "android" (
  call npx cap add android || ( echo cap add android failed & pause & exit /b 1 )
)
node scripts\patch-android.mjs || ( pause & exit /b 1 )
call npx cap sync android || ( echo cap sync failed & pause & exit /b 1 )

pushd android
call gradlew.bat assembleDebug || ( popd & echo Gradle build failed & pause & exit /b 1 )
popd

copy /y "android\app\build\outputs\apk\debug\app-debug.apk" "Wire.apk" >nul
echo.
echo Done: %cd%\Wire.apk  (copy it to your phone and install)
pause
