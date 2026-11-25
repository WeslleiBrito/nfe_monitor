import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime

__all__ = ["AVISO_DIAS", "Certificado", "ErroCertificados", "extrair_cnpj",
           "listar", "selecionado", "validar_para_uso"]

AVISO_DIAS = 30

_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CN_ECNPJ = re.compile(r"CN=([^,]*?):(\d{14})")
_CN = re.compile(r"CN=([^,]+)")
_QUATORZE = re.compile(r"(?<!\d)(\d{14})(?!\d)")

# Usa X509Store direto: não depende da unidade Cert: (que falha no 5.1 aberto pelo pwsh 7).
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$lista = New-Object System.Collections.ArrayList
foreach ($loja in 'CurrentUser', 'LocalMachine') {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store('My', $loja)
    try {
        $store.Open('ReadOnly, OpenExistingOnly')
    } catch {
        continue
    }
    foreach ($c in $store.Certificates) {
        [void]$lista.Add([pscustomobject]@{
            thumbprint = $c.Thumbprint
            subject    = $c.Subject
            validade   = $c.NotAfter.ToString('yyyy-MM-dd HH:mm:ss')
            loja       = $loja
            chave      = [bool]$c.HasPrivateKey
        })
    }
    $store.Close()
}
ConvertTo-Json -InputObject @($lista) -Compress
"""


class ErroCertificados(RuntimeError):
    """Falha ao ler o repositório de certificados do Windows."""


@dataclass(frozen=True)
class Certificado:
    thumbprint: str
    subject: str
    validade: datetime
    cnpj: str | None
    nome: str | None
    loja: str = "CurrentUser"
    tem_chave: bool = True

    @property
    def dias_restantes(self) -> int:
        return (self.validade - datetime.now()).days

    @property
    def vencido(self) -> bool:
        return self.validade <= datetime.now()

    @property
    def titular(self) -> str:
        if self.nome:
            return self.nome
        m = _CN.search(self.subject)
        return m.group(1).strip() if m else self.subject

    @property
    def situacao(self) -> str:
        return "Vencido" if self.vencido else "Válido"

    @property
    def descricao(self) -> str:
        return (f"{self.titular} ({self.cnpj or 'sem CNPJ'}) - vence {self.validade:%d/%m/%Y}"
                f" [{self.loja}]")


def extrair_cnpj(subject: str) -> tuple[str | None, str | None]:
    """Devolve (cnpj, nome) do subject. e-CNPJ usa 'CN=RAZAO SOCIAL:CNPJ'."""
    m = _CN_ECNPJ.search(subject)
    if m:
        return m.group(2), m.group(1).strip() or None
    m = _QUATORZE.search(subject)
    return (m.group(1) if m else None), None


def _ambiente_limpo() -> dict:
    """Remove o PSModulePath herdado do PowerShell 7, que quebra o Windows PowerShell 5.1."""
    env = dict(os.environ)
    env.pop("PSModulePath", None)
    return env


def listar() -> list[Certificado]:
    codificado = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
            capture_output=True, timeout=30, creationflags=_SEM_JANELA, env=_ambiente_limpo(),
        )
    except subprocess.TimeoutExpired as e:
        raise ErroCertificados("Tempo esgotado ao listar certificados") from e

    erro = r.stderr.decode("utf-8", errors="replace").strip()
    if r.returncode != 0:
        raise ErroCertificados(erro or f"PowerShell saiu com código {r.returncode}")

    texto = r.stdout.decode("utf-8-sig", errors="replace").strip() or "[]"
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErroCertificados(f"Saída inesperada do PowerShell: {texto[:200]!r} {erro[:200]}") from e
    if isinstance(dados, dict):
        dados = [dados]

    # Mesmo certificado nas duas lojas: fica o que tem chave privada.
    unicos: dict[str, Certificado] = {}
    for d in dados:
        cnpj, nome = extrair_cnpj(d["subject"])
        c = Certificado(
            thumbprint=d["thumbprint"].upper(),
            subject=d["subject"],
            validade=datetime.strptime(d["validade"], "%Y-%m-%d %H:%M:%S"),
            cnpj=cnpj,
            nome=nome,
            loja=d.get("loja", "CurrentUser"),
            tem_chave=bool(d.get("chave", True)),
        )
        atual = unicos.get(c.thumbprint)
        if atual is None or (c.tem_chave and not atual.tem_chave):
            unicos[c.thumbprint] = c
    return sorted(unicos.values(), key=lambda c: c.validade, reverse=True)


def selecionado() -> Certificado | None:
    """Certificado salvo no config.json, se ainda estiver instalado."""
    from nfe_monitor.infrastructure import preferencias
    thumb = preferencias.carregar().thumbprint.strip().upper()
    if not thumb:
        return None
    return next((c for c in listar() if c.thumbprint == thumb), None)


def validar_para_uso() -> Certificado:
    cert = selecionado()
    if cert is None:
        raise ErroCertificados("Nenhum certificado configurado ou ele não está mais instalado. "
                               "Abra as Configurações e selecione um.")
    if cert.vencido:
        raise ErroCertificados(f"O certificado venceu em {cert.validade:%d/%m/%Y}.")
    return cert
