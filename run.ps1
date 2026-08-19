<#
.SYNOPSIS
    Inicia o FlowRank usando o interpretador do .venv.

.EXAMPLE
    .\run.ps1            # abre a GUI
    .\run.ps1 -Tests     # roda os testes
    .\run.ps1 -Check 5   # diagnostico do Excel por 5 segundos
#>
[CmdletBinding()]
param(
    [switch]$Tests,
    [double]$Check = 0
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Ambiente virtual nao encontrado. Criando com CPython 3.12..." -ForegroundColor Yellow
    py -3.12 -m venv .venv
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.txt
}

if ($Tests) {
    & $python -m pytest @args
}
elseif ($Check -gt 0) {
    & $python -m tools.check_excel $Check
}
else {
    & $python main.py @args
}

exit $LASTEXITCODE
