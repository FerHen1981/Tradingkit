<#
    MEX ops — PowerShell helper voor de dagelijkse controle van de trechter.

    Draai dit op JE EIGEN WINDOWS-MACHINE in PowerShell. Niet plakken in een
    SSH-sessie: daar draait bash en die begrijpt geen PowerShell (dat ging de
    vorige keer mis). Elke functie hieronder maakt zelf verbinding.

    Eenmalig instellen:
        1. Open PowerShell.
        2. cd naar de map waar dit bestand staat.
        3. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
        4. . .\mex-ops.ps1          <-- let op de losse punt vooraan: dat laadt de functies
        5. $env:MEX_HOST = "root@<ip-of-hostnaam-van-mex-mw-01>"

    Daarna heb je deze commando's:
        Get-MexHealth        - draait de middleware, staat rendering aan?
        Get-MexRouted        - laatste 15 doorgestuurde berichten van vandaag
        Watch-MexRouted      - live meekijken (Ctrl+C om te stoppen)
        Get-MexCharts        - charts van vandaag naar je Downloads halen
        Get-MexCron          - welke crontab draait er nu echt
        Test-MexFunnel       - stuurt één testkaart door de trechter
#>

if (-not $env:MEX_HOST) { $env:MEX_HOST = "root@mw.mex-traders.com" }

function Invoke-MexSsh {
    param([Parameter(Mandatory)][string]$Command)
    ssh $env:MEX_HOST $Command
}

function Get-MexHealth {
    <# renderEnabled moet true zijn, dryRun false, armed true. #>
    Invoke-MexSsh "curl -s localhost:5000/health" | ConvertFrom-Json | Format-List
}

function Get-MexRouted {
    param([int]$Last = 15)
    # De audit staat op UTC-datum; daarom date -u, niet de lokale datum.
    $out = Invoke-MexSsh "tail -n $Last /root/intent-store/routed_`$(date -u +%Y%m%d).jsonl"
    $out | ForEach-Object {
        $r = $_ | ConvertFrom-Json
        [pscustomobject]@{
            Tijd   = ([datetime]$r.ts).ToLocalTime().ToString("HH:mm:ss")
            Soort  = $r.kind
            Account= $r.account
            Uitkomst = $r.result
        }
    } | Format-Table -AutoSize
}

function Watch-MexRouted {
    Write-Host "Live meekijken. Ctrl+C stopt." -ForegroundColor Cyan
    Invoke-MexSsh "tail -f /root/intent-store/routed_`$(date -u +%Y%m%d).jsonl"
}

function Get-MexCharts {
    <# Haalt de charts van vandaag op. De crawler benoemt op ET-datum, dus die
       rekenen we hier uit — na 20:00 jouw tijd is de UTC-datum al morgen. #>
    param([string]$Date = "")
    if (-not $Date) {
        $et = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
                  [DateTime]::UtcNow, "Eastern Standard Time")
        $Date = $et.ToString("yyyyMMdd")
    }
    $dest = Join-Path $env:USERPROFILE "Downloads\mex-charts\$Date"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($a in @("NQ","ES","GC","QQQ","BTC")) {
        $url = "https://mw.mex-traders.com/charts/$Date/${Date}_$a.png"
        $f   = Join-Path $dest "${Date}_$a.png"
        try {
            Invoke-WebRequest -Uri $url -OutFile $f -ErrorAction Stop
            Write-Host ("{0,-4} {1:N0} kB" -f $a, ((Get-Item $f).Length/1kb)) -ForegroundColor Green
        } catch {
            Write-Host ("{0,-4} ONTBREEKT — {1}" -f $a, $_.Exception.Message) -ForegroundColor Red
        }
    }
    Write-Host "`nOpgeslagen in $dest" -ForegroundColor Cyan
}

function Get-MexCron {
    <# Toon wat er echt draait; dit is stap 1 vóór je de tijden aanpast. #>
    Invoke-MexSsh "crontab -l; echo '--- systemd timers ---'; systemctl list-timers --all | grep -i chart"
}

function Test-MexFunnel {
    <# Stuurt één FILL door de trechter. Bij dryRun=false komt de kaart echt in
       Discord — doe dit dus niet tijdens de sessie in het live kanaal. #>
    $secret = Read-Host "Middleware-secret"
    $body = '{"username":"MEX TEST","embeds":[{"title":"TEST MGC1! FILL LONG","color":3447003,"description":"TEST | 1ct @ 4407.0 | SL 4397.0 | TP 4432.0","footer":{"text":"MGC1!"}}]}'
    Invoke-MexSsh "curl -s -X POST localhost:5000/signal/$secret -H 'Content-Type: application/json' -d '$body'"
    Write-Host "`nNa ~5 seconden zou 'card sent 200' in de audit moeten staan:" -ForegroundColor Cyan
    Start-Sleep -Seconds 6
    Get-MexRouted -Last 3
}

Write-Host "MEX ops geladen. Host: $env:MEX_HOST" -ForegroundColor Green
Write-Host "Begin met: Get-MexHealth" -ForegroundColor DarkGray
