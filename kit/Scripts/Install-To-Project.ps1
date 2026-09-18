[CmdletBinding(SupportsShouldProcess=$true)] param([Parameter(Mandatory=$true)][string]$TargetPath,[string]$RootPath)
$ErrorActionPreference='Stop'
if(-not $RootPath) { $RootPath=Join-Path $PSScriptRoot '..' }
$pipelineTarget=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TargetPath)
if($PSCmdlet.ShouldProcess($pipelineTarget,'Initialize pipeline without overwriting files')) {
 Import-Module (Join-Path $PSScriptRoot 'Pipeline.Common.psm1') -Force
 Invoke-WebPipeline $RootPath @('init','--target',$pipelineTarget)
}
