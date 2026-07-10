; ============================================================
;  Home Bar POS — NSIS Installer Script
;  Builds a single HomeBarPOS_Setup.exe from dist\HomeBarPOS\
;
;  Requirements:
;    1. Run build_exe.bat first (creates dist\HomeBarPOS\)
;    2. Install NSIS from https://nsis.sourceforge.io/Download
;    3. Right-click this .nsi file → "Compile NSIS script"
;       OR let build_exe.bat call makensis automatically.
; ============================================================

!define APP_NAME    "Home Bar POS"
!define APP_EXE     "HomeBarPOS.exe"
!define APP_DIR     "HomeBarPOS"
!define OUTPUT_FILE "HomeBarPOS_Setup.exe"
!define INSTALL_DIR "$PROGRAMFILES\HomeBarPOS"
!define REG_KEY     "Software\Microsoft\Windows\CurrentVersion\Uninstall\HomeBarPOS"

Name "${APP_NAME}"
OutFile "${OUTPUT_FILE}"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor lzma

; ---- Pages ----
Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

; ---- Install ----
Section "Install"
    SetOutPath "$INSTDIR"

    ; Copy everything from dist\HomeBarPOS\ into the install directory
    File /r "dist\${APP_DIR}\*.*"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr   HKLM "${REG_KEY}" "DisplayName"      "${APP_NAME}"
    WriteRegStr   HKLM "${REG_KEY}" "UninstallString"  "$INSTDIR\Uninstall.exe"
    WriteRegStr   HKLM "${REG_KEY}" "InstallLocation"  "$INSTDIR"
    WriteRegStr   HKLM "${REG_KEY}" "DisplayVersion"   "2.0"
    WriteRegDWORD HKLM "${REG_KEY}" "NoModify"         1
    WriteRegDWORD HKLM "${REG_KEY}" "NoRepair"         1

    ; Desktop shortcut
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
                   "$INSTDIR\${APP_EXE}" "" \
                   "$INSTDIR\${APP_EXE}" 0

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" \
                    "$INSTDIR\${APP_EXE}" 0
    CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                    "$INSTDIR\Uninstall.exe"

    MessageBox MB_OK "Home Bar POS installed!$\n$\nA shortcut has been added to your Desktop and Start Menu.$\nDouble-click it to launch."
SectionEnd

; ---- Uninstall ----
Section "Uninstall"
    ; Remove install directory (but NOT the instance\ folder — that's the database)
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    ; Leave $INSTDIR\instance\ intact so the database survives uninstall

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    ; Remove registry keys
    DeleteRegKey HKLM "${REG_KEY}"

    MessageBox MB_OK "Home Bar POS uninstalled.$\n$\nYour database (instance\bar_pos.db) was kept at:$\n$LOCALAPPDATA\HomeBarPOS\instance\"
SectionEnd
