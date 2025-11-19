param(
  [int]    $Port      = 8080,
  [string] $BindHost  = "0.0.0.0",
  [string] $AppModule = "public_web:app",
  [string] $MainApp   = ".\main.py",
  [string] $PythonExe = "python",
  [string] $NgrokExe  = "ngrok"
)

$ErrorActionPreference = "Stop"

function Start-Child {
  param(
    [string]$FilePath,
    [string]$CmdLine   # <- NO usar $Args
  )
  Write-Host ("-> " + $FilePath + " " + $CmdLine)
  Start-Process -FilePath $FilePath -ArgumentList $CmdLine -WindowStyle Hidden -PassThru
}

function Wait-NgrokUrl {
  param([int]$MaxTries = 40)
  for ($i = 0; $i -lt $MaxTries; $i++) {
    try {
      $resp = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
      $https = $resp.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
      if ($https) { return $https.public_url }
    } catch { }
    Start-Sleep -Milliseconds 500
  }
  return $null
}

# Checks
try { & $NgrokExe version > $null 2>&1 } catch {
  Write-Host "ERROR: ngrok no esta en PATH. Ajusta -NgrokExe." -ForegroundColor Red
  exit 1
}
try { & $PythonExe --version > $null 2>&1 } catch {
  Write-Host "ERROR: Python no esta en PATH. Ajusta -PythonExe." -ForegroundColor Red
  exit 1
}

# 1) Uvicorn (public_web)
$uvArgs = "-m uvicorn $AppModule --host $BindHost --port $Port"
$uv = Start-Child $PythonExe $uvArgs

# 2) ngrok apuntando al mismo puerto
$ngArgs = "http http://127.0.0.1:$Port"
$ng = Start-Child $NgrokExe $ngArgs

# 3) Obtener URL publica https
$publicUrl = Wait-NgrokUrl
if (-not $publicUrl) {
  Write-Host "ERROR: No pude obtener la URL de ngrok." -ForegroundColor Red
  if ($uv) { Stop-Process -Id $uv.Id -Force -ErrorAction SilentlyContinue }
  if ($ng) { Stop-Process -Id $ng.Id -Force -ErrorAction SilentlyContinue }
  exit 1
}
Write-Host ("PUBLIC_BASE_URL = " + $publicUrl)

# 4) Exportar variable y lanzar la app Flet
$env:PUBLIC_BASE_URL = $publicUrl

try {
  Write-Host ("-> Lanzando " + $MainApp)
  & $PythonExe $MainApp
}
finally {
  Write-Host "Deteniendo servicios auxiliares..."
  if ($uv) { Stop-Process -Id $uv.Id -Force -ErrorAction SilentlyContinue }
  if ($ng) { Stop-Process -Id $ng.Id -Force -ErrorAction SilentlyContinue }
  Write-Host "Listo."
}
