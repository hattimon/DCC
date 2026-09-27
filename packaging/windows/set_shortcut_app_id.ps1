param(
    [Parameter(Mandatory = $true)][string]$MainShortcut,
    [Parameter(Mandatory = $true)][string]$MainAppId,
    [Parameter(Mandatory = $true)][string]$RepoShortcut,
    [Parameter(Mandatory = $true)][string]$RepoAppId,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'

function Write-ShortcutHelperLog([string]$Message) {
    if ([string]::IsNullOrWhiteSpace($LogPath)) {
        return
    }
    try {
        $directory = Split-Path -Parent $LogPath
        if ($directory -and -not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
        }
        $stamp = [DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss.fffZ')
        Add-Content -LiteralPath $LogPath -Value "[$stamp] $Message" -Encoding UTF8
    } catch {
        [Console]::Error.WriteLine("Could not write shortcut identity log: $($_.Exception.Message)")
    }
}

trap {
    $message = $_.Exception.ToString()
    Write-ShortcutHelperLog "ERROR: $message"
    [Console]::Error.WriteLine($message)
    exit 1
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

[StructLayout(LayoutKind.Sequential)]
public struct DccPropertyKey
{
    public Guid FormatId;
    public UInt32 PropertyId;
}

[StructLayout(LayoutKind.Explicit, Size = 16)]
public struct DccPropVariant
{
    [FieldOffset(0)] public UInt16 VariantType;
    [FieldOffset(8)] public IntPtr StringValue;
}

[ComImport]
[Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface DccIPropertyStore
{
    [PreserveSig] int GetCount(out UInt32 count);
    [PreserveSig] int GetAt(UInt32 index, out DccPropertyKey key);
    [PreserveSig] int GetValue(ref DccPropertyKey key, out DccPropVariant value);
    [PreserveSig] int SetValue(ref DccPropertyKey key, ref DccPropVariant value);
    [PreserveSig] int Commit();
}

public static class DccShortcutIdentity
{
    private static readonly Guid PropertyStoreId = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
    private static readonly DccPropertyKey AppUserModelIdKey = new DccPropertyKey
    {
        FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
        PropertyId = 5
    };

    public static void Set(string shortcutPath, string appId)
    {
        object link = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046")));
        DccIPropertyStore store = null;
        IntPtr unknown = IntPtr.Zero;
        IntPtr storePointer = IntPtr.Zero;
        IntPtr appIdPointer = IntPtr.Zero;
        try
        {
            IPersistFile persist = (IPersistFile)link;
            persist.Load(shortcutPath, 2);
            unknown = Marshal.GetIUnknownForObject(link);
            Guid propertyStoreId = PropertyStoreId;
            int queryResult = Marshal.QueryInterface(unknown, ref propertyStoreId, out storePointer);
            Marshal.ThrowExceptionForHR(queryResult);
            store = (DccIPropertyStore)Marshal.GetObjectForIUnknown(storePointer);
            DccPropVariant value = new DccPropVariant { VariantType = 31 };
            appIdPointer = Marshal.StringToCoTaskMemUni(appId);
            value.StringValue = appIdPointer;
            DccPropertyKey appUserModelIdKey = AppUserModelIdKey;
            Marshal.ThrowExceptionForHR(store.SetValue(ref appUserModelIdKey, ref value));
            Marshal.ThrowExceptionForHR(store.Commit());
            persist.Save(shortcutPath, true);
        }
        finally
        {
            if (appIdPointer != IntPtr.Zero) Marshal.FreeCoTaskMem(appIdPointer);
            if (store != null) Marshal.FinalReleaseComObject(store);
            if (storePointer != IntPtr.Zero) Marshal.Release(storePointer);
            if (unknown != IntPtr.Zero) Marshal.Release(unknown);
            if (link != null) Marshal.FinalReleaseComObject(link);
        }
    }
}
"@

[DccShortcutIdentity]::Set($MainShortcut, $MainAppId)
Write-ShortcutHelperLog "Assigned '$MainAppId' to '$MainShortcut'."
[DccShortcutIdentity]::Set($RepoShortcut, $RepoAppId)
Write-ShortcutHelperLog "Assigned '$RepoAppId' to '$RepoShortcut'."
