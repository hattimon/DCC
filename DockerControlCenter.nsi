Unicode True
ManifestDPIAware True
RequestExecutionLevel user

!define APP_NAME "Docker Control Center"
!define APP_EXE "DockerControlCenter.exe"
!define APP_ID "DockerControlCenter"
!define APP_PUBLISHER "Docker Control Center"
!define APP_VERSION "1.1.0"

Name "${APP_NAME}"
OutFile "release\DockerControlCenter-Setup.exe"
InstallDir "$LocalAppData\Programs\${APP_ID}"
InstallDirRegKey HKCU "Software\${APP_ID}" "InstallDir"
BrandingText "${APP_NAME}"
Icon "icon.ico"
UninstallIcon "icon.ico"
ShowInstDetails show
ShowUninstDetails show

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$InstDir"
  File "/oname=${APP_EXE}" "dist\DockerControlCenter.exe"

  WriteRegStr HKCU "Software\${APP_ID}" "InstallDir" "$InstDir"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayIcon" "$InstDir\${APP_EXE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "InstallLocation" "$InstDir"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString" '"$InstDir\Uninstall.exe"'
  WriteUninstaller "$InstDir\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$InstDir\${APP_EXE}"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$InstDir\${APP_EXE}"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  Delete "$InstDir\${APP_EXE}"
  Delete "$InstDir\Uninstall.exe"
  RMDir "$InstDir"

  DeleteRegKey HKCU "Software\${APP_ID}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
SectionEnd





