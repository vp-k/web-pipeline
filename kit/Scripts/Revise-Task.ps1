[CmdletBinding()] param([Parameter(Mandatory=$true)][string]$TaskId,[Parameter(Mandatory=$true)][string]$Reason,[string]$RootPath='.')
$ErrorActionPreference='Stop';Import-Module (Join-Path $PSScriptRoot 'Pipeline.Common.psm1') -Force;Invoke-WebPipeline $RootPath @('revise','--task',$TaskId,'--reason',$Reason)
