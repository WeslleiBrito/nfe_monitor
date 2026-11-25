try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$ErrorActionPreference = 'Stop'

$loja = New-Object System.Security.Cryptography.X509Certificates.X509Store('My', 'CurrentUser')
$loja.Open('ReadOnly')
try {
    $lista = @(
        $loja.Certificates |
            Where-Object { $_.HasPrivateKey } |
            ForEach-Object {
                [pscustomobject]@{
                    Thumbprint = $_.Thumbprint
                    Titular    = $_.Subject
                    Validade   = $_.NotAfter.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                }
            }
    )
} finally {
    $loja.Close()
}

ConvertTo-Json -InputObject $lista -Compress
