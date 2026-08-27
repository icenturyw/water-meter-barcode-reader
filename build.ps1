[CmdletBinding()]
param(
    [switch]$SkipDependencyInstall,
    [string]$VenvPath = ".venv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$projectRoot = Split-Path -Parent $PSCommandPath
$venvRoot = if ([System.IO.Path]::IsPathRooted($VenvPath)) {
    $VenvPath
}
else {
    Join-Path $projectRoot $VenvPath
}
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$requirementsFile = Join-Path $projectRoot "requirements.txt"
$entryPoint = Join-Path $projectRoot "app.py"
$noticesFile = Join-Path $projectRoot "THIRD_PARTY_NOTICES.txt"
$userGuideName = (-join @([char]0x4F7F, [char]0x7528, [char]0x8BF4, [char]0x660E)) + ".txt"
$userGuideFile = Join-Path $projectRoot $userGuideName
$appName = -join @(
    [char]0x6C34, [char]0x8868, [char]0x8868, [char]0x53F7,
    [char]0x6279, [char]0x91CF, [char]0x8BC6, [char]0x522B,
    [char]0x5DE5, [char]0x5177
)

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Project virtual environment not found: $venvPython`nRun this first: python -m venv .venv"
}

if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) {
    throw "Application entry point not found: $entryPoint"
}

function Invoke-VenvPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $venvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $venvPython $($Arguments -join ' ')"
    }
}

function Copy-ReleaseDocuments {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Copy-Item -LiteralPath $noticesFile -Destination (Join-Path $Destination "THIRD_PARTY_NOTICES.txt") -Force
    Copy-Item -LiteralPath $userGuideFile -Destination (Join-Path $Destination $userGuideName) -Force

    $licensesDestination = Join-Path $Destination "THIRD_PARTY_LICENSES"
    New-Item -ItemType Directory -Path $licensesDestination -Force | Out-Null

    $sitePackages = (& $venvPython -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to locate site-packages in the virtual environment."
    }

    $basePrefix = (& $venvPython -c "import sys; print(sys.base_prefix)").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to locate the base Python installation."
    }

    $licenseFiles = @(
        @{
            Source = Join-Path $sitePackages "zxing_cpp-3.1.1.dist-info\licenses\LICENSE"
            Name = "zxing-cpp-3.1.1-APACHE-2.0.txt"
        },
        @{
            Source = Join-Path $sitePackages "pillow-12.3.0.dist-info\licenses\LICENSE"
            Name = "Pillow-12.3.0-and-bundled-libraries.txt"
        },
        @{
            Source = Join-Path $sitePackages "openpyxl-3.1.5.dist-info\LICENCE.rst"
            Name = "openpyxl-3.1.5-MIT.txt"
        },
        @{
            Source = Join-Path $sitePackages "pyinstaller-6.22.0.dist-info\licenses\COPYING.txt"
            Name = "PyInstaller-6.22.0-GPL-2.0-or-later-with-bootloader-exception.txt"
        },
        @{
            Source = Join-Path $basePrefix "LICENSE.txt"
            Name = "CPython-license.txt"
        }
    )

    foreach ($licenseFile in $licenseFiles) {
        if (Test-Path -LiteralPath $licenseFile.Source -PathType Leaf) {
            Copy-Item -LiteralPath $licenseFile.Source -Destination (Join-Path $licensesDestination $licenseFile.Name) -Force
        }
        else {
            Write-Warning "License file not found: $($licenseFile.Source)"
        }
    }

    $etXmlDistInfo = Get-ChildItem -LiteralPath $sitePackages -Directory |
        Where-Object { $_.Name -like "et_xmlfile-*.dist-info" } |
        Select-Object -First 1
    if ($null -ne $etXmlDistInfo) {
        foreach ($licenseName in @("LICENCE.rst", "LICENCE.python")) {
            $source = Join-Path $etXmlDistInfo.FullName $licenseName
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                Copy-Item -LiteralPath $source -Destination (Join-Path $licensesDestination "et-xmlfile-$licenseName.txt") -Force
            }
        }
    }

    foreach ($tclTkLicense in @(
        @{ Source = Join-Path $basePrefix "tcl\tcl8.6\license.terms"; Name = "Tcl-8.6-license.txt" },
        @{ Source = Join-Path $basePrefix "tcl\tk8.6\license.terms"; Name = "Tk-8.6-license.txt" }
    )) {
        if (Test-Path -LiteralPath $tclTkLicense.Source -PathType Leaf) {
            Copy-Item -LiteralPath $tclTkLicense.Source -Destination (Join-Path $licensesDestination $tclTkLicense.Name) -Force
        }
    }
}

Push-Location $projectRoot
try {
    if (-not $SkipDependencyInstall) {
        Write-Host "Installing pinned dependencies..." -ForegroundColor Cyan
        Invoke-VenvPython -Arguments @(
            "-m", "pip", "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--requirement", $requirementsFile
        )
    }

    $onedirDist = Join-Path $projectRoot "dist\onedir"
    $onefileDist = Join-Path $projectRoot "dist\onefile"
    $onedirWork = Join-Path $projectRoot "build\onedir"
    $onefileWork = Join-Path $projectRoot "build\onefile"
    $onedirSpec = Join-Path $projectRoot "build\spec-onedir"
    $onefileSpec = Join-Path $projectRoot "build\spec-onefile"

    foreach ($directory in @($onedirDist, $onefileDist, $onedirWork, $onefileWork, $onedirSpec, $onefileSpec)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $commonArguments = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--noupx",
        "--name", $appName,
        "--paths", $projectRoot,
        "--hidden-import", "zxingcpp"
    )

    Write-Host "Building the onedir release..." -ForegroundColor Cyan
    Invoke-VenvPython -Arguments ($commonArguments + @(
        "--onedir",
        "--distpath", $onedirDist,
        "--workpath", $onedirWork,
        "--specpath", $onedirSpec,
        $entryPoint
    ))

    $onedirApp = Join-Path $onedirDist $appName
    Copy-ReleaseDocuments -Destination $onedirApp

    Write-Host "Building the onefile release..." -ForegroundColor Cyan
    Invoke-VenvPython -Arguments ($commonArguments + @(
        "--onefile",
        "--distpath", $onefileDist,
        "--workpath", $onefileWork,
        "--specpath", $onefileSpec,
        $entryPoint
    ))

    Copy-ReleaseDocuments -Destination $onefileDist

    Write-Host "Build completed." -ForegroundColor Green
    Write-Host "onedir: $onedirApp"
    Write-Host "onefile: $(Join-Path $onefileDist ($appName + '.exe'))"
}
finally {
    Pop-Location
}
