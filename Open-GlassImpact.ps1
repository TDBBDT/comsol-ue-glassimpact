param(
    [string]$EngineRoot = 'D:/Users/Epic/Install/UE_5.6',
    [switch]$Editor
)
$ErrorActionPreference = 'Stop'
$glassProject = Join-Path $PSScriptRoot 'unreal/GlassImpact.uproject'
$glassEditor = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$glassMap = Join-Path $PSScriptRoot 'unreal/Content/GlassImpact/Maps/GlassImpactDemo.umap'
$glassData = Join-Path $PSScriptRoot 'unreal/Content/GlassImpactData/metadata.json'
if (!(Test-Path -LiteralPath $glassEditor)) { throw 'UE 5.6 not found. Pass -EngineRoot with your UE installation directory.' }
if (!(Test-Path -LiteralPath $glassMap) -or !(Test-Path -LiteralPath $glassData)) {
    throw 'Demo assets or data are missing. Follow docs/ue_setup_guide.md before launching.'
}
if ($Editor) {
    & $glassEditor $glassProject '/Game/GlassImpact/Maps/GlassImpactDemo'
} else {
    & $glassEditor $glassProject '/Game/GlassImpact/Maps/GlassImpactDemo' '-game' '-windowed' '-ResX=1440' '-ResY=900'
}
