# Creates the signing key used for release builds of the Android app, once.
#
# WHY THIS EXISTS
# ---------------
# Until now the APK was signed with the Android SDK's debug key
# (CN=Android Debug), which has two problems that only look cosmetic:
#
#   * Its keystore lives at ~/.android/debug.keystore with the universally
#     known password "android". Anyone who gets that file can build an APK
#     that Android accepts as an *update* to JobPilot, because the signature
#     matches.
#   * Nobody backs it up. It is regenerated silently if it goes missing, and
#     the moment it changes, no existing install can be updated any more.
#     So the "lost key" risk already exists today - it is just invisible and
#     unmanaged.
#
# A deliberate release key does not add that risk. It makes it explicit and
# gives you something you can actually back up.
#
# IMPORTANT
# ---------
# Back up BOTH files this creates, somewhere off this machine:
#     frontend/android/keystore/jobpilot-release.keystore
#     frontend/android/keystore.properties
# Lose them and you can never publish an update over an existing install
# again - every device would have to uninstall and reinstall. Both are
# gitignored on purpose; they must never reach the repository.
#
# Usage:  .\scripts\create-release-keystore.ps1
# Safe to re-run: it refuses to overwrite an existing keystore.

$ErrorActionPreference = "Stop"

$repoDir  = Split-Path -Parent $PSScriptRoot
$androidDir = Join-Path $repoDir "frontend\android"
$keyDir   = Join-Path $androidDir "keystore"
$ksPath   = Join-Path $keyDir "jobpilot-release.keystore"
$propsPath = Join-Path $androidDir "keystore.properties"
$keytool  = Join-Path $env:JAVA_HOME "bin\keytool.exe"

if (-not (Test-Path $keytool)) {
    $keytool = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot\bin\keytool.exe"
}
if (-not (Test-Path $keytool)) {
    throw "No se encontro keytool. Instala el JDK 21 o define JAVA_HOME."
}

if (Test-Path $ksPath) {
    Write-Host "[keystore] Ya existe en $ksPath - no se toca."
    Write-Host "[keystore] Borralo a mano solo si estas absolutamente seguro."
    return
}

New-Item -ItemType Directory -Force $keyDir | Out-Null

# A long random password. Nobody types this: Gradle reads it from
# keystore.properties, which sits next to the keystore and is equally secret.
Add-Type -AssemblyName System.Web
$pass = [System.Web.Security.Membership]::GeneratePassword(40, 8)

# 30 years: an app signing key should outlive the app. Google Play requires
# validity past 2033 for exactly this reason.
& $keytool -genkeypair -v `
    -keystore $ksPath `
    -alias jobpilot `
    -keyalg RSA -keysize 4096 `
    -validity 10950 `
    -storepass $pass -keypass $pass `
    -dname "CN=JobPilot, OU=Personal, O=JobPilot, C=DO" | Out-Null

if ($LASTEXITCODE -ne 0) { throw "keytool fallo con codigo $LASTEXITCODE" }

$props = @"
# Credenciales de firma del APK de release. NUNCA se commitea (gitignored).
#
# Si pierdes este archivo o el .keystore que acompana, no podras volver a
# publicar una actualizacion sobre las instalaciones existentes: Android
# rechaza un APK firmado con otra clave. Copia ambos fuera de esta maquina.
storeFile=keystore/jobpilot-release.keystore
storePassword=$pass
keyAlias=jobpilot
keyPassword=$pass
"@

Set-Content -Path $propsPath -Value $props -Encoding UTF8

Write-Host "[keystore] Creado: $ksPath"
Write-Host "[keystore] Credenciales: $propsPath"
Write-Host ""
Write-Host "SIGUIENTE PASO OBLIGATORIO: respalda esos dos archivos fuera de esta PC."
