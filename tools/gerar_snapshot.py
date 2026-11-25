"""
Gera um único arquivo com a estrutura e o conteúdo do projeto,
pronto para ser enviado a uma IA.

Uso:
    python tools/gerar_snapshot.py
    python tools/gerar_snapshot.py --saida snapshot.txt --max-kb 200
"""

from __future__ import annotations

import argparse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PASTAS_IGNORADAS = {
    ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
    "build", "dist", "htmlcov", ".tox", "node_modules",
}

EXTENSOES_INCLUIDAS = {
    ".py", ".toml", ".cfg", ".ini", ".md", ".txt",
    ".yaml", ".yml", ".json", ".spec",
}

ARQUIVOS_IGNORADOS = {"snapshot_projeto.txt", ".coverage"}


def deve_ignorar(caminho: Path) -> bool:
    partes = set(caminho.relative_to(RAIZ).parts)
    if partes & PASTAS_IGNORADAS:
        return True
    if any(p.endswith(".egg-info") for p in partes):
        return True
    return caminho.name in ARQUIVOS_IGNORADOS


def gerar_arvore(arquivos: list[Path]) -> str:
    linhas = [f"{RAIZ.name}/"]
    for arquivo in arquivos:
        relativo = arquivo.relative_to(RAIZ)
        nivel = len(relativo.parts) - 1
        linhas.append(f"{'    ' * nivel}{relativo.name}")
    return "\n".join(linhas)


def coletar_arquivos() -> list[Path]:
    return sorted(
        p for p in RAIZ.rglob("*")
        if p.is_file()
        and not deve_ignorar(p)
        and p.suffix.lower() in EXTENSOES_INCLUIDAS
    )


def ler_conteudo(arquivo: Path, max_bytes: int) -> str:
    if arquivo.stat().st_size > max_bytes:
        return f"[arquivo omitido: maior que {max_bytes // 1024} KB]"
    try:
        return arquivo.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return arquivo.read_text(encoding="latin-1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--saida", default="snapshot_projeto.txt")
    parser.add_argument("--max-kb", type=int, default=200)
    args = parser.parse_args()

    arquivos = coletar_arquivos()
    saida = RAIZ / args.saida
    max_bytes = args.max_kb * 1024

    with saida.open("w", encoding="utf-8") as f:
        f.write("# ESTRUTURA DO PROJETO\n\n")
        f.write(gerar_arvore(arquivos))
        f.write("\n\n# CONTEÚDO DOS ARQUIVOS\n")

        for arquivo in arquivos:
            relativo = arquivo.relative_to(RAIZ).as_posix()
            f.write(f"\n\n{'=' * 80}\n")
            f.write(f"ARQUIVO: {relativo}\n")
            f.write(f"{'=' * 80}\n")
            f.write(ler_conteudo(arquivo, max_bytes))

    tamanho_kb = saida.stat().st_size / 1024
    print(f"✔ {len(arquivos)} arquivos -> {saida.name} ({tamanho_kb:.1f} KB)")


if __name__ == "__main__":
    main()
