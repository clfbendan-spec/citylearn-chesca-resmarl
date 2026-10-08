# Compile check with de-duplicated jars (keep highest version per artifactId),
# so fake errors from version mixing (spring-web 5.2 vs 5.3, mybatis-plus old vs 3.5.15) disappear.
$ErrorActionPreference = 'Continue'
$root = 'd:/citylearn-demo/citylearnjava'
$repo = "$env:USERPROFILE\.m2\repository"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

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
# force lombok 1.18.34 (only JDK21-compatible one available)
$lombok34 = Get-Item "$repo/org/projectlombok/lombok/1.18.34/lombok-1.18.34.jar"
$best['lombok'] = @{ jar = $lombok34; ver = [version]'1.18.34' }

$jars = $best.Values | ForEach-Object { $_.jar.FullName.Replace('\', '/') }
Write-Host "deduped jars: $($jars.Count) (was $($all.Count))"
$cp = ($jars -join ';')

$files = Get-ChildItem "$root/src/main/java" -Recurse -Filter *.java |
    ForEach-Object { $_.FullName.Replace('\', '/') }
Write-Host "source files: $($files.Count)"

$out = "$root/target/_check2"
Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $out | Out-Null

$argfile = "$root/target/_check2_args.txt"
$lines = @('-encoding', 'UTF-8', '-nowarn', '-proc:full', '-d', ($out.Replace('\', '/')), '-cp')
$lines += '"' + $cp + '"'
$lines += ($files | ForEach-Object { '"' + $_ + '"' })
[System.IO.File]::WriteAllLines($argfile, $lines, $utf8NoBom)

$jvmArgs = @('-J-Duser.language=en', '-J-Duser.country=US')
foreach ($m in @('api', 'code', 'comp', 'file', 'main', 'model', 'parser', 'processing', 'tree', 'util', 'jvm')) {
    $jvmArgs += "-J--add-exports=jdk.compiler/com.sun.tools.javac.$m=ALL-UNNAMED"
}
foreach ($m in @('code', 'comp', 'file', 'main', 'model', 'parser', 'processing', 'tree', 'util')) {
    $jvmArgs += "-J--add-opens=jdk.compiler/com.sun.tools.javac.$m=ALL-UNNAMED"
}

$rawFile = "$out/_javac_raw.txt"
& javac @jvmArgs "@$argfile" *> $rawFile
$code = $LASTEXITCODE
$raw = Get-Content $rawFile -Raw -Encoding UTF8
if ($raw) { ($raw -split "`r?`n") | Where-Object { $_ -match 'error' } | Select-Object -First 40 }
Write-Host "=== javac exit code: $code ==="
Write-Host "=== .class generated: $((Get-ChildItem $out -Recurse -Filter *.class -ErrorAction SilentlyContinue).Count) ==="
foreach ($c in @('com/citylearn/param/PyFileParam.class',
                 'com/citylearn/service/BaseDataService.class',
                 'com/citylearn/controller/BaseDataController.class')) {
    Write-Host "  $c : $(Test-Path "$out/$c")"
}