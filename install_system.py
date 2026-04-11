#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_system.py — Instala las dependencias del Linux Agent en el Python del sistema.

Uso en Ubuntu:
    python3 install_system.py

Esto permite ejecutar `python3 main.py` directamente sin activar el venv.
En Ubuntu 24.04+ se necesita --break-system-packages o la instalación falla.
"""
import sys
import subprocess
import os

RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"


def _ok(msg):    print(f"{GREEN}  ✓ {msg}{RESET}")
def _info(msg):  print(f"{CYAN}  → {msg}{RESET}")
def _warn(msg):  print(f"{YELLOW}  ⚠ {msg}{RESET}")
def _fail(msg):
    print(f"{RED}  ✗ {msg}{RESET}")
    sys.exit(1)


def detectar_python() -> str:
    """Retorna el ejecutable de Python del sistema (no del venv)."""
    # Si estamos dentro de un venv, usar el Python real del sistema
    real_python = getattr(sys, "real_prefix", None) or getattr(sys, "base_prefix", sys.prefix)
    candidatos = [
        os.path.join(real_python, "bin", "python3"),
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    ]
    for p in candidatos:
        if os.path.exists(p):
            return p
    return "python3"  # Fallback


def main():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║   🐍  Linux Agent — Instalación en Python del sistema    ║
╚══════════════════════════════════════════════════════════╝{RESET}

  Esto instala las dependencias en el Python global, permitiendo
  ejecutar el agente con {CYAN}python3 main.py{RESET} sin activar el venv.
""")

    python_exe = detectar_python()
    _info(f"Python del sistema detectado: {python_exe}")

    # Verificar versión
    result = subprocess.run([python_exe, "--version"], capture_output=True, text=True)
    version_str = result.stdout.strip() or result.stderr.strip()
    _info(f"Versión: {version_str}")

    # Nombre del paquete pip
    pip_cmd_base = [python_exe, "-m", "pip", "install", "--upgrade"]

    # En Ubuntu 24.04+, pip requiere --break-system-packages para instalar en el sistema
    # Detectar si el entorno está marcado como "externally-managed"
    test_result = subprocess.run(
        [python_exe, "-m", "pip", "install", "requests", "--dry-run"],
        capture_output=True, text=True
    )
    needs_break_flag = "externally-managed-environment" in (test_result.stderr or "")

    if needs_break_flag:
        _warn("Ubuntu 24.04+ detectado: usando --break-system-packages")
        pip_cmd_base.append("--break-system-packages")
    
    _info("Actualizando pip...")
    subprocess.run(pip_cmd_base + ["pip"], check=False)

    # Paquetes a instalar (igual que requirements.txt)
    paquetes = [
        "openai>=1.0.0",
        "google-genai>=1.0.0",
        "anthropic>=0.40.0",
        "python-dotenv>=1.0.0",
        "rich>=13.0.0",
        "httpx>=0.27.0",
        "prompt_toolkit>=3.0.0",
    ]

    print(f"\n{BOLD}Instalando dependencias del agente...{RESET}")
    for paquete in paquetes:
        _info(f"Instalando {paquete}...")
        result = subprocess.run(
            pip_cmd_base + [paquete],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            _ok(f"{paquete}")
        else:
            _warn(f"Error instalando {paquete}:")
            print(f"    {result.stderr[:200]}")

    # Verificar importaciones
    print(f"\n{BOLD}Verificando importaciones...{RESET}")
    imports_test = [
        ("dotenv",     "from dotenv import load_dotenv"),
        ("openai",     "import openai"),
        ("rich",       "from rich.console import Console"),
        ("httpx",      "import httpx"),
        ("google-genai","from google import genai"),
        ("anthropic",  "import anthropic"),
    ]

    todos_ok = True
    for nombre, stmt in imports_test:
        result = subprocess.run(
            [python_exe, "-c", stmt],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            _ok(f"import {nombre}")
        else:
            _warn(f"import {nombre} FALLÓ: {result.stderr.strip()[:100]}")
            todos_ok = False

    print()
    if todos_ok:
        print(f"""
{GREEN}{BOLD}
==========================================================
  ✓  Instalación completada exitosamente
==========================================================
{RESET}
  Ahora podés ejecutar el agente directamente:

  {CYAN}cd ~/linux_agent
  python3 main.py{RESET}

  O añadir un alias a tu ~/.bashrc para mayor comodidad:

  {CYAN}echo "alias linux-agent='cd ~/linux_agent && python3 main.py'" >> ~/.bashrc
  source ~/.bashrc
  linux-agent{RESET}
""")
    else:
        _warn("Algunas dependencias no se importaron correctamente.")
        _warn("Si el error persiste, intentá con: sudo python3 -m pip install -r requirements.txt --break-system-packages")


if __name__ == "__main__":
    main()
