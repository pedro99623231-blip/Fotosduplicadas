"""Interface gráfica (Tkinter) do detector de fotos duplicadas."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from . import nucleo

MARCADO, DESMARCADO = "☑", "☐"
OPCOES_SENS = {
    "Somente cópias idênticas (byte a byte)": None,
    "Rigorosa (mesma foto, outro formato/tamanho)": nucleo.SENSIBILIDADE["rigorosa"],
    "Normal (recomendado)": nucleo.SENSIBILIDADE["normal"],
    "Ampla (compressão pesada; revise com cuidado)": nucleo.SENSIBILIDADE["ampla"],
}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fotos Duplicadas")
        self.geometry("1150x720")
        self.minsize(900, 560)

        self.pastas: list[str] = []
        self.grupos: list[nucleo.Grupo] = []
        self.item_info: dict[str, nucleo.InfoImagem] = {}
        self.item_grupo: dict[str, nucleo.Grupo] = {}
        self.marcados: set[str] = set()
        self.fila: queue.Queue = queue.Queue()
        self._cancelar = False
        self._thumb = None

        self._montar()
        self.after(100, self._processar_fila)

    # ------------------------------------------------------------------ layout
    def _montar(self) -> None:
        topo = ttk.Frame(self, padding=8)
        topo.pack(fill="x")

        ttk.Label(topo, text="Pastas a analisar:").grid(row=0, column=0, sticky="w")
        self.lista_pastas = tk.Listbox(topo, height=3)
        self.lista_pastas.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(0, 6))
        ttk.Button(topo, text="Adicionar pasta…", command=self._add_pasta).grid(row=1, column=1, sticky="ew")
        ttk.Button(topo, text="Remover", command=self._rem_pasta).grid(row=2, column=1, sticky="ew")

        ttk.Label(topo, text="Sensibilidade:").grid(row=1, column=2, padx=(12, 4), sticky="e")
        self.sens = ttk.Combobox(topo, values=list(OPCOES_SENS), state="readonly", width=44)
        self.sens.current(2)
        self.sens.grid(row=1, column=3, sticky="w")
        self.btn_procurar = ttk.Button(topo, text="🔍 Procurar duplicadas", command=self._procurar)
        self.btn_procurar.grid(row=2, column=2, columnspan=2, sticky="ew", padx=(12, 0))
        topo.columnconfigure(0, weight=1)

        prog = ttk.Frame(self, padding=(8, 0))
        prog.pack(fill="x")
        self.barra = ttk.Progressbar(prog, mode="determinate")
        self.barra.pack(fill="x", side="left", expand=True)
        self.status = ttk.Label(prog, text="Adicione uma ou mais pastas e clique em Procurar.", width=60)
        self.status.pack(side="left", padx=8)

        meio = ttk.PanedWindow(self, orient="horizontal")
        meio.pack(fill="both", expand=True, padx=8, pady=8)

        esq = ttk.Frame(meio)
        cols = ("marcar", "formato", "dimensoes", "tamanho", "pasta")
        self.arvore = ttk.Treeview(esq, columns=cols, selectmode="browse")
        self.arvore.heading("#0", text="Arquivo")
        self.arvore.heading("marcar", text="Mover?")
        self.arvore.heading("formato", text="Formato")
        self.arvore.heading("dimensoes", text="Dimensões")
        self.arvore.heading("tamanho", text="Tamanho")
        self.arvore.heading("pasta", text="Pasta")
        self.arvore.column("#0", width=230)
        self.arvore.column("marcar", width=60, anchor="center")
        self.arvore.column("formato", width=65, anchor="center")
        self.arvore.column("dimensoes", width=90, anchor="center")
        self.arvore.column("tamanho", width=75, anchor="e")
        self.arvore.column("pasta", width=260)
        sb = ttk.Scrollbar(esq, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=sb.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.arvore.bind("<<TreeviewSelect>>", self._ao_selecionar)
        self.arvore.bind("<Button-1>", self._ao_clicar)
        self.arvore.bind("<space>", lambda e: self._alternar(self.arvore.focus()))
        self.arvore.bind("<Double-1>", lambda e: self._abrir_arquivo())
        self.arvore.tag_configure("grupo", background="#e8eef7")
        meio.add(esq, weight=3)

        dir_ = ttk.Frame(meio, padding=6)
        self.preview = ttk.Label(dir_, anchor="center", text="Selecione um arquivo\npara ver a prévia")
        self.preview.pack(fill="both", expand=True)
        self.detalhe = ttk.Label(dir_, wraplength=320, justify="left")
        self.detalhe.pack(fill="x", pady=(6, 0))
        bts = ttk.Frame(dir_)
        bts.pack(fill="x", pady=4)
        ttk.Button(bts, text="Abrir imagem", command=self._abrir_arquivo).pack(side="left")
        ttk.Button(bts, text="Abrir pasta", command=self._abrir_pasta).pack(side="left", padx=4)
        meio.add(dir_, weight=2)

        base = ttk.Frame(self, padding=8)
        base.pack(fill="x")
        ttk.Button(base, text="Marcar sugeridas", command=self._marcar_sugeridas).pack(side="left")
        ttk.Button(base, text="Desmarcar todas", command=self._desmarcar_todas).pack(side="left", padx=4)
        ttk.Button(base, text="Exportar relatório (CSV)…", command=self._exportar).pack(side="left", padx=4)
        self.btn_mover = ttk.Button(base, text="Mover marcadas para outra pasta…", command=self._mover)
        self.btn_mover.pack(side="right")
        self.resumo = ttk.Label(base, text="")
        self.resumo.pack(side="right", padx=10)

    # ------------------------------------------------------------------ pastas
    def _add_pasta(self) -> None:
        p = filedialog.askdirectory(title="Escolha uma pasta com fotos")
        if p and p not in self.pastas:
            self.pastas.append(p)
            self.lista_pastas.insert("end", p)

    def _rem_pasta(self) -> None:
        for idx in reversed(self.lista_pastas.curselection()):
            self.lista_pastas.delete(idx)
            del self.pastas[idx]

    # ------------------------------------------------------------------ busca
    def _procurar(self) -> None:
        if self.btn_procurar.cget("text").startswith("Cancelar"):
            self._cancelar = True
            return
        if not self.pastas:
            messagebox.showinfo("Fotos Duplicadas", "Adicione pelo menos uma pasta.")
            return
        self._cancelar = False
        self.btn_procurar.configure(text="Cancelar")
        self.arvore.delete(*self.arvore.get_children())
        self.item_info.clear()
        self.marcados.clear()
        limite = OPCOES_SENS[self.sens.get()]
        self.status.configure(text="Listando arquivos…")
        threading.Thread(target=self._trabalho, args=(list(self.pastas), limite), daemon=True).start()

    def _trabalho(self, pastas: list[str], limite) -> None:
        try:
            def prog(n, total, caminho):
                self.fila.put(("progresso", n, total, caminho))
            grupos, erros = nucleo.procurar_duplicadas(pastas, limite, prog, lambda: self._cancelar)
            self.fila.put(("fim", grupos, erros))
        except Exception as e:  # pragma: no cover
            self.fila.put(("erro", e))

    def _processar_fila(self) -> None:
        try:
            ultimo = None
            while True:
                msg = self.fila.get_nowait()
                if msg[0] == "progresso":
                    ultimo = msg
                else:
                    self._tratar(msg)
        except queue.Empty:
            pass
        if ultimo:
            _, n, total, caminho = ultimo
            self.barra.configure(maximum=max(total, 1), value=n)
            self.status.configure(text=f"Analisando {n} de {total}: {Path(caminho).name}")
        self.after(100, self._processar_fila)

    def _tratar(self, msg) -> None:
        self.btn_procurar.configure(text="🔍 Procurar duplicadas")
        if msg[0] == "erro":
            messagebox.showerror("Erro", str(msg[1]))
            return
        _, grupos, erros = msg
        self.grupos = grupos
        self._preencher()
        txt = (f"{'Cancelado. ' if self._cancelar else ''}{len(grupos)} grupos de duplicadas encontrados.")
        if erros:
            txt += f" {len(erros)} arquivos não puderam ser lidos."
        self.status.configure(text=txt)

    def _preencher(self, marcar: bool = True) -> None:
        self.arvore.delete(*self.arvore.get_children())
        self.item_info.clear()
        self.item_grupo.clear()
        self.marcados.clear()
        for n, g in enumerate(self.grupos, 1):
            rotulo = (f"Grupo {n}: {len(g.itens)} arquivos "
                      f"({'cópias idênticas' if g.tipo == 'idêntica' else 'mesma imagem'})")
            gid = self.arvore.insert("", "end", text=rotulo, open=True, tags=("grupo",))
            for i in g.itens:
                iid = self.arvore.insert(gid, "end", text=i.caminho.name, values=(
                    DESMARCADO, i.formato, f"{i.largura}×{i.altura}",
                    nucleo.tamanho_legivel(i.tamanho_bytes), str(i.caminho.parent)))
                self.item_info[iid] = i
                self.item_grupo[iid] = g
        if marcar:
            self._marcar_sugeridas()
        self._atualizar_resumo()

    # ------------------------------------------------------------------ marcação
    def _set_marca(self, iid: str, marcar: bool) -> None:
        if iid not in self.item_info:
            return
        (self.marcados.add if marcar else self.marcados.discard)(iid)
        self.arvore.set(iid, "marcar", MARCADO if marcar else DESMARCADO)

    def _alternar(self, iid: str) -> None:
        if iid in self.item_info:
            self._set_marca(iid, iid not in self.marcados)
            self._atualizar_resumo()

    def _ao_clicar(self, ev) -> None:
        if self.arvore.identify_column(ev.x) == "#1":
            self._alternar(self.arvore.identify_row(ev.y))

    def _marcar_sugeridas(self) -> None:
        for iid, info in self.item_info.items():
            self._set_marca(iid, info is not self.item_grupo[iid].manter)
        self._atualizar_resumo()

    def _desmarcar_todas(self) -> None:
        for iid in list(self.marcados):
            self._set_marca(iid, False)
        self._atualizar_resumo()

    def _atualizar_resumo(self) -> None:
        total = sum(self.item_info[i].tamanho_bytes for i in self.marcados)
        self.resumo.configure(text=f"{len(self.marcados)} marcados ({nucleo.tamanho_legivel(total)})")

    # ------------------------------------------------------------------ prévia
    def _ao_selecionar(self, _ev=None) -> None:
        iid = self.arvore.focus()
        info = self.item_info.get(iid)
        if not info:
            return
        try:
            with Image.open(info.caminho) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail((380, 380))
                self._thumb = ImageTk.PhotoImage(img)
            self.preview.configure(image=self._thumb, text="")
        except Exception as e:
            self.preview.configure(image="", text=f"Sem prévia: {e}")
        self.detalhe.configure(text=(
            f"{info.caminho}\n{info.formato} · {info.largura}×{info.altura} · "
            f"{nucleo.tamanho_legivel(info.tamanho_bytes)}"))

    def _abrir(self, alvo: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(alvo)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(alvo)])
        else:
            subprocess.Popen(["xdg-open", str(alvo)])

    def _abrir_arquivo(self) -> None:
        info = self.item_info.get(self.arvore.focus())
        if info:
            self._abrir(info.caminho)

    def _abrir_pasta(self) -> None:
        info = self.item_info.get(self.arvore.focus())
        if not info:
            return
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(info.caminho)])
        else:
            self._abrir(info.caminho.parent)

    # ------------------------------------------------------------------ ações
    def _exportar(self) -> None:
        if not self.grupos:
            return
        arq = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                           initialfile="duplicadas.csv")
        if arq:
            nucleo.exportar_csv(self.grupos, arq)
            messagebox.showinfo("Fotos Duplicadas", f"Relatório salvo em:\n{arq}")

    def _mover(self) -> None:
        if not self.marcados:
            messagebox.showinfo("Fotos Duplicadas", "Nenhum arquivo marcado.")
            return
        # segurança: não deixar um grupo inteiro marcado (sobraria nenhuma cópia)
        for g in self.grupos:
            ids = [iid for iid, gg in self.item_grupo.items() if gg is g]
            if ids and all(iid in self.marcados for iid in ids):
                if not messagebox.askyesno(
                        "Atenção",
                        "Em pelo menos um grupo TODOS os arquivos estão marcados, "
                        "então nenhuma cópia ficaria no lugar original.\n\nContinuar mesmo assim?"):
                    return
                break
        destino = filedialog.askdirectory(title="Para qual pasta mover as duplicadas?")
        if not destino:
            return
        total = sum(self.item_info[i].tamanho_bytes for i in self.marcados)
        if not messagebox.askyesno(
                "Confirmar",
                f"Mover {len(self.marcados)} arquivos ({nucleo.tamanho_legivel(total)}) para:\n"
                f"{destino}\n\nNada será apagado; você pode revisar e apagar depois."):
            return
        arquivos = [self.item_info[i].caminho for i in self.marcados]
        try:
            movidos = nucleo.mover_para_pasta(arquivos, destino, raizes=self.pastas)
        except Exception as e:
            messagebox.showerror("Erro ao mover", str(e))
            return
        movidos_set = {o for o, _ in movidos}
        restantes = []
        for g in self.grupos:
            itens = [i for i in g.itens if i.caminho not in movidos_set]
            if len(itens) >= 2:
                restantes.append(nucleo.Grupo(itens=itens, tipo=g.tipo, distancia_max=g.distancia_max))
        self.grupos = restantes
        self._preencher(marcar=False)
        messagebox.showinfo("Pronto", f"{len(movidos)} arquivos movidos para:\n{destino}")


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
