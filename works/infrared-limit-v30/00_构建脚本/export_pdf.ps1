# 用 Word COM 把 DOCX 导出为 PDF
param(
    [Parameter(Mandatory=$true)][string]$In,
    [Parameter(Mandatory=$true)][string]$Out
)
$ErrorActionPreference = "Stop"
$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($In, $false, $false)
    # wdFormatPDF = 17
    $doc.SaveAs([ref]$Out, [ref]17)
    $doc.Close($false)
    Write-Host "PDF -> $Out"
} finally {
    if ($word -ne $null) { $word.Quit() }
}
