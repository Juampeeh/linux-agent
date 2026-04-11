# =============================================================================
# tools.py — Herramienta execute_local_bash del Linux Local AI Agent
# =============================================================================

from __future__ import annotations
import subprocess
import shlex
import config as cfg
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm

console = Console()

# Máximo de caracteres a retornar al LLM (evita sobrecargar el contexto)
_MAX_OUTPUT = cfg.MAX_OUTPUT_CHARS

# Patrones de comandos que pueden bloquearse esperando input interactivo
_PATRONES_INTERACTIVOS = [
    r"^\s*python\s*$",          # python sin argumentos
    r"^\s*python3\s*$",         # python3 sin argumentos
    r"^\s*vim\b",               # vim
    r"^\s*nano\b",              # nano
    r"^\s*less\b",              # less
    r"^\s*more\b",              # more
    r"^\s*top\b",               # top
    r"^\s*htop\b",              # htop
    r"^\s*ssh\b",               # ssh interactivo
    r"^\s*mysql\s*$",           # mysql sin argumentos
    r"^\s*psql\s*$",            # psql sin argumentos
    r"^\s*grep -r .{0,50} ~/",  # grep recursivo en home (puede ser lento)
    r"^\s*find / ",             # find en raiz (muy lento)
    r"^\s*find ~/ ",            # find en home (puede ser lento)
    r"^\s*ls -R ~/",            # ls recursivo en home
]

import re as _re


def _es_comando_riesgoso(comando: str) -> str | None:
    """Retorna una advertencia si el comando puede bloquearse, o None si es seguro."""
    for patron in _PATRONES_INTERACTIVOS:
        if _re.search(patron, comando, _re.IGNORECASE):
            return (
                f"El comando `{comando[:60]}` puede bloquearse esperando input interactivo. "
                "El agente lo ejecutará con timeout pero no podrá interactuar con él."
            )
    return None


def ejecutar_bash(
    comando: str,
    require_confirmation: bool | None = None,
) -> str:
    """
    Ejecuta un comando bash localmente usando subprocess.

    Parámetros
    ----------
    comando              : String con el comando a ejecutar.
    require_confirmation : Si True, pausa y pide confirmación al usuario.
                           Si None, usa el valor de cfg.REQUIRE_CONFIRMATION.

    Retorna
    -------
    String con stdout + stderr combinados (máx MAX_OUTPUT_CHARS).
    En caso de error retorna el mensaje de error.
    """
    if require_confirmation is None:
        require_confirmation = cfg.REQUIRE_CONFIRMATION

    # ── Advertencia si el comando puede bloquearse ────────────────────────────
    advertencia = _es_comando_riesgoso(comando)
    if advertencia:
        console.print(f"[yellow]  ⚠ Advertencia:[/] {advertencia}")

    # ── Mostrar el comando propuesto ──────────────────────────────────────────
    cmd_text = Text()
    cmd_text.append("$ ", style="bold green")
    cmd_text.append(comando, style="bold yellow")

    console.print(Panel(cmd_text, title="[bold cyan]Comando a ejecutar[/]", border_style="cyan"))

    # ── Pedir confirmación si está activo ─────────────────────────────────────
    if require_confirmation:
        try:
            ok = Confirm.ask(
                "[bold yellow]  ¿Ejecutar este comando?[/]",
                default=True,
                console=console,
            )
        except (KeyboardInterrupt, EOFError):
            ok = False

        if not ok:
            console.print("  [dim]↩ Comando cancelado por el usuario.[/dim]")
            return "Comando cancelado por el usuario."

    # ── Ejecutar ──────────────────────────────────────────────────────────────
    try:
        resultado = subprocess.run(
            comando,
            shell=True,
            capture_output=True,
            text=True,
            timeout=cfg.COMMAND_TIMEOUT,
        )

        stdout = resultado.stdout.strip()
        stderr = resultado.stderr.strip()
        returncode = resultado.returncode

        # Combinar salidas
        partes = []
        if stdout:
            partes.append(stdout)
        if stderr:
            partes.append(f"[STDERR]\n{stderr}")

        output = "\n".join(partes) if partes else "(sin salida)"

        # Mostrar en terminal con colores
        if returncode == 0:
            _mostrar_output(output, "OK", "green")
        else:
            _mostrar_output(output, f"Exit code: {returncode}", "red")

        # Truncar para no sobrecargar el contexto del LLM
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n\n[...output truncado a {_MAX_OUTPUT} chars]"

        return f"Exit code: {returncode}\n{output}"

    except subprocess.TimeoutExpired:
        msg = f"Error: El comando excedió el timeout de {cfg.COMMAND_TIMEOUT} segundos."
        console.print(f"[bold red]⏱ Timeout:[/] {msg}")
        return msg

    except Exception as e:
        msg = f"Error inesperado al ejecutar el comando: {e}"
        console.print(f"[bold red]✗ Error:[/] {msg}")
        return msg


def _mostrar_output(output: str, status: str, color: str) -> None:
    """Muestra el output del comando en un panel con colores."""
    # Limitar la visualización en terminal (el LLM recibe más si hay)
    lines = output.splitlines()
    if len(lines) > 50:
        display = "\n".join(lines[:50]) + f"\n[dim]... ({len(lines) - 50} líneas más)[/dim]"
    else:
        display = output

    console.print(
        Panel(
            display or "[dim](sin salida)[/dim]",
            title=f"[bold {color}]Output [{status}][/]",
            border_style=color,
        )
    )
