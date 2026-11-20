"""Interface gráfica do Fotos Duplicadas (PySide6), com visual "Liquid Glass".

O efeito de vidro é desenhado pelo próprio programa: um fundo com manchas de
cor suaves e painéis translúcidos que mostram uma versão desfocada desse fundo,
com brilho na borda superior e contorno claro. Funciona em qualquer Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog,
                               QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QSizePolicy, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import nucleo

OPCOES_SENS = {
    "Somente cópias idênticas (byte a byte)": None,
    "Rigorosa (mesma foto, outro formato/tamanho)": nucleo.SENSIBILIDADE["rigorosa"],
    "Normal (recomendado)": nucleo.SENSIBILIDADE["normal"],
    "Ampla (compressão pesada; revise com cuidado)": nucleo.SENSIBILIDADE["ampla"],
}

RAIO = 22

ESTILO = """
* { color: #1C1C1E; font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif; font-size: 10pt; }
QLabel#titulo { font-size: 20pt; font-weight: 600; }
QLabel#subtitulo { color: rgba(28,28,30,0.60); }
QLabel#rotulo { color: rgba(28,28,30,0.55); font-weight: 600; font-size: 9pt; }
QLabel#status, QLabel#detalhe, QLabel#resumo { color: rgba(28,28,30,0.75); }

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.85), stop:1 rgba(255,255,255,0.55));
    border: 1px solid rgba(255,255,255,0.95);
    border-bottom: 1px solid rgba(0,0,0,0.10);
    border-radius: 16px; padding: 7px 16px;
}
QPushButton:hover { background: rgba(255,255,255,0.95); }
QPushButton:pressed { background: rgba(235,235,240,0.80); }
QPushButton:disabled { color: rgba(28,28,30,0.35); }
QPushButton#destaque {
    color: white; font-weight: 600;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(70,70,76,0.92), stop:1 rgba(28,28,30,0.92));
    border: 1px solid rgba(255,255,255,0.35);
}
QPushButton#destaque:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(90,90,96,0.95), stop:1 rgba(44,44,48,0.95));
}

QListWidget, QTreeWidget {
    background: rgba(255,255,255,0.40);
    border: 1px solid rgba(255,255,255,0.75); border-radius: 14px; padding: 4px;
    outline: 0;
}
QTreeWidget::item, QListWidget::item { padding: 4px 2px; border-radius: 8px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: rgba(0,0,0,0.10); color: #1C1C1E; }
QTreeWidget::item:hover, QListWidget::item:hover { background: rgba(0,0,0,0.04); }
QTreeView::branch, QTreeView::branch:selected, QTreeView::branch:hover { background: transparent; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: transparent; color: rgba(28,28,30,0.55); font-weight: 600;
    border: none; border-bottom: 1px solid rgba(0,0,0,0.08); padding: 6px 4px;
}
QTreeWidget::indicator { width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid rgba(0,0,0,0.30); background: rgba(255,255,255,0.75); }
QTreeWidget::indicator:checked { border: 1px solid rgba(0,0,0,0.6);
    background: #2C2C2E; image: url(%MARCA%); }

QComboBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.85), stop:1 rgba(255,255,255,0.55));
    border: 1px solid rgba(255,255,255,0.95); border-bottom: 1px solid rgba(0,0,0,0.10);
    border-radius: 14px; padding: 6px 14px;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #F7F7F9; border: 1px solid rgba(0,0,0,0.12); border-radius: 10px;
    selection-background-color: rgba(0,0,0,0.08); selection-color: #1C1C1E; padding: 4px;
}

QProgressBar {
    background: rgba(255,255,255,0.45); border: 1px solid rgba(255,255,255,0.85);
    border-radius: 7px; height: 14px; text-align: center; color: transparent;
}
QProgressBar::chunk { border-radius: 6px; background: rgba(44,44,46,0.80); }

QSplitter::handle { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: rgba(0,0,0,0.22); border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 4px; }
QScrollBar::handle:horizontal { background: rgba(0,0,0,0.22); border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; border: none; }
QToolTip { background: #F7F7F9; color: #1C1C1E; border: 1px solid rgba(0,0,0,0.15); }
QMessageBox, QFileDialog { background: #F2F2F5; }
"""


# --------------------------------------------------------------------------
# Fundo "líquido" e painéis de vidro
# --------------------------------------------------------------------------

class FundoLiquido(QWidget):
    """Fundo com manchas de cor; guarda também uma versão desfocada para o vidro."""

    # manchas neutras (branco e cinza), só para o vidro ter o que refratar
    MANCHAS = [  # (x, y, raio relativo, cor, opacidade)
        (0.10, 0.15, 0.50, QColor(255, 255, 255), 230),
        (0.90, 0.10, 0.45, QColor(200, 202, 210), 200),
        (0.80, 0.92, 0.55, QColor(255, 255, 255), 220),
        (0.18, 0.92, 0.40, QColor(185, 188, 196), 170),
        (0.50, 0.45, 0.35, QColor(255, 255, 255), 160),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.fundo = QPixmap()
        self.desfocado = QPixmap()

    def _desenhar(self, tamanho: QSize) -> QImage:
        img = QImage(tamanho, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, tamanho.width(), tamanho.height())
        g.setColorAt(0, QColor(232, 233, 238))
        g.setColorAt(1, QColor(214, 216, 223))
        p.fillRect(img.rect(), g)
        lado = max(tamanho.width(), tamanho.height())
        for x, y, r, cor, alfa in self.MANCHAS:
            c = QPointF(x * tamanho.width(), y * tamanho.height())
            rg = QRadialGradient(c, r * lado)
            c1, c2 = QColor(cor), QColor(cor)
            c1.setAlpha(alfa)
            c2.setAlpha(0)
            rg.setColorAt(0, c1)
            rg.setColorAt(1, c2)
            p.setBrush(QBrush(rg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, r * lado, r * lado)
        p.end()
        return img

    def resizeEvent(self, ev) -> None:  # noqa: N802
        img = self._desenhar(self.size())
        self.fundo = QPixmap.fromImage(img)
        # desfoque barato e bonito: reduz muito e amplia suavemente
        pequeno = img.scaled(max(1, img.width() // 24), max(1, img.height() // 24),
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        self.desfocado = QPixmap.fromImage(pequeno.scaled(
            img.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        for painel in self.findChildren(PainelVidro):
            painel.update()
        super().resizeEvent(ev)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(0, 0, self.fundo)


class PainelVidro(QFrame):
    """Painel translúcido com fundo desfocado, brilho e borda clara."""

    def __init__(self, fundo: FundoLiquido, raio: int = RAIO) -> None:
        super().__init__()
        self.fundo_ref = fundo
        self.raio = raio
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        caminho = QPainterPath()
        caminho.addRoundedRect(r, self.raio, self.raio)
        p.setClipPath(caminho)

        # 1) o que está "atrás" do vidro, desfocado
        origem = self.mapTo(self.fundo_ref, self.rect().topLeft())
        if not self.fundo_ref.desfocado.isNull():
            p.drawPixmap(0, 0, self.fundo_ref.desfocado,
                         origem.x(), origem.y(), self.width(), self.height())
        # 2) leve tom branco (vidro fosco)
        p.fillRect(self.rect(), QColor(255, 255, 255, 105))
        # 3) brilho "líquido" na parte de cima
        brilho = QLinearGradient(0, 0, 0, self.height())
        brilho.setColorAt(0.0, QColor(255, 255, 255, 120))
        brilho.setColorAt(0.25, QColor(255, 255, 255, 25))
        brilho.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), brilho)
        p.setClipping(False)
        # 4) contorno: mais claro em cima, sumindo embaixo
        borda = QLinearGradient(0, 0, 0, self.height())
        borda.setColorAt(0, QColor(255, 255, 255, 255))
        borda.setColorAt(1, QColor(255, 255, 255, 120))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # contorno externo bem discreto (dá volume sem sombra)
        externo = QPainterPath()
        externo.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.raio, self.raio)
        p.setPen(QPen(QColor(0, 0, 0, 28), 1))
        p.drawPath(externo)
        interno = QPainterPath()
        interno.addRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), self.raio - 1, self.raio - 1)
        p.setPen(QPen(QBrush(borda), 1.4))
        p.drawPath(interno)


# --------------------------------------------------------------------------
# Prévia que sempre mostra a foto inteira
# --------------------------------------------------------------------------

class Previa(QLabel):
    def __init__(self) -> None:
        super().__init__("Selecione um arquivo\npara ver a prévia")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setStyleSheet("color: rgba(28,28,30,0.45);")
        self._original: QPixmap | None = None

    def mostrar(self, caminho: Path | None) -> None:
        self._original = None
        if caminho is None:
            self.setPixmap(QPixmap())
            self.setText("Selecione um arquivo\npara ver a prévia")
            return
        try:
            with Image.open(caminho) as img:
                img.draft("RGB", (1600, 1600))
                img = ImageOps.exif_transpose(img)  # foto em pé fica em pé
                img.thumbnail((1600, 1600))
                img = img.convert("RGBA")
                dados = img.tobytes("raw", "RGBA")
                qimg = QImage(dados, img.width, img.height, img.width * 4,
                              QImage.Format.Format_RGBA8888).copy()
            self._original = QPixmap.fromImage(qimg)
            self.setText("")
            self._ajustar()
        except Exception as e:
            self.setPixmap(QPixmap())
            self.setText(f"Sem prévia:\n{e}")

    def _ajustar(self) -> None:
        if not self._original:
            return
        dpr = self.devicePixelRatioF()
        alvo = self.size() * dpr
        pm = self._original.scaled(alvo, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        # cantos arredondados na foto
        final = QPixmap(pm.size())
        final.fill(Qt.GlobalColor.transparent)
        p = QPainter(final)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPainterPath()
        c.addRoundedRect(QRectF(final.rect()), 14 * dpr, 14 * dpr)
        p.setClipPath(c)
        p.drawPixmap(0, 0, pm)
        p.end()
        final.setDevicePixelRatio(dpr)
        self.setPixmap(final)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._ajustar()


# --------------------------------------------------------------------------
# Busca em segundo plano
# --------------------------------------------------------------------------

class Trabalhador(QObject):
    progresso = Signal(int, int, str)
    terminou = Signal(object, object)
    falhou = Signal(str)

    def __init__(self, pastas: list[str], limite) -> None:
        super().__init__()
        self.pastas, self.limite = pastas, limite
        self.cancelar = False

    def rodar(self) -> None:
        try:
            grupos, erros = nucleo.procurar_duplicadas(
                self.pastas, self.limite,
                lambda n, t, c: self.progresso.emit(n, t, str(c)),
                lambda: self.cancelar)
            self.terminou.emit(grupos, erros)
        except Exception as e:  # pragma: no cover
            self.falhou.emit(str(e))


# --------------------------------------------------------------------------
# Janela principal
# --------------------------------------------------------------------------

def _botao(texto: str, destaque: bool = False) -> QPushButton:
    b = QPushButton(texto)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if destaque:
        b.setObjectName("destaque")
    return b


class Janela(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Fotos Duplicadas")
        self.resize(1280, 800)
        self.setMinimumSize(980, 620)
        self.setAcceptDrops(True)

        self.grupos: list[nucleo.Grupo] = []
        self.thread: QThread | None = None
        self.trab: Trabalhador | None = None

        self.fundo = FundoLiquido()
        self.setCentralWidget(self.fundo)
        raiz = QVBoxLayout(self.fundo)
        raiz.setContentsMargins(22, 18, 22, 20)
        raiz.setSpacing(16)

        # ---- cabeçalho
        cab = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(0)
        t = QLabel("Fotos Duplicadas")
        t.setObjectName("titulo")
        s = QLabel("Encontre a mesma foto, mesmo com outro nome, formato ou tamanho. Nada é apagado.")
        s.setObjectName("subtitulo")
        tit.addWidget(t)
        tit.addWidget(s)
        cab.addLayout(tit)
        cab.addStretch()
        raiz.addLayout(cab)

        # ---- painel de pastas e busca
        topo = PainelVidro(self.fundo)
        lt = QHBoxLayout(topo)
        lt.setContentsMargins(18, 16, 18, 16)
        lt.setSpacing(16)

        col_pastas = QVBoxLayout()
        rp = QLabel("PASTAS A ANALISAR  ·  arraste pastas para cá")
        rp.setObjectName("rotulo")
        self.lista_pastas = QListWidget()
        self.lista_pastas.setFixedHeight(78)
        self.lista_pastas.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        col_pastas.addWidget(rp)
        col_pastas.addWidget(self.lista_pastas)
        lt.addLayout(col_pastas, 3)

        col_bp = QVBoxLayout()
        col_bp.addStretch()
        b_add = _botao("＋  Adicionar pasta")
        b_add.clicked.connect(self._add_pasta)
        b_rem = _botao("Remover")
        b_rem.clicked.connect(self._rem_pasta)
        col_bp.addWidget(b_add)
        col_bp.addWidget(b_rem)
        lt.addLayout(col_bp)

        col_busca = QVBoxLayout()
        rs = QLabel("SENSIBILIDADE")
        rs.setObjectName("rotulo")
        self.sens = QComboBox()
        self.sens.addItems(list(OPCOES_SENS))
        self.sens.setCurrentIndex(2)
        self.btn_procurar = _botao("Procurar duplicadas", destaque=True)
        self.btn_procurar.setMinimumHeight(38)
        self.btn_procurar.clicked.connect(self._procurar)
        col_busca.addWidget(rs)
        col_busca.addWidget(self.sens)
        col_busca.addWidget(self.btn_procurar)
        lt.addLayout(col_busca, 2)
        raiz.addWidget(topo)

        # ---- progresso
        lp = QHBoxLayout()
        self.barra = QProgressBar()
        self.barra.setFixedHeight(14)
        self.status = QLabel("Adicione uma ou mais pastas e clique em Procurar.")
        self.status.setObjectName("status")
        self.status.setMinimumWidth(420)
        lp.addWidget(self.barra, 1)
        lp.addWidget(self.status)
        raiz.addLayout(lp)

        # ---- meio: lista de grupos + prévia
        div = QSplitter(Qt.Orientation.Horizontal)
        div.setChildrenCollapsible(False)
        div.setHandleWidth(16)

        p_lista = PainelVidro(self.fundo)
        ll = QVBoxLayout(p_lista)
        ll.setContentsMargins(14, 14, 14, 14)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Arquivo", "Formato", "Dimensões", "Tamanho", "Pasta"])
        self.arvore.setAlternatingRowColors(False)
        self.arvore.setRootIsDecorated(True)
        self.arvore.setUniformRowHeights(True)
        h = self.arvore.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h.resizeSection(0, 300)
        for c, w in ((1, 70), (2, 100), (3, 80)):
            h.resizeSection(c, w)
        h.setStretchLastSection(True)
        self.arvore.currentItemChanged.connect(self._ao_selecionar)
        self.arvore.itemChanged.connect(lambda *_: self._atualizar_resumo())
        self.arvore.itemDoubleClicked.connect(lambda *_: self._abrir_arquivo())
        ll.addWidget(self.arvore)
        div.addWidget(p_lista)

        p_prev = PainelVidro(self.fundo)
        lv = QVBoxLayout(p_prev)
        lv.setContentsMargins(16, 16, 16, 16)
        self.previa = Previa()
        lv.addWidget(self.previa, 1)
        self.detalhe = QLabel("")
        self.detalhe.setObjectName("detalhe")
        self.detalhe.setWordWrap(True)
        self.detalhe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(self.detalhe)
        lb = QHBoxLayout()
        b1 = _botao("Abrir imagem")
        b1.clicked.connect(self._abrir_arquivo)
        b2 = _botao("Mostrar na pasta")
        b2.clicked.connect(self._abrir_pasta)
        lb.addWidget(b1)
        lb.addWidget(b2)
        lb.addStretch()
        lv.addLayout(lb)
        div.addWidget(p_prev)
        div.setStretchFactor(0, 3)
        div.setStretchFactor(1, 2)
        div.setSizes([760, 480])
        raiz.addWidget(div, 1)

        # ---- rodapé
        base = PainelVidro(self.fundo, raio=20)
        lr = QHBoxLayout(base)
        lr.setContentsMargins(14, 10, 14, 10)
        for texto, fn in (("Marcar sugeridas", self._marcar_sugeridas),
                          ("Desmarcar todas", self._desmarcar_todas),
                          ("Exportar relatório (CSV)", self._exportar)):
            b = _botao(texto)
            b.clicked.connect(fn)
            lr.addWidget(b)
        lr.addStretch()
        self.resumo = QLabel("")
        self.resumo.setObjectName("resumo")
        lr.addWidget(self.resumo)
        self.btn_mover = _botao("Mover marcadas para outra pasta…", destaque=True)
        self.btn_mover.clicked.connect(self._mover)
        lr.addWidget(self.btn_mover)
        raiz.addWidget(base)

    # ------------------------------------------------------------- pastas
    def _pastas(self) -> list[str]:
        return [self.lista_pastas.item(i).text() for i in range(self.lista_pastas.count())]

    def _incluir_pasta(self, p: str) -> None:
        p = os.path.normpath(p)
        if p and p not in self._pastas():
            self.lista_pastas.addItem(p)

    def _add_pasta(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Escolha uma pasta com fotos")
        if p:
            self._incluir_pasta(p)

    def _rem_pasta(self) -> None:
        for it in self.lista_pastas.selectedItems():
            self.lista_pastas.takeItem(self.lista_pastas.row(it))

    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:  # noqa: N802
        for url in ev.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                self._incluir_pasta(p)

    # ------------------------------------------------------------- busca
    def _procurar(self) -> None:
        if self.trab is not None:
            self.trab.cancelar = True
            self.status.setText("Cancelando…")
            return
        pastas = self._pastas()
        if not pastas:
            QMessageBox.information(self, "Fotos Duplicadas", "Adicione pelo menos uma pasta.")
            return
        self.arvore.clear()
        self.previa.mostrar(None)
        self.detalhe.setText("")
        self.barra.setValue(0)
        self.status.setText("Listando arquivos…")
        self.btn_procurar.setText("Cancelar")
        self.thread = QThread(self)
        self.trab = Trabalhador(pastas, OPCOES_SENS[self.sens.currentText()])
        self.trab.moveToThread(self.thread)
        self.thread.started.connect(self.trab.rodar)
        self.trab.progresso.connect(self._progresso)
        self.trab.terminou.connect(self._terminou)
        self.trab.falhou.connect(self._falhou)
        self.thread.start()

    def _progresso(self, n: int, total: int, caminho: str) -> None:
        self.barra.setMaximum(max(total, 1))
        self.barra.setValue(n)
        self.status.setText(f"Analisando {n} de {total}: {Path(caminho).name}")

    def _encerrar_thread(self) -> bool:
        cancelado = bool(self.trab and self.trab.cancelar)
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.thread, self.trab = None, None
        self.btn_procurar.setText("Procurar duplicadas")
        return cancelado

    def _falhou(self, msg: str) -> None:
        self._encerrar_thread()
        QMessageBox.critical(self, "Erro", msg)

    def _terminou(self, grupos, erros) -> None:
        cancelado = self._encerrar_thread()
        self.grupos = grupos
        self._preencher()
        txt = f"{'Cancelado. ' if cancelado else ''}{len(grupos)} grupos de duplicadas encontrados."
        if erros:
            txt += f" {len(erros)} arquivos não puderam ser lidos."
        self.status.setText(txt)

    # ------------------------------------------------------------- lista
    def _preencher(self, marcar: bool = True) -> None:
        self.arvore.blockSignals(True)
        self.arvore.clear()
        negrito = QFont()
        negrito.setBold(True)
        for n, g in enumerate(self.grupos, 1):
            tipo = "cópias idênticas" if g.tipo == "idêntica" else "mesma imagem"
            gi = QTreeWidgetItem([f"Grupo {n}  ·  {len(g.itens)} arquivos  ·  {tipo}"])
            gi.setFirstColumnSpanned(True)
            gi.setFont(0, negrito)
            gi.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.arvore.addTopLevelItem(gi)
            gi.setFirstColumnSpanned(True)
            for i in g.itens:
                it = QTreeWidgetItem([i.caminho.name, i.formato, f"{i.largura}×{i.altura}",
                                      nucleo.tamanho_legivel(i.tamanho_bytes), str(i.caminho.parent)])
                it.setData(0, Qt.ItemDataRole.UserRole, (g, i))
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable)
                manter = i is g.manter
                it.setCheckState(0, Qt.CheckState.Checked if (marcar and not manter) else Qt.CheckState.Unchecked)
                it.setToolTip(0, "Sugestão: MANTER (maior resolução)" if manter else "Sugestão: mover")
                if manter:
                    f = it.font(0)
                    f.setBold(True)
                    it.setFont(0, f)
                gi.addChild(it)
            gi.setExpanded(True)
        self.arvore.blockSignals(False)
        self._atualizar_resumo()

    def _itens(self):
        for a in range(self.arvore.topLevelItemCount()):
            gi = self.arvore.topLevelItem(a)
            for b in range(gi.childCount()):
                yield gi.child(b)

    def _marcados(self):
        return [it for it in self._itens() if it.checkState(0) == Qt.CheckState.Checked]

    def _marcar_sugeridas(self) -> None:
        self.arvore.blockSignals(True)
        for it in self._itens():
            g, i = it.data(0, Qt.ItemDataRole.UserRole)
            it.setCheckState(0, Qt.CheckState.Unchecked if i is g.manter else Qt.CheckState.Checked)
        self.arvore.blockSignals(False)
        self._atualizar_resumo()

    def _desmarcar_todas(self) -> None:
        self.arvore.blockSignals(True)
        for it in self._itens():
            it.setCheckState(0, Qt.CheckState.Unchecked)
        self.arvore.blockSignals(False)
        self._atualizar_resumo()

    def _atualizar_resumo(self) -> None:
        m = self._marcados()
        total = sum(it.data(0, Qt.ItemDataRole.UserRole)[1].tamanho_bytes for it in m)
        self.resumo.setText(f"{len(m)} marcados  ·  {nucleo.tamanho_legivel(total)}")

    def _info_atual(self) -> nucleo.InfoImagem | None:
        it = self.arvore.currentItem()
        d = it.data(0, Qt.ItemDataRole.UserRole) if it else None
        return d[1] if d else None

    def _ao_selecionar(self, *_):
        info = self._info_atual()
        if not info:
            return
        self.previa.mostrar(info.caminho)
        self.detalhe.setText(f"{info.caminho}\n{info.formato}  ·  {info.largura}×{info.altura}  ·  "
                             f"{nucleo.tamanho_legivel(info.tamanho_bytes)}")

    # ------------------------------------------------------------- abrir
    def _abrir(self, alvo: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(alvo)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(alvo)])
        else:
            subprocess.Popen(["xdg-open", str(alvo)])

    def _abrir_arquivo(self) -> None:
        info = self._info_atual()
        if info:
            self._abrir(info.caminho)

    def _abrir_pasta(self) -> None:
        info = self._info_atual()
        if not info:
            return
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(info.caminho)])
        else:
            self._abrir(info.caminho.parent)

    # ------------------------------------------------------------- ações
    def _exportar(self) -> None:
        if not self.grupos:
            return
        arq, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", "duplicadas.csv", "CSV (*.csv)")
        if arq:
            nucleo.exportar_csv(self.grupos, arq)
            QMessageBox.information(self, "Fotos Duplicadas", f"Relatório salvo em:\n{arq}")

    def _mover(self) -> None:
        marcados = self._marcados()
        if not marcados:
            QMessageBox.information(self, "Fotos Duplicadas", "Nenhum arquivo marcado.")
            return
        sel = [it.data(0, Qt.ItemDataRole.UserRole) for it in marcados]
        for g in self.grupos:
            if all(any(i is s[1] for s in sel) for i in g.itens):
                r = QMessageBox.question(
                    self, "Atenção",
                    "Em pelo menos um grupo TODOS os arquivos estão marcados, então nenhuma "
                    "cópia ficaria no lugar original.\n\nContinuar mesmo assim?")
                if r != QMessageBox.StandardButton.Yes:
                    return
                break
        destino = QFileDialog.getExistingDirectory(self, "Para qual pasta mover as duplicadas?")
        if not destino:
            return
        total = sum(i.tamanho_bytes for _, i in sel)
        r = QMessageBox.question(
            self, "Confirmar",
            f"Mover {len(sel)} arquivos ({nucleo.tamanho_legivel(total)}) para:\n{destino}\n\n"
            "Nada será apagado; você pode revisar e apagar depois.")
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            movidos = nucleo.mover_para_pasta([i.caminho for _, i in sel], destino, raizes=self._pastas())
        except Exception as e:
            QMessageBox.critical(self, "Erro ao mover", str(e))
            return
        movidos_set = {o for o, _ in movidos}
        restantes = []
        for g in self.grupos:
            itens = [i for i in g.itens if i.caminho not in movidos_set]
            if len(itens) >= 2:
                restantes.append(nucleo.Grupo(itens=itens, tipo=g.tipo, distancia_max=g.distancia_max))
        self.grupos = restantes
        self._preencher(marcar=False)
        self.previa.mostrar(None)
        QMessageBox.information(self, "Pronto", f"{len(movidos)} arquivos movidos para:\n{destino}")


def _marca_de_verificacao() -> str:
    """Gera o desenho do ✓ usado nas caixas marcadas e devolve o caminho."""
    import tempfile
    caminho = Path(tempfile.gettempdir()) / "fotosduplicadas_marca.png"
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("white"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(8, 17), QPointF(14, 23), QPointF(25, 10)])
    p.end()
    pm.save(str(caminho))
    return caminho.as_posix()


def _icone() -> QIcon:
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 256, 256)
    g.setColorAt(0, QColor(120, 170, 255))
    g.setColorAt(1, QColor(180, 110, 255))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(40, 20, 170, 170), 36, 36)
    p.setBrush(QColor(255, 255, 255, 120))
    p.setPen(QPen(QColor(255, 255, 255, 220), 4))
    p.drawRoundedRect(QRectF(70, 70, 170, 170), 36, 36)
    p.end()
    return QIcon(pm)


def main() -> None:
    if sys.platform.startswith("win"):
        try:  # ícone próprio na barra de tarefas
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FotosDuplicadas.App")
        except Exception:
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    from PySide6.QtGui import QPalette
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 26))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(28, 28, 30))
    app.setPalette(pal)
    app.setStyleSheet(ESTILO.replace("%MARCA%", _marca_de_verificacao()))
    app.setWindowIcon(_icone())
    j = Janela()
    j.show()
    app.exec()


if __name__ == "__main__":
    main()
