"""Consulta de status ao NFeDistribuicaoDFe em homologação (tpAmb=2).

Localiza o certificado no repositório Pessoal do usuário pelo CNPJ e envia
UMA requisição com distNSU=0 via WinHTTP (Schannel). Não grava nada.

Uso (na raiz do projeto):
    python tests\\teste_distribuicao_hom.py --cnpj 00000000000000
"""
import argparse
import ctypes
import re
import sys
from ctypes import wintypes

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, ObjectIdentifier

if sys.platform != "win32":
    raise SystemExit("Este teste só roda no Windows.")

crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
winhttp = ctypes.WinDLL("winhttp", use_last_error=True)

HANDLE = ctypes.c_void_p
DWORD = wintypes.DWORD
BOOL = wintypes.BOOL

# Constantes do Windows
CERT_STORE_PROV_SYSTEM_W = 10
CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_STORE_READONLY_FLAG = 0x00008000
CERT_KEY_PROV_INFO_PROP_ID = 2
WINHTTP_ACCESS_TYPE_DEFAULT_PROXY = 0
WINHTTP_FLAG_SECURE = 0x00800000
WINHTTP_OPTION_CLIENT_CERT_CONTEXT = 105
WINHTTP_OPTION_SECURE_PROTOCOLS = 84
WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 = 0x00000800
WINHTTP_QUERY_STATUS_CODE = 19
WINHTTP_QUERY_FLAG_NUMBER = 0x20000000

HOST = "hom1.nfe.fazenda.gov.br"
CAMINHO = "/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
ACTION = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
OID_CNPJ = ObjectIdentifier("2.16.76.1.3.3")


class CERT_CONTEXT(ctypes.Structure):
    _fields_ = [
        ("dwCertEncodingType", DWORD),
        ("pbCertEncoded", ctypes.c_void_p),
        ("cbCertEncoded", DWORD),
        ("pCertInfo", ctypes.c_void_p),
        ("hCertStore", ctypes.c_void_p),
    ]


# --- Assinaturas do crypt32 ---
crypt32.CertOpenStore.argtypes = [
    ctypes.c_void_p, DWORD, ctypes.c_void_p, DWORD, wintypes.LPCWSTR,
]
crypt32.CertOpenStore.restype = HANDLE
crypt32.CertEnumCertificatesInStore.argtypes = [HANDLE, HANDLE]
crypt32.CertEnumCertificatesInStore.restype = HANDLE
crypt32.CertDuplicateCertificateContext.argtypes = [HANDLE]
crypt32.CertDuplicateCertificateContext.restype = HANDLE
crypt32.CertFreeCertificateContext.argtypes = [HANDLE]
crypt32.CertFreeCertificateContext.restype = BOOL
crypt32.CertCloseStore.argtypes = [HANDLE, DWORD]
crypt32.CertCloseStore.restype = BOOL
crypt32.CertGetCertificateContextProperty.argtypes = [
    HANDLE, DWORD, ctypes.c_void_p, ctypes.POINTER(DWORD),
]
crypt32.CertGetCertificateContextProperty.restype = BOOL

# --- Assinaturas do winhttp ---
winhttp.WinHttpOpen.argtypes = [
    wintypes.LPCWSTR, DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD,
]
winhttp.WinHttpOpen.restype = HANDLE
winhttp.WinHttpSetTimeouts.argtypes = [HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
winhttp.WinHttpSetTimeouts.restype = BOOL
winhttp.WinHttpConnect.argtypes = [HANDLE, wintypes.LPCWSTR, wintypes.WORD, DWORD]
winhttp.WinHttpConnect.restype = HANDLE
winhttp.WinHttpOpenRequest.argtypes = [
    HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.LPCWSTR, ctypes.c_void_p, DWORD,
]
winhttp.WinHttpOpenRequest.restype = HANDLE
winhttp.WinHttpSetOption.argtypes = [HANDLE, DWORD, ctypes.c_void_p, DWORD]
winhttp.WinHttpSetOption.restype = BOOL
winhttp.WinHttpSendRequest.argtypes = [
    HANDLE, wintypes.LPCWSTR, DWORD, ctypes.c_void_p, DWORD, DWORD, ctypes.c_void_p,
]
winhttp.WinHttpSendRequest.restype = BOOL
winhttp.WinHttpReceiveResponse.argtypes = [HANDLE, ctypes.c_void_p]
winhttp.WinHttpReceiveResponse.restype = BOOL
winhttp.WinHttpQueryHeaders.argtypes = [
    HANDLE, DWORD, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(DWORD), ctypes.c_void_p,
]
winhttp.WinHttpQueryHeaders.restype = BOOL
winhttp.WinHttpQueryDataAvailable.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
winhttp.WinHttpQueryDataAvailable.restype = BOOL
winhttp.WinHttpReadData.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)]
winhttp.WinHttpReadData.restype = BOOL
winhttp.WinHttpCloseHandle.argtypes = [HANDLE]
winhttp.WinHttpCloseHandle.restype = BOOL


def erro_win(operacao: str) -> OSError:
    codigo = ctypes.get_last_error()
    return OSError(codigo, f"{operacao} falhou (código Windows {codigo})")


def tem_chave_privada(contexto: int) -> bool:
    tamanho = DWORD(0)
    return bool(crypt32.CertGetCertificateContextProperty(
        contexto, CERT_KEY_PROV_INFO_PROP_ID, None, ctypes.byref(tamanho),
    ))


def extrair_cnpj(certificado: x509.Certificate) -> str | None:
    try:
        san = certificado.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        ).value
    except x509.ExtensionNotFound:
        return None
    for nome in san:
        if isinstance(nome, x509.OtherName) and nome.type_id == OID_CNPJ:
            achados = re.findall(rb"\d{14}", nome.value)
            if achados:
                return achados[0].decode()
    return None


def localizar_certificado(cnpj: str) -> int:
    """Retorna um CERT_CONTEXT duplicado (liberar com CertFreeCertificateContext)."""
    loja = crypt32.CertOpenStore(
        CERT_STORE_PROV_SYSTEM_W, 0, None,
        CERT_SYSTEM_STORE_CURRENT_USER | CERT_STORE_READONLY_FLAG, "MY",
    )
    if not loja:
        raise erro_win("CertOpenStore")
    try:
        ctx = crypt32.CertEnumCertificatesInStore(loja, None)
        while ctx:
            info = ctypes.cast(ctx, ctypes.POINTER(CERT_CONTEXT)).contents
            der = ctypes.string_at(info.pbCertEncoded, info.cbCertEncoded)
            certificado = x509.load_der_x509_certificate(der)
            if extrair_cnpj(certificado) == cnpj and tem_chave_privada(ctx):
                escolhido = crypt32.CertDuplicateCertificateContext(ctx)
                crypt32.CertFreeCertificateContext(ctx)
                return escolhido
            ctx = crypt32.CertEnumCertificatesInStore(loja, ctx)
        raise LookupError(
            f"Nenhum certificado com chave privada para o CNPJ {cnpj[:2]}***********"
        )
    finally:
        crypt32.CertCloseStore(loja, 0)


def montar_envelope(cnpj: str, uf: str) -> bytes:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>2</tpAmb>
          <cUFAutor>{uf}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <distNSU>
            <ultNSU>000000000000000</ultNSU>
          </distNSU>
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""
    return xml.encode("utf-8")


def enviar(corpo: bytes, cert_ctx: int) -> tuple[int, bytes]:
    sessao = winhttp.WinHttpOpen(
        "nfe_monitor/teste", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, None, None, 0,
    )
    if not sessao:
        raise erro_win("WinHttpOpen")
    try:
        protocolos = DWORD(WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2)
        winhttp.WinHttpSetOption(
            sessao, WINHTTP_OPTION_SECURE_PROTOCOLS,
            ctypes.addressof(protocolos), ctypes.sizeof(protocolos),
        )
        winhttp.WinHttpSetTimeouts(sessao, 15000, 15000, 30000, 60000)

        conexao = winhttp.WinHttpConnect(sessao, HOST, 443, 0)
        if not conexao:
            raise erro_win("WinHttpConnect")
        try:
            req = winhttp.WinHttpOpenRequest(
                conexao, "POST", CAMINHO, None, None, None, WINHTTP_FLAG_SECURE,
            )
            if not req:
                raise erro_win("WinHttpOpenRequest")
            try:
                if not winhttp.WinHttpSetOption(
                    req, WINHTTP_OPTION_CLIENT_CERT_CONTEXT,
                    cert_ctx, 0,
                ):
                    raise erro_win("WinHttpSetOption(certificado de cliente)")

                cabecalhos = (
                    "Content-Type: application/soap+xml; charset=utf-8; "
                    f'action="{ACTION}"'
                )
                if not winhttp.WinHttpSendRequest(
                    req, cabecalhos, 0xFFFFFFFF, corpo, len(corpo), len(corpo), None,
                ):
                    raise erro_win("WinHttpSendRequest")
                if not winhttp.WinHttpReceiveResponse(req, None):
                    raise erro_win("WinHttpReceiveResponse")

                status = DWORD(0)
                tamanho = DWORD(ctypes.sizeof(status))
                winhttp.WinHttpQueryHeaders(
                    req, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, None,
                    ctypes.addressof(status), ctypes.byref(tamanho), None,
                )

                resposta = bytearray()
                disponivel = DWORD(0)
                while True:
                    if not winhttp.WinHttpQueryDataAvailable(req, ctypes.byref(disponivel)):
                        raise erro_win("WinHttpQueryDataAvailable")
                    if disponivel.value == 0:
                        break
                    buf = ctypes.create_string_buffer(disponivel.value)
                    lidos = DWORD(0)
                    if not winhttp.WinHttpReadData(
                        req, buf, disponivel.value, ctypes.byref(lidos),
                    ):
                        raise erro_win("WinHttpReadData")
                    resposta += buf.raw[: lidos.value]
                return status.value, bytes(resposta)
            finally:
                winhttp.WinHttpCloseHandle(req)
        finally:
            winhttp.WinHttpCloseHandle(conexao)
    finally:
        winhttp.WinHttpCloseHandle(sessao)


def resumir(corpo: bytes) -> None:
    texto = corpo.decode("utf-8", errors="replace")
    cstat = re.search(r"<cStat>(\d+)</cStat>", texto)
    motivo = re.search(r"<xMotivo>(.*?)</xMotivo>", texto, re.S)
    ult = re.search(r"<ultNSU>(\d+)</ultNSU>", texto)
    print(f"  cStat:    {cstat.group(1) if cstat else 'não encontrado'}")
    print(f"  xMotivo:  {motivo.group(1).strip() if motivo else 'não encontrado'}")
    print(f"  ultNSU:   {ult.group(1) if ult else 'não encontrado'}")
    print("\nTrecho inicial da resposta:")
    print(texto[:800])


def main() -> None:
    parser = argparse.ArgumentParser(description="Status do NFeDistribuicaoDFe em homologação.")
    parser.add_argument("--cnpj", required=True, help="CNPJ da empresa (14 dígitos)")
    parser.add_argument("--uf", default="29", help="Código IBGE da UF (BA = 29)")
    args = parser.parse_args()

    cnpj = re.sub(r"\D", "", args.cnpj)
    if len(cnpj) != 14:
        raise SystemExit("CNPJ deve ter 14 dígitos.")

    print("Localizando certificado no repositório...")
    cert_ctx = localizar_certificado(cnpj)
    try:
        print(f"Enviando consulta para {HOST} (tpAmb=2, distNSU=0)...")
        status, corpo = enviar(montar_envelope(cnpj, args.uf), cert_ctx)
    finally:
        crypt32.CertFreeCertificateContext(cert_ctx)

    print(f"\nHTTP {status}")
    resumir(corpo)


if __name__ == "__main__":
    main()
