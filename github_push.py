#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
github_push.py — Inicializa el repo git en la VM y hace el push a GitHub.

Las credenciales se leen del .env. El token PAT se pasa por CLI (--token)
por seguridad (no se guarda en disco).

Uso: python github_push.py --token <PAT>
"""
import sys
import io

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import argparse
import paramiko
import urllib.request
import urllib.error
import json
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
_BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(_BASE_DIR / ".env")

# ── Configuración leída del .env ──────────────────────────────────────────────
VM_HOST    = os.getenv("VM_HOST",    "192.168.0.162")
VM_PORT    = int(os.getenv("VM_PORT", "22"))
VM_USER    = os.getenv("VM_USER",    "test")
VM_PASS    = os.getenv("VM_PASS",    "")
REMOTE_DIR = os.getenv("REMOTE_DIR", "/home/test/linux_agent")

GITHUB_USER  = os.getenv("GITHUB_USER",  "JuampeehSA")
GITHUB_EMAIL = os.getenv("GITHUB_EMAIL", "Juampeeh@hotmail.com")
GITHUB_REPO  = os.getenv("GITHUB_REPO",  "linux-agent")

RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"


def run_remote(ssh, cmd, check=True, env=""):
    full_cmd = f"{env} {cmd}".strip() if env else cmd
    _, stdout, stderr = ssh.exec_command(full_cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if out:
        print(f"    {out}")
    if err and exit_code != 0:
        print(f"    {YELLOW}{err}{RESET}")
    if check and exit_code != 0:
        print(f"{RED}  [FAIL] Comando falló (exit {exit_code}): {cmd}{RESET}")
        print(f"    {err}")
        sys.exit(1)
    return out, err, exit_code


def crear_repo_github(token: str) -> bool:
    """
    Crea el repositorio en GitHub via API si no existe.
    Retorna True si fue creado o ya existía, False si hubo error.
    """
    print(f"\n{BOLD}[0/5] Verificando/creando repositorio en GitHub...{RESET}")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Verificar si el repo ya existe
    check_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"
    req = urllib.request.Request(check_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                print(f"  {YELLOW}⚠ El repositorio ya existe en GitHub.{RESET}")
                return True
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  {RED}✗ Error verificando repo: {e}{RESET}")
            return False

    # Crear el repo
    create_url = "https://api.github.com/user/repos"
    payload = json.dumps({
        "name": GITHUB_REPO,
        "description": "Linux Local AI Agent — Agente autónomo con ejecución de comandos bash y soporte multi-LLM (LM Studio, Ollama, Gemini, OpenAI, Grok, Claude)",
        "private": False,
        "auto_init": False,
    }).encode("utf-8")

    req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            print(f"  {GREEN}✓ Repositorio creado: {data.get('html_url')}{RESET}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"  {RED}✗ Error creando repo: {e} — {body}{RESET}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Push Linux Agent a GitHub")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token (scope: repo)")
    args = parser.parse_args()

    PAT = args.token

    if not VM_PASS:
        print(f"{RED}  ✗ VM_PASS no configurada en .env{RESET}")
        sys.exit(1)

    REMOTE_URL = f"https://{GITHUB_USER}:{PAT}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

    print(f"\n{BOLD}{CYAN}== GitHub Push: {GITHUB_USER}/{GITHUB_REPO} =={RESET}\n")

    # ── Crear repo en GitHub ──────────────────────────────────────────────────
    if not crear_repo_github(PAT):
        print(f"{YELLOW}  Continuando igual (el repo puede existir)...{RESET}")

    # ── Conectar SSH a la VM ──────────────────────────────────────────────────
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASS, timeout=15)
    print(f"{GREEN}  ✓ SSH conectado a {VM_USER}@{VM_HOST}{RESET}")

    GIT_ENV = "GIT_TERMINAL_PROMPT=0"

    # ── Configurar git global en la VM ────────────────────────────────────────
    print(f"\n{BOLD}[1/5] Configurando git...{RESET}")
    run_remote(ssh, f'git config --global user.email "{GITHUB_EMAIL}"')
    run_remote(ssh, f'git config --global user.name "{GITHUB_USER}"')
    run_remote(ssh, f'git config --global init.defaultBranch main')
    print(f"{GREEN}  ✓ Git configurado{RESET}")

    # ── Inicializar repo ──────────────────────────────────────────────────────
    print(f"\n{BOLD}[2/5] Inicializando repositorio...{RESET}")
    run_remote(ssh, f"cd {REMOTE_DIR} && git init", check=False)
    print(f"{GREEN}  ✓ git init{RESET}")

    # ── Verificar .gitignore ──────────────────────────────────────────────────
    print(f"\n{BOLD}[3/5] Verificando .gitignore...{RESET}")
    run_remote(ssh, f"cat {REMOTE_DIR}/.gitignore")

    # ── Commit inicial ────────────────────────────────────────────────────────
    print(f"\n{BOLD}[4/5] Commit inicial...{RESET}")
    run_remote(ssh, f"cd {REMOTE_DIR} && git add -A")
    out, err, code = run_remote(
        ssh,
        f'cd {REMOTE_DIR} && git commit -m "feat: Linux Local AI Agent v1.0 — Initial commit"',
        check=False,
    )
    if code != 0 and "nothing to commit" in out + err:
        print(f"{YELLOW}  ⚠ Nada nuevo que commitear. Continuando...{RESET}")
    elif code != 0:
        print(f"{RED}  ✗ Error en git commit{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}  ✓ Commit realizado{RESET}")

    # ── Push a GitHub ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}[5/5] Push a GitHub...{RESET}")
    print(f"  Destino: https://github.com/{GITHUB_USER}/{GITHUB_REPO}")
    run_remote(ssh, f"cd {REMOTE_DIR} && git remote remove origin", check=False)
    run_remote(ssh, f"cd {REMOTE_DIR} && git remote add origin '{REMOTE_URL}'")

    out, err, code = run_remote(
        ssh,
        f"cd {REMOTE_DIR} && {GIT_ENV} git push -u origin main 2>&1",
        check=False,
    )

    if code == 0:
        print(f"""
{GREEN}{BOLD}
==========================================================
  ✓ Repositorio publicado exitosamente!
==========================================================
{RESET}
  URL: {CYAN}https://github.com/{GITHUB_USER}/{GITHUB_REPO}{RESET}
""")
    else:
        print(f"""
{YELLOW}
  ⚠ El push falló. Causas posibles:
  1. El token PAT no tiene permisos 'repo'
  2. El repo ya tiene historial diferente → intentá con --force
  3. Problema de red desde la VM hacia GitHub

  Intentá manualmente en la VM:
  cd {REMOTE_DIR}
  git push -u origin main
{RESET}""")

    ssh.close()


if __name__ == "__main__":
    main()
