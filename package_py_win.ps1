# Get the old working directory using Get-Location and Write-Host
$oldDir = Get-Location
Write-Host "The old working directory is: $oldDir"

# Get the directory path of the currently executing script using $PSScriptRoot
$scriptDir = $PSScriptRoot

# Change the working directory to the script directory using Set-Location or cd
Set-Location $scriptDir

# Print the new working directory using Get-Location and Write-Host
$newDir = Get-Location
Write-Host "The new working directory is: $newDir"
python -m pip install -e ./
