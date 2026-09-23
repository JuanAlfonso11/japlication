Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$RepoDir = Split-Path -Parent $PSScriptRoot
$Tailscale = "C:\Program Files\Tailscale\tailscale.exe"
$DockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

# Re-points :443 (real app <-> offline page) with whichever of `serve`
# (tailnet only) or `funnel` (public) is active now. A plain `serve` on a
# funneled port would quietly take the app off the internet.
function Set-Https443([string]$target) {
    $mode = if ((& $Tailscale funnel status 2>$null) -match "Funnel on") { "funnel" } else { "serve" }
    & $Tailscale $mode --bg --https=443 $target *> $null
}

# -- Palette. Mirrors frontend/tailwind.config.ts exactly, so this window
#    and the app read as the same product: brand-600 #6d28f5, brand-700
#    #5b1fd6, and the ink neutrals (gray-50/900/500/200). The dot colours
#    are the app's own emerald-500 and gray-300. --
$ColorBg      = [System.Drawing.Color]::FromArgb(246, 247, 251)
$ColorBrand   = [System.Drawing.Color]::FromArgb(109, 40, 245)
$ColorBrandHv = [System.Drawing.Color]::FromArgb(91, 31, 214)
$ColorText    = [System.Drawing.Color]::FromArgb(27, 32, 48)
$ColorMuted   = [System.Drawing.Color]::FromArgb(110, 118, 145)
$ColorBorder  = [System.Drawing.Color]::FromArgb(220, 223, 235)
$ColorOn      = [System.Drawing.Color]::FromArgb(16, 185, 129)
$ColorOff     = [System.Drawing.Color]::FromArgb(195, 200, 219)
$ColorWorking = $ColorBrand

function New-RoundedRegion([int]$width, [int]$height, [int]$radius) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $path.AddArc(0, 0, $d, $d, 180, 90)
    $path.AddArc($width - $d, 0, $d, $d, 270, 90)
    $path.AddArc($width - $d, $height - $d, $d, $d, 0, 90)
    $path.AddArc(0, $height - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return New-Object System.Drawing.Region $path
}

function Test-Running {
    Set-Location $RepoDir
    $result = & docker compose ps --status running --services 2>$null
    return ($result -and ($result -join "").Trim().Length -gt 0)
}

function Set-Status([string]$text, [System.Drawing.Color]$dotColor) {
    $statusText.Text = $text
    $statusDot.BackColor = $dotColor
    $form.Refresh()
}

function Update-Status {
    if (Test-Running) { Set-Status "Encendido" $ColorOn }
    else { Set-Status "Apagado" $ColorOff }
}

function Start-JobPilot {
    $startButton.Enabled = $false
    $stopButton.Enabled = $false

    Set-Status "Conectando Tailscale..." $ColorWorking
    & $Tailscale up --timeout 20s 2>&1 | Out-Null

    Set-Status "Revisando Docker..." $ColorWorking
    Set-Location $RepoDir
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Set-Status "Abriendo Docker Desktop..." $ColorWorking
        Start-Process $DockerDesktop
        $attempts = 0
        while ($attempts -lt 40) {
            Start-Sleep -Seconds 3
            docker info *> $null
            if ($LASTEXITCODE -eq 0) { break }
            $attempts++
            Set-Status "Esperando a Docker ($attempts/40)..." $ColorWorking
        }
        if ($LASTEXITCODE -ne 0) {
            Set-Status "Docker no respondio" $ColorOff
            $startButton.Enabled = $true
            $stopButton.Enabled = $true
            return
        }
    }

    Set-Status "Encendiendo..." $ColorWorking
    docker compose up -d *> $null

    # Point tailscale serve back at the real frontend now that it's up —
    # while it was off, this pointed at the offline placeholder page
    # instead (see Stop-JobPilot). scripts\offline-page\serve-offline.ps1
    # (started at login, independent of Docker) keeps answering on :3001
    # either way; only where tailscale serve forwards to changes.
    Set-Https443 "http://localhost:3000"

    # A job-matching sweep runs every 2 hours while the app is on
    # (install-job-sweep-schedule.ps1) — also fire one right now, in the
    # background, so turning the app back on after any stretch of being
    # off immediately catches the queue up instead of waiting for the
    # next scheduled slot. Detached (Start-Process, not called inline) so
    # the button doesn't sit disabled for however long the external job
    # searches take.
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList `
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$RepoDir\scripts\daily-job-sweep.ps1`""

    Update-Status
    $startButton.Enabled = $true
    $stopButton.Enabled = $true
}

function Stop-JobPilot {
    $startButton.Enabled = $false
    $stopButton.Enabled = $false
    Set-Status "Apagando..." $ColorWorking

    Set-Location $RepoDir

    # Switch tailscale serve to the always-on offline placeholder page
    # BEFORE stopping the containers, so there's no gap where the real
    # app is down but the URL still points at it (which would just show a
    # connection error instead of the "JobPilot esta descansando" page).
    Set-Https443 "http://localhost:3001"
    docker compose stop *> $null

    Update-Status
    $startButton.Enabled = $true
    $stopButton.Enabled = $true
}

# -- Window --
$form = New-Object System.Windows.Forms.Form
$form.Text = "JobPilot"
$form.ClientSize = New-Object System.Drawing.Size(300, 280)
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.StartPosition = "CenterScreen"
$form.BackColor = $ColorBg
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

$logoPath = Join-Path $RepoDir "frontend\public\icons\icon-192.png"
try {
    if (Test-Path $logoPath) {
        $bmp = [System.Drawing.Bitmap]::FromFile($logoPath)
        $form.Icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
    }
} catch {}

# Logo
$logoBox = New-Object System.Windows.Forms.PictureBox
$logoBox.Size = New-Object System.Drawing.Size(56, 56)
$logoBox.Location = New-Object System.Drawing.Point(122, 26)
$logoBox.SizeMode = "Zoom"
$logoBox.BackColor = [System.Drawing.Color]::Transparent
try {
    if (Test-Path $logoPath) { $logoBox.Image = [System.Drawing.Image]::FromFile($logoPath) }
} catch {}
$form.Controls.Add($logoBox)

# Title
$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "JobPilot"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$titleLabel.ForeColor = $ColorText
$titleLabel.AutoSize = $false
$titleLabel.TextAlign = "MiddleCenter"
$titleLabel.Size = New-Object System.Drawing.Size(300, 30)
$titleLabel.Location = New-Object System.Drawing.Point(0, 86)
$form.Controls.Add($titleLabel)

# Status row: dot + text, centered as a group
$statusDot = New-Object System.Windows.Forms.Panel
$statusDot.Size = New-Object System.Drawing.Size(9, 9)
$statusDot.Location = New-Object System.Drawing.Point(112, 130)
$statusDot.Region = New-RoundedRegion 9 9 5
$statusDot.BackColor = $ColorOff
$form.Controls.Add($statusDot)

$statusText = New-Object System.Windows.Forms.Label
$statusText.Text = "Revisando..."
$statusText.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$statusText.ForeColor = $ColorMuted
$statusText.AutoSize = $true
$statusText.Location = New-Object System.Drawing.Point(128, 126)
$form.Controls.Add($statusText)

# Start button (primary, filled brand blue)
$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "Encender"
$startButton.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$startButton.Size = New-Object System.Drawing.Size(260, 46)
$startButton.Location = New-Object System.Drawing.Point(20, 160)
$startButton.BackColor = $ColorBrand
$startButton.ForeColor = [System.Drawing.Color]::White
$startButton.FlatStyle = "Flat"
$startButton.FlatAppearance.BorderSize = 0
$startButton.FlatAppearance.MouseOverBackColor = $ColorBrandHv
$startButton.Cursor = "Hand"
$startButton.Region = New-RoundedRegion 260 46 12
$startButton.Add_Click({ Start-JobPilot })
$form.Controls.Add($startButton)

# Stop button (secondary, outlined)
$stopButton = New-Object System.Windows.Forms.Button
$stopButton.Text = "Apagar"
$stopButton.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$stopButton.Size = New-Object System.Drawing.Size(260, 46)
$stopButton.Location = New-Object System.Drawing.Point(20, 214)
$stopButton.BackColor = [System.Drawing.Color]::White
$stopButton.ForeColor = $ColorText
$stopButton.FlatStyle = "Flat"
$stopButton.FlatAppearance.BorderSize = 1
$stopButton.FlatAppearance.BorderColor = $ColorBorder
$stopButton.FlatAppearance.MouseOverBackColor = $ColorBg
$stopButton.Cursor = "Hand"
$stopButton.Region = New-RoundedRegion 260 46 12
$stopButton.Add_Click({ Stop-JobPilot })
$form.Controls.Add($stopButton)

$form.Add_Shown({ Update-Status })
[System.Windows.Forms.Application]::Run($form)
