param(
    [string[]]$Inputs = @("data/evaluation_sets/synthetic_example.json"),
    [string]$Config = "configs/example.json",
    [string]$Database = "data/results/platform.sqlite3",
    [string]$Output = "data/results/exports",
    [switch]$AllowExternalModelCalls
)
$batchArgs = @("-m", "ai_reliability.experiments.batch") + $Inputs + @("--config", $Config, "--db", $Database, "--output", $Output)
if ($AllowExternalModelCalls) { $batchArgs += "--allow-external-model-calls" }
& "$PSScriptRoot/../.venv/Scripts/python.exe" @batchArgs
exit $LASTEXITCODE
