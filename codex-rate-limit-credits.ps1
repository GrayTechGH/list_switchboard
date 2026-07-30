[CmdletBinding()]
param(
    [Parameter()]
    [string] $AuthPath
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($AuthPath)) {
    $codexAuthRoot = $env:CODEX_HOME
    if ([string]::IsNullOrWhiteSpace($codexAuthRoot)) {
        $codexAuthRoot = Join-Path $env:USERPROFILE '.codex'
    }

    $AuthPath = Join-Path $codexAuthRoot 'auth.json'
}

if (-not (Test-Path -LiteralPath $AuthPath -PathType Leaf)) {
    throw "Codex authentication file not found: $AuthPath"
}

try {
    $auth = Get-Content -LiteralPath $AuthPath -Raw | ConvertFrom-Json
}
catch {
    throw "Could not read Codex authentication data from '$AuthPath': $($_.Exception.Message)"
}

$accessToken = $auth.tokens.access_token
$accountId = $auth.tokens.account_id

if ([string]::IsNullOrWhiteSpace($accessToken)) {
    throw "The authentication file does not contain tokens.access_token."
}

if ([string]::IsNullOrWhiteSpace($accountId)) {
    throw "The authentication file does not contain tokens.account_id."
}

$headers = @{
    Authorization        = "Bearer $accessToken"
    'ChatGPT-Account-ID' = $accountId
    originator           = 'Codex Desktop'
}

try {
    $response = Invoke-RestMethod `
        -Method Get `
        -Uri 'https://chatgpt.com/backend-api/wham/rate-limit-reset-credits' `
        -Headers $headers
}
catch {
    throw "The ChatGPT credits request failed: $($_.Exception.Message)"
}

function Format-LocalTimestamp {
    param(
        [Parameter(Mandatory)]
        [string] $Timestamp
    )

    $parsedTimestamp = [DateTimeOffset]::Parse(
        $Timestamp,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal
    )
    $localTimestamp = $parsedTimestamp.ToLocalTime()

    return '{0} (UTC{1})' -f (
        $localTimestamp.ToString(
            "MMMM d, yyyy 'at' h:mm:ss tt",
            [Globalization.CultureInfo]::InvariantCulture
        )
    ), $localTimestamp.ToString('zzz')
}

$localTimeZone = [TimeZoneInfo]::Local
$localNow = [DateTimeOffset]::Now
$localTimeZoneName = if (
    $localTimeZone.IsDaylightSavingTime($localNow.DateTime)
) {
    $localTimeZone.DaylightName
}
else {
    $localTimeZone.StandardName
}

Write-Output "Available credits : $($response.available_count)"
Write-Output "Total earned      : $($response.total_earned_count)"
Write-Output (
    'Local time zone   : {0} (currently UTC{1})' -f (
        $localTimeZoneName,
        $localNow.ToString('zzz')
    )
)

$creditNumber = 0
foreach ($credit in @($response.credits)) {
    $creditNumber++
    Write-Output ''
    Write-Output "Credit $creditNumber"
    Write-Output "  Status  : $($credit.status)"
    Write-Output "  Granted : $(Format-LocalTimestamp -Timestamp $credit.granted_at)"
    Write-Output "  Expires : $(Format-LocalTimestamp -Timestamp $credit.expires_at)"
}
