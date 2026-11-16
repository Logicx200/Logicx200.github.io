# gap-check.ps1 -- acceptance readings for the upstream-gap capabilities (task-10).
#
# Drives the PRODUCTION page through the documented dev channels and reads the model
# parameters IN-FRAME (the page samples them in `beforeModelUpdate`, then reports over
# the web-message channel).  Nothing here opens a second pet window: it is the panel's
# own pet window, and at the end every channel file is removed so the page returns to
# plain production polling.
#
#   pet\host\force-state.json   -> window.postMessage({type:'pet-force',payload})
#   pet\host\watch.json         -> window.postMessage({type:'pet-watch',payload})
#   pet\host\page-message.json  <- the page's report (web message)
#
# Pure ASCII on purpose (PS 5.1 reads a BOM-less .ps1 as ANSI); Chinese labels are
# never written from here - only the ASCII capability keys are.
param(
  [string]$Here = $PSScriptRoot,
  [string]$Out = (Join-Path (Split-Path $PSScriptRoot -Parent) 'showcase\task10-gap-check.txt')
)
$force = Join-Path $Here 'force-state.json'
$watch = Join-Path $Here 'watch.json'
$msg = Join-Path $Here 'page-message.json'
$lines = New-Object System.Collections.ArrayList
$script:nonce = 0

# The host only pushes a channel file when its CONTENT changes, and it reads it every
# 300 ms tick - so (a) every payload needs a nonce to be distinct, and (b) the write
# must be atomic (temp + move), otherwise the host can read a half-written file.
function Write-Channel([string]$path, [string]$json) {
  $script:nonce += 1
  $tmp = "$path.tmp"
  [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -LiteralPath $tmp -Destination $path -Force
}
function Send-Force([string]$json) {
  $body = $json.Trim()
  $withNonce = if ($body -eq '{}') { '{"n":' + $script:nonce + '}' } else { $body.Substring(0, $body.Length - 1) + ',"n":' + $script:nonce + '}' }
  Write-Channel $force $withNonce
  Start-Sleep -Milliseconds 1200
}
function Run-Watch([int]$ms) {
  Remove-Item -LiteralPath $msg -Force -ErrorAction SilentlyContinue
  Write-Channel $watch ('{"ms":' + $ms + ',"n":' + $script:nonce + '}')
  Start-Sleep -Milliseconds ($ms + 2200)
  if (-not (Test-Path -LiteralPath $msg)) { return $null }
  try { return ([System.IO.File]::ReadAllText($msg, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json).motionWatch } catch { return $null }
}
function Show([string]$title, $w) {
  if ($null -eq $w) { [void]$lines.Add("$title : NO REPORT"); Write-Host "$title : NO REPORT"; return }
  # first-sample snapshot: one-shot actions and the 1.6 s error face are gone by the
  # end of the sampling window, so that is the reading that proves they were applied.
  $r = if ($w.firstReactions) { $w.firstReactions } else { $w.reactions }
  $ap = if ($w.firstApplied) { $w.firstApplied } else { $w.applied }
  $props = if ($r -and $r.userProps) { ($r.userProps -join ',') } else { '-' }
  $anim = if ($r -and $r.anim) { $r.anim.name } else { '-' }
  $ovr = if ($r -and $r.override) { $r.override.act + $(if ($r.override.exclusive) { '(exclusive)' } else { '' }) } else { '-' }
  $appliedProps = if ($ap -and $ap.props) { ($ap.props -join ',') } else { '-' }
  $moving = if ($w.moving) { ($w.moving -join ',') } else { '(none)' }
  $text = "$title`n  userProps=[$props] anim=[$anim] override=[$ovr] applied.props=[$appliedProps] exclusive=[$($ap.exclusive)] lowPower=[$($r.lowPower)]`n  params moving: $moving  |  playing=$($w.playingSeen) queuedMax=$($w.queuedMax) idleGroup=$($w.meta.idleGroup) motiveGroups=$($w.meta.motionGroupsLoaded)"
  [void]$lines.Add($text)
  Write-Host $text
}

Write-Host '=== task-10 upstream-gap acceptance readings ==='
# start from a clean channel: a leftover watch.json from an earlier run would be
# pushed once on the first tick and its (long) report would land in the middle of
# this run.
Remove-Item -LiteralPath $force -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $watch -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $msg -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1500
# 0. baseline: which tables exist
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check baseline","clearBubble":true,"props":[]}'
$w = Run-Watch 2200
if ($null -ne $w -and $null -ne $w.reactions) {
  $t = $w.reactions.tables
  $text = "tables: decor=$($t.decor) scenes=$($t.scenes) actions=$($t.actions)"
  [void]$lines.Add($text); Write-Host $text
}
# 1. decoration: one key per slot (glasses + sticker + a scene) -- all three should stick
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check props","props":["glassesRound","stickerCat","parfait"]}'
Show 'P1 three decorations across three slots' (Run-Watch 2600)
# 2. mutual exclusion: two keys of the same slot -> only the last survives
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check exclusive slot","props":["glassesRound","sunglasses"]}'
Show 'P2 same slot twice -> one survives' (Run-Watch 2600)
# 3. prerequisite: clawRecolor implies claw; phoneRecolor implies the phone device
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check needs","props":["clawRecolor"]}'
Show 'P3 clawRecolor -> claw auto-added' (Run-Watch 2600)
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check device","props":["phoneRecolor"]}'
Show 'P4 phoneRecolor -> phone (openLid hold) auto-added' (Run-Watch 3200)
# 4. one-shot actions: act() composition + duration accounting
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check act","props":[],"act":"doubleV"}'
Show 'A1 act(doubleV) 2800 ms' (Run-Watch 2400)
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check act2","act":"love"}'
Show 'A2 act(love) 3200 ms + pulse' (Run-Watch 2600)
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check act3","act":"omurice"}'
Show 'A3 act(omurice) 6200 ms + ketchup motion' (Run-Watch 2600)
# 5. exclusive error: props are remembered but NOT applied, device put away
$nowMs = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
Send-Force ('{"state":"error","label":"error","color":"#F85149","pose":"gloomy","detail":"err","reason":"gap-check exclusive","props":["glassesRound","parfait"],"signals":{"lastError":{"name":"edit","error":"FsError/FS_STALE_VERSION","at":' + $nowMs + '}}}')
Show 'E1 tool error -> props:[] + exclusive' (Run-Watch 2200)
# 6. low power
Send-Force '{"state":"idle","label":"idle","color":"#9DA7B3","pose":"idle","detail":"","reason":"gap-check perf","props":[],"lowPower":true}'
Show 'L1 low power (ticker 20 fps, no idle brain)' (Run-Watch 2200)

# ---- restore: drop both channel files, the host then pushes payload=null once ----
Remove-Item -LiteralPath $force -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $watch -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 900
$lines | Set-Content -LiteralPath $Out -Encoding UTF8
Write-Host ('gap-check: readings -> ' + $Out)
