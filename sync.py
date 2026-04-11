#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync.py — Sincronización completa: despliega a la VM y publica en GitHub.

Uso:
    python sync.py --token <PAT>          # deploy + push
    python sync.py --token <PAT> --vm-only   # solo deploy a VM
    python sync.py --token <PAT> --git-only  # solo push a GitHub
    python sync.py --no-git               # solo deploy, sin GitHub
"""
import sys
import io

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import argparse
import subprocess
import time
from pathlib import Path
from dotenv import load_dotenv

_BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(_BASE_DIR / ".env")

RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


def _ok(msg):    print(f"{GREEN}  ✓ {msg}{RESET}")
def _info(msg):  print(f"{CYAN}  → {msg}{RESET}")
def _warn(msg):  print(f"{YELLOW}  ⚠ {msg}{RESET}")
def _header(msg): print(f"\n{BOLD}{CYAN}{msg}{RESET}")
def _sep():       print(f"{DIM}{'─' * 60}{RESET}")


def run_script(script: str, extra_args: list | None = None) -> int:
    """Ejecuta un script Python del proyecto y retorna el exit code."""
    cmd = [sys.executable, str(_BASE_DIR / script)] + (extra_args or [])
    result = subprocess.run(cmd, cwd=str(_BASE_DIR))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Sincronización completa: VM + GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python sync.py --token ghp_...           # Todo: VM + GitHub
  python sync.py --no-git                  # Solo VM, sin GitHub
  python sync.py --token ghp_... --vm-only # Solo VM
  python sync.py --token ghp_... --git-only # Solo GitHub
        """,
    )
    parser.add_argument("--token",    help="GitHub Personal Access Token (scope: repo)")
    parser.add_argument("--no-git",   action="store_true", help="Omitir push a GitHub")
    parser.add_argument("--vm-only",  action="store_true", help="Solo deploy a VM")
    parser.add_argument("--git-only", action="store_true", help="Solo push a GitHub")
    parser.add_argument("--skip-tests", action="store_true", help="No correr tests en VM")
    args = parser.parse_args()

    pasos_totales = 0
    pasos_ok = 0

    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║         🔄  Linux Agent — Sincronización completa        ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")

    t_inicio = time.time()

    # ── Paso 1: Deploy a VM ────────────────────────────────────────────────────
    if not args.git_only:
        pasos_totales += 1
        _header("[1/3] Desplegando a VM...")
        _sep()
        code = run_script("deploy_to_vm.py")
        if code == 0:
            _ok("Deploy a VM completado.")
            pasos_ok += 1
        else:
            _warn(f"Deploy a VM terminó con errores (exit {code}). Continuando...")

    # ── Paso 2: Tests en VM ───────────────────────────────────────────────────
    if not args.git_only and not args.skip_tests:
        pasos_totales += 1
        _header("[2/3] Ejecutando tests en VM...")
        _sep()
        code = run_script("run_tests_on_vm.py")
        if code == 0:
            _ok("Tests: todos pasaron ✓")
            pasos_ok += 1
        else:
            _warn("Algunos tests fallaron. Revisá el output arriba.")

    # ── Paso 3: Push a GitHub ─────────────────────────────────────────────────
    if not args.no_git and not args.vm_only:
        pasos_totales += 1
        _header("[3/3] Publicando en GitHub...")
        _sep()

        if not args.token:
            _warn("No se proporcionó --token. Omitiendo push a GitHub.")
            _warn("Para publicar: python sync.py --token ghp_...")
        else:
            code = run_script("github_push.py", ["--token", args.token])
            if code == 0:
                _ok("GitHub: push completado ✓")
                pasos_ok += 1
            else:
                _warn(f"GitHub push terminó con errores (exit {code}).")

    # ── Resumen ───────────────────────────────────────────────────────────────
    t_total = time.time() - t_inicio
    _sep()
    print(f"""
{BOLD}=== Resumen de sincronización ==={RESET}
  Pasos completados : {GREEN}{pasos_ok}/{pasos_totales}{RESET}
  Tiempo total      : {t_total:.1f}s
  Repo GitHub       : {CYAN}https://github.com/{os.getenv('GITHUB_USER', 'Juampeeh')}/{os.getenv('GITHUB_REPO', 'linux-agent')}{RESET}
""")

    if pasos_ok == pasos_totales:
        print(f"{GREEN}  ✓ Sincronización completada exitosamente.{RESET}\n")
    else:
        print(f"{YELLOW}  ⚠ Sincronización completada con advertencias.{RESET}\n")


if __name__ == "__main__":
    main()
