$root = $PSScriptRoot
$port = 8080
$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://localhost:$port/")
$listener.Start()
Write-Host "Serving at http://localhost:$port"

$mimeTypes = @{
  '.html' = 'text/html; charset=utf-8'
  '.js'   = 'application/javascript'
  '.json' = 'application/json'
  '.css'  = 'text/css'
  '.png'  = 'image/png'
  '.ico'  = 'image/x-icon'
  '.svg'  = 'image/svg+xml'
}

# Read API key from config.js
$configContent = Get-Content (Join-Path $root 'config.js') -Raw
$apiKey = ''
if ($configContent -match "API_KEY:\s*'([^']+)'") { $apiKey = $Matches[1] }

$webClient = [System.Net.WebClient]::new()

while ($listener.IsListening) {
  $ctx = $listener.GetContext()
  $req = $ctx.Request
  $res = $ctx.Response
  $res.Headers.Add('Access-Control-Allow-Origin', '*')

  $rawPath = $req.Url.AbsolutePath.TrimStart('/')
  if ($rawPath -eq '') { $rawPath = 'index.html' }

  # Proxy /proxy/* -> https://api.football-data.org/v4/*
  if ($rawPath.StartsWith('proxy/')) {
    $apiPath = $rawPath.Substring(6)
    $query = $req.Url.Query
    $upstreamUrl = "https://api.football-data.org/v4/$apiPath$query"
    try {
      $wc = [System.Net.WebClient]::new()
      $wc.Headers.Add('X-Auth-Token', $apiKey)
      $wc.Headers.Add('Accept', 'application/json')
      $bytes = $wc.DownloadData($upstreamUrl)
      $res.ContentType = 'application/json'
      $res.ContentLength64 = $bytes.Length
      $res.OutputStream.Write($bytes, 0, $bytes.Length)
    } catch [System.Net.WebException] {
      $httpEx = $_.Exception.Response
      $res.StatusCode = if ($httpEx) { [int]$httpEx.StatusCode } else { 502 }
      $body = [System.Text.Encoding]::UTF8.GetBytes($_.Exception.Message)
      $res.OutputStream.Write($body, 0, $body.Length)
    }
    $res.OutputStream.Close()
    continue
  }

  $filePath = Join-Path $root $rawPath
  if (Test-Path $filePath -PathType Leaf) {
    $ext = [System.IO.Path]::GetExtension($filePath)
    $res.ContentType = if ($mimeTypes[$ext]) { $mimeTypes[$ext] } else { 'application/octet-stream' }
    $bytes = [System.IO.File]::ReadAllBytes($filePath)
    $res.ContentLength64 = $bytes.Length
    $res.OutputStream.Write($bytes, 0, $bytes.Length)
  } else {
    $res.StatusCode = 404
    $body = [System.Text.Encoding]::UTF8.GetBytes("Not found: $rawPath")
    $res.OutputStream.Write($body, 0, $body.Length)
  }
  $res.OutputStream.Close()
}
