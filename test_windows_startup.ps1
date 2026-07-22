$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot 'dist\FakeGPS')).Path
$exe = Join-Path $root 'FakeGPS.exe'
$runtimeDll = Join-Path $root 'pythonnet\runtime\Python.Runtime.dll'
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
  throw "Expected exactly one Python.Runtime.dll at pythonnet\runtime"
}

Write-Host "Checking packaged Python.Runtime.Loader.Initialize"
python (Join-Path $PSScriptRoot 'check_pythonnet_runtime.py') $runtimeDll

$stdout = Join-Path $logs 'stdout.log'
$stderr = Join-Path $logs 'stderr.log'
$process = Start-Process -FilePath $exe -WorkingDirectory $root -PassThru `
  -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
  Start-Sleep -Seconds 10
  if ($process.HasExited) {
    Write-Host "FakeGPS.exe exited after $($process.ExitTime - $process.StartTime). Exit code: $($process.ExitCode)"
    if (Test-Path $stdout) { Get-Content $stdout }
    if (Test-Path $stderr) { Get-Content $stderr }
    throw 'FakeGPS.exe exited during the 10-second startup smoke test'
  }
  Write-Host 'FakeGPS.exe remained alive for 10 seconds; startup smoke test passed.'
}
finally {
  if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()
  }
}
