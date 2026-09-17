param(
    [string]$TargetUserSid = ''
)

$secret = Read-Host 'Enter the Dify workflow API Key (input is hidden)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($key)) {
        throw 'API Key cannot be empty'
    }
    if ($TargetUserSid) {
        $registry = [Microsoft.Win32.Registry]::Users.OpenSubKey("$TargetUserSid\Environment", $true)
        if (-not $registry) {
            throw 'Target user environment is unavailable'
        }
        try {
            $registry.SetValue('DIFY_API_KEY', $key, [Microsoft.Win32.RegistryValueKind]::String)
        }
        finally {
            $registry.Dispose()
        }
    }
    else {
        [Environment]::SetEnvironmentVariable('DIFY_API_KEY', $key, 'User')
    }
    Write-Host 'Dify API Key was saved for the current Windows user. Restart start.bat to apply it.' -ForegroundColor Green
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
