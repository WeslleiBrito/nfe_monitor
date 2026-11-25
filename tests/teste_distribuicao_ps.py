"""Consulta de status ao NFeDistribuicaoDFe em homologação (tpAmb=2, distNSU=0).

Usa o PowerShell (Invoke-WebRequest -Certificate) para fazer o mTLS com o
certificado do repositório do usuário. Uma única chamada, sem gravação.

Uso:
    python tests\\teste_distribuicao_ps.py --cnpj 00000000000000
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

URL = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
ACTION = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
SCRIPT = Path(__file__).with_name("envia_soap.ps1")


def montar_envelope(cnpj: str, uf: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
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


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Este teste só roda no Windows.")

    parser = argparse.ArgumentParser()
    parser.add_argument("--cnpj", required=True)
    parser.add_argument("--uf", default="29")
    args = parser.parse_args()

    cnpj = re.sub(r"\D", "", args.cnpj)
    if len(cnpj) != 14:
        raise SystemExit("CNPJ deve ter 14 dígitos.")

    with tempfile.TemporaryDirectory() as pasta:
        entrada = Path(pasta) / "entrada.xml"
        saida = Path(pasta) / "saida.txt"
        entrada.write_text(montar_envelope(cnpj, args.uf), encoding="utf-8")

        resultado = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(SCRIPT),
                "-Cnpj", cnpj, "-Url", URL,
                "-ArquivoEntrada", str(entrada),
                "-ArquivoSaida", str(saida),
                "-SoapAction", ACTION,
            ],
            capture_output=True, text=True,
        )
        if resultado.returncode != 0:
            raise SystemExit(f"Falha no PowerShell:\n{resultado.stdout}{resultado.stderr}")

        texto = saida.read_text(encoding="utf-8")

    linha_status, _, corpo = texto.partition("\n")
    print(linha_status)
    cstat = re.search(r"<cStat>(\d+)</cStat>", corpo)
    motivo = re.search(r"<xMotivo>(.*?)</xMotivo>", corpo, re.S)
    print(f"cStat:   {cstat.group(1) if cstat else 'não encontrado'}")
    print(f"xMotivo: {motivo.group(1).strip() if motivo else 'não encontrado'}")
    print("\nTrecho da resposta:")
    print(corpo[:800])


if __name__ == "__main__":
    main()
