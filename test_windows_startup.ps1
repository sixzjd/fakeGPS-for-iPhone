$ErrorActionPreference = 'Stop'

Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class FakeGpsWindowProbe {
  private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr extra);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);

  public static string FindVisibleWindow(uint targetPid) {
    string result = null;
    EnumWindows((hWnd, extra) => {
      uint pid;
      GetWindowThreadProcessId(hWnd, out pid);
      if (pid == targetPid && IsWindowVisible(hWnd)) {
        var title = new StringBuilder(512);
        GetWindowText(hWnd, title, title.Capacity);
        result = hWnd.ToString() + "|" + title.ToString();
        return false;
      }
      return true;
    }, IntPtr.Zero);
    return result;
  }
}
'@

$root = (Resolve-Path (Join-Path $PSScriptRoot 'dist\FakeGPS')).Path
$exe = Join-Path $root 'FakeGPS.exe'
$runtimeDll = Join-Path $root '_internal\pythonnet\runtime\Python.Runtime.dll'
$logs = Join-Path $root 'startup-test'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

if (-not (Test-Path $exe)) {
  throw "Packaged executable not found: $exe"
}
if (-not (Test-Path $runtimeDll)) {
  throw "Packaged Python.NET runtime not found: $runtimeDll"
}

$dlls = @(Get-ChildItem -Path $root -Recurse -Filter 'Python.Runtime.dll' -File)
if ($dlls.Count -ne 1 -or $dlls[0].FullName -ne (Resolve-Path $runtimeDll).Path) {
  $dlls | ForEach-Object { Write-Host "Python.Runtime.dll: $($_.FullName)" }
  throw "Expected exactly one Python.Runtime.dll at _internal\pythonnet\runtime"
}

Write-Host "Checking packaged Python.Runtime.Loader.Initialize"
python (Join-Path $PSScriptRoot 'check_pythonnet_runtime.py') $runtimeDll

$stdout = Join-Path $logs 'stdout.log'
$stderr = Join-Path $logs 'stderr.log'
$process = Start-Process -FilePath $exe -WorkingDirectory $root -PassThru `
  -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
  # WebView2 can create the native window several seconds after the frozen
  # process starts. Poll throughout the required 10-second smoke window so a
  # slow hosted runner is not mistaken for a GUI startup failure.
  $window = $null
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) {
      Write-Host "FakeGPS.exe exited after $($process.ExitTime - $process.StartTime). Exit code: $($process.ExitCode)"
      if (Test-Path $stdout) { Get-Content $stdout }
      if (Test-Path $stderr) { Get-Content $stderr }
      throw 'FakeGPS.exe exited during the 10-second startup smoke test'
    }
    $window = [FakeGpsWindowProbe]::FindVisibleWindow([uint32]$process.Id)
    if (-not [string]::IsNullOrWhiteSpace($window)) { break }
  }
  if ([string]::IsNullOrWhiteSpace($window)) {
    if (Test-Path $stdout) { Get-Content $stdout }
    if (Test-Path $stderr) { Get-Content $stderr }
    throw 'FakeGPS.exe stayed alive but did not create a visible Windows GUI window'
  }
  Write-Host "FakeGPS.exe created a visible window ($window) and remained alive for 10 seconds; startup smoke test passed."
}
finally {
  if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()
  }
}
