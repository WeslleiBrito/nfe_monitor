param(
    [Parameter(Mandatory = $true)][string]$Thumbprint,
    [Parameter(Mandatory = $true)][string]$ArquivoEntrada,
    [Parameter(Mandatory = $true)][string]$ArquivoSaida
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security

$loja = New-Object System.Security.Cryptography.X509Certificates.X509Store('My', 'CurrentUser')
$loja.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
try {
    $cert = $loja.Certificates |
        Where-Object { $_.HasPrivateKey -and $_.Thumbprint -eq $Thumbprint } |
        Select-Object -First 1
} finally {
    $loja.Close()
}
if (-not $cert) { throw "Certificado com thumbprint $Thumbprint não encontrado em CurrentUser\My" }

$chave = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
if (-not $chave) { throw 'Não foi possível obter a chave privada do certificado' }

# 1. Isola o bloco <evento> do envelope original
$texto = [IO.File]::ReadAllText($ArquivoEntrada, [Text.Encoding]::UTF8)
$m = [regex]::Match($texto, '<evento\s[^>]*>.*?</evento>', 'Singleline')
if (-not $m.Success) { throw 'Bloco <evento> não encontrado no XML' }
$eventoOriginal = $m.Value

# 2. Declara o namespace da NF-e no próprio <evento>
$eventoIsolado = $eventoOriginal -replace '^<evento\s', '<evento xmlns="http://www.portalfiscal.inf.br/nfe" '

$doc = New-Object System.Xml.XmlDocument
$doc.PreserveWhitespace = $true
$doc.LoadXml($eventoIsolado)

$infEvento = $doc.GetElementsByTagName('infEvento')[0]
if (-not $infEvento) { throw 'infEvento não encontrado' }
$id = $infEvento.GetAttribute('Id')

# 3. Assina
$signedXml = New-Object System.Security.Cryptography.Xml.SignedXml($doc)
$signedXml.SigningKey = $chave

$ref = New-Object System.Security.Cryptography.Xml.Reference
$ref.Uri = "#$id"
$ref.AddTransform((New-Object System.Security.Cryptography.Xml.XmlDsigEnvelopedSignatureTransform))
$ref.AddTransform((New-Object System.Security.Cryptography.Xml.XmlDsigC14NTransform))
$signedXml.AddReference($ref)

$keyInfo = New-Object System.Security.Cryptography.Xml.KeyInfo
$keyInfo.AddClause((New-Object System.Security.Cryptography.Xml.KeyInfoX509Data($cert)))
$signedXml.KeyInfo = $keyInfo

$signedXml.ComputeSignature()

$doc.DocumentElement.AppendChild($doc.ImportNode($signedXml.GetXml(), $true)) | Out-Null
$eventoAssinado = $doc.DocumentElement.OuterXml

# 4. Troca só o bloco <evento> no envelope
$textoFinal = $texto.Replace($eventoOriginal, $eventoAssinado)
[IO.File]::WriteAllText($ArquivoSaida, $textoFinal, (New-Object System.Text.UTF8Encoding($false)))
