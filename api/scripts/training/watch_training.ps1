# Shows a training run's progress from its log, refreshed every 10 seconds.
# Closing THIS window is harmless: it only watches. The training window must stay open.
param([string]$Log = "runs\victim_lying_train.log")
$Host.UI.RawUI.WindowTitle = "RescueEye training progress (safe to close)"
while ($true) {
    $lines = (Get-Content $Log -Raw -ErrorAction SilentlyContinue) -split "`r|`n"
    $progress = $lines | Where-Object { $_ -match '^\s+\d+/\d+\s' } | Select-Object -Last 1
    $epochs = $lines | Where-Object { $_ -match '^\s+all\s' } | Select-Object -Last 3
    $problem = $lines | Where-Object { $_ -match 'Traceback|Error|\snan\s' } | Select-Object -Last 1
    Clear-Host
    "RescueEye training: teaching the person detector to find people lying down"
    "Started 14:40. About 40 minutes per epoch, 8 epochs, finishes around 20:30."
    ""
    "  Epoch   GPU mem   box loss   cls loss   dfl loss   boxes   size   progress"
    "  $progress"
    ""
    if ($epochs) { "Validation after each finished epoch (P, R, mAP50, mAP50-95):"; $epochs | ForEach-Object { "  $_" } }
    if ($problem) { ""; "PROBLEM: $problem" }
    if ($lines -match 'Done\. Compare') { ""; "FINISHED. Tell Claude: the training is done." }
    ""
    "Updated $(Get-Date -Format 'HH:mm:ss'). This window is safe to close; keep the TRAINING window open."
    Start-Sleep -Seconds 10
}
