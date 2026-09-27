Unicode True
ManifestDPIAware True
RequestExecutionLevel user
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "nsDialogs.nsh"

!define APP_NAME "DCC - Docker Control Center"
!define APP_EXE "DockerControlCenter.exe"
!define REPO_BUILDER_EXE "DCCRepoBuilder.exe"
!define APP_ID "DockerControlCenter"
!define APP_PUBLISHER "Hattimon"
!define APP_VERSION "1.3.9"
!define START_MENU_DIR "DCC"

Name "${APP_NAME}"
OutFile "..\release\DockerControlCenter-Setup.exe"
InstallDir "$LocalAppData\Programs\${APP_ID}"
InstallDirRegKey HKCU "Software\${APP_ID}" "InstallDir"
BrandingText "${APP_NAME}"
Icon "icon.ico"
UninstallIcon "icon.ico"
ShowInstDetails show
ShowUninstDetails show

Var UpdateMode
Var CloseAttempts
Var LaunchDccCheckbox

Page directory
Page instfiles
Page custom LaunchDccPage LaunchDccLeave
UninstPage uninstConfirm
UninstPage instfiles

Function CheckDccProcesses
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -Command "if (Get-Process -Name DockerControlCenter,DCCRepoBuilder -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"'
  Pop $0
  Pop $1
  Push $0
FunctionEnd

Function RequestGracefulClose
  DetailPrint "Requesting graceful close of DCC processes."
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -Command "Get-Process -Name DockerControlCenter,DCCRepoBuilder -ErrorAction SilentlyContinue | ForEach-Object { [void]$$_.CloseMainWindow() }"'
  Pop $0
  Pop $1
FunctionEnd

Function WaitForDccClose
  StrCpy $CloseAttempts 0
wait_for_dcc_close:
  Call CheckDccProcesses
  Pop $0
  StrCmp $0 "0" processes_closed
  IntOp $CloseAttempts $CloseAttempts + 1
  IntCmp $CloseAttempts 30 wait_a_bit close_failed close_failed
wait_a_bit:
  Sleep 500
  Goto wait_for_dcc_close
processes_closed:
  Push "0"
  Return
close_failed:
  Push "1"
FunctionEnd

Function .onInit
  StrCpy $UpdateMode "0"
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} "$0" "/DCCUPDATE=" $1
  ${IfNot} ${Errors}
    StrCmp $1 "1" 0 +2
      StrCpy $UpdateMode "1"
  ${EndIf}

  ; Older 1.3.8 updaters launch the staged installer without command-line
  ; arguments. Their handoff script is a marker that this is an update.
  StrCmp $UpdateMode "1" update_mode_silent
  ClearErrors
  FindFirst $R0 $R1 "$EXEDIR\dcc-update-handoff*.ps1"
  IfErrors update_mode_check_done
  FindClose $R0
  StrCmp $R1 "" update_mode_check_done
  StrCpy $UpdateMode "1"
update_mode_check_done:
  StrCmp $UpdateMode "1" 0 check_running
update_mode_silent:
  SetSilent silent

check_running:
  Call CheckDccProcesses
  Pop $0
  StrCmp $0 "0" init_done
  IfSilent silent_close interactive_close

interactive_close:
  System::Call 'kernel32::GetUserDefaultUILanguage() i .r2'
  IntCmp $2 1045 close_prompt_pl close_prompt_en close_prompt_en
close_prompt_pl:
  MessageBox MB_ICONEXCLAMATION|MB_OKCANCEL|MB_DEFBUTTON1 "DCC jest obecnie uruchomione. Aplikacja musi zostać zamknięta przed instalacją lub aktualizacją. Zamknąć DCC i kontynuować?" IDOK do_close IDCANCEL init_cancel
  Goto init_cancel
close_prompt_en:
  MessageBox MB_ICONEXCLAMATION|MB_OKCANCEL|MB_DEFBUTTON1 "DCC is currently running. The application must be closed before installation or update. Close DCC and continue?" IDOK do_close IDCANCEL init_cancel

silent_close:
do_close:
  Call RequestGracefulClose
  Call WaitForDccClose
  Pop $0
  StrCmp $0 "0" init_done
  IfSilent init_cancel close_retry

close_retry:
  System::Call 'kernel32::GetUserDefaultUILanguage() i .r2'
  IntCmp $2 1045 close_retry_pl close_retry_en close_retry_en
close_retry_pl:
  MessageBox MB_ICONEXCLAMATION|MB_RETRYCANCEL "Nie udało się zamknąć DCC. Wybierz Ponów po zamknięciu aplikacji albo Anuluj instalację." IDRETRY check_running IDCANCEL init_cancel
  Goto init_cancel
close_retry_en:
  MessageBox MB_ICONEXCLAMATION|MB_RETRYCANCEL "DCC could not be closed. Select Retry after closing the application, or Cancel installation." IDRETRY check_running IDCANCEL init_cancel

init_cancel:
  Abort

init_done:
FunctionEnd

Section "Install"
  SetOutPath "$InstDir"
  File "/oname=${APP_EXE}" "..\dist\DockerControlCenter.exe"
  File "/oname=${REPO_BUILDER_EXE}" "..\dist\DCCRepoBuilder.exe"
  SetOutPath "$PLUGINSDIR"
  File "..\packaging\windows\set_shortcut_app_id.ps1"
  SetOutPath "$InstDir"

  ; Runtime self-checks are executed on the exact PyInstaller binaries by the
  ; build pipeline. Do not start one-file EXEs from inside NSIS while replacing
  ; an installed version because antivirus/temp extraction can race _MEI files.
  IfFileExists "$InstDir\${APP_EXE}" app_payload_ready
    MessageBox MB_ICONSTOP "Docker Control Center executable was not installed correctly. Installation cannot continue."
    Abort
app_payload_ready:
  IfFileExists "$InstDir\${REPO_BUILDER_EXE}" repo_builder_payload_ready
    MessageBox MB_ICONSTOP "DCC Repo Builder executable was not installed correctly. Installation cannot continue."
    Abort
repo_builder_payload_ready:

  ${If} ${RunningX64}
    IfFileExists "$WINDIR\Sysnative\OpenSSH\ssh.exe" openssh_ready
  ${EndIf}
  IfFileExists "$SYSDIR\OpenSSH\ssh.exe" openssh_ready
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

  ; Remove only DCC-owned legacy shortcuts during an upgrade. User-created and
  ; pinned shortcuts are not deleted or rebuilt.
  Delete "$SMPROGRAMS\Docker Control Center\Docker Control Center.lnk"
  Delete "$SMPROGRAMS\Docker Control Center\DCC Repo Builder.lnk"
  Delete "$SMPROGRAMS\Docker Control Center\Uninstall DCC.lnk"
  RMDir "$SMPROGRAMS\Docker Control Center"
  Delete "$DESKTOP\Docker Control Center.lnk"

  CreateDirectory "$SMPROGRAMS\${START_MENU_DIR}"
  Delete "$SMPROGRAMS\${START_MENU_DIR}\DCC - Docker Control Center.lnk"
  Delete "$SMPROGRAMS\${START_MENU_DIR}\DCC Repo Builder.lnk"
  Delete "$SMPROGRAMS\${START_MENU_DIR}\Uninstall DCC.lnk"
  CreateShortcut "$SMPROGRAMS\${START_MENU_DIR}\DCC - Docker Control Center.lnk" "$InstDir\${APP_EXE}" "" "$InstDir\${APP_EXE}" 0
  CreateShortcut "$SMPROGRAMS\${START_MENU_DIR}\DCC Repo Builder.lnk" "$InstDir\${REPO_BUILDER_EXE}" "" "$InstDir\${REPO_BUILDER_EXE}" 0
  CreateShortcut "$SMPROGRAMS\${START_MENU_DIR}\Uninstall DCC.lnk" "$InstDir\Uninstall.exe" "" "$InstDir\Uninstall.exe" 0
  Delete "$DESKTOP\DCC - Docker Control Center.lnk"
  CreateShortcut "$DESKTOP\DCC - Docker Control Center.lnk" "$InstDir\${APP_EXE}" "" "$InstDir\${APP_EXE}" 0

  ClearErrors
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\set_shortcut_app_id.ps1" -MainShortcut "$SMPROGRAMS\${START_MENU_DIR}\DCC - Docker Control Center.lnk" -MainAppId "Hattimon.DCC" -RepoShortcut "$SMPROGRAMS\${START_MENU_DIR}\DCC Repo Builder.lnk" -RepoAppId "Hattimon.DCC.RepoBuilder" -LogPath "$InstDir\shortcut-appids.log"' $0
  IfErrors shortcut_ids_helper_launch_failed
  IntCmp $0 0 shortcut_ids_ready shortcut_ids_failed shortcut_ids_failed
  Goto shortcut_ids_ready
shortcut_ids_helper_launch_failed:
  StrCpy $0 -1
  Goto shortcut_ids_failed
shortcut_ids_failed:
  DetailPrint "WARNING: Shortcut AppUserModelIDs could not be assigned (exit code $0). Installation will continue."
  FileOpen $1 "$InstDir\shortcut-appids.log" a
  IfErrors shortcut_ids_warning_message
  FileWrite $1 "NSIS: shortcut identity helper failed with exit code $0.$\r$\n"
  FileClose $1
shortcut_ids_warning_message:
  System::Call 'kernel32::GetUserDefaultUILanguage() i .r2'
  IntCmp $2 1045 shortcut_ids_warning_pl shortcut_ids_warning_en shortcut_ids_warning_en
shortcut_ids_warning_pl:
  MessageBox MB_ICONEXCLAMATION "Skróty utworzono, ale system Windows nie przypisał im identyfikatorów aplikacji. Instalacja będzie kontynuowana. Szczegóły zapisano w pliku shortcut-appids.log."
  Goto shortcut_ids_ready
shortcut_ids_warning_en:
  MessageBox MB_ICONEXCLAMATION "The shortcuts were created, but Windows could not assign their application identities. Installation will continue. Details are in shortcut-appids.log."
shortcut_ids_ready:
  Delete "$PLUGINSDIR\set_shortcut_app_id.ps1"

  ; Non-destructive shell refresh for shortcut/icon metadata.
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'

  StrCmp $UpdateMode "1" launch_after_install
  Goto install_done

launch_after_install:
  Exec '"$InstDir\${APP_EXE}"'

install_done:
SectionEnd

Function LaunchDccPage
  StrCmp $UpdateMode "1" launch_page_done
  IfSilent launch_page_done
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  System::Call 'kernel32::GetUserDefaultUILanguage() i .r2'
  IntCmp $2 1045 launch_label_pl launch_label_en launch_label_en
launch_label_pl:
  ${NSD_CreateCheckbox} 0 0 100% 12u "Uruchom DCC"
  Goto launch_checkbox_ready
launch_label_en:
  ${NSD_CreateCheckbox} 0 0 100% 12u "Launch DCC"
launch_checkbox_ready:
  Pop $LaunchDccCheckbox
  ${NSD_Check} $LaunchDccCheckbox
  nsDialogs::Show
  Return
launch_page_done:
  Abort
FunctionEnd

Function LaunchDccLeave
  ${NSD_GetState} $LaunchDccCheckbox $0
  ${If} $0 == ${BST_CHECKED}
    Exec '"$InstDir\${APP_EXE}"'
  ${EndIf}
FunctionEnd

Section "Uninstall"
  Delete "$DESKTOP\DCC - Docker Control Center.lnk"
  Delete "$DESKTOP\Docker Control Center.lnk"
  Delete "$SMPROGRAMS\${START_MENU_DIR}\DCC - Docker Control Center.lnk"
  Delete "$SMPROGRAMS\${START_MENU_DIR}\DCC Repo Builder.lnk"
  Delete "$SMPROGRAMS\${START_MENU_DIR}\Uninstall DCC.lnk"
  RMDir "$SMPROGRAMS\${START_MENU_DIR}"
  Delete "$SMPROGRAMS\Docker Control Center\Docker Control Center.lnk"
  Delete "$SMPROGRAMS\Docker Control Center\DCC Repo Builder.lnk"
  RMDir "$SMPROGRAMS\Docker Control Center"

  Delete "$InstDir\${APP_EXE}"
  Delete "$InstDir\${REPO_BUILDER_EXE}"
  Delete "$InstDir\Uninstall.exe"
  RMDir "$InstDir"

  DeleteRegKey HKCU "Software\${APP_ID}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
