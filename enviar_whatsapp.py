"""
Automacao WhatsApp via Selenium - Edge
Interface grafica com CustomTkinter
"""

import sys
import os
import json
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import math
import threading
import pandas as pd
import time
import pyperclip
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER = True
except ImportError:
    WEBDRIVER_MANAGER = False

# ============================================================
# CONFIGURACOES
# ============================================================

PAUSA_ENTRE_MENSAGENS = 10

OPERADORES_PADRAO = {
    "Ana Paula": "11900000001",
}

def _pasta_app():
    """Retorna a pasta correta tanto rodando .py quanto .exe (PyInstaller)."""
    import sys
    if getattr(sys, "frozen", False):
        # Rodando como .exe gerado pelo PyInstaller
        return os.path.dirname(sys.executable)
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()

ARQUIVO_OPERADORES = os.path.join(_pasta_app(), "operadores.json")

def carregar_operadores():
    try:
        if os.path.exists(ARQUIVO_OPERADORES):
            with open(ARQUIVO_OPERADORES, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if dados:
                    return dados
    except Exception as e:
        print(f"[AVISO] Erro ao carregar operadores: {e}")
    salvar_operadores(dict(OPERADORES_PADRAO))
    return dict(OPERADORES_PADRAO)

def salvar_operadores(ops):
    try:
        caminho = os.path.join(_pasta_app(), "operadores.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(ops, f, ensure_ascii=False, indent=2)
        print(f"[OK] Operadores salvos em: {caminho}")
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao salvar operadores: {e}")
        return False

# ============================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

parar_envio   = threading.Event()
driver_global = None


def extrair_numeros_lead(row):
    """Extrai tel1 a tel5 do lead, so o numero puro sem adicionar 55."""
    numeros = []
    for i in range(1, 6):
        tel = row.get(f"tel{i}")
        if pd.isna(tel) or str(tel).strip() in ("", "0", "nan"):
            continue
        tel_str = "".join(filter(str.isdigit, str(tel)))
        if tel_str:
            numeros.append(tel_str)
    return numeros


def distribuir_leads(df, operadores):
    nomes = list(operadores.keys())
    total = len(df)
    qtd_por_op = math.ceil(total / len(nomes))
    distribuicao = {}
    for i, nome in enumerate(nomes):
        inicio = i * qtd_por_op
        fim = min(inicio + qtd_por_op, total)
        distribuicao[nome] = df.iloc[inicio:fim]
    return distribuicao


def montar_mensagem(nome_operador, leads_operador):
    """Monta mensagem apenas com os numeros, sem nome do cliente."""
    linhas = [f"Ola {nome_operador}! Aqui estao seus leads para hoje:\n"]
    for _, row in leads_operador.iterrows():
        numeros = extrair_numeros_lead(row)
        for num in numeros:
            linhas.append(num)
    linhas.append("\nBom trabalho!")
    return "\n".join(linhas)


def iniciar_driver():
    pasta_script = _pasta_app()
    pasta_sessao = os.path.join(pasta_script, "whatsapp_session")
    os.makedirs(pasta_sessao, exist_ok=True)

    opcoes = ChromeOptions()
    opcoes.add_argument(f"--user-data-dir={pasta_sessao}")
    opcoes.add_argument("--profile-directory=Default")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")

    try:
        if WEBDRIVER_MANAGER:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opcoes)
        else:
            driver = webdriver.Chrome(options=opcoes)
        driver.minimize_window()
        return driver
    except Exception as e:
        raise Exception(f"Erro ao iniciar Chrome: {e}\nCertifique-se que o Google Chrome esta instalado.")


def enviar_mensagem(driver, numero_whatsapp, mensagem):
    """Envia mensagem para o operador. Adiciona 55 apenas no numero do operador."""
    numero_fmt = "55" + "".join(filter(str.isdigit, numero_whatsapp))
    url = f"https://web.whatsapp.com/send?phone={numero_fmt}"
    driver.get(url)
    try:
        campo = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located(
                (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
            )
        )
        time.sleep(2)
        pyperclip.copy(mensagem)
        campo.click()
        campo.send_keys(Keys.CONTROL, "v")
        time.sleep(1)
        campo.send_keys(Keys.ENTER)
        time.sleep(3)
        return True
    except Exception as e:
        print(f"[ERRO enviar_mensagem] {e}")
        return False


# ============================================================
# JANELA DE OPERADORES
# ============================================================

class JanelaOperadores(ctk.CTkToplevel):
    def __init__(self, master, callback_atualizar):
        super().__init__(master)
        self.title("Gerenciar Operadores")
        self.geometry("520x750")
        self.resizable(True, True)
        self.grab_set()
        self.callback_atualizar = callback_atualizar
        self.operadores = carregar_operadores()
        self.scroll = None
        self._build_ui()
        self._atualizar_lista()

    def _build_ui(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Gerenciar Operadores", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 2))
        ctk.CTkLabel(self, text="Adicione, edite ou remova operadores", text_color="gray", font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 8))

        # Formulario
        frame_form = ctk.CTkFrame(self, corner_radius=12)
        frame_form.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 10))
        frame_form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame_form, text="Nome do Operador", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 2))
        self.entry_nome = ctk.CTkEntry(frame_form, placeholder_text="Ex: Ana Paula", height=36)
        self.entry_nome.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))

        ctk.CTkLabel(frame_form, text="WhatsApp (DDD + numero, sem +55)", font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 2))
        self.entry_tel = ctk.CTkEntry(frame_form, placeholder_text="Ex: 11999990001", height=36)
        self.entry_tel.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

        ctk.CTkButton(frame_form, text="Adicionar / Atualizar", height=36, command=self._adicionar).grid(row=4, column=0, sticky="ew", padx=(14, 6), pady=(0, 14))
        ctk.CTkButton(frame_form, text="Limpar", height=36, width=90, fg_color="gray30", hover_color="gray20", command=self._limpar_form).grid(row=4, column=1, sticky="e", padx=(0, 14), pady=(0, 14))

        # Lista
        frame_lista = ctk.CTkFrame(self, corner_radius=12)
        frame_lista.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 8))
        frame_lista.grid_rowconfigure(1, weight=1)
        frame_lista.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame_lista, text="Operadores Cadastrados", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.scroll = ctk.CTkScrollableFrame(frame_lista, height=180)
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))

        # Botao fixo na base
        ctk.CTkButton(self, text="Salvar e Fechar", height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._salvar_fechar).grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 20))

    def _atualizar_lista(self):
        if self.scroll is None:
            return
        for w in self.scroll.winfo_children():
            w.destroy()

        if not self.operadores:
            ctk.CTkLabel(self.scroll, text="Nenhum operador cadastrado.", text_color="gray").pack(pady=10)
            return

        for nome, tel in self.operadores.items():
            row = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray85", "gray20"))
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=nome, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(side="left", padx=10, pady=8, fill="x", expand=True)
            ctk.CTkLabel(row, text=tel, text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
            ctk.CTkButton(row, text="Editar", width=60, height=28, fg_color="gray40", hover_color="gray30",
                command=lambda n=nome: self._editar(n)).pack(side="left", padx=4, pady=6)
            ctk.CTkButton(row, text="Remover", width=70, height=28, fg_color="#c0392b", hover_color="#a93226",
                command=lambda n=nome: self._remover(n)).pack(side="left", padx=(0, 8), pady=6)

    def _adicionar(self):
        nome = self.entry_nome.get().strip()
        tel  = "".join(filter(str.isdigit, self.entry_tel.get().strip()))
        if not nome or not tel:
            messagebox.showwarning("Atencao", "Preencha nome e telefone.", parent=self)
            return
        self.operadores[nome] = tel
        self._limpar_form()
        self._atualizar_lista()

    def _editar(self, nome):
        self.entry_nome.delete(0, "end")
        self.entry_nome.insert(0, nome)
        self.entry_tel.delete(0, "end")
        self.entry_tel.insert(0, self.operadores[nome])

    def _remover(self, nome):
        if messagebox.askyesno("Confirmar", f"Remover '{nome}'?", parent=self):
            del self.operadores[nome]
            self._atualizar_lista()

    def _limpar_form(self):
        self.entry_nome.delete(0, "end")
        self.entry_tel.delete(0, "end")

    def _salvar_fechar(self):
        if not self.operadores:
            messagebox.showwarning("Atencao", "Nenhum operador cadastrado.", parent=self)
            return
        ok = salvar_operadores(self.operadores)
        if ok:
            messagebox.showinfo("Salvo", f"{len(self.operadores)} operador(es) salvos!", parent=self)
            self.callback_atualizar(self.operadores)
            self.destroy()
        else:
            messagebox.showerror("Erro", "Nao foi possivel salvar. Verifique as permissoes da pasta.", parent=self)


# ============================================================
# JANELA PRINCIPAL
# ============================================================

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Fallen")
        self.geometry("700x800")
        self.resizable(False, False)
        self.arquivo_excel = None
        self.operadores = carregar_operadores()
        self._build_ui()

    def _build_ui(self):
        # Cabecalho
        frame_header = ctk.CTkFrame(self, fg_color="transparent")
        frame_header.pack(fill="x", padx=30, pady=(24, 0))

        try:
            logo_path = os.path.join(_pasta_app(), "logo.png")
            logo_img = ctk.CTkImage(Image.open(logo_path), size=(52, 52))
            ctk.CTkLabel(frame_header, image=logo_img, text="").pack(side="left", padx=(0, 10))
        except Exception:
            pass

        ctk.CTkLabel(frame_header, text="Fallen", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkButton(frame_header, text="Operadores", width=130, height=34,
            fg_color="gray30", hover_color="gray20",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.abrir_operadores).pack(side="right")

        ctk.CTkLabel(self, text="Distribuicao automatica de leads para operadores", font=ctk.CTkFont(size=13), text_color="gray").pack(pady=(4, 12))

        # Abas
        self.tabview = ctk.CTkTabview(self, height=600)
        self.tabview.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        self.tabview.add("Distribuir Leads")
        self.tabview.add("Mensagem Livre")
        self.tabview.add("Casamento")

        self._build_aba_leads(self.tabview.tab("Distribuir Leads"))
        self._build_aba_mensagem(self.tabview.tab("Mensagem Livre"))
        self._build_aba_casamento(self.tabview.tab("Casamento"))

    def _build_aba_leads(self, parent):
        # Arquivo
        frame_arquivo = ctk.CTkFrame(parent, corner_radius=12)
        frame_arquivo.pack(fill="x", pady=(12, 8))
        ctk.CTkLabel(frame_arquivo, text="Arquivo de Leads", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        row_arquivo = ctk.CTkFrame(frame_arquivo, fg_color="transparent")
        row_arquivo.pack(fill="x", padx=16, pady=(0, 12))
        self.label_arquivo = ctk.CTkLabel(row_arquivo, text="Nenhum arquivo selecionado", text_color="gray", anchor="w")
        self.label_arquivo.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row_arquivo, text="Selecionar Excel", width=150, command=self.selecionar_arquivo).pack(side="right")

        # Info
        frame_info = ctk.CTkFrame(parent, corner_radius=12)
        frame_info.pack(fill="x", pady=(0, 8))
        self.label_leads  = ctk.CTkLabel(frame_info, text="Leads: --", font=ctk.CTkFont(size=13))
        self.label_ops    = ctk.CTkLabel(frame_info, text=f"Operadores: {len(self.operadores)}", font=ctk.CTkFont(size=13))
        self.label_por_op = ctk.CTkLabel(frame_info, text="Leads por operador: --", font=ctk.CTkFont(size=13))
        self.label_leads.pack(side="left", padx=20, pady=12)
        self.label_ops.pack(side="left", padx=20, pady=12)
        self.label_por_op.pack(side="left", padx=20, pady=12)

        # Progresso
        frame_prog = ctk.CTkFrame(parent, corner_radius=12)
        frame_prog.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(frame_prog, text="Progresso", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.barra = ctk.CTkProgressBar(frame_prog, height=18, corner_radius=8)
        self.barra.pack(fill="x", padx=16, pady=(0, 8))
        self.barra.set(0)
        self.label_progresso = ctk.CTkLabel(frame_prog, text="Aguardando inicio...", text_color="gray", font=ctk.CTkFont(size=12))
        self.label_progresso.pack(anchor="w", padx=16, pady=(0, 12))

        # Log
        frame_log = ctk.CTkFrame(parent, corner_radius=12)
        frame_log.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(frame_log, text="Log de Atividades", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.log_box = ctk.CTkTextbox(frame_log, height=120, font=ctk.CTkFont(size=12), state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Botoes
        frame_btns = ctk.CTkFrame(parent, fg_color="transparent")
        frame_btns.pack(fill="x", pady=(0, 8))
        self.btn_iniciar = ctk.CTkButton(frame_btns, text="Iniciar Envio", height=42,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.iniciar_envio)
        self.btn_iniciar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_parar = ctk.CTkButton(frame_btns, text="Parar", height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#e74c3c", hover_color="#c0392b",
            state="disabled", command=self.parar)
        self.btn_parar.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _build_aba_mensagem(self, parent):
        self.checks_operadores = {}

        # Layout lado a lado: esquerda mensagem, direita operadores
        frame_main = ctk.CTkFrame(parent, fg_color="transparent")
        frame_main.pack(fill="both", expand=True, pady=(12, 8))
        frame_main.grid_columnconfigure(0, weight=2)
        frame_main.grid_columnconfigure(1, weight=1)
        frame_main.grid_rowconfigure(0, weight=1)

        # Coluna esquerda - mensagem + progresso + log
        frame_esq = ctk.CTkFrame(frame_main, fg_color="transparent")
        frame_esq.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        frame_msg = ctk.CTkFrame(frame_esq, corner_radius=12)
        frame_msg.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(frame_msg, text="Mensagem", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.text_mensagem = ctk.CTkTextbox(frame_msg, height=140, font=ctk.CTkFont(size=12))
        self.text_mensagem.pack(fill="x", padx=16, pady=(0, 12))

        frame_prog2 = ctk.CTkFrame(frame_esq, corner_radius=12)
        frame_prog2.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(frame_prog2, text="Progresso", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.barra2 = ctk.CTkProgressBar(frame_prog2, height=18, corner_radius=8)
        self.barra2.pack(fill="x", padx=16, pady=(0, 8))
        self.barra2.set(0)
        self.label_progresso2 = ctk.CTkLabel(frame_prog2, text="Aguardando inicio...", text_color="gray", font=ctk.CTkFont(size=12))
        self.label_progresso2.pack(anchor="w", padx=16, pady=(0, 12))

        frame_log2 = ctk.CTkFrame(frame_esq, corner_radius=12)
        frame_log2.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(frame_log2, text="Log", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.log_box2 = ctk.CTkTextbox(frame_log2, height=100, font=ctk.CTkFont(size=12), state="disabled")
        self.log_box2.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Coluna direita - checkboxes operadores
        frame_dir = ctk.CTkFrame(frame_main, corner_radius=12)
        frame_dir.grid(row=0, column=1, sticky="nsew")
        frame_dir.grid_rowconfigure(1, weight=1)
        frame_dir.grid_columnconfigure(0, weight=1)

        # Cabecalho com selecionar todos
        frame_topo_dir = ctk.CTkFrame(frame_dir, fg_color="transparent")
        frame_topo_dir.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(frame_topo_dir, text="Operadores", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(frame_topo_dir, text="Todos", width=55, height=24,
            fg_color="gray30", hover_color="gray20", font=ctk.CTkFont(size=11),
            command=self._selecionar_todos).pack(side="right", padx=(4, 0))
        ctk.CTkButton(frame_topo_dir, text="Nenhum", width=65, height=24,
            fg_color="gray30", hover_color="gray20", font=ctk.CTkFont(size=11),
            command=self._desmarcar_todos).pack(side="right")

        self.scroll_checks = ctk.CTkScrollableFrame(frame_dir)
        self.scroll_checks.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._popular_checks()

        # Botoes na base
        frame_btns2 = ctk.CTkFrame(parent, fg_color="transparent")
        frame_btns2.pack(fill="x", pady=(0, 8))
        self.btn_enviar_livre = ctk.CTkButton(frame_btns2, text="Enviar para Selecionados", height=42,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.iniciar_envio_livre)
        self.btn_enviar_livre.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_parar_livre = ctk.CTkButton(frame_btns2, text="Parar", height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#e74c3c", hover_color="#c0392b",
            state="disabled", command=self.parar_livre)
        self.btn_parar_livre.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _popular_checks(self):
        for w in self.scroll_checks.winfo_children():
            w.destroy()
        self.checks_operadores = {}
        for nome in self.operadores:
            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(self.scroll_checks, text=nome, variable=var, font=ctk.CTkFont(size=12))
            cb.pack(anchor="w", pady=3)
            self.checks_operadores[nome] = var

    def _selecionar_todos(self):
        for var in self.checks_operadores.values():
            var.set(True)

    def _desmarcar_todos(self):
        for var in self.checks_operadores.values():
            var.set(False)

    def log(self, texto):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", texto + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def log2(self, texto):
        self.log_box2.configure(state="normal")
        self.log_box2.insert("end", texto + "\n")
        self.log_box2.see("end")
        self.log_box2.configure(state="disabled")

    def abrir_operadores(self):
        JanelaOperadores(self, self._atualizar_operadores)

    def _atualizar_operadores(self, novos_ops):
        self.operadores = novos_ops
        self.label_ops.configure(text=f"Operadores: {len(self.operadores)}")
        self.log(f"[OK] Operadores atualizados: {len(self.operadores)} cadastrados.")
        self._popular_checks()

    def iniciar_envio_livre(self):
        mensagem = self.text_mensagem.get("1.0", "end").strip()
        if not mensagem:
            messagebox.showwarning("Atencao", "Digite uma mensagem antes de enviar.")
            return
        selecionados = {n: self.operadores[n] for n, v in self.checks_operadores.items() if v.get()}
        if not selecionados:
            messagebox.showwarning("Atencao", "Selecione ao menos um operador.")
            return
        parar_envio.clear()
        self.btn_enviar_livre.configure(state="disabled")
        self.btn_parar_livre.configure(state="normal")
        self.barra2.set(0)
        self.label_progresso2.configure(text="Iniciando...")
        t = threading.Thread(target=self.executar_livre, args=(mensagem, selecionados), daemon=True)
        t.start()

    def parar_livre(self):
        parar_envio.set()
        self.log2("[PARADO] Envio interrompido.")
        self.btn_parar_livre.configure(state="disabled")
        self.btn_enviar_livre.configure(state="normal")

    def executar_livre(self, mensagem, selecionados):
        global driver_global
        try:
            self.log2("=" * 45)
            self.log2("   Enviando mensagem livre")
            self.log2("=" * 45)

            self.log2("\n[1/2] Iniciando Edge (minimizado)...")
            driver_global = iniciar_driver()
            driver_global.get("https://web.whatsapp.com")
            self.log2("[LOGIN] Aguardando 60s para login/verificacao...")
            for _ in range(60):
                if parar_envio.is_set():
                    break
                time.sleep(1)

            if parar_envio.is_set():
                driver_global.quit()
                return

            self.log2("\n[2/2] Enviando para operadores...")
            total = len(selecionados)
            enviados = 0
            falhas   = 0

            for i, (nome, whatsapp) in enumerate(selecionados.items(), start=1):
                if parar_envio.is_set():
                    self.log2("\n[PARADO] Envio cancelado.")
                    break

                self.log2(f"\n[{i}/{total}] Enviando para: {nome}")
                self.label_progresso2.configure(text=f"Enviando para {nome} ({i}/{total})")
                sucesso = enviar_mensagem(driver_global, whatsapp, mensagem)

                if sucesso:
                    enviados += 1
                    self.log2(f"      [OK] Enviado!")
                else:
                    falhas += 1
                    self.log2(f"      [ERRO] Falha no envio.")

                self.barra2.set(i / total)

                if i < total and not parar_envio.is_set():
                    self.log2(f"      Aguardando {PAUSA_ENTRE_MENSAGENS}s...")
                    for _ in range(PAUSA_ENTRE_MENSAGENS):
                        if parar_envio.is_set():
                            break
                        time.sleep(1)

            self.barra2.set(1)
            self.log2("\n" + "=" * 45)
            self.log2(f"   Concluido! Enviados: {enviados}  Falhas: {falhas}")
            self.log2("=" * 45)
            self.label_progresso2.configure(text=f"Concluido! {enviados} enviados, {falhas} falhas.")
            driver_global.quit()

        except Exception as e:
            self.log2(f"\n[ERRO GERAL] {e}")
        finally:
            self.btn_enviar_livre.configure(state="normal")
            self.btn_parar_livre.configure(state="disabled")

    def selecionar_arquivo(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            self.arquivo_excel = path
            nome = os.path.basename(path)
            self.label_arquivo.configure(text=nome, text_color="white")
            try:
                df = pd.read_excel(path)
                total = len(df)
                por_op = math.ceil(total / len(self.operadores)) if self.operadores else 0
                self.label_leads.configure(text=f"Leads: {total}")
                self.label_por_op.configure(text=f"Leads por operador: {por_op}")
                self.log(f"[OK] Arquivo carregado: {nome} ({total} leads)")
            except Exception as e:
                self.log(f"[ERRO] Nao foi possivel ler o arquivo: {e}")

    def parar(self):
        parar_envio.set()
        self.log("[PARADO] Envio interrompido pelo usuario.")
        self.btn_parar.configure(state="disabled")
        self.btn_iniciar.configure(state="normal")

    def iniciar_envio(self):
        if not self.arquivo_excel:
            messagebox.showwarning("Atencao", "Selecione o arquivo Excel antes de iniciar.")
            return
        if not self.operadores:
            messagebox.showwarning("Atencao", "Cadastre ao menos um operador antes de iniciar.")
            return
        parar_envio.clear()
        self.btn_iniciar.configure(state="disabled")
        self.btn_parar.configure(state="normal")
        self.barra.set(0)
        self.label_progresso.configure(text="Iniciando...")
        t = threading.Thread(target=self.executar, daemon=True)
        t.start()

    def executar(self):
        global driver_global
        try:
            self.log("=" * 45)
            self.log("   Iniciando envio de leads")
            self.log("=" * 45)

            self.log(f"\n[1/4] Lendo arquivo: {os.path.basename(self.arquivo_excel)}")
            df = pd.read_excel(self.arquivo_excel)
            self.log(f"      {len(df)} leads encontrados.")

            self.log(f"\n[2/4] Distribuindo entre {len(self.operadores)} operadores...")
            distribuicao = distribuir_leads(df, self.operadores)
            for nome, leads in distribuicao.items():
                self.log(f"      {nome}: {len(leads)} leads")

            self.log("\n[3/4] Iniciando Edge (minimizado)...")
            driver_global = iniciar_driver()

            self.log("[LOGIN] Abrindo WhatsApp Web...")
            driver_global.get("https://web.whatsapp.com")
            self.log("       Aguardando 60s para login/verificacao...")
            for i in range(60):
                if parar_envio.is_set():
                    break
                time.sleep(1)

            if parar_envio.is_set():
                driver_global.quit()
                return

            self.log("\n[4/4] Enviando mensagens...")
            total_ops = len(self.operadores)
            enviados  = 0
            falhas    = 0

            for i, (nome, whatsapp) in enumerate(self.operadores.items(), start=1):
                if parar_envio.is_set():
                    self.log("\n[PARADO] Envio cancelado.")
                    break

                leads_op = distribuicao.get(nome)
                if leads_op is None or len(leads_op) == 0:
                    self.log(f"\n[{i}/{total_ops}] {nome} - sem leads, pulando.")
                    continue

                mensagem = montar_mensagem(nome, leads_op)
                self.log(f"\n[{i}/{total_ops}] Enviando para: {nome} (WA: {whatsapp})")
                self.log(f"      Total numeros na mensagem: {len(leads_op)}")
                self.label_progresso.configure(text=f"Enviando para {nome} ({i}/{total_ops})")

                sucesso = enviar_mensagem(driver_global, whatsapp, mensagem)

                if sucesso:
                    enviados += 1
                    self.log(f"      [OK] Enviado com sucesso!")
                else:
                    falhas += 1
                    self.log(f"      [ERRO] Falha no envio.")

                self.barra.set(i / total_ops)
                self.label_progresso.configure(text=f"{i}/{total_ops} operadores concluidos")

                if i < total_ops and not parar_envio.is_set():
                    self.log(f"      Aguardando {PAUSA_ENTRE_MENSAGENS}s...")
                    for _ in range(PAUSA_ENTRE_MENSAGENS):
                        if parar_envio.is_set():
                            break
                        time.sleep(1)

            self.barra.set(1)
            self.log("\n" + "=" * 45)
            self.log(f"   Concluido! Enviados: {enviados}  Falhas: {falhas}")
            self.log("=" * 45)
            self.label_progresso.configure(text=f"Concluido! {enviados} enviados, {falhas} falhas.")
            driver_global.quit()

        except Exception as e:
            self.log(f"\n[ERRO GERAL] {e}")
        finally:
            self.btn_iniciar.configure(state="normal")
            self.btn_parar.configure(state="disabled")


    def _build_aba_casamento(self, parent):
        self.casamento_arquivo   = None
        self.casamento_imagem    = None

        ctk.CTkLabel(parent, text="Enviar convite com imagem para convidados",
            font=ctk.CTkFont(size=13), text_color="gray").pack(anchor="w", pady=(12, 8))

        # Arquivo Excel
        frame_arq = ctk.CTkFrame(parent, corner_radius=12)
        frame_arq.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(frame_arq, text="Lista de Convidados (Excel)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        row_arq = ctk.CTkFrame(frame_arq, fg_color="transparent")
        row_arq.pack(fill="x", padx=16, pady=(0, 12))
        self.label_casamento_arq = ctk.CTkLabel(row_arq, text="Nenhum arquivo selecionado", text_color="gray", anchor="w")
        self.label_casamento_arq.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row_arq, text="Selecionar Excel", width=150,
            command=self._selecionar_arq_casamento).pack(side="right")

        # Imagem
        frame_img = ctk.CTkFrame(parent, corner_radius=12)
        frame_img.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(frame_img, text="Imagem (paleta de cores)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        row_img = ctk.CTkFrame(frame_img, fg_color="transparent")
        row_img.pack(fill="x", padx=16, pady=(0, 12))
        self.label_casamento_img = ctk.CTkLabel(row_img, text="Nenhuma imagem selecionada", text_color="gray", anchor="w")
        self.label_casamento_img.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row_img, text="Selecionar Imagem", width=150,
            command=self._selecionar_img_casamento).pack(side="right")

        # Mensagem
        frame_msg = ctk.CTkFrame(parent, corner_radius=12)
        frame_msg.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(frame_msg, text="Mensagem", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.text_casamento = ctk.CTkTextbox(frame_msg, height=100, font=ctk.CTkFont(size=12))
        self.text_casamento.pack(fill="x", padx=16, pady=(0, 4))
        self.text_casamento.insert("1.0", "Oi! Estamos ansiosos para te ver no nosso casamento!\nSegue abaixo a paleta de cores do evento para nos ajudar na decoracao. \nObrigado!")
        ctk.CTkLabel(frame_msg, text="Sera enviado apenas para quem confirmou presenca (Sim)", text_color="gray", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 12))

        # Progresso e log
        frame_prog = ctk.CTkFrame(parent, corner_radius=12)
        frame_prog.pack(fill="x", pady=(0, 8))
        self.barra3 = ctk.CTkProgressBar(frame_prog, height=18, corner_radius=8)
        self.barra3.pack(fill="x", padx=16, pady=(12, 8))
        self.barra3.set(0)
        self.label_prog3 = ctk.CTkLabel(frame_prog, text="Aguardando inicio...", text_color="gray", font=ctk.CTkFont(size=12))
        self.label_prog3.pack(anchor="w", padx=16, pady=(0, 12))

        frame_log3 = ctk.CTkFrame(parent, corner_radius=12)
        frame_log3.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(frame_log3, text="Log", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.log_box3 = ctk.CTkTextbox(frame_log3, height=80, font=ctk.CTkFont(size=12), state="disabled")
        self.log_box3.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Botoes
        frame_btns3 = ctk.CTkFrame(parent, fg_color="transparent")
        frame_btns3.pack(fill="x", pady=(0, 8))
        self.btn_casamento = ctk.CTkButton(frame_btns3, text="Enviar para Convidados", height=42,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.iniciar_casamento)
        self.btn_casamento.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_parar_casamento = ctk.CTkButton(frame_btns3, text="Parar", height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#e74c3c", hover_color="#c0392b",
            state="disabled", command=self.parar_casamento)
        self.btn_parar_casamento.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _selecionar_arq_casamento(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            self.casamento_arquivo = path
            self.label_casamento_arq.configure(text=os.path.basename(path), text_color="white")
            try:
                df = pd.read_excel(path)
                confirmados = df[df["Ira ao evento?"].str.strip().str.lower() == "sim"] if "Ira ao evento?" in df.columns else df
                # tenta coluna com acento tambem
                for col in df.columns:
                    if "ir" in col.lower() and "evento" in col.lower():
                        confirmados = df[df[col].str.strip().str.lower() == "sim"]
                        break
                self.log3(f"[OK] {len(confirmados)} convidados confirmados encontrados.")
            except Exception as e:
                self.log3(f"[ERRO] {e}")

    def _selecionar_img_casamento(self):
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.png *.jpg *.jpeg *.gif *.webp")])
        if path:
            self.casamento_imagem = path
            self.label_casamento_img.configure(text=os.path.basename(path), text_color="white")
            self.log3(f"[OK] Imagem selecionada: {os.path.basename(path)}")

    def log3(self, texto):
        self.log_box3.configure(state="normal")
        self.log_box3.insert("end", texto + "\n")
        self.log_box3.see("end")
        self.log_box3.configure(state="disabled")

    def parar_casamento(self):
        parar_envio.set()
        self.log3("[PARADO] Envio interrompido.")
        self.btn_parar_casamento.configure(state="disabled")
        self.btn_casamento.configure(state="normal")

    def iniciar_casamento(self):
        if not self.casamento_arquivo:
            messagebox.showwarning("Atencao", "Selecione o arquivo Excel dos convidados.")
            return
        if not self.casamento_imagem:
            messagebox.showwarning("Atencao", "Selecione a imagem da paleta de cores.")
            return
        mensagem = self.text_casamento.get("1.0", "end").strip()
        if not mensagem:
            messagebox.showwarning("Atencao", "Digite uma mensagem.")
            return
        parar_envio.clear()
        self.btn_casamento.configure(state="disabled")
        self.btn_parar_casamento.configure(state="normal")
        self.barra3.set(0)
        self.label_prog3.configure(text="Iniciando...")
        t = threading.Thread(target=self.executar_casamento, args=(mensagem,), daemon=True)
        t.start()

    def executar_casamento(self, mensagem):
        global driver_global
        try:
            self.log3("=" * 40)
            self.log3("   Enviando convites")
            self.log3("=" * 40)

            # Le e filtra confirmados
            df = pd.read_excel(self.casamento_arquivo)
            col_resp = None
            col_tel  = None
            for col in df.columns:
                if "ir" in col.lower() and "evento" in col.lower():
                    col_resp = col
                if "telefone" in col.lower() or "tel" in col.lower() or "phone" in col.lower():
                    col_tel = col

            if not col_resp or not col_tel:
                self.log3(f"[ERRO] Colunas nao encontradas. Colunas: {list(df.columns)}")
                return

            confirmados = df[df[col_resp].str.strip().str.lower() == "sim"]
            numeros = confirmados[col_tel].dropna().tolist()
            self.log3(f"[OK] {len(numeros)} convidados confirmados.")

            # Inicia navegador
            self.log3("\n[1/2] Iniciando Chrome...")
            driver_global = iniciar_driver()
            driver_global.get("https://web.whatsapp.com")
            self.log3("[LOGIN] Aguardando 60s para login...")
            for _ in range(60):
                if parar_envio.is_set():
                    break
                time.sleep(1)

            if parar_envio.is_set():
                driver_global.quit()
                return

            self.log3("\n[2/2] Enviando mensagens...")
            enviados = 0
            falhas   = 0
            total    = len(numeros)

            for i, numero in enumerate(numeros, start=1):
                if parar_envio.is_set():
                    self.log3("[PARADO] Envio cancelado.")
                    break

                numero_fmt = "".join(filter(str.isdigit, str(numero)))
                if not numero_fmt.startswith("55"):
                    numero_fmt = "55" + numero_fmt

                self.log3(f"[{i}/{total}] Enviando para: {numero_fmt}")
                self.label_prog3.configure(text=f"Enviando {i}/{total}...")

                try:
                    # Abre conversa
                    driver_global.get(f"https://web.whatsapp.com/send?phone={numero_fmt}")
                    campo = WebDriverWait(driver_global, 30).until(
                        EC.presence_of_element_located(
                            (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
                        )
                    )
                    time.sleep(2)

                    # Envia mensagem de texto
                    pyperclip.copy(mensagem)
                    campo.click()
                    campo.send_keys(Keys.CONTROL, "v")
                    time.sleep(1)
                    campo.send_keys(Keys.ENTER)
                    time.sleep(3)

                    # Envia imagem via botao de anexo
                    btn_anexo = WebDriverWait(driver_global, 10).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, '//button[@aria-label="Attach"]|//button[@title="Attach"]|//div[@title="Attach"]|//span[@data-icon="plus"]/..')
                        )
                    )
                    btn_anexo.click()
                    time.sleep(1)

                    # Clica em "Photos & Videos" ou input de arquivo
                    input_file = WebDriverWait(driver_global, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH, '//input[@accept="image/*,video/mp4,video/3gpp,video/quicktime"]')
                        )
                    )
                    input_file.send_keys(self.casamento_imagem)
                    time.sleep(3)

                    # Clica em enviar
                    btn_send = WebDriverWait(driver_global, 10).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, '//span[@data-icon="send"]/..')
                        )
                    )
                    btn_send.click()
                    time.sleep(3)

                    enviados += 1
                    self.log3(f"      [OK] Enviado!")
                except Exception as e:
                    falhas += 1
                    self.log3(f"      [ERRO] {e}")

                self.barra3.set(i / total)

                if i < total and not parar_envio.is_set():
                    for _ in range(PAUSA_ENTRE_MENSAGENS):
                        if parar_envio.is_set():
                            break
                        time.sleep(1)

            self.barra3.set(1)
            self.log3("\n" + "=" * 40)
            self.log3(f"   Concluido! Enviados: {enviados}  Falhas: {falhas}")
            self.log3("=" * 40)
            self.label_prog3.configure(text=f"Concluido! {enviados} enviados, {falhas} falhas.")
            driver_global.quit()

        except Exception as e:
            self.log3(f"\n[ERRO GERAL] {e}")
        finally:
            self.btn_casamento.configure(state="normal")
            self.btn_parar_casamento.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
