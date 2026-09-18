function Invoke-WebPipeline {
 param([string]$RootPath='.',[Parameter(Mandatory=$true)][string[]]$Arguments)
 $pipelineRoot=(Resolve-Path -LiteralPath $RootPath).Path
 $pipelineEngineRoot=Split-Path -Parent $PSScriptRoot
 $python=if($env:PYTHON){$env:PYTHON}else{'python'}
 Push-Location -LiteralPath $pipelineEngineRoot
 try {
  & $python -m web_pipeline --root $pipelineRoot @Arguments
  if($LASTEXITCODE -ne 0){throw "web_pipeline failed with exit code $LASTEXITCODE"}
 } finally { Pop-Location }
}
Export-ModuleMember -Function Invoke-WebPipeline
