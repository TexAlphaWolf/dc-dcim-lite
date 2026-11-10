# End to end inside the image, from Windows PowerShell: a synthetic data center and its truth are written to a volume, checked and
# scored, traced, drawn and exported, edited by hand in a database with a history, the report is rebuilt from its JSON, the two
# implementations are compared and the benchmark runs small (read-only root, no capabilities, no network). Needs Docker Desktop.
# Usage: .\tools\docker_e2e.ps1 [-Image dcim]
param([string]$Image = "dcim")
$ErrorActionPreference = "Stop"

$id = Get-Random
$vol = "dcim-e2e-$id"
$secure = @("--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--network", "none", "-v", "${vol}:/data")

# Windows PowerShell 5.1 turns a program's message on stderr into an error under "Stop": the commands that are expected to
# fail run with errors not terminating, and only their exit code is looked at.
function Invoke-DcimCode([int[]]$Allowed, [string[]]$DcimArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = docker run --rm @secure $Image @DcimArgs 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($Allowed -notcontains $code) { throw "dcim $DcimArgs exited with $code : $out" }
    ($out | Out-String)
}
function Invoke-Dcim([string[]]$DcimArgs) { Invoke-DcimCode @(0) $DcimArgs }
function Read-Volume($path) {
    $out = docker run --rm --entrypoint cat -v "${vol}:/data" $Image $path 2>$null
    if ($LASTEXITCODE -ne 0) { throw "cannot read $path" }
    ($out | Out-String)
}
function Assert-Contains($text, $needle) { if ($text -notmatch [regex]::Escape($needle)) { throw "expected '$needle' in: $text" } }

try {
    docker volume create $vol | Out-Null
    docker run --rm --user 0 -v "${vol}:/data" --entrypoint chown $Image 10001 /data
    if ($LASTEXITCODE -ne 0) { throw "could not prepare the volume" }

    Assert-Contains (Invoke-Dcim @("generate", "/data/dc", "--racks", "6", "--seed", "3")) "written: /data/dc/dcim.db, /data/dc/truth.json"
    $chk = Invoke-DcimCode @(1) @("check", "/data/dc/dcim.db", "--truth", "/data/dc/truth.json")
    Assert-Contains $chk "5 findings in 132 devices"
    Assert-Contains $chk "against the injected faults: 5 of 5 found, 0 extra"
    Assert-Contains (Invoke-Dcim @("trace", "/data/dc/dcim.db", "R02-srv-2u-01:eth1")) "ends at core-01:19"
    Invoke-Dcim @("elevation", "/data/dc/dcim.db", "-o", "/data/dc/rack.svg") | Out-Null
    Assert-Contains (Read-Volume "/data/dc/rack.svg") "<svg"
    Invoke-Dcim @("export", "/data/dc/dcim.db", "-o", "/data/dc/dc.html") | Out-Null
    Assert-Contains (Read-Volume "/data/dc/dc.html") "<!doctype html>"

    Invoke-Dcim @("init", "/data/mine.db") | Out-Null
    Invoke-Dcim @("add-rack", "/data/mine.db", "A", "--units", "10", "--power-w", "3000") | Out-Null
    Invoke-Dcim @("add-device", "/data/mine.db", "pduA", "--rack", "A", "--kind", "pdu", "--feed", "A", "--outlets", "4", "--capacity-w", "2000") | Out-Null
    Invoke-Dcim @("add-device", "/data/mine.db", "s1", "--rack", "A", "--u", "1", "--watts", "1000") | Out-Null
    Invoke-DcimCode @(1) @("check", "/data/mine.db") | Out-Null
    Invoke-Dcim @("connect", "/data/mine.db", "s1:psu0", "pduA:out1") | Out-Null
    Assert-Contains (Invoke-Dcim @("history", "/data/mine.db")) "connect"

    $rep = Invoke-Dcim @("report", "--out", "/data/out")
    Assert-Contains $rep "demo data center (synthetic, 24 racks, seed 1, with injected faults): 24 racks, 473 devices"
    Assert-Contains $rep "12 of 12 found, 0 reports that are not an injected fault"
    $md = Read-Volume "/data/out/report.md"
    Invoke-Dcim @("render", "/data/out/report.json", "-o", "/data/out/again.md") | Out-Null
    if ((Read-Volume "/data/out/again.md") -ne $md) { throw "the report rebuilt from the JSON is not identical" }

    Assert-Contains (Invoke-Dcim @("verify", "--draws", "5")) "6 of 6 comparisons agree"
    Invoke-Dcim @("bench", "--sizes", "300,600", "--ref-sizes", "100,200", "--repeat", "1", "--draws", "3", "--seeds", "2", "--out", "/data/bench") | Out-Null
    Assert-Contains (Read-Volume "/data/bench/bench.json") '"ok": true'

    Invoke-DcimCode @(2) @("check", "/data/nope.db") | Out-Null
    Write-Host "docker end-to-end: OK"
}
finally {
    $ErrorActionPreference = "Continue"
    docker volume rm -f $vol 2>&1 | Out-Null
}
