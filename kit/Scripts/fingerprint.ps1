[CmdletBinding()] param([Parameter(Mandatory=$true)][string]$TaskId,[string]$RootPath='.')
$ErrorActionPreference='Stop';Import-Module (Join-Path $PSScriptRoot 'Pipeline.Common.psm1') -Force;Invoke-WebPipeline $RootPath @('fingerprint','--task',$TaskId)
