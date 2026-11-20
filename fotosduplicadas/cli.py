"""Uso pela linha de comando (sem interface gráfica).

Exemplos:
    python -m fotosduplicadas.cli "F:\\Fotos"
    python -m fotosduplicadas.cli "F:\\Fotos" "D:\\Backup" --sensibilidade rigorosa --csv relatorio.csv
    python -m fotosduplicadas.cli "F:\\Fotos" --mover "F:\\Duplicadas"
"""

from __future__ import annotations

import argparse
import sys

from . import nucleo


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fotosduplicadas",
        description="Encontra fotos duplicadas, mesmo com nomes e formatos diferentes.",
    )
    p.add_argument("pastas", nargs="+", help="pastas a analisar (inclui subpastas)")
    p.add_argument("--sensibilidade", choices=list(nucleo.SENSIBILIDADE) + ["exata"],
                   default="normal",
                   help="'exata' só encontra cópias idênticas byte a byte (padrão: normal)")
    p.add_argument("--csv", help="salva o relatório em um arquivo CSV (abre no Excel)")
    p.add_argument("--mover", metavar="PASTA",
                   help="move as duplicadas sugeridas para PASTA (pede confirmação; nunca apaga)")
    p.add_argument("--sim", action="store_true", help="não pergunta antes de mover")
    a = p.parse_args(argv)

    limite = None if a.sensibilidade == "exata" else nucleo.SENSIBILIDADE[a.sensibilidade]

    def progresso(n: int, total: int, _caminho) -> None:
        if n == total or n % 25 == 0:
            print(f"\rAnalisando {n}/{total}...", end="", file=sys.stderr, flush=True)

    ignorar = [a.mover] if a.mover else []
    grupos, erros = nucleo.procurar_duplicadas(a.pastas, limite, progresso, ignorar=ignorar)
    print(file=sys.stderr)

    total_bytes = sum(g.bytes_recuperaveis for g in grupos)
    for n, g in enumerate(grupos, 1):
        print(f"\nGrupo {n} ({g.tipo}, {len(g.itens)} arquivos)")
        for i in g.itens:
            marca = "MANTER   " if i is g.manter else "duplicada"
            print(f"  [{marca}] {i.caminho}  ({i.formato} {i.largura}x{i.altura}, "
                  f"{nucleo.tamanho_legivel(i.tamanho_bytes)})")
    print(f"\n{len(grupos)} grupos de duplicadas; "
          f"{sum(len(g.duplicatas) for g in grupos)} arquivos sobrando "
          f"({nucleo.tamanho_legivel(total_bytes)} que podem ser liberados).")
    if erros:
        print(f"{len(erros)} arquivos não puderam ser lidos:")
        for e in erros:
            print(f"  {e.caminho}: {e.erro}")

    if a.csv:
        nucleo.exportar_csv(grupos, a.csv)
        print(f"Relatório salvo em {a.csv}")

    if a.mover and grupos:
        arquivos = [i.caminho for g in grupos for i in g.duplicatas]
        if not a.sim:
            r = input(f"\nMover {len(arquivos)} arquivos para '{a.mover}'? [s/N] ")
            if r.strip().lower() not in ("s", "sim", "y", "yes"):
                print("Nada foi movido.")
                return 0
        movidos = nucleo.mover_para_pasta(arquivos, a.mover, raizes=a.pastas)
        print(f"{len(movidos)} arquivos movidos para {a.mover}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
