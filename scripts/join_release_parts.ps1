$ErrorActionPreference = 'Stop'
$base = 'ForgeMind-Portable-Windows-Mac-2026-10-12.zip'
$parts = @("$base.001", "$base.002", "$base.003")
$out = "$base"
$stream = [IO.File]::Create($out)
try {
    foreach ($part in $parts) {
        if (-not (Test-Path -LiteralPath $part)) { throw "Missing release part: $part" }
        $input = [IO.File]::OpenRead($part)
        try { $input.CopyTo($stream) } finally { $input.Dispose() }
    }
} finally { $stream.Dispose() }
$actual = (Get-Item -LiteralPath $out).Length
if ($actual -ne 4721365816) { throw "Combined ZIP size mismatch: $actual" }
Write-Output "Combined ZIP ready: $out ($actual bytes)"
