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
