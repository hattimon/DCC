Unicode True
ManifestDPIAware True
RequestExecutionLevel user
!include "LogicLib.nsh"
!include "x64.nsh"

!define APP_NAME "Docker Control Center"
!define APP_EXE "DockerControlCenter.exe"
!define REPO_BUILDER_EXE "DCCRepoBuilder.exe"
!define APP_ID "DockerControlCenter"
!define APP_PUBLISHER "Docker Control Center"
!define APP_VERSION "1.3.9"

Name "${APP_NAME}"
OutFile "..\release\DockerControlCenter-Setup.exe"
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
  File "/oname=${APP_EXE}" "..\dist\DockerControlCenter.exe"
  File "/oname=${REPO_BUILDER_EXE}" "..\dist\DCCRepoBuilder.exe"

  ; The build pipeline already executes --self-check on the exact EXE before
  ; NSIS packages it. Running a PyInstaller one-file binary again immediately
  ; after extraction can race with AV/temp scanning of _MEI\python312.dll and
  ; produce a false installation failure. Verify the installed payload exists
  ; here and leave runtime validation to the pre-package build check.
  IfFileExists "$InstDir\${APP_EXE}" app_payload_ready
    MessageBox MB_ICONSTOP "Docker Control Center executable was not installed correctly. Installation cannot continue."
    Abort
app_payload_ready:
  IfFileExists "$InstDir\${REPO_BUILDER_EXE}" repo_builder_payload_ready
    MessageBox MB_ICONSTOP "DCC Repo Builder executable was not installed correctly. Installation cannot continue."
    Abort
repo_builder_payload_ready:

  ; The internal SSH backend uses Paramiko, while interactive terminal actions
  ; use the Windows OpenSSH client. A 32-bit NSIS process can be redirected away
  ; from the real 64-bit System32 directory, so check Sysnative explicitly.
  ${If} ${RunningX64}
    IfFileExists "$WINDIR\Sysnative\OpenSSH\ssh.exe" openssh_ready
  ${EndIf}
  IfFileExists "$SYSDIR\OpenSSH\ssh.exe" openssh_ready

  ; Interactive installs may elevate and install the Windows capability. Silent
  ; updates must never wait forever on a hidden MessageBox/UAC prompt.
  IfSilent openssh_missing_silent openssh_missing_interactive

openssh_missing_interactive:
  MessageBox MB_ICONINFORMATION "Windows OpenSSH Client is missing. Windows will ask for administrator approval to install this required terminal dependency."
  ExecShellWait "runas" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -Command "Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0"' SW_HIDE $2
  ${If} ${RunningX64}
    IfFileExists "$WINDIR\Sysnative\OpenSSH\ssh.exe" openssh_ready
  ${EndIf}
  IfFileExists "$SYSDIR\OpenSSH\ssh.exe" openssh_ready
  MessageBox MB_ICONEXCLAMATION "OpenSSH Client could not be installed. DCC will still work with its built-in SSH connection engine, but opening an interactive SSH terminal may be unavailable."
  Goto openssh_done

openssh_missing_silent:
  DetailPrint "OpenSSH Client is missing; silent update continues without an elevation prompt."
  Goto openssh_done

openssh_ready:
  DetailPrint "OpenSSH Client detected."

openssh_done:

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
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\DCC Repo Builder.lnk" "$InstDir\${REPO_BUILDER_EXE}"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$InstDir\${APP_EXE}"

  IfSilent install_done
  MessageBox MB_ICONINFORMATION|MB_OK "Docker Control Center ${APP_VERSION} was installed successfully."
install_done:
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\DCC Repo Builder.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  Delete "$InstDir\${APP_EXE}"
  Delete "$InstDir\${REPO_BUILDER_EXE}"
  Delete "$InstDir\Uninstall.exe"
  RMDir "$InstDir"

  DeleteRegKey HKCU "Software\${APP_ID}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
SectionEnd
