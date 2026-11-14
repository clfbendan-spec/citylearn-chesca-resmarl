# 生成并缓存编译/运行 classpath（去重版，与 _compile_check.ps1 同口径）。
$ErrorActionPreference = 'Continue'
$root = 'd:/citylearn-demo/citylearnjava'
$repo = "$env:USERPROFILE\.m2\repository"

function Get-Ver([string]$s) {
    $t = ($s -replace '[^0-9.].*$', '').Trim('.')
    if (-not $t) { return $null }
    try { return [version]$t } catch { return $null }
}

$all = Get-ChildItem $repo -Recurse -Filter *.jar -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike '*sources*' -and $_.Name -notlike '*javadoc*' }
$best = @{}
foreach ($j in $all) {
    $p = $j.FullName.Split('\')
    if ($p.Count -lt 3) { continue }
    $art = $p[$p.Count - 3]
    $ver = $p[$p.Count - 2]
    $v = Get-Ver $ver
    if (-not $best.ContainsKey($art)) { $best[$art] = @{ jar = $j; ver = $v }; continue }
    $cv = $best[$art].ver
    if ($v -and ((-not $cv) -or ($v -gt $cv))) { $best[$art] = @{ jar = $j; ver = $v } }
}
$lombok34 = Get-Item "$repo/org/projectlombok/lombok/1.18.34/lombok-1.18.34.jar"
$best['lombok'] = @{ jar = $lombok34; ver = [version]'1.18.34' }

$jars = $best.Values | ForEach-Object { $_.jar.FullName.Replace('\', '/') }
$cp = ($jars -join ';')
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText("$root/target/_cp.txt", $cp, $utf8NoBom)
Write-Host "jars: $($jars.Count)"
Write-Host "cp written to $root/target/_cp.txt ($($cp.Length) chars)"
