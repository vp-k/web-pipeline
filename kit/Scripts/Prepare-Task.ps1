[CmdletBinding()] param([Parameter(Mandatory=$true)][string]$TaskId,[string]$Implementer='claude',[string]$RootPath='.')
$ErrorActionPreference='Stop';Import-Module (Join-Path $PSScriptRoot 'Pipeline.Common.psm1') -Force;Invoke-WebPipeline $RootPath @('prepare','--task',$TaskId,'--implementer',$Implementer)
