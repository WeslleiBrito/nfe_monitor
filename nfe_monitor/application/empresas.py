import logging
import sys
from dataclasses import dataclass, field

from nfe_monitor.application.sincronizar import cnpj_valido
from nfe_monitor.infrastructure import brasilapi, certificados, preferencias
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import UF_CODIGO, conectar
from nfe_monitor.infrastructure.sefaz.parametros import Config

__all__ = ["DIAS_AVISO", "ErroCadastro", "Cadastro", "cadastrar_por_certificado"]

log = logging.getLogger("nfe_monitor")

DIAS_AVISO = 30


class ErroCadastro(ValueError):
    """Certificado inadequado para cadastrar a empresa (mostrado ao usuário)."""


@dataclass
class Cadastro:
    empresa: repo.Empresa
    nova: bool
    avisos: list[str] = field(default_factory=list)


def cadastrar_por_certificado(thumbprint: str, cfg: Config | None = None,
                              uf: str | None = None, definir_padrao: bool = True) -> Cadastro:
    """Cadastra (ou atualiza) a empresa do certificado. `uf` sobrepõe a BrasilAPI."""
    thumbprint = thumbprint.strip().replace(" ", "").upper()
    if not thumbprint:
        raise ErroCadastro("Nenhum thumbprint informado nem salvo no config.json")
    cert = next((c for c in certificados.listar() if c.thumbprint == thumbprint), None)
    if cert is None:
        raise ErroCadastro(f"Certificado {thumbprint} não encontrado no Windows")
    if not cert.cnpj or not cnpj_valido(cert.cnpj):
        raise ErroCadastro("O certificado não é um e-CNPJ válido")
    if cert.vencido:
        raise ErroCadastro(f"Certificado vencido em {cert.validade:%d/%m/%Y}")

    avisos = []
    if not cert.tem_chave:
        avisos.append("Windows não informou chave privada (token A3 desconectado?)")
    if cert.dias_restantes <= DIAS_AVISO:
        avisos.append(f"O certificado vence em {cert.dias_restantes} dia(s) "
                      f"({cert.validade:%d/%m/%Y})")

    if uf is not None:
        uf = uf.strip().upper()
        if uf not in UF_CODIGO:
            raise ErroCadastro(f"UF inválida: {uf}")

    cfg = cfg or Config()
    con = conectar(cfg.banco)
    try:
        existente = repo.obter_empresa(con, cert.cnpj)
        api = {} if uf else (brasilapi.consultar_cnpj(cert.cnpj) or {})
        if not uf and not api:
            avisos.append("BrasilAPI indisponível: dados tirados do certificado")

        uf_api = api.get("uf") if api.get("uf") in UF_CODIGO else None
        uf_final = uf or uf_api or (existente.uf if existente else None)
        if not uf_final:
            avisos.append("UF não identificada: informe com --uf para liberar a consulta")

        empresa = repo.Empresa(
            cnpj=cert.cnpj,
            razao_social=api.get("razao_social") or cert.nome
                         or (existente.razao_social if existente else None),
            uf=uf_final,
            thumbprint=cert.thumbprint,
            origem="windows",
            ativo=True,
        )
        with con:
            repo.salvar_empresa(con, empresa)
    finally:
        con.close()

    if definir_padrao:
        p = preferencias.carregar()
        p.thumbprint = cert.thumbprint
        preferencias.salvar(p)

    return Cadastro(empresa, existente is None, avisos)


def _ler_args(args: list[str]) -> tuple[str | None, str | None]:
    """Separa (thumbprint, uf). Thumbprint ausente ou 'atual' = o do config.json."""
    uf, posicionais, i = None, [], 0
    while i < len(args):
        if args[i] == "--uf" and i + 1 < len(args):
            uf, i = args[i + 1], i + 2
            continue
        posicionais.append(args[i])
        i += 1
    thumb = posicionais[0] if posicionais else None
    if thumb is None or thumb.lower() == "atual":
        thumb = preferencias.carregar().thumbprint or None
    return thumb, uf


def _listar_certificados() -> int:
    lista = certificados.listar()
    atual = preferencias.carregar().thumbprint.upper()
    if not lista:
        print("Nenhum certificado encontrado em CurrentUser\\My nem LocalMachine\\My.")
        print("  - Certificado A3: conecte o token/cartão e rode de novo.")
        print("  - Certificado A1: importe o .pfx (duplo clique > Usuário atual).")
        if atual:
            print(f"  Thumbprint salvo no config.json: {atual}")
        return 1
    for i, c in enumerate(lista, 1):
        marcas = []
        if c.thumbprint == atual:
            marcas.append("ATUAL")
        if c.vencido:
            marcas.append("VENCIDO")
        elif c.dias_restantes <= DIAS_AVISO:
            marcas.append("VENCE LOGO")
        if not c.tem_chave:
            marcas.append("SEM CHAVE")
        extra = f" [{', '.join(marcas)}]" if marcas else ""
        print(f"{i:>2}. {c.thumbprint}  {c.descricao}{extra}")
    return 0


def _main(argv: list[str]) -> int:
    uso = ("Uso:\n"
           "  python -m nfe_monitor.application.empresas certificados\n"
           "  python -m nfe_monitor.application.empresas cadastrar [THUMBPRINT|atual] [--uf BA]\n"
           "  python -m nfe_monitor.application.empresas listar")
    if not argv:
        print(uso)
        return 1

    comando, args = argv[0], argv[1:]
    try:
        if comando == "certificados":
            return _listar_certificados()

        if comando == "cadastrar":
            thumb, uf = _ler_args(args)
            res = cadastrar_por_certificado(thumb or "", uf=uf)
            e = res.empresa
            print(f"{'Cadastrada' if res.nova else 'Atualizada'}: "
                  f"{e.cnpj} {e.razao_social or '(sem nome)'} ({e.uf or 'sem UF'})")
            for a in res.avisos:
                print(f"  Aviso: {a}")
            return 0

        if comando == "listar":
            con = conectar(Config().banco)
            try:
                for e in repo.listar_empresas(con, somente_ativas=False):
                    estado = "ativa" if e.ativo else "inativa"
                    pronto = "ok" if e.completa else "incompleta"
                    print(f"{e.cnpj}  {e.uf or '--'}  {estado:<7} {pronto:<10} "
                          f"{e.razao_social or '(sem nome)'}")
            finally:
                con.close()
            return 0
    except (ErroCadastro, certificados.ErroCertificados) as e:
        log.error("%s", e)
        return 1

    print(uso)
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(_main(sys.argv[1:]))
