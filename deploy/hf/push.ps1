# Publish the current commit to a Hugging Face Space (Docker SDK).
#   powershell -ExecutionPolicy Bypass -File deploy\hf\push.ps1 -Space <hf-user>/<space-name>
# Git asks for your Hugging Face username and an access token with write rights; nothing is
# stored by this script. Needs git-lfs (the model files are larger than 10 MB).
param([Parameter(Mandatory = $true)][string]$Space)
$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\..\.."
$out = Join-Path $env:TEMP "solartriage-space"
if (Test-Path $out) { Remove-Item -Recurse -Force $out }

git clone "https://huggingface.co/spaces/$Space" $out
Get-ChildItem $out -Force | Where-Object Name -ne ".git" | Remove-Item -Recurse -Force

# Only what the container needs, as committed (no .venv, node_modules or local data).
git -C $root archive --format=tar HEAD backend frontend RL ml/splits | tar -x -C $out
Copy-Item "$root\deploy\hf\Dockerfile", "$root\deploy\hf\README.md" $out
Set-Content -Path "$out\.gitattributes" -Encoding ascii -Value @(
    "*.onnx filter=lfs diff=lfs merge=lfs -text",
    "*.pt filter=lfs diff=lfs merge=lfs -text",
    "*.npy filter=lfs diff=lfs merge=lfs -text",
    "*.png filter=lfs diff=lfs merge=lfs -text",
    "*.tar.gz filter=lfs diff=lfs merge=lfs -text"
)

Push-Location $out
git lfs install --local
git add -A
git commit -m "SolarTriage $(git -C $root rev-parse --short HEAD)"
git push
Pop-Location
Write-Host "Gata: https://huggingface.co/spaces/$Space (build-ul durează câteva minute)"
