"""Teste da camada de certificados do Windows.

Somente leitura: lista os certificados do repositório Pessoal do usuário
atual, extrai o CNPJ, a validade e confirma se há chave privada.
Não faz chamadas de rede e não usa senha.
"""
import ctypes
import re
import sys
from ctypes import wintypes
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID, NameOID, ObjectIdentifier

if sys.platform != "win32":
    raise SystemExit("Este teste só roda no Windows.")

crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)

CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_STORE_READONLY_FLAG = 0x00008000
CERT_STORE_PROV_SYSTEM_W = 10
CERT_KEY_PROV_INFO_PROP_ID = 2
OID_CNPJ = ObjectIdentifier("2.16.76.1.3.3")


class CERT_CONTEXT(ctypes.Structure):
    _fields_ = [
        ("dwCertEncodingType", wintypes.DWORD),
        ("pbCertEncoded", ctypes.c_void_p),
        ("cbCertEncoded", wintypes.DWORD),
        ("pCertInfo", ctypes.c_void_p),
        ("hCertStore", ctypes.c_void_p),
    ]


crypt32.CertOpenStore.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_wchar_p,
]
crypt32.CertOpenStore.restype = ctypes.c_void_p

crypt32.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
crypt32.CertEnumCertificatesInStore.restype = ctypes.c_void_p

crypt32.CertGetCertificateContextProperty.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
]
crypt32.CertGetCertificateContextProperty.restype = wintypes.BOOL

crypt32.CertCloseStore.argtypes = [ctypes.c_void_p, wintypes.DWORD]
crypt32.CertCloseStore.restype = wintypes.BOOL


def tem_chave_privada(contexto: int) -> bool:
    tamanho = wintypes.DWORD(0)
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


def listar_certificados() -> list[tuple[x509.Certificate, bool]]:
    loja = crypt32.CertOpenStore(
        CERT_STORE_PROV_SYSTEM_W, 0, None,
        CERT_SYSTEM_STORE_CURRENT_USER | CERT_STORE_READONLY_FLAG, "MY",
    )
    if not loja:
        raise OSError(ctypes.get_last_error(), "Falha ao abrir o repositório MY.")

    encontrados = []
    try:
        contexto = crypt32.CertEnumCertificatesInStore(loja, None)
        while contexto:
            ctx = ctypes.cast(contexto, ctypes.POINTER(CERT_CONTEXT)).contents
            der = ctypes.string_at(ctx.pbCertEncoded, ctx.cbCertEncoded)
            cert = x509.load_der_x509_certificate(der)
            encontrados.append((cert, tem_chave_privada(contexto)))
            contexto = crypt32.CertEnumCertificatesInStore(loja, contexto)
    finally:
        crypt32.CertCloseStore(loja, 0)
    return encontrados


def nome_comum(nome: x509.Name) -> str:
    atributos = nome.get_attributes_for_oid(NameOID.COMMON_NAME)
    return atributos[0].value if atributos else nome.rfc4514_string()


def mascarar_cnpj(cnpj: str | None) -> str:
    if not cnpj:
        return "não encontrado"
    return f"{cnpj[:2]}.***.***/****-{cnpj[-2:]}"


def main() -> None:
    agora = datetime.now(timezone.utc)
    certificados = listar_certificados()
    print(f"Certificados no repositório Pessoal do usuário: {len(certificados)}\n")

    for i, (cert, tem_chave) in enumerate(certificados, start=1):
        dias = (cert.not_valid_after_utc - agora).days
        print(f"[{i}] {nome_comum(cert.subject)}")
        print(f"    CNPJ:            {mascarar_cnpj(extrair_cnpj(cert))}")
        print(f"    Emissor:         {nome_comum(cert.issuer)}")
        print(f"    Validade até:    {cert.not_valid_after_utc:%d/%m/%Y} ({dias} dias)")
        print(f"    Chave privada:   {'sim' if tem_chave else 'NÃO (não serve para mTLS)'}")
        print(f"    Thumbprint:      {cert.fingerprint(hashes.SHA1()).hex()[:8]}...")
        print()


if __name__ == "__main__":
    main()
