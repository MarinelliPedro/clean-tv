<#
Compila o launcher Clean TV.

O código fica no projeto (pasta com acento e no OneDrive), mas o Gradle/Android não lida bem
com caminhos assim. Este script espelha o código para C:\dev\cleantv-launcher-build, compila lá
e traz de volta o APK (launcher\dist) e os prints das telas.

Uso:
  .\build.ps1              # APK de release + testes
  .\build.ps1 -Snapshots   # também regrava os prints em app\src\test\snapshots\images
#>
param([switch]$Snapshots)

$ErrorActionPreference = "Continue"
$src = $PSScriptRoot
$build = "C:\dev\cleantv-launcher-build"
$tools = "C:\dev\tools"
$keys = "C:\dev\cleantv-keys"
$env:JAVA_HOME = "$tools\jdk-17"
$env:ANDROID_HOME = "$tools\android-sdk"

robocopy $src $build /MIR /XD build .gradle dist /XF local.properties /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar o código para $build" }
"sdk.dir=" + ($env:ANDROID_HOME -replace '\\', '/') | Set-Content "$build\local.properties" -Encoding ascii

# Chave de assinatura local (gerada uma vez, fica fora do repositório). Guarde uma cópia:
# sem ela não dá para atualizar o launcher instalado sem desinstalar antes.
if (-not (Test-Path "$keys\signing.properties")) {
    New-Item -ItemType Directory -Force $keys | Out-Null
    $pass = [guid]::NewGuid().ToString("N")
    & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -keystore "$keys\release.jks" -alias cleantv -keyalg RSA -keysize 2048 `
        -validity 10000 -storepass $pass -keypass $pass -dname "CN=Clean TV, O=Clean TV project" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "keytool falhou" }
    @("storeFile=$($keys -replace '\\', '/')/release.jks", "storePassword=$pass", "keyAlias=cleantv", "keyPassword=$pass") |
        Set-Content "$keys\signing.properties" -Encoding ascii
}

$gradle = if (Test-Path "$tools\gradle-8.9\bin\gradle.bat") { "$tools\gradle-8.9\bin\gradle.bat" } else { "$build\gradlew.bat" }
$tasks = @(":app:assembleRelease", ":app:testDebugUnitTest")
if ($Snapshots) { $tasks += ":app:recordPaparazziDebug" }

Push-Location $build
& $gradle @tasks "-Pcleantv.signing=$($keys -replace '\\', '/')/signing.properties" --console=plain
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { throw "Build falhou (código $code)" }

New-Item -ItemType Directory -Force "$src\dist" | Out-Null
Copy-Item "$build\app\build\outputs\apk\release\app-release.apk" "$src\dist\clean-tv-launcher.apk" -Force
if ($Snapshots) {
    robocopy "$build\app\src\test\snapshots" "$src\app\src\test\snapshots" /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
}
$apk = Get-Item "$src\dist\clean-tv-launcher.apk"
"APK: $($apk.FullName) ({0:N0} KB)" -f ($apk.Length / 1KB)
exit 0  # o robocopy deixa $LASTEXITCODE=1 quando copia arquivos; isso não é erro
