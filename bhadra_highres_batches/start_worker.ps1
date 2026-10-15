param(
    [ValidateSet('cpu','cuda','auto')][string]$Device = 'cpu',
    [switch]$Resume
)
$ErrorActionPreference = 'Stop'
$batchRoot = $PSScriptRoot
$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
$logDirectory = Join-Path $batchRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$workerArguments = @('-u', 'worker.py', 'run', '--device', $Device)
if ($Resume) { $workerArguments += '--resume' }
$batchProcess = Start-Process -FilePath $pythonExecutable -ArgumentList $workerArguments -WorkingDirectory $batchRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory "$runStamp.stdout.log") -RedirectStandardError (Join-Path $logDirectory "$runStamp.stderr.log") -PassThru
Write-Output "Worker process $($batchProcess.Id). Logs: $logDirectory. The exclusive worker lock rejects duplicate launches."
