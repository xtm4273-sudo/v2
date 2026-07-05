param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [Parameter(Mandatory = $true)]
    [string]$Calmonth,

    [Parameter(Mandatory = $true)]
    [string]$ReportPeriod,

    [string]$Name = "",
    [string]$Department = "",
    [string]$Province = "",
    [string]$Region = "",
    [string]$OutputRoot = "Reports\windows_live_strict",
    [int]$Timeout = 60
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env，请先填写 SKSHU_BI_API_KEY 和 AI_API_KEY 后重新运行。"
    exit 1
}

Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and !$line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
    }
}

if (!$env:SKSHU_BI_API_KEY -or $env:SKSHU_BI_API_KEY -eq "填写你的apikey") {
    throw ".env 里缺少有效的 SKSHU_BI_API_KEY"
}

if (!(Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium

.\.venv\Scripts\python.exe run_full_report_strict.py `
    --job-id $JobId `
    --calmonth $Calmonth `
    --report-period $ReportPeriod `
    --api-key $env:SKSHU_BI_API_KEY `
    --name $Name `
    --department $Department `
    --province $Province `
    --region $Region `
    --output-root $OutputRoot `
    --timeout $Timeout
