param(
    [string]$PublicUrl = 'http://192.168.32.5:8116'
)

$secret = Read-Host 'Enter Dify API Key for this server process (input is hidden)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($key)) {
        throw 'API Key cannot be empty'
    }
    $env:DIFY_API_KEY = $key
    $env:RECRUIT_PUBLIC_URL = $PublicUrl
    python server.py --host 0.0.0.0 --port 8116
}
finally {
    Remove-Item Env:DIFY_API_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
