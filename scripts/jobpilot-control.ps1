Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$RepoDir = Split-Path -Parent $PSScriptRoot
$Tailscale = "C:\Program Files\Tailscale\tailscale.exe"
$DockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

# -- Palette (matches the app's brand blue) --
$ColorBg      = [System.Drawing.Color]::FromArgb(247, 248, 250)
$ColorBrand   = [System.Drawing.Color]::FromArgb(37, 71, 233)
$ColorBrandHv = [System.Drawing.Color]::FromArgb(31, 55, 209)
$ColorText    = [System.Drawing.Color]::FromArgb(32, 33, 36)
$ColorMuted   = [System.Drawing.Color]::FromArgb(128, 134, 139)
$ColorBorder  = [System.Drawing.Color]::FromArgb(222, 225, 230)
$ColorOn      = [System.Drawing.Color]::FromArgb(16, 150, 88)
$ColorOff     = [System.Drawing.Color]::FromArgb(180, 184, 189)
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

    Update-Status
    $startButton.Enabled = $true
    $stopButton.Enabled = $true
}

function Stop-JobPilot {
    $startButton.Enabled = $false
    $stopButton.Enabled = $false
    Set-Status "Apagando..." $ColorWorking

    Set-Location $RepoDir
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
