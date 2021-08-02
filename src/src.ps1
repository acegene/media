# src.ps1
#
# descr: this file is sourced via this repo's init.ps1

$ErrorActionPreference = "Stop"

function _src {
    #### hardcoded values
    $path_this = $PSCommandPath # not compatible with PS version < 3.0
    $dir_this = $PSScriptRoot # not compatible with PS version < 3.0
    $dir_repo = "$(pushd $(git -C $($dir_this) rev-parse --show-toplevel); echo $PWD; popd)"
    # $dir_bin = "$($dir_repo)\bin"
    #### exports
    $global:GWSM = $dir_repo
    # $env:PATH += ";$($dir_bin)"
    #### aliases
    function global:gwsm {cd $global:GWSM; if($?){git status -sb}}
}

_src @args
