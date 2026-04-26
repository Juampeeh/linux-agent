# =============================================================================
# tools_files.py — Herramientas nativas de archivos (read/write)
# Linux Local AI Agent v2.0
# =============================================================================

from __future__ import annotations
from pathlib import Path
from typing import Optional

import config as cfg
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

console = Console()

# Límite de caracteres al leer un archivo (evita sobrecargar el contexto del LLM)
_MAX_READ_CHARS = 8000
# Número máximo de líneas mostradas en terminal por leer
_MAX_DISPLAY_LINES = 60


def leer_archivo(
    path: str,
    encoding: str = "utf-8",
    inicio_linea: Optional[int] = None,
    fin_linea: Optional[int] = None,
) -> str:
    """
    Lee el contenido de un archivo y lo retorna como string.

    Parámetros
    ----------
    path          : Ruta absoluta o relativa al archivo.
    encoding      : Codificación (default: utf-8, fallback a latin-1).
    inicio_linea  : Línea desde la que leer (1-indexed, opcional).
    fin_linea     : Línea hasta la que leer (1-indexed, opcional).

    Retorna
    -------
    Contenido del archivo (posiblemente truncado) o mensaje de error.
    """
    p = Path(path).expanduser().resolve()

    console.print(f"  [dim]📄 Leyendo archivo: [italic]{p}[/italic]...[/dim]")

    if not p.exists():
        return f"Error: El archivo '{path}' no existe."

    if not p.is_file():
        return f"Error: '{path}' no es un archivo regular."

    # Verificar tamaño antes de leer
    size_bytes = p.stat().st_size
    if size_bytes > 10 * 1024 * 1024:  # > 10 MB
        return (
            f"Error: El archivo es demasiado grande ({size_bytes // 1024 // 1024} MB). "
            f"Usá 'execute_local_bash' con tail/head para leer partes específicas."
        )

    try:
        contenido = p.read_text(encoding=encoding, errors="replace")
    except (OSError, PermissionError) as e:
        return f"Error al leer '{path}': {e}"

    # Filtrar por rango de líneas si se especificó
    if inicio_linea is not None or fin_linea is not None:
        lineas = contenido.splitlines()
        ini = max(0, (inicio_linea or 1) - 1)
        fin = fin_linea or len(lineas)
        lineas = lineas[ini:fin]
        contenido = "\n".join(lineas)

    # Detectar extensión para syntax highlight en terminal
    extension = p.suffix.lstrip(".") or "text"

    # Mostrar en terminal (limitado)
    lineas_display = contenido.splitlines()
    if len(lineas_display) > _MAX_DISPLAY_LINES:
        display_text = "\n".join(lineas_display[:_MAX_DISPLAY_LINES])
        display_text += f"\n[dim]... ({len(lineas_display) - _MAX_DISPLAY_LINES} líneas más)[/dim]"
    else:
        display_text = contenido

    try:
        syntax = Syntax(
            display_text if len(display_text) < 4000 else display_text[:4000],
            extension,
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
        )
        console.print(Panel(
            syntax,
            title=f"[bold green]📄 {p.name}[/] [dim]({size_bytes} bytes)[/dim]",
            border_style="green",
        ))
    except Exception:
        console.print(Panel(
            display_text[:2000],
            title=f"[bold green]📄 {p.name}[/]",
            border_style="green",
        ))

    # Truncar para el LLM
    if len(contenido) > _MAX_READ_CHARS:
        contenido = (
            contenido[:_MAX_READ_CHARS]
            + f"\n\n[...archivo truncado a {_MAX_READ_CHARS} chars. "
            f"Total: {len(contenido)} chars.]\n"
            f"⚠ ADVERTENCIA PARA EL LLM: El archivo es inmenso. "
            f"Usá execute_local_bash con grep o leé por rango de líneas para no saturar tu memoria de contexto."
        )

    return f"Contenido de '{path}':\n{contenido}"


def escribir_archivo(
    path: str,
    content: str,
    modo: str = "w",
    require_confirmation: Optional[bool] = None,
) -> str:
    """
    Escribe contenido en un archivo.

    Parámetros
    ----------
    path                 : Ruta al archivo de destino.
    content              : Contenido a escribir.
    modo                 : 'w' (sobreescribir, default) o 'a' (append).
    require_confirmation : Si True (o None en modo seguro), pide confirmación.

    Retorna
    -------
    Mensaje de éxito o error.
    """
    if require_confirmation is None:
        require_confirmation = cfg.REQUIRE_CONFIRMATION

    p = Path(path).expanduser().resolve()
    accion = "sobreescribir" if modo == "w" else "añadir al final de"
    existe = p.exists()

    # Mostrar preview del contenido
    preview = content[:300] + ("..." if len(content) > 300 else "")
    console.print(Panel(
        f"[bold]Archivo:[/] {p}\n"
        f"[bold]Acción:[/] {'Crear/'+accion if not existe else accion.capitalize()}\n"
        f"[bold]Tamaño:[/] {len(content)} chars\n\n"
        f"[dim]Preview:[/dim]\n{preview}",
        title="[bold yellow]✏️ Escritura de archivo[/]",
        border_style="yellow",
    ))

    # Pedir confirmación en modo seguro
    if require_confirmation:
        try:
            ok = Confirm.ask(
                "[bold yellow]  ¿Escribir este archivo?[/]",
                default=True,
                console=console,
            )
        except (KeyboardInterrupt, EOFError):
            ok = False

        if not ok:
            console.print("  [dim]↩ Escritura cancelada por el usuario.[/dim]")
            return "Escritura cancelada por el usuario."

    # Ejecutar escritura
    try:
        # Crear directorios padre si no existen
        p.parent.mkdir(parents=True, exist_ok=True)

        write_mode = "a" if modo == "a" else "w"
        with open(p, write_mode, encoding="utf-8") as f:
            f.write(content)

        accion_pasada = "añadido al final de" if modo == "a" else "escrito en"
        msg = f"Contenido {accion_pasada} '{path}' exitosamente ({len(content)} chars)."
        console.print(f"  [green]✓ {msg}[/green]")
        return msg

    except PermissionError:
        msg = f"Error: Sin permisos para escribir en '{path}'."
        console.print(f"  [red]✗ {msg}[/red]")
        return msg
    except Exception as e:
        msg = f"Error al escribir '{path}': {e}"
        console.print(f"  [red]✗ {msg}[/red]")
        return msg
