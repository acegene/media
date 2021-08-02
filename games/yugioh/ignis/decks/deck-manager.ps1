# deck-manager.ps1
#
# descr:

$ErrorActionPreference = "Stop"

function __backup {
    Param(
        [Parameter(Mandatory, Position=0)]
        [ValidateNotNullOrEmpty()]
        [object] $file,
        [Parameter(Mandatory, Position=1)]
        [ValidateNotNullOrEmpty()]
        [object] $dir_dest,
        [Parameter(Mandatory, Position=2)]
        [ValidateNotNullOrEmpty()]
        [object] $date,
        [Parameter(Mandatory, Position=3)]
        [ValidateSet('cp','mv')]
        [System.String] $operation
    )
    #### convert arguments
    $file = [System.IO.FileInfo]"$file"
    $dir_dest = [System.IO.DirectoryInfo]$dir_dest
    $date = "$date"
    #### generate backup file name
    $file_backup = "$($file.BaseName)-$($date)$($file.Extension)"
    #### perform backup
    Write-Host "EXEC: $($operation) '$($file)' '$($dir_dest)\$($file_backup)'"
    if ($operation -eq "mv"){
        Move-Item "$($file)" -Destination "$($dir_dest)\$($file_backup)"
    }elseif($operation -eq "cp"){
        Copy-Item "$($file)" -Destination "$($dir_dest)\$($file_backup)"
    }
}

function __copy_backup {
    Param(
        [Parameter(Mandatory, Position=0)]
        [ValidateNotNullOrEmpty()]
        [object] $file,
        [Parameter(Mandatory, Position=1)]
        [ValidateNotNullOrEmpty()]
        [object] $dir_src,
        [Parameter(Mandatory, Position=2)]
        [ValidateNotNullOrEmpty()]
        [object] $dir_dest,
        [Parameter(Mandatory, Position=3)]
        [ValidateNotNullOrEmpty()]
        [object] $dir_backup,
        [Parameter(Mandatory, Position=4)]
        [ValidateNotNullOrEmpty()]
        [object] $date
    )
    #### convert arguments
    $file = [System.IO.FileInfo]"$file"
    $dir_src = [System.IO.DirectoryInfo]$dir_src
    $dir_dest = [System.IO.DirectoryInfo]$dir_dest
    $dir_backup = [System.IO.DirectoryInfo]$dir_backup
    $date = "$date"
    if(Test-Path "$($dir_dest)\$($file.name)"){
        if(!((Get-FileHash "$($dir_src)\$($file.name)").Hash -eq (Get-FileHash "$($dir_dest)\$($file.name)").Hash)){
            Write-Host "WARNING: existing deck: $($dir_dest)\$($file.name)"
            $confirmation = Read-Host -Prompt "PROMPT: differences were found between $($dir_src)\$($file.name) and $($dir_dest)\$($file.name), backup and overwrite $($dir_dest)\$($file.name)? y/n"
            if ("$confirmation" -eq 'yes' -Or "$confirmation" -eq 'y') {
                __backup "$($dir_dest)\$($file.name)" "$dir_backup" "$date" "mv"
            }else{
                continue
            }
        }else{
            continue
        }
    }
    Write-Host "EXEC: cp '$($dir_src)\$($deck.name)' '$($dir_dest)\'"
    Copy-Item "$($dir_src)\$($deck.name)" -Destination "$($dir_dest)\"
}

function __import {
    #### print current and importable decks
    Write-Host "NOTE: current decks below:"
    foreach ($deck in $decks){Write-Host "      $($deck.name)"}
    Write-Host "NOTE: importable decks below:"
    foreach ($deck in $decks_src){Write-Host "      $($deck.name)"}
    #### prompt for whether to import decks
    $confirmation = Read-Host -Prompt "PROMPT: import above 'importable' decks? y/n"
    if ("$confirmation" -eq 'yes' -Or "$confirmation" -eq 'y') {
        #### import all decks, prompting to back them up if they already exist and are different
        foreach ($deck in $decks_src){
            __copy_backup "$($dir_deck_src)\$($deck.name)" $dir_deck_src $dir_deck $dir_deck_backup $date
        }
    }else{
        Write-Host "INFO: aborting..."
    }
}

function __save {
    #### print current decks
    Write-Host "NOTE: current decks below:"
    foreach ($deck in $decks){Write-Host "      $($deck.name)"}
    #### prompt for whether to import decks
    $confirmation = Read-Host -Prompt "PROMPT: save above decks? y/n"
    if ("$confirmation" -eq 'yes' -Or "$confirmation" -eq 'y') {
        #### save all decks, prompting to back them up if they already exist and are different
        foreach ($deck in $decks){
            __copy_backup "$($dir_deck)\$($deck.name)" $dir_deck $dir_deck_src $dir_deck_backup $date
        }
    }else{
        Write-Host "INFO: aborting..."
    }
}

function _deck_manager {
    #### hardcoded values
    $dir_this = $PSScriptRoot # not compatible with PS version < 3.0
    $dir_deck = [System.IO.DirectoryInfo]"C:\ProjectIgnis\deck"
    $dir_deck_backup = [System.IO.DirectoryInfo]"$($dir_this)\deck-bk"
    $dir_deck_src = [System.IO.DirectoryInfo]"$($dir_this)\deck"
    #### get date to use for file naming
    $date = "$((Get-Date).tostring("yyMMdd-hhmmss"))"
    #### checks if dirs exist
    if (!(Test-Path "$dir_deck")){
        throw "ERROR: cannot find: $dir_deck, aborting..."
    }elseif(!(Test-Path $dir_deck_backup)){
        throw "ERROR: cannot find: $dir_deck_backup, aborting..."
    }elseif(!(Test-Path $dir_deck_src)){
        throw "ERROR: cannot find: $dir_deck_src, aborting..."
    }
    #### collect decks from $decks and $decks_src into vars
    $decks_src = Get-Childitem $dir_deck_src # | Get-Childitem
    $decks = Get-Childitem $dir_deck # | Get-Childitem
    #### choose which script function to perform
    $choice = Read-Host -Prompt "PROMPT: import/i decks, save/s decks?"
    if ("$choice" -eq 'import' -Or "$choice" -eq 'i') {
        __import
    }elseif ("$choice" -eq 'save' -Or "$choice" -eq 's') {
        __save
    }else{
        Write-Host "INFO: aborting..."
    }
}

_deck_manager @args
