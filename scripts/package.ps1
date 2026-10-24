$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $project 'dist'
[IO.Directory]::CreateDirectory($destination) | Out-Null
$archive = Join-Path $destination 'window-pilot-0.1.0-source.zip'
if (Test-Path -LiteralPath $archive) { throw 'Archive already exists; inspect it before replacing' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
try {
    $files = @('README.md', 'NOTICE.md', 'pyproject.toml', '.gitignore', 'config.example.json')
    foreach ($folder in @('src', 'tests', 'scripts', 'docs', '.github', 'dsh-plugin')) {
        $base = Join-Path $project $folder
        if (Test-Path -LiteralPath $base) {
            $files += Get-ChildItem -LiteralPath $base -File -Recurse |
                Where-Object { $_.Extension -notin @('.pyc', '.pyo') -and $_.FullName -notmatch '[\\/]__pycache__[\\/]' } |
                ForEach-Object { $_.FullName.Substring($project.Length + 1) }
        }
    }
    foreach ($file in $files) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $project $file), $file.Replace('\', '/')) | Out-Null
    }
} finally { $zip.Dispose() }
Get-FileHash -LiteralPath $archive -Algorithm SHA256
Write-Output "Local source archive: $archive"
