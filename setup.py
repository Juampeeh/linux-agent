#!/usr/bin/env python3
# =============================================================================
# setup.py — Instalador automático del Linux Local AI Agent
# Uso: python3 setup.py
# =============================================================================

from __future__ import annotations
import os
import sys
import subprocess
import shutil
from pathlib import Path

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"


def _ok(msg: str) -> None:
    print(f"{GREEN}  ✓ {msg}{RESET}")


def _info(msg: str) -> None:
    print(f"{CYAN}  → {msg}{RESET}")


def _warn(msg: str) -> None:
    print(f"{YELLOW}  ⚠ {msg}{RESET}")


def _fail(msg: str) -> None:
    print(f"{RED}  ✗ {msg}{RESET}")
    sys.exit(1)


def _run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, **kwargs)


# =============================================================================
# Verificaciones de entorno
# =============================================================================

def verificar_python() -> None:
    print(f"\n{BOLD}[1/5] Verificando Python...{RESET}")
    version = sys.version_info
    if version < (3, 10):
        _fail(f"Python 3.10+ requerido. Tenés: {sys.version}")
    _ok(f"Python {version.major}.{version.minor}.{version.micro}")


def verificar_venv_disponible() -> None:
    """En Ubuntu mínimo, python3-venv puede no estar instalado."""
    result = subprocess.run(
        [sys.executable, "-m", "venv", "--help"],
        capture_output=True
    )
    if result.returncode != 0:
        _warn("python3-venv no disponible. Intentando instalar...")
        if shutil.which("apt"):
            subprocess.run(
                ["sudo", "apt", "install", "-y", "python3-venv", "python3-pip"],
                check=False
            )
        else:
            _fail(
                "python3-venv no está instalado y no se pudo instalar automáticamente.\n"
                "  Instalá manualmente: sudo apt install python3-venv python3-pip"
            )


def crear_venv() -> Path:
    print(f"\n{BOLD}[2/5] Creando entorno virtual...{RESET}")
    venv_path = Path(".") / "venv"

    if venv_path.exists():
        _warn(f"El directorio venv/ ya existe. Usando el existente.")
        return venv_path

    verificar_venv_disponible()

    _info("Creando venv en ./venv/")
    _run([sys.executable, "-m", "venv", str(venv_path)])
    _ok("Entorno virtual creado.")
    return venv_path


def instalar_dependencias(venv_path: Path) -> None:
    print(f"\n{BOLD}[3/5] Instalando dependencias...{RESET}")

    if sys.platform == "win32":
        pip = venv_path / "Scripts" / "pip"
    else:
        pip = venv_path / "bin" / "pip"

    _info("Actualizando pip...")
    _run([str(pip), "install", "--upgrade", "pip", "-q"])

    req_file = Path("requirements.txt")
    if not req_file.exists():
        _fail("requirements.txt no encontrado.")

    _info("Instalando paquetes de requirements.txt...")
    _run([str(pip), "install", "-r", str(req_file)])
    _ok("Dependencias instaladas.")


def configurar_env() -> None:
    print(f"\n{BOLD}[4/5] Configurando variables de entorno (.env)...{RESET}")
    env_path = Path(".env")

    if env_path.exists():
        _warn(".env ya existe. No se sobreescribirá.")
        return

    example = Path(".env.example")
    if not example.exists():
        _fail(".env.example no encontrado.")

    # Copiar el ejemplo como base
    shutil.copy(str(example), str(env_path))

    print(f"\n{CYAN}  ┌─────────────────────────────────────────────────────┐{RESET}")
    print(f"{CYAN}  │  Configuración inicial del agente                   │{RESET}")
    print(f"{CYAN}  └─────────────────────────────────────────────────────┘{RESET}")
    print(f"  {YELLOW}(Presioná Enter para usar el valor por defecto){RESET}\n")

    updates: dict[str, str] = {}

    # LM Studio
    lmstudio_url = input(
        f"  URL de LM Studio [{CYAN}http://192.168.0.142:1234/v1{RESET}]: "
    ).strip()
    updates["LMSTUDIO_BASE_URL"] = lmstudio_url or "http://192.168.0.142:1234/v1"

    # Confirmación
    confirmacion = input(
        f"  ¿Requerir confirmación antes de ejecutar comandos? [{CYAN}True{RESET}]: "
    ).strip()
    updates["REQUIRE_CONFIRMATION"] = confirmacion or "True"

    # API Keys opcionales
    print(f"\n  {YELLOW}APIs opcionales (presioná Enter para omitir):{RESET}")
    for clave, desc, ejemplo in [
        ("GEMINI_API_KEY",    "Google Gemini",    "AIza..."),
        ("OPENAI_API_KEY",    "OpenAI ChatGPT",   "sk-..."),
        ("GROK_API_KEY",      "Grok (xAI)",       "xai-..."),
        ("ANTHROPIC_API_KEY", "Anthropic Claude", "sk-ant-..."),
    ]:
        valor = input(f"  {desc} key [{CYAN}{ejemplo}{RESET}]: ").strip()
        if valor:
            updates[clave] = valor

    # Escribir actualizaciones en el .env
    contenido = env_path.read_text(encoding="utf-8")
    for key, val in updates.items():
        lines = []
        found = False
        for line in contenido.splitlines():
            if line.startswith(f"{key}=") or line.startswith(f"#{key}="):
                lines.append(f"{key}={val}")
                found = True
            else:
                lines.append(line)
        if not found:
            lines.append(f"{key}={val}")
        contenido = "\n".join(lines)
    env_path.write_text(contenido + "\n", encoding="utf-8")

    _ok(".env configurado correctamente.")


def mostrar_instrucciones(venv_path: Path) -> None:
    print(f"\n{BOLD}[5/5] ¡Instalación completada!{RESET}")

    activar = (
        f"source {venv_path}/bin/activate"
        if sys.platform != "win32"
        else rf"{venv_path}\Scripts\activate"
    )

    print(f"""
{GREEN}╔══════════════════════════════════════════════════════════╗
║          🚀  Linux Local AI Agent — Listo para usar       ║
╚══════════════════════════════════════════════════════════╝{RESET}

  Para iniciar el agente:

  {CYAN}1. Activá el entorno virtual:{RESET}
     {BOLD}{activar}{RESET}

  {CYAN}2. Ejecutá el agente:{RESET}
     {BOLD}python main.py{RESET}

  {CYAN}Comandos útiles dentro del agente:{RESET}
     /ayuda     → Ver todos los comandos
     /auto      → Toggle modo autónomo
     /switch    → Cambiar motor de IA
     Ctrl+C     → Salir
""")


def main() -> None:
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║     🔧  Linux Local AI Agent — Setup Automático          ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")

    verificar_python()
    venv_path = crear_venv()
    instalar_dependencias(venv_path)
    configurar_env()
    mostrar_instrucciones(venv_path)


if __name__ == "__main__":
    main()
