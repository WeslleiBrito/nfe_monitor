param(
    [Parameter(Mandatory)][string]$Cnpj,
    [Parameter(Mandatory)][string]$Url,
    [Parameter(Mandatory)][string]$ArquivoEntrada,
    [Parameter(Mandatory)][string]$ArquivoSaida,
    [Parameter(Mandatory)][string]$SoapAction
)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Lê o repositório pela API .NET, sem depender do drive Cert:
$loja = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    "My", [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$loja.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)

$cert = $loja.Certificates |
    Where-Object { $_.HasPrivateKey -and $_.Subject -match $Cnpj } |
    Select-Object -First 1

$loja.Close()

if (-not $cert) {
    Write-Error "Certificado com o CNPJ informado não encontrado."
    exit 2
}

$corpo = [IO.File]::ReadAllText($ArquivoEntrada, [Text.Encoding]::UTF8)

try {
    $resp = Invoke-WebRequest -Uri $Url -Method Post -Body $corpo `
        -ContentType "application/soap+xml; charset=utf-8" `
        -Headers @{ SOAPAction = $SoapAction } `
        -Certificate $cert -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
    $status = [int]$resp.StatusCode
    $conteudo = $resp.Content
}
catch {
    $status = 0
    $conteudo = $_.Exception.Message
    if ($_.Exception.Response) {
        $status = [int]$_.Exception.Response.StatusCode
        $stream = $_.Exception.Response.GetResponseStream()
        $leitor = New-Object IO.StreamReader($stream)
        $conteudo = $leitor.ReadToEnd()
    }
}

[IO.File]::WriteAllText($ArquivoSaida, "HTTP $status`n$conteudo", [Text.Encoding]::UTF8)
Write-Output "OK"
