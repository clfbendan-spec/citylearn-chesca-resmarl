param(
    [string]$TexBin = $env:THESIS_TEX_BIN,
    [switch]$Clean
)

$ErrorActionPreference = 'Continue'
Push-Location $PSScriptRoot
try {
    $tools = @{}
    foreach ($name in @('xelatex', 'biber')) {
        if ($TexBin) {
            $path = Join-Path $TexBin "$name.exe"
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Tool not found: $path"
            }
            $tools[$name] = $path
        } else {
            $tool = Get-Command $name -CommandType Application -ErrorAction Stop
            $tools[$name] = $tool.Source
        }
    }
    if ($Clean) {
        foreach ($name in @('main.aux', 'main.bbl', 'main.bcf', 'main.blg',
                            'main.log', 'main.out', 'main.toc', 'main.run.xml')) {
            Remove-Item -LiteralPath $name -Force -ErrorAction SilentlyContinue
        }
        Get-ChildItem -LiteralPath contents -Filter '*.aux' -File |
            Remove-Item -Force
    }
    $steps = @(
        @{ Tool = 'xelatex'; Arguments = @('-interaction=nonstopmode', '-halt-on-error', '-file-line-error', '-recorder', 'main.tex') },
        @{ Tool = 'biber'; Arguments = @('main') },
        @{ Tool = 'xelatex'; Arguments = @('-interaction=nonstopmode', '-halt-on-error', '-file-line-error', '-recorder', 'main.tex') },
        @{ Tool = 'xelatex'; Arguments = @('-interaction=nonstopmode', '-halt-on-error', '-file-line-error', '-recorder', 'main.tex') }
    )
    $number = 0
    foreach ($step in $steps) {
        $number++
        Write-Host "[$number/4] $($step.Tool)"
        & $tools[$step.Tool] @($step.Arguments) *> "build_step$number.log"
        if ($LASTEXITCODE -ne 0) {
            throw "Build failed at step $number; see build_step$number.log"
        }
    }
    $result = Select-String -LiteralPath main.log -Pattern 'Output written on main\.pdf \((\d+) pages\)'
    if (-not $result) { throw 'PDF output was not confirmed in main.log' }
    Write-Host "[OK] main.pdf - $($result.Matches[-1].Groups[1].Value) pages"
} catch {
    Write-Error $_
    exit 1
} finally {
    Pop-Location
}
