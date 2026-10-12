$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$state=Join-Path $root 'runstate'
foreach($name in @('website','model')){
  $file=Join-Path $state ($name+'.pid')
  if(!(Test-Path -LiteralPath $file)){continue}
  $id=[int](Get-Content -LiteralPath $file -Raw)
  $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
  if($proc -and $proc.CommandLine -like "*$root*"){
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    Write-Output "Stopped ForgeMind $name process $id"
  }
  Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
}