#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy_to_vm.py — Despliega el Linux Agent a la VM remota via Paramiko + SFTP.

Las credenciales y configuración se leen del archivo .env del proyecto.
Ejecutar desde Windows: python deploy_to_vm.py
"""
import sys
import io

# Forzar UTF-8 en PowerShell/Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import paramiko
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
_BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(_BASE_DIR / ".env")

# ── Configuración de conexión (leída del .env) ────────────────────────────────
VM_HOST    = os.getenv("VM_HOST",    "192.168.0.162")
VM_PORT    = int(os.getenv("VM_PORT", "22"))
VM_USER    = os.getenv("VM_USER",    "test")
VM_PASS    = os.getenv("VM_PASS",    "")
REMOTE_DIR = os.getenv("REMOTE_DIR", "/home/test/linux_agent")

# ── Archivos a subir ──────────────────────────────────────────────────────────
LOCAL_DIR = _BASE_DIR

FILES_TO_UPLOAD = [
    # ── Core ──────────────────────────────────────────────────────────────────
    "main.py",
    "config.py",
    "requirements.txt",
    "requirements-dev.txt",
    ".env.example",
    ".gitignore",
    "setup.py",
    "test_agent.py",
    "sync.py",
    "install_system.py",
    "lm_models.json",
    "README.md",
    "MANUAL.md",
    "linux agent PROJECT_CONTEXT.md",
    # ── Herramientas (v2.0) ────────────────────────────────────────────────────
    "tools.py",
    "tools_web.py",
    "tools_files.py",
    "tools_remote.py",
    # ── Módulos nuevos (v2.0) ─────────────────────────────────────────────────
    "agentic_loop.py",
    "memory_consolidator.py",
    "sentinel.py",
    "telegram_bot.py",
    # ── LLM adapters ──────────────────────────────────────────────────────────
    "llm/__init__.py",
    "llm/base.py",
    "llm/history.py",
    "llm/memory.py",
    "llm/tool_registry.py",
    "llm/router.py",
    "llm/lmstudio_agent.py",
    "llm/ollama_agent.py",
    "llm/gemini_agent.py",
    "llm/openai_agent.py",
    "llm/grok_agent.py",
    "llm/anthropic_agent.py",
]

RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"


def _ok(msg):   print(f"{GREEN}  ✓ {msg}{RESET}")
def _info(msg): print(f"{CYAN}  → {msg}{RESET}")
def _warn(msg): print(f"{YELLOW}  ⚠ {msg}{RESET}")
def _fail(msg, exc=None):
    print(f"{RED}  ✗ {msg}{RESET}")
    if exc:
        print(f"    {exc}")
    sys.exit(1)


def run_remote(ssh: paramiko.SSHClient, cmd: str, check: bool = True) -> tuple[str, str, int]:
    """Ejecuta un comando remoto y retorna (stdout, stderr, exit_code)."""
    _, stdout, stderr = ssh.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if out:
        print(f"    {out}")
    if err and exit_code != 0:
        print(f"    {YELLOW}STDERR: {err}{RESET}")
    if check and exit_code != 0:
        _fail(f"Comando falló (exit {exit_code}): {cmd}", err)
    return out, err, exit_code


def main():
    if not VM_PASS:
        _fail("VM_PASS no está configurada en el .env. Revisá el archivo .env.")

    print(f"\n{BOLD}{CYAN}== Deploy Linux Agent → VM {VM_USER}@{VM_HOST}:{VM_PORT} =={RESET}\n")

    # ── Conectar SSH ──────────────────────────────────────────────────────────
    _info(f"Conectando a {VM_USER}@{VM_HOST}:{VM_PORT}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASS, timeout=15)
        _ok("Conexión SSH establecida.")
    except Exception as e:
        _fail(f"No se pudo conectar a la VM: {e}")

    # ── Crear estructura de directorios ───────────────────────────────────────
    _info("Creando estructura de directorios...")
    run_remote(ssh, f"mkdir -p {REMOTE_DIR}/llm")
    _ok("Directorios creados.")

    # Crear directorio de logs del centinela
    run_remote(ssh, f"touch {REMOTE_DIR}/sentinel.log 2>/dev/null || true", check=False)

    # ── Subir archivos via SFTP ───────────────────────────────────────────────
    _info("Subiendo archivos del proyecto...")
    sftp = ssh.open_sftp()

    for relpath in FILES_TO_UPLOAD:
        local_path  = LOCAL_DIR / relpath
        remote_path = f"{REMOTE_DIR}/{relpath}"

        if not local_path.exists():
            _warn(f"Archivo no encontrado localmente: {relpath}")
            continue

        # Asegurar que el directorio remoto existe
        remote_dir = os.path.dirname(remote_path)
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            sftp.mkdir(remote_dir)

        sftp.put(str(local_path), remote_path)
        print(f"  {GREEN}↑{RESET} {relpath}")

    sftp.close()
    _ok("Archivos subidos correctamente.")

    # ── Verificar Python ──────────────────────────────────────────────────────
    _info("Verificando versión de Python...")
    run_remote(ssh, "python3 --version")

    # ── Crear venv ────────────────────────────────────────────────────────────
    _info("Creando entorno virtual...")
    run_remote(ssh, f"cd {REMOTE_DIR} && python3 -m venv venv", check=False)
    _ok("Venv listo.")

    # ── Instalar dependencias ─────────────────────────────────────────────────
    _info("Instalando dependencias (puede tardar unos minutos)...")
    PIP = f"{REMOTE_DIR}/venv/bin/pip"
    run_remote(ssh, f"{PIP} install --upgrade pip -q")
    out, err, code = run_remote(
        ssh,
        f"{PIP} install -r {REMOTE_DIR}/requirements.txt",
        check=False,
    )
    if code != 0:
        _warn("Algunos paquetes fallaron (continuamos de todas formas)")
    else:
        _ok("Dependencias instaladas.")

    # ── Crear .env en la VM ───────────────────────────────────────────────────
    _info("Creando .env en la VM (si no existe)...")
    lmstudio_url = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.0.142:1234/v1")
    # Verificar si ya existe .env en la VM
    _, _, rc = run_remote(ssh, f"test -f {REMOTE_DIR}/.env", check=False)
    if rc == 0:
        _warn(".env ya existe en la VM — no se sobreescribe. Editá manualmente si necesitás agregar nuevas variables.")
    else:
        env_content = f"""# Linux Local AI Agent v2.0 — Configuración mínima
# Editá este archivo con: nano {REMOTE_DIR}/.env
LMSTUDIO_BASE_URL={lmstudio_url}
LMSTUDIO_MODEL=
LMSTUDIO_EMBED_MODEL=
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
GROK_API_KEY=
GROK_MODEL=grok-3-mini
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
REQUIRE_CONFIRMATION=True
COMMAND_TIMEOUT=60
DEFAULT_ENGINE=local
MAX_OUTPUT_CHARS=4000
MEMORY_ENABLED=True
MEMORY_TOP_K=3
MEMORY_THRESHOLD=0.75
MEMORY_MAX_ENTRIES=2000
# v2.0 — Telegram (deshabilitado por defecto)
TELEGRAM_ENABLED=False
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_IDS=
# v2.0 — Centinela (deshabilitado por defecto)
SENTINEL_ENABLED=False
SENTINEL_INTERVAL_SECONDS=300
SENTINEL_LOG_TAIL_LINES=100
# v2.0 — Búsqueda web
WEB_SEARCH_ENABLED=True
WEB_SEARCH_MAX_RESULTS=5
# v2.0 — Heimdall (FASE 2 — no configurar aún)
HEIMDALL_ENABLED=False
"""
        sftp2 = ssh.open_sftp()
        with sftp2.open(f"{REMOTE_DIR}/.env", "w") as f:
            f.write(env_content)
        sftp2.close()
        _ok(".env creado en la VM.")

    # ── Tests de importación ──────────────────────────────────────────────────
    print(f"\n{BOLD}[TEST] Verificando imports del proyecto...{RESET}")
    PYTHON = f"{REMOTE_DIR}/venv/bin/python"

    test_cmds = [
        ("config.py",  f"cd {REMOTE_DIR} && {PYTHON} -c \"import config; print('config OK, URL=', config.LMSTUDIO_BASE_URL)\""),
        ("tools.py",   f"cd {REMOTE_DIR} && {PYTHON} -c \"import tools; print('tools OK')\""),
        ("llm/router", f"cd {REMOTE_DIR} && {PYTHON} -c \"from llm.router import motores_disponibles; print('router OK, motores=', list(motores_disponibles().keys()))\""),
    ]

    for nombre, cmd in test_cmds:
        out, err, code = run_remote(ssh, cmd, check=False)
        if code == 0:
            _ok(f"Import {nombre}: OK")
        else:
            _warn(f"Import {nombre} falló:")
            if err:
                print(f"    {err}")

    # ── Test conexión LM Studio ───────────────────────────────────────────────
    print(f"\n{BOLD}[TEST] Probando conexión a LM Studio ({lmstudio_url})...{RESET}")
    test_lmstudio = f"""cd {REMOTE_DIR} && {PYTHON} -c "
import sys, openai, config
client = openai.OpenAI(base_url=config.LMSTUDIO_BASE_URL, api_key='lm-studio')
try:
    models = client.models.list()
    ids = [m.id for m in models.data]
    print('LM Studio CONECTADO. Modelos cargados:', ids[:3])
except Exception as e:
    print('ERROR conectando a LM Studio:', e)
    sys.exit(1)
" """
    out, err, code = run_remote(ssh, test_lmstudio, check=False)
    if code == 0:
        _ok("LM Studio: CONECTADO ✓")
    else:
        _warn(f"LM Studio no accesible desde la VM (verificá que esté corriendo en {lmstudio_url})")

    # ── Resultado final ────────────────────────────────────────────────────────
    print(f"""
{GREEN}{BOLD}
==========================================================
  ✓ Deploy completado exitosamente
==========================================================
{RESET}
  Para usar el agente, conectate a la VM:
  {CYAN}ssh {VM_USER}@{VM_HOST}{RESET}

  Luego ejecutá:
  {CYAN}cd {REMOTE_DIR}
  source venv/bin/activate
  python main.py{RESET}

  Para correr los tests completos en la VM:
  {CYAN}python test_agent.py{RESET}
""")

    ssh.close()


if __name__ == "__main__":
    main()
