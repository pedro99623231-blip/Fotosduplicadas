import shutil

from PIL import Image, ImageDraw

from fotosduplicadas import nucleo


def _foto(caminho, semente=0, tamanho=(800, 600)):
    img = Image.new("RGB", tamanho, (30 + semente * 40 % 200, 120, 200))
    d = ImageDraw.Draw(img)
    for k in range(12):
        x = (k * 97 + semente * 53) % tamanho[0]
        y = (k * 61 + semente * 29) % tamanho[1]
        d.ellipse([x, y, x + 120, y + 90], fill=((k * 50 + semente * 70) % 255, (k * 20) % 255, 40))
    d.rectangle([0, 0, tamanho[0] // 3, tamanho[1] // 4], fill=(250, 250, 250))
    return img


def test_encontra_duplicadas_com_nome_e_formato_diferentes(tmp_path):
    a, b = tmp_path / "album", tmp_path / "backup" / "sub"
    a.mkdir(); b.mkdir(parents=True)
    original = _foto(None, 1)
    original.save(a / "praia.jpg", quality=92)
    shutil.copy(a / "praia.jpg", b / "IMG_0001.jpg")                  # cópia idêntica
    original.save(b / "copia praia.png")                                # outro formato
    original.resize((400, 300)).save(b / "pequena.webp", quality=80)  # redimensionada
    _foto(None, 2).save(a / "outra.jpg")                                # foto diferente
    _foto(None, 3).save(a / "mais_outra.png")

    grupos, erros = nucleo.procurar_duplicadas([tmp_path])
    assert not erros
    assert len(grupos) == 1
    nomes = {i.caminho.name for i in grupos[0].itens}
    assert nomes == {"praia.jpg", "IMG_0001.jpg", "copia praia.png", "pequena.webp"}
    # sugere manter a de maior resolução e nunca a redimensionada
    assert grupos[0].manter.caminho.name != "pequena.webp"


def test_modo_exato(tmp_path):
    f = _foto(None, 4)
    f.save(tmp_path / "a.jpg")
    shutil.copy(tmp_path / "a.jpg", tmp_path / "b.jpg")
    f.save(tmp_path / "c.png")
    grupos, _ = nucleo.procurar_duplicadas([tmp_path], limite=None)
    assert len(grupos) == 1 and grupos[0].tipo == "idêntica"
    assert {i.caminho.name for i in grupos[0].itens} == {"a.jpg", "b.jpg"}


def test_arquivo_corrompido_nao_quebra(tmp_path):
    (tmp_path / "quebrada.jpg").write_bytes(b"nao sou imagem")
    _foto(None, 5).save(tmp_path / "ok.jpg")
    grupos, erros = nucleo.procurar_duplicadas([tmp_path])
    assert grupos == [] and len(erros) == 1


def test_mover_nao_sobrescreve(tmp_path):
    origem = tmp_path / "fotos"
    origem.mkdir()
    (origem / "x.jpg").write_bytes(b"1")
    destino = tmp_path / "dup"
    (destino / "fotos").mkdir(parents=True)
    (destino / "fotos" / "x.jpg").write_bytes(b"ja existia")
    movidos = nucleo.mover_para_pasta([origem / "x.jpg"], destino, raizes=[origem])
    assert not (origem / "x.jpg").exists()
    assert (destino / "fotos" / "x.jpg").read_bytes() == b"ja existia"
    assert movidos[0][1].name == "x (1).jpg"


# --------------------------------------------------------------------------
# Fotos em sequência (burst): parecidas, mas NÃO são duplicadas
# --------------------------------------------------------------------------

import io
import random

from PIL import ImageChops, ImageEnhance, ImageFilter

W, H = 1008, 756


def _cena(semente):
    r = random.Random(semente)
    random.seed(semente)
    bg = Image.effect_noise((W, H), 80).convert("RGB").filter(ImageFilter.GaussianBlur(6))
    d = ImageDraw.Draw(bg)
    for _ in range(40):
        x, y, s = r.randrange(W), r.randrange(H), r.randrange(20, 200)
        d.rectangle([x, y, x + s, y + s // 2], fill=tuple(r.randrange(256) for _ in range(3)))
    for _ in range(200):
        x, y = r.randrange(W), r.randrange(H)
        d.ellipse([x, y, x + 4, y + 4], fill=(255, 255, 200))
    return bg


def _pessoa(img, x, y, braco=0):
    img = img.copy()
    d = ImageDraw.Draw(img)
    d.ellipse([x, y, x + 60, y + 60], fill=(220, 180, 150))
    d.rectangle([x - 10, y + 60, x + 70, y + 200], fill=(120, 160, 220))
    d.line([x + 70, y + 80, x + 130, y + 80 - braco], fill=(220, 180, 150), width=14)
    d.rectangle([x, y + 200, x + 60, y + 300], fill=(20, 20, 30))
    return img


def _sequencia():
    fundo = _cena(3)
    base = _pessoa(fundo, 600, 350)
    return base, {
        "braco.jpg": _pessoa(fundo, 600, 350, braco=60),
        "andou15.jpg": _pessoa(fundo, 615, 350),
        "andou6.jpg": _pessoa(fundo, 606, 352),
        "tremida4.jpg": ImageChops.offset(base, 4, 2),
        "tremida1_braco.jpg": ImageChops.offset(_pessoa(fundo, 600, 350, 30), 1, 1),
        "exposicao.jpg": ImageEnhance.Brightness(base).enhance(1.08),
    }


def test_fotos_em_sequencia_nao_sao_duplicadas(tmp_path):
    base, seq = _sequencia()
    base.save(tmp_path / "base.jpg", quality=92)
    for nome, img in seq.items():
        img.save(tmp_path / nome, quality=92)
    for sens, limite in nucleo.SENSIBILIDADE.items():
        grupos, _ = nucleo.procurar_duplicadas([tmp_path], limite)
        assert grupos == [], (sens, [[i.caminho.name for i in g.itens] for g in grupos])


def test_mesma_foto_recomprimida_e_reduzida_e_duplicada(tmp_path):
    base, seq = _sequencia()
    base.save(tmp_path / "original.jpg", quality=92)
    base.save(tmp_path / "copia.png")
    base.save(tmp_path / "recomprimida.jpg", quality=60)
    base.resize((W // 4, H // 4)).save(tmp_path / "pequena.jpg", quality=70)
    base.resize((320, 240)).save(tmp_path / "minuscula_q30.jpg", quality=30)
    seq["braco.jpg"].save(tmp_path / "outra_da_sequencia.jpg", quality=92)
    grupos, _ = nucleo.procurar_duplicadas([tmp_path])
    assert len(grupos) == 1
    assert {i.caminho.name for i in grupos[0].itens} == {
        "original.jpg", "copia.png", "recomprimida.jpg", "pequena.jpg", "minuscula_q30.jpg"}
    assert grupos[0].manter.caminho.name in {"original.jpg", "copia.png"}


def test_rotacao_e_recorte_nao_viram_duplicada(tmp_path):
    base, _ = _sequencia()
    base.save(tmp_path / "a.jpg")
    base.crop((0, 0, W, H - 120)).save(tmp_path / "recortada.jpg")
    grupos, _ = nucleo.procurar_duplicadas([tmp_path])
    assert grupos == []
