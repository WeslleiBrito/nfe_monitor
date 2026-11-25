import re
import subprocess
import tempfile
from pathlib import Path

from nfe_monitor.infrastructure.sefaz.parametros import Config


class ErroTransporte(RuntimeError):
    """Falha ao chamar a SEFAZ ou resposta HTTP inesperada."""


_LINHA_STATUS = re.compile(r"^HTTP/?\S*\s+(\d{3})\b")

# Existe só no Windows. Em outros sistemas, vale 0 (sem efeito).
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _envelope_distribuicao(cnpj: str, bloco_consulta: str, cfg: Config) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{cfg.tp_amb}</tpAmb>
          <cUFAutor>{cfg.uf_autor}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          {bloco_consulta}
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""


def montar_envelope(cnpj: str, ult_nsu: str, cfg: Config) -> str:
    bloco = f"""<distNSU>
            <ultNSU>{ult_nsu}</ultNSU>
          </distNSU>"""
    return _envelope_distribuicao(cnpj, bloco, cfg)


def montar_envelope_chave(cnpj: str, chave: str, cfg: Config) -> str:
    bloco = f"""<consChNFe>
            <chNFe>{chave}</chNFe>
          </consChNFe>"""
    return _envelope_distribuicao(cnpj, bloco, cfg)


def _decodificar(bruto: bytes) -> str:
    """Converte bytes em texto, tratando BOM UTF-8 e UTF-16 (o que o PowerShell grava)."""
    if bruto.startswith((b"\xff\xfe", b"\xfe\xff")):
        texto = bruto.decode("utf-16")
    else:
        texto = bruto.decode("utf-8-sig", errors="replace")
    return texto.replace("\x00", "").lstrip("\ufeff")


def _executar_powershell(entrada: Path, saida: Path, cfg: Config) -> None:
    try:
        r = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(cfg.script_ps),
                "-Thumbprint", cfg.thumbprint,
                "-Url", cfg.url,
                "-ArquivoEntrada", str(entrada),
                "-ArquivoSaida", str(saida),
                "-SoapAction", cfg.soap_action,
            ],
            capture_output=True,
            timeout=cfg.timeout_s,
            creationflags=_SEM_JANELA,
        )
    except subprocess.TimeoutExpired as e:
        raise ErroTransporte(f"Sem resposta da SEFAZ após {cfg.timeout_s}s") from e

    if r.returncode != 0:
        erro = _decodificar(r.stderr) + _decodificar(r.stdout)
        raise ErroTransporte(f"PowerShell falhou (código {r.returncode}):\n{erro.strip()}")

    if not saida.exists():
        raise ErroTransporte("O script PowerShell terminou sem gerar o arquivo de saída")


def _validar_resposta(texto: str) -> str:
    """Confere a linha de status e devolve somente o corpo XML."""
    texto = texto.lstrip()
    linha, _, corpo = texto.partition("\n")
    corpo = corpo.strip()

    m = _LINHA_STATUS.match(linha.strip())
    if not m:
        raise ErroTransporte(
            "Linha de status não reconhecida.\n"
            f"Início do arquivo: {texto[:200]!r}"
        )
    if m.group(1) != "200":
        raise ErroTransporte(f"HTTP {m.group(1)} da SEFAZ:\n{corpo[:500]}")
    if not corpo.startswith("<"):
        raise ErroTransporte(f"Corpo da resposta não é XML:\n{corpo[:300]}")
    return corpo


def enviar_soap(envelope: str, cfg: Config) -> str:
    """Envia um envelope SOAP já montado (e assinado, se for o caso) e devolve o corpo XML."""
    with tempfile.TemporaryDirectory() as pasta:
        entrada = Path(pasta) / "entrada.xml"
        saida = Path(pasta) / "saida.txt"

        entrada.write_text(envelope, encoding="utf-8")
        _executar_powershell(entrada, saida, cfg)
        texto = _decodificar(saida.read_bytes())

    return _validar_resposta(texto)


def consultar(cnpj: str, ult_nsu: str, cfg: Config) -> str:
    """Distribuição a partir do NSU (lotes)."""
    return enviar_soap(montar_envelope(cnpj, ult_nsu, cfg), cfg)


def consultar_chave(cnpj: str, chave: str, cfg: Config) -> str:
    """Distribuição pela chave (consChNFe). Devolve o XML completo se a ciência já foi registrada."""
    return enviar_soap(montar_envelope_chave(cnpj, chave, cfg), cfg)
