param(
    [Parameter(Mandatory)][string]$Thumbprint,
    [Parameter(Mandatory)][string]$Url,
    [Parameter(Mandatory)][string]$ArquivoEntrada,
    [Parameter(Mandatory)][string]$ArquivoSaida,
    [Parameter(Mandatory)][string]$SoapAction
)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$loja = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    'My', [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$loja.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
try {
    $cert = $loja.Certificates |
        Where-Object { $_.HasPrivateKey -and $_.Thumbprint -eq $Thumbprint } |
        Select-Object -First 1
} finally {
    $loja.Close()
}

if (-not $cert) {
    Write-Error 'Certificado com o thumbprint informado não encontrado.'
    exit 2
}

$corpo = [IO.File]::ReadAllText($ArquivoEntrada, [Text.Encoding]::UTF8)
$ct = "application/soap+xml; charset=utf-8; action=`"$SoapAction`""

try {
    $resp = Invoke-WebRequest -Uri $Url -Method Post -Body $corpo `
        -ContentType $ct `
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
    }
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $conteudo = $_.ErrorDetails.Message
    }
    $conteudo = "[status=$status] " + $conteudo
}

# Primeira linha: status HTTP. Demais linhas: corpo da resposta.
$conteudoFinal = "HTTP $status`n$conteudo"
[System.IO.File]::WriteAllText($ArquivoSaida, $conteudoFinal, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "OK HTTP $status"
