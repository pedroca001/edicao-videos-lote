$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$editorConfig = Join-Path $HOME '.local/share/local_video_editor/config.json'
$editorInstallation = Get-Content -LiteralPath (Join-Path $HOME '.local/share/local_video_editor/installation.json') -Raw | ConvertFrom-Json
if ($args.Count -gt 0 -and $args[0] -eq '--avatar') {
    & $editorInstallation.python -B (Join-Path $PSScriptRoot 'run_pipeline.py') --avatar --config $editorConfig @($args | Select-Object -Skip 1)
} elseif ($args.Count -gt 0 -and $args[0] -eq '--matrix-manifest') {
    $editorMatrixArgs = @($args | Select-Object -Skip 1)
    if ($editorMatrixArgs.Count -gt 0 -and $editorMatrixArgs[0] -eq '-') {
        $input | & $editorInstallation.python -B (Join-Path $PSScriptRoot 'edit_hook_matrix.py') --config $editorConfig --manifest @editorMatrixArgs
    } else {
        & $editorInstallation.python -B (Join-Path $PSScriptRoot 'edit_hook_matrix.py') --config $editorConfig --manifest @editorMatrixArgs
    }
} else {
    & $editorInstallation.python -B (Join-Path $PSScriptRoot 'batch_assistant.py') --config $editorConfig --no-ui @args
}
exit $LASTEXITCODE
