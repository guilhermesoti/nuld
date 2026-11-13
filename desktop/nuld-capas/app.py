"""Gerenciador de Capas NULD — Retrogames. GPL-3.0."""
import csv
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from core import scan, process, serial_id


class App:
    def __init__(self, root):
        self.root, self.games, self.busy = root, [], False
        self.events, self.cancel = queue.Queue(), threading.Event()
        self.dest, self.art = tk.StringVar(), tk.StringVar()
        self.replace, self.online = tk.BooleanVar(), tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Escolha o pendrive ou a pasta que contém DVD, CD e POPS.')
        root.title('NULD • Gerenciador de Capas | Retrogames')
        root.geometry('1020x670')
        root.minsize(800, 520)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Treeview', rowheight=28)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Capas prontas para o seu NULD', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Baixe pelo PC ou aproveite suas capas do OPL. O PS2 pode ficar offline.').pack(anchor='w', pady=(4, 18))
        self.controls = []
        for label, variable in [('Pendrive / jogos', self.dest), ('ART do OPL (opcional)', self.art)]:
            line = ttk.Frame(frame)
            line.pack(fill='x', pady=4)
            ttk.Label(line, text=label, width=24).pack(side='left')
            field = ttk.Entry(line, textvariable=variable)
            field.pack(side='left', fill='x', expand=True, padx=8)
            button = ttk.Button(line, text='Escolher pasta', command=lambda v=variable: self.choose(v))
            button.pack(side='left')
            self.controls.extend([field, button])
        options = ttk.Frame(frame)
        options.pack(fill='x', pady=12)
        for text, variable in [('Baixar da internet quando não houver na ART', self.online), ('Substituir capas existentes', self.replace)]:
            widget = ttk.Checkbutton(options, text=text, variable=variable)
            widget.pack(side='left', padx=(0, 20))
            self.controls.append(widget)
        bar = ttk.Frame(frame)
        bar.pack(fill='x', pady=(0, 10))
        for text, action in [('1. Identificar jogos', self.start_scan), ('2. Preparar capas', self.start_process), ('Exportar relatório', self.export)]:
            widget = ttk.Button(bar, text=text, command=action)
            widget.pack(side='left', padx=(0, 8))
            self.controls.append(widget)
        self.stop = ttk.Button(bar, text='Cancelar', command=self.stop_work, state='disabled')
        self.stop.pack(side='right')
        table = ttk.Frame(frame)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('kind', 'title', 'serial', 'status'), show='headings', selectmode='extended')
        for key, label, width in [('kind', 'Sistema', 65), ('title', 'Jogo', 310), ('serial', 'Código', 120), ('status', 'Situação', 320)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=60)
        scrollbar = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.tree.bind('<Double-1>', self.edit)
        ttk.Label(frame, text='Sem seleção = todos os jogos. Ctrl/clique seleciona vários. Duplo clique permite corrigir o código.').pack(anchor='w', pady=(10, 4))
        self.progress = ttk.Progressbar(frame, mode='determinate')
        self.progress.pack(fill='x', pady=5)
        ttk.Label(frame, textvariable=self.status, wraplength=950).pack(anchor='w')
        ttk.Label(frame, text='Lê ISOs de PS2 e VCDs de PS1. Grava somente em covers; não altera os jogos.', foreground='#555555').pack(anchor='w', pady=(8, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.drain)
        self.scanned_root = None

    def choose(self, variable):
        value = filedialog.askdirectory(title='Selecionar pasta', parent=self.root)
        if value:
            variable.set(value)
            if variable is self.dest:
                art = Path(value) / 'ART'
                self.art.set(str(art) if art.is_dir() else '')

    def folder(self):
        if not self.dest.get().strip():
            raise ValueError('Escolha primeiro o pendrive ou a pasta dos jogos.')
        path = Path(self.dest.get()).resolve()
        if not path.is_dir():
            raise ValueError('A pasta selecionada não está disponível.')
        return path

    def launch(self, fn):
        self.busy = True
        self.cancel.clear()
        for widget in self.controls:
            widget.configure(state='disabled')
        self.stop.configure(state='normal')
        def run():
            try:
                fn()
            except Exception as e:
                self.events.put(('error', str(e)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    def start_scan(self):
        try:
            folder = self.folder()
        except ValueError as e:
            messagebox.showerror('Selecionar jogos', str(e), parent=self.root)
            return
        self.status.set('Identificando jogos...')
        self.scanned_root = folder
        self.progress.configure(value=0)
        self.launch(lambda: self.events.put(('games', scan(folder, self.cancel.is_set))))

    def start_process(self):
        try:
            folder = self.folder()
            if not self.games or folder != self.scanned_root:
                raise ValueError('Clique em Identificar jogos para esta pasta antes de continuar.')
            art = Path(self.art.get()).resolve() if self.art.get().strip() else None
            if art and not art.is_dir():
                raise ValueError('A pasta ART não está disponível.')
        except ValueError as e:
            messagebox.showerror('Preparar capas', str(e), parent=self.root)
            return
        selected = [int(x) for x in self.tree.selection()] or list(range(len(self.games)))
        replace, online = self.replace.get(), self.online.get()
        self.progress.configure(maximum=len(selected), value=0)
        def work():
            for n, index in enumerate(selected, 1):
                if self.cancel.is_set():
                    break
                game = self.games[index]
                self.events.put(('message', f'Preparando {n}/{len(selected)}: {game.title}'))
                try:
                    result = process(folder, game, art, replace, online, self.cancel.is_set)
                except Exception as e:
                    result = f'Erro: {e}'
                self.events.put(('row', (index, result, n)))
        self.launch(work)

    def stop_work(self):
        self.cancel.set()
        self.status.set('Cancelando após concluir a operação atual (rede: até 20 segundos)...')
        self.stop.configure(state='disabled')

    def drain(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'games':
                    self.games = data
                    self.tree.delete(*self.tree.get_children())
                    for index, game in enumerate(data):
                        self.tree.insert('', 'end', iid=str(index), values=(game.kind, game.title, game.serial, game.status))
                    self.status.set(f'{len(data)} jogo(s) encontrado(s).' if data else 'Nenhum jogo encontrado. Selecione a pasta que contém DVD, CD ou POPS.')
                elif kind == 'row':
                    index, result, n = data
                    game = self.games[index]
                    game.status = result
                    self.tree.item(str(index), values=(game.kind, game.title, game.serial, result))
                    self.tree.see(str(index))
                    self.progress.configure(value=n)
                elif kind == 'message':
                    self.status.set(data)
                elif kind == 'error':
                    self.status.set(data)
                    messagebox.showerror('NULD Capas', data, parent=self.root)
                elif kind == 'done':
                    self.busy = False
                    for widget in self.controls:
                        widget.configure(state='normal')
                    self.stop.configure(state='disabled')
                    if self.progress['value']:
                        self.status.set('Cancelado. Capas concluídas foram mantidas.' if self.cancel.is_set() else 'Concluído. Confira a situação de cada jogo e exporte o relatório se desejar.')
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def edit(self, event):
        if self.busy:
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        game = self.games[int(row)]
        value = simpledialog.askstring('Código do jogo', 'Informe o código exato da sua região (ex.: SLUS-21376):', initialvalue=game.serial, parent=self.root)
        if value is not None:
            code = serial_id(value)
            if not code:
                messagebox.showerror('Código inválido', 'Use SLUS-21376 ou SLUS_213.76.', parent=self.root)
                return
            game.serial, game.status = code, 'Código informado; pronto para preparar'
            self.tree.item(row, values=(game.kind, game.title, code, game.status))

    def export(self):
        filename = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='NULD-relatorio-capas.csv', filetypes=[('Relatório CSV', '*.csv')], parent=self.root)
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(['Sistema', 'Jogo', 'Código', 'Situação', 'Arquivo'])
                    for g in self.games:
                        writer.writerow([g.kind, g.title, g.serial, g.status, str(g.path)])
                self.status.set(f'Relatório salvo: {filename}')
            except OSError as e:
                messagebox.showerror('Relatório', str(e), parent=self.root)

    def close(self):
        if self.busy:
            self.stop_work()
            self.status.set('Cancelamento solicitado. Aguarde concluir e feche novamente.')
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    if '--smoke-test' in sys.argv:
        root.withdraw()
        root.update()
        root.destroy()
        return
    root.mainloop()


if __name__ == '__main__':
    main()
