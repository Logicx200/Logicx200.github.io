# Run every self-check with one command and report a single verdict.
#
# ASCII ONLY. Windows PowerShell 5.1 parses .ps1 as the system ANSI code page
# unless the file carries a UTF-8 BOM, and a non-ASCII comment can silently
# break the parser. Keep this file pure ASCII.
#
# Why this is a one-line wrapper around a node runner:
#   this session's file sandbox denies BOTH `node x | Out-Null`
#   (a pipe whose left side is a native command) and Start-Process.
#   `node` spawning `node` with stdio:'inherit' is the one approach that works,
#   so test/all.mjs owns the actual orchestration and this file just calls it.
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File verify.ps1

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

node test/all.mjs
$code = $LASTEXITCODE

Pop-Location
exit $code
