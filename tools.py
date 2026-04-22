# =============================================================================
# tools.py — Herramienta execute_local_bash (con streaming)
# Linux Local AI Agent v2.0
# =============================================================================

from __future__ import annotations
import re as _re
import select
import subprocess
import time
import config as cfg
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm

console = Console()

# Máximo de caracteres a retornar al LLM (evita sobrecargar el contexto)
_MAX_OUTPUT = cfg.MAX_OUTPUT_CHARS

# Máximo de líneas mostradas en el terminal durante el streaming
_MAX_DISPLAY_LINES = 60

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
    Ejecuta un comando bash localmente usando subprocess con streaming en tiempo real.

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

    # ── Ejecutar con streaming ────────────────────────────────────────────────
    try:
        proc = subprocess.Popen(
            comando,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        displayed_lines = 0
        truncated_display = False
        start_time = time.time()

        console.print(f"[dim]──── Output ────[/dim]")

        # Usar select para leer stdout y stderr sin bloquear (funciona en Linux)
        try:
            while True:
                # ── Verificar timeout global ──────────────────────────────────
                elapsed = time.time() - start_time
                if elapsed >= cfg.COMMAND_TIMEOUT:
                    proc.kill()
                    msg = f"Error: El comando excedió el timeout de {cfg.COMMAND_TIMEOUT} segundos."
                    console.print(f"[bold red]⏱ Timeout:[/] {msg}")
                    return msg

                # Verificar si el proceso terminó
                if proc.poll() is not None:
                    # Proceso terminó — leer lo que queda
                    remaining_out = proc.stdout.read()
                    remaining_err = proc.stderr.read()
                    if remaining_out:
                        for line in remaining_out.splitlines():
                            stdout_lines.append(line)
                            if displayed_lines < _MAX_DISPLAY_LINES:
                                console.print(line)
                                displayed_lines += 1
                            else:
                                truncated_display = True
                    if remaining_err:
                        for line in remaining_err.splitlines():
                            stderr_lines.append(line)
                    break

                reads = [proc.stdout.fileno(), proc.stderr.fileno()]
                try:
                    readable, _, _ = select.select(reads, [], [], 1.0)
                except (ValueError, OSError):
                    break

                for fd in readable:
                    if fd == proc.stdout.fileno():
                        line = proc.stdout.readline()
                        if line:
                            stripped = line.rstrip()
                            stdout_lines.append(stripped)
                            if displayed_lines < _MAX_DISPLAY_LINES:
                                console.print(stripped)
                                displayed_lines += 1
                            elif not truncated_display:
                                console.print(
                                    f"[dim]  ... (output continúa, mostrando hasta "
                                    f"{_MAX_DISPLAY_LINES} líneas)[/dim]"
                                )
                                truncated_display = True

                    elif fd == proc.stderr.fileno():
                        line = proc.stderr.readline()
                        if line:
                            stderr_lines.append(line.rstrip())

        except Exception:
            # Fallback: esperar a que termine y leer todo
            try:
                outs, errs = proc.communicate(timeout=cfg.COMMAND_TIMEOUT)
                for line in outs.splitlines():
                    stdout_lines.append(line)
                    if displayed_lines < _MAX_DISPLAY_LINES:
                        console.print(line)
                        displayed_lines += 1
                for line in errs.splitlines():
                    stderr_lines.append(line)
            except subprocess.TimeoutExpired:
                proc.kill()
                msg = f"Error: El comando excedió el timeout de {cfg.COMMAND_TIMEOUT} segundos."
                console.print(f"[bold red]⏱ Timeout:[/] {msg}")
                return msg

        # Esperar fin del proceso con timeout
        try:
            proc.wait(timeout=cfg.COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            msg = f"Error: El comando excedió el timeout de {cfg.COMMAND_TIMEOUT} segundos."
            console.print(f"[bold red]⏱ Timeout:[/] {msg}")
            return msg

        returncode = proc.returncode

        # Construir output combinado para el LLM
        stdout_str = "\n".join(stdout_lines).strip()
        stderr_str = "\n".join(stderr_lines).strip()

        partes = []
        if stdout_str:
            partes.append(stdout_str)
        if stderr_str:
            partes.append(f"[STDERR]\n{stderr_str}")

        output = "\n".join(partes) if partes else "(sin salida)"

        # Mostrar status final
        color = "green" if returncode == 0 else "red"
        console.print(f"[{color}]  ↳ Exit code: {returncode}[/{color}]")

        # Truncar para no sobrecargar el contexto del LLM
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n\n[...output truncado a {_MAX_OUTPUT} chars]"

        return f"Exit code: {returncode}\n{output}"

    except Exception as e:
        msg = f"Error inesperado al ejecutar el comando: {e}"
        console.print(f"[bold red]✗ Error:[/] {msg}")
        return msg
