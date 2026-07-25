$ErrorActionPreference = "Stop"
$siteRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8765

Write-Host "Adeptus Logistica 控制中樞啟動中..." -ForegroundColor Green
Write-Host "請保持此視窗開啟；瀏覽器將開啟 http://127.0.0.1:$port/" -ForegroundColor Green
Start-Process "http://127.0.0.1:$port/"

if (Get-Command python -ErrorAction SilentlyContinue) {
  Set-Location -LiteralPath $siteRoot
  python -m http.server $port --bind 127.0.0.1
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  Set-Location -LiteralPath $siteRoot
  py -m http.server $port --bind 127.0.0.1
} else {
  Write-Host "找不到 Python。請依 README 的方式啟動本機伺服器。" -ForegroundColor Red
  Read-Host "按 Enter 關閉"
}
