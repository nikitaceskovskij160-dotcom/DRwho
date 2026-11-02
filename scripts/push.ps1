# Pushes the working directory to GitHub via the REST API (no git required).
# Token is read from secrets.local.env (GITHUB_TOKEN, GITHUB_REPO). The remote tree is
# replaced by the local one, so files deleted locally are deleted on GitHub too.
param(
    [string]$Message = "Update",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot

function Read-Secret([string]$name) {
    $line = Get-Content (Join-Path $root "secrets.local.env") | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if (-not $line) { throw "$name not found in secrets.local.env" }
    return $line.Substring($name.Length + 1).Trim()
}

$token = Read-Secret "GITHUB_TOKEN"
$repo = Read-Secret "GITHUB_REPO"
$api = "https://api.github.com/repos/$repo"
$headers = @{ Authorization = "token $token"; "User-Agent" = "drwho-push"; Accept = "application/vnd.github+json" }

function Invoke-GitHub([string]$method, [string]$url, $body = $null) {
    $params = @{ Method = $method; Uri = $url; Headers = $headers }
    if ($null -ne $body) {
        $json = $body | ConvertTo-Json -Depth 10 -Compress
        $params.Body = [Text.Encoding]::UTF8.GetBytes($json)
        $params.ContentType = "application/json; charset=utf-8"
    }
    return Invoke-RestMethod @params
}

# --- collect files ---
$excludedDirs = @(".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".claude", "backups")
$excludedFiles = @(".env", "secrets.local.env")
$excludedPatterns = @("*.local.env", "*.db", "*.sqlite3", "*.pyc")

function Test-Included([IO.FileInfo]$file) {
    $rel = $file.FullName.Substring($root.Length + 1)
    $dirs = @(Split-Path $rel -Parent) -split "[\\/]" | Where-Object { $_ }
    foreach ($dir in $dirs) { if ($excludedDirs -contains $dir) { return $false } }
    if ($excludedFiles -contains $file.Name) { return $false }
    foreach ($pattern in $excludedPatterns) { if ($file.Name -like $pattern) { return $false } }
    return $true
}

$files = @(Get-ChildItem -Path $root -Recurse -File -Force | Where-Object { Test-Included $_ })

# Workflow files need the "workflow" token scope; without it GitHub rejects the whole tree
$scopes = (Invoke-WebRequest -UseBasicParsing -Uri $api -Headers $headers).Headers["X-OAuth-Scopes"]
if ($scopes -notmatch "\bworkflow\b") {
    Write-Warning "Token has no 'workflow' scope: skipping .github/workflows (add the scope to push CI)"
    $files = @($files | Where-Object { $_.FullName.Substring($root.Length + 1) -notlike ".github\workflows\*" })
}

# --- safety check: never push secrets ---
$secretValues = @()
foreach ($line in Get-Content (Join-Path $root "secrets.local.env")) {
    if ($line -match "^[A-Z_]*(TOKEN|KEY|PASSWORD|SECRET|DATABASE_URL)[A-Z_]*=(.{8,})$") {
        $secretValues += $Matches[2].Trim()
    }
}
foreach ($file in $files) {
    $text = [IO.File]::ReadAllText($file.FullName)
    foreach ($secret in $secretValues) {
        if ($text.Contains($secret)) { throw "Secret value found in $($file.FullName). Push aborted." }
    }
}

# --- ensure the branch exists (an empty repo has no refs) ---
$head = $null
try { $head = Invoke-GitHub GET "$api/git/ref/heads/$Branch" } catch { $head = $null }
if ($null -eq $head) {
    Write-Host "Empty repository: creating initial commit"
    $init = @{ message = "Initial commit"; content = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("# DRwho`n")); branch = $Branch }
    Invoke-GitHub PUT "$api/contents/.init" $init | Out-Null
    $head = Invoke-GitHub GET "$api/git/ref/heads/$Branch"
}
$parentSha = $head.object.sha

# --- blobs and tree ---
$tree = @()
foreach ($file in $files) {
    $rel = $file.FullName.Substring($root.Length + 1).Replace("\", "/")
    $content = [Convert]::ToBase64String([IO.File]::ReadAllBytes($file.FullName))
    $blob = Invoke-GitHub POST "$api/git/blobs" @{ content = $content; encoding = "base64" }
    $tree += @{ path = $rel; mode = "100644"; type = "blob"; sha = $blob.sha }
    Write-Host "  + $rel"
}
$newTree = Invoke-GitHub POST "$api/git/trees" @{ tree = $tree }
$commit = Invoke-GitHub POST "$api/git/commits" @{ message = $Message; tree = $newTree.sha; parents = @($parentSha) }
Invoke-GitHub PATCH "$api/git/refs/heads/$Branch" @{ sha = $commit.sha } | Out-Null

Write-Host "Pushed $($files.Count) files to $repo@$Branch, commit $($commit.sha)"
