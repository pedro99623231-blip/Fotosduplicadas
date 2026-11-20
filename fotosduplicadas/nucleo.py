"""Núcleo do detector de fotos duplicadas.

Duas técnicas são combinadas:

1. **Hash exato (SHA-256)** do conteúdo do arquivo: encontra cópias idênticas
   byte a byte, mesmo com nomes diferentes.
2. **Hash perceptual (dHash + aHash, 64 bits cada)** calculado sobre a imagem
   reduzida e em tons de cinza: encontra a *mesma foto* salva em outro formato
   (JPG x PNG x WEBP...), redimensionada ou recomprimida.

Nenhuma função deste módulo apaga arquivos. A única operação que mexe em
arquivos é :func:`mover_para_pasta`, que apenas move (nunca apaga) e precisa
ser chamada explicitamente.
"""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageOps

try:  # suporte opcional a fotos de iPhone (.heic)
    from pillow_heif import register_heif_opener  # type: ignore

    register_heif_opener()
    _HEIC = True
except Exception:  # pragma: no cover - depende de pacote opcional
    _HEIC = False

Image.MAX_IMAGE_PIXELS = None  # fotos grandes (panorâmicas) não devem falhar

EXTENSOES = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif", ".bmp", ".dib",
    ".tif", ".tiff", ".webp", ".ico",
}
if _HEIC:
    EXTENSOES |= {".heic", ".heif"}

# Distância de Hamming máxima (em 64 bits) para considerar duas imagens iguais.
SENSIBILIDADE = {
    "rigorosa": 4,   # quase só a mesma imagem em outro formato/tamanho
    "normal": 8,     # bom equilíbrio (padrão)
    "ampla": 12,     # pega edições leves, mas pode juntar fotos parecidas
}


@dataclass
class InfoImagem:
    caminho: Path
    tamanho_bytes: int
    largura: int = 0
    altura: int = 0
    formato: str = ""
    sha256: str = ""
    dhash: int | None = None
    ahash: int | None = None
    erro: str = ""

    @property
    def pixels(self) -> int:
        return self.largura * self.altura


@dataclass
class Grupo:
    """Um conjunto de arquivos que são a mesma imagem."""

    itens: list[InfoImagem]
    tipo: str  # "idêntica" (bytes iguais) ou "semelhante" (perceptual)
    distancia_max: int = 0
    manter: InfoImagem = field(init=False)

    def __post_init__(self) -> None:
        # Sugestão de qual manter: maior resolução, depois maior arquivo,
        # depois o caminho mais curto (geralmente o "original").
        self.itens.sort(
            key=lambda i: (-i.pixels, -i.tamanho_bytes, len(str(i.caminho)), str(i.caminho))
        )
        self.manter = self.itens[0]

    @property
    def duplicatas(self) -> list[InfoImagem]:
        return [i for i in self.itens if i is not self.manter]

    @property
    def bytes_recuperaveis(self) -> int:
        return sum(i.tamanho_bytes for i in self.duplicatas)


# --------------------------------------------------------------------------
# Varredura e hashes
# --------------------------------------------------------------------------

def listar_imagens(pastas: Iterable[str | os.PathLike], ignorar: Iterable[str] = ()) -> list[Path]:
    """Lista recursivamente os arquivos de imagem dentro das pastas."""
    ignorar_abs = {Path(p).resolve() for p in ignorar}
    vistos: set[Path] = set()
    resultado: list[Path] = []
    for pasta in pastas:
        raiz = Path(pasta)
        if raiz.is_file():
            candidatos = [raiz]
        else:
            candidatos = []
            for dirpath, dirnames, filenames in os.walk(raiz):
                d = Path(dirpath)
                # não entra em pastas ignoradas nem ocultas (ex.: .git, .thumbnails)
                dirnames[:] = [
                    n for n in dirnames
                    if not n.startswith(".") and (d / n).resolve() not in ignorar_abs
                ]
                candidatos.extend(d / f for f in filenames)
        for c in candidatos:
            if c.suffix.lower() in EXTENSOES and not c.name.startswith("._"):
                r = c.resolve()
                if r not in vistos:
                    vistos.add(r)
                    resultado.append(c)
    resultado.sort()
    return resultado


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _bits_para_int(bits: Iterable[bool]) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def hashes_perceptuais(img: Image.Image) -> tuple[int, int]:
    """Retorna (dHash, aHash) de 64 bits de uma imagem PIL."""
    img = ImageOps.exif_transpose(img)  # respeita a rotação gravada pela câmera
    if img.mode in ("RGBA", "LA", "P"):
        # fundo branco para transparências, para PNG e JPG baterem
        img = img.convert("RGBA")
        fundo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(fundo, img)
    cinza = img.convert("L")

    d = cinza.resize((9, 8), Image.Resampling.LANCZOS)
    pd = list(d.tobytes())
    dh = _bits_para_int(
        pd[y * 9 + x] > pd[y * 9 + x + 1] for y in range(8) for x in range(8)
    )

    a = cinza.resize((8, 8), Image.Resampling.LANCZOS)
    pa = list(a.tobytes())
    media = sum(pa) / 64
    ah = _bits_para_int(p > media for p in pa)
    return dh, ah


def analisar_arquivo(caminho: Path, perceptual: bool = True) -> InfoImagem:
    info = InfoImagem(caminho=caminho, tamanho_bytes=0)
    try:
        info.tamanho_bytes = caminho.stat().st_size
        info.sha256 = _sha256(caminho)
        with Image.open(caminho) as img:
            info.formato = img.format or caminho.suffix.lstrip(".").upper()
            info.largura, info.altura = img.size
            img.draft("L", (256, 256))  # acelera muito JPGs grandes
            if perceptual:
                info.dhash, info.ahash = hashes_perceptuais(img)
    except Exception as e:  # arquivo corrompido, sem permissão etc.
        info.erro = f"{type(e).__name__}: {e}"
    return info


# --------------------------------------------------------------------------
# Agrupamento
# --------------------------------------------------------------------------

def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class _UniaoBusca:
    def __init__(self, n: int) -> None:
        self.pai = list(range(n))

    def achar(self, x: int) -> int:
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def unir(self, a: int, b: int) -> None:
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self.pai[rb] = ra


class _ArvoreBK:
    """Árvore BK para buscar hashes próximos sem comparar todos com todos."""

    def __init__(self) -> None:
        self.raiz: tuple[int, int, dict] | None = None  # (hash, indice, filhos)

    def inserir(self, h: int, idx: int) -> None:
        if self.raiz is None:
            self.raiz = (h, idx, {})
            return
        no = self.raiz
        while True:
            d = _hamming(h, no[0])
            filho = no[2].get(d)
            if filho is None:
                no[2][d] = (h, idx, {})
                return
            no = filho

    def buscar(self, h: int, limite: int) -> list[int]:
        if self.raiz is None:
            return []
        achados, pilha = [], [self.raiz]
        while pilha:
            no = pilha.pop()
            d = _hamming(h, no[0])
            if d <= limite:
                achados.append(no[1])
            for dist, filho in no[2].items():
                if d - limite <= dist <= d + limite:
                    pilha.append(filho)
        return achados


def agrupar(infos: list[InfoImagem], limite: int | None = SENSIBILIDADE["normal"]) -> list[Grupo]:
    """Agrupa imagens duplicadas.

    ``limite=None`` desliga a comparação perceptual (só cópias idênticas).
    Duas imagens são consideradas iguais pelo modo perceptual quando o dHash
    E o aHash ficam dentro do limite, o que reduz muito os falsos positivos.
    """
    validas = [i for i in infos if not i.erro]
    n = len(validas)
    uf = _UniaoBusca(n)

    # 1) idênticas por conteúdo
    por_sha: dict[str, int] = {}
    for idx, info in enumerate(validas):
        if info.sha256 in por_sha:
            uf.unir(por_sha[info.sha256], idx)
        else:
            por_sha[info.sha256] = idx

    # 2) semelhantes por hash perceptual
    if limite is not None:
        arvore = _ArvoreBK()
        for idx, info in enumerate(validas):
            if info.dhash is None:
                continue
            for j in arvore.buscar(info.dhash, limite):
                outro = validas[j]
                if _hamming(info.ahash, outro.ahash) <= limite:
                    uf.unir(j, idx)
            arvore.inserir(info.dhash, idx)

    conjuntos: dict[int, list[InfoImagem]] = {}
    for idx, info in enumerate(validas):
        conjuntos.setdefault(uf.achar(idx), []).append(info)

    grupos: list[Grupo] = []
    for membros in conjuntos.values():
        if len(membros) < 2:
            continue
        identicos = len({m.sha256 for m in membros}) == 1
        dist = 0
        if not identicos and all(m.dhash is not None for m in membros):
            dist = max(
                _hamming(a.dhash, b.dhash) for a in membros for b in membros
            )
        grupos.append(Grupo(itens=membros, tipo="idêntica" if identicos else "semelhante",
                            distancia_max=dist))
    grupos.sort(key=lambda g: (-g.bytes_recuperaveis, str(g.manter.caminho)))
    return grupos


def procurar_duplicadas(
    pastas: Iterable[str | os.PathLike],
    limite: int | None = SENSIBILIDADE["normal"],
    progresso: Callable[[int, int, Path], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    ignorar: Iterable[str] = (),
) -> tuple[list[Grupo], list[InfoImagem]]:
    """Varre as pastas e devolve (grupos de duplicadas, arquivos com erro)."""
    arquivos = listar_imagens(pastas, ignorar=ignorar)
    infos: list[InfoImagem] = []
    total = len(arquivos)
    for n, caminho in enumerate(arquivos, 1):
        if cancelar and cancelar():
            break
        infos.append(analisar_arquivo(caminho, perceptual=limite is not None))
        if progresso:
            progresso(n, total, caminho)
    erros = [i for i in infos if i.erro]
    return agrupar(infos, limite), erros


# --------------------------------------------------------------------------
# Ações sobre os arquivos (somente quando o usuário pede)
# --------------------------------------------------------------------------

def mover_para_pasta(arquivos: Iterable[Path], destino: str | os.PathLike,
                     raizes: Iterable[str | os.PathLike] = ()) -> list[tuple[Path, Path]]:
    """Move arquivos para ``destino`` preservando a estrutura de subpastas.

    Nunca apaga nada: se um nome já existir no destino, acrescenta um número.
    Retorna a lista de (origem, novo_caminho).
    """
    destino = Path(destino)
    raizes_abs = [Path(r).resolve() for r in raizes]
    movidos: list[tuple[Path, Path]] = []
    for arq in arquivos:
        arq = Path(arq)
        rel: Path = Path(arq.name)
        abs_arq = arq.resolve()
        for r in raizes_abs:
            try:
                rel = abs_arq.relative_to(r)
                rel = Path(r.name) / rel
                break
            except ValueError:
                continue
        alvo = destino / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        base, ext, k = alvo.stem, alvo.suffix, 1
        while alvo.exists():
            alvo = alvo.with_name(f"{base} ({k}){ext}")
            k += 1
        shutil.move(str(arq), str(alvo))
        movidos.append((arq, alvo))
    return movidos


def exportar_csv(grupos: list[Grupo], arquivo: str | os.PathLike) -> None:
    with open(arquivo, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["grupo", "tipo", "sugestao", "caminho", "formato",
                    "largura", "altura", "tamanho_bytes"])
        for n, g in enumerate(grupos, 1):
            for i in g.itens:
                w.writerow([n, g.tipo, "manter" if i is g.manter else "duplicada",
                            str(i.caminho), i.formato, i.largura, i.altura,
                            i.tamanho_bytes])


def tamanho_legivel(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"
