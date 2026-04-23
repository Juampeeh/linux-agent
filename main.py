#!/usr/bin/env python3
# =============================================================================
# main.py — Linux Local AI Agent v2.0 (AI Sysadmin Autónomo)
# Punto de entrada: banner + selección de motor + bucle de chat interactivo
# =============================================================================

from __future__ import annotations
import sys
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

# Historial de comandos con flechas ↑↓ (readline, disponible en Linux/Mac)
try:
    import readline as _rl
    import atexit as _atexit
    _HIST_FILE = Path.home() / ".linux_agent_history"
    try:
        _rl.read_history_file(str(_HIST_FILE))
    except FileNotFoundError:
        pass
    _rl.set_history_length(500)
    _atexit.register(_rl.write_history_file, str(_HIST_FILE))
except ImportError:
    pass  # Windows sin pyreadline3 — degradación silenciosa

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.prompt import Prompt
from rich import print as rprint

import config as cfg
from llm.router import crear_agente, motores_disponibles, intentar_fallback_local
from llm.history import HistorialCanonico
from llm.tool_registry import HERRAMIENTAS, SYSTEM_PROMPT, get_system_prompt
from llm.memory import crear_memoria, formatear_contexto_memoria
from agentic_loop import ejecutar_tool, AgenticTaskRunner

console = Console()

# ── Constantes ────────────────────────────────────────────────────────────────
MAX_ITERACIONES = 10   # Máx de tool calls por turno normal (evita loops)
VERSION         = "2.0.0"

# ── Estado global del centinela ───────────────────────────────────────────────
_sentinel_proc: subprocess.Popen | None = None
_sentinel_pid: int | None = None

# ── Estado global del bot Telegram ───────────────────────────────────────────
_telegram_bot = None   # TelegramBot | None


# =============================================================================
# Banner ASCII
# =============================================================================

BANNER = r"""
 ██╗     ██╗███╗   ██╗██╗   ██╗██╗  ██╗      █████╗  ██████╗ ███████╗███╗   ██╗████████╗
 ██║     ██║████╗  ██║██║   ██║╚██╗██╔╝     ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
 ██║     ██║██╔██╗ ██║██║   ██║ ╚███╔╝      ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
 ██║     ██║██║╚██╗██║██║   ██║ ██╔██╗      ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
 ███████╗██║██║ ╚████║╚██████╔╝██╔╝ ██╗     ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
 ╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
"""


def mostrar_banner() -> None:
    console.print(Text(BANNER, style="bold cyan"))
    console.print(
        Panel(
            f"[bold]Linux Local AI Agent[/] [dim]v{VERSION}[/]\\n"
            f"[dim]AI Sysadmin Autónomo — bash · web · archivos · SSH · centinela · Telegram[/]",
            border_style="cyan",
            expand=False,
        )
    )
    console.print()


# =============================================================================
# Menú de selección de motor
# =============================================================================

def _load_lm_models() -> list[str]:
    path = Path(cfg.LM_MODELS_FILE)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("models", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _save_lm_models(models: list[str]) -> None:
    data = {
        "_comentario": "Lista de modelos LM Studio. Editá o usá /model en el chat.",
        "models": models,
    }
    Path(cfg.LM_MODELS_FILE).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def menu_modelo_local() -> str | None:
    modelos = _load_lm_models()
    if len(modelos) <= 1:
        return modelos[0] if modelos else None

    console.print()
    console.print(Rule("[bold cyan]🧠 Seleccionar modelo LM Studio[/]", style="cyan"))
    console.print("  [dim]0.[/] Autodetectar modelo activo en LM Studio")
    for i, m in enumerate(modelos, 1):
        console.print(f"  [cyan]{i}.[/] {m}")
    opcion_add = len(modelos) + 1
    console.print(f"  [green]{opcion_add}.[/] ➕ Agregar modelo manualmente")
    console.print()

    while True:
        try:
            opcion = Prompt.ask("  Modelo", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if opcion == "0":
            return None
        if opcion.isdigit():
            idx = int(opcion) - 1
            if 0 <= idx < len(modelos):
                return modelos[idx]
            if int(opcion) == opcion_add:
                nuevo = Prompt.ask("  Identificador del modelo", console=console).strip()
                if nuevo:
                    if nuevo not in modelos:
                        modelos.append(nuevo)
                        _save_lm_models(modelos)
                    return nuevo
        console.print("[red]  Opción no válida.[/]")


def menu_motor() -> tuple[str, str | None]:
    disponibles = motores_disponibles()
    claves = list(disponibles.keys())

    if len(claves) == 1:
        clave = claves[0]
        console.print(f"\n  [dim]Motor único disponible: {disponibles[clave]['nombre']}[/dim]\n")
        model_id = menu_modelo_local() if clave == "local" else None
        return clave, model_id

    console.print()
    console.print(Rule("[bold magenta]🤖 Seleccionar motor de IA[/]", style="magenta"))
    for i, clave in enumerate(claves, 1):
        meta = disponibles[clave]
        console.print(f"  [magenta]{i}.[/] [bold]{meta['nombre']}[/]")
        console.print(f"     [dim]{meta['descripcion']}[/dim]")
    console.print()

    while True:
        try:
            opcion = Prompt.ask("  Motor", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[cyan]  Usando LM Studio por defecto.[/]\n")
            return "local", None

        elegido = None
        if opcion.isdigit():
            idx = int(opcion) - 1
            if 0 <= idx < len(claves):
                elegido = claves[idx]
        elif opcion.lower() in disponibles:
            elegido = opcion.lower()

        if elegido:
            console.print(f"\n[green]  ✓ Motor: {disponibles[elegido]['nombre']}[/]\n")
            model_id = menu_modelo_local() if elegido == "local" else None
            return elegido, model_id

        console.print("[red]  Opción no válida.[/]")


# =============================================================================
# Centinela — control desde main.py
# =============================================================================

def _sentinel_start(memoria=None) -> bool:
    """Arranca el proceso centinela en background."""
    global _sentinel_proc, _sentinel_pid

    if _sentinel_proc and _sentinel_proc.poll() is None:
        console.print("  [yellow]⚠ El centinela ya está corriendo.[/yellow]")
        return False

    try:
        script = Path(__file__).parent / "sentinel.py"
        _sentinel_proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _sentinel_pid = _sentinel_proc.pid
        console.print(f"  [green]✓ Centinela iniciado (PID: {_sentinel_pid})[/green]")
        return True
    except Exception as e:
        console.print(f"  [red]✗ Error iniciando centinela: {e}[/red]")
        return False


def _sentinel_stop(memoria=None) -> None:
    """Envía CMD_STOP al centinela via bus SQLite."""
    global _sentinel_proc, _sentinel_pid

    if memoria:
        try:
            memoria.enviar_mensaje_sentinel("main", "CMD_STOP")
        except Exception:
            pass

    if _sentinel_proc:
        try:
            _sentinel_proc.terminate()
        except Exception:
            pass
        _sentinel_proc = None
        _sentinel_pid = None

    console.print("  [yellow]⚠ Señal de stop enviada al centinela.[/yellow]")


def _sentinel_status(memoria=None) -> None:
    """Muestra el último STATUS del centinela."""
    if memoria:
        try:
            msgs = memoria.leer_mensajes_sentinel(source_filter="sentinel", solo_no_leidos=False)
            # Buscar el último STATUS (de ciclo o de arranque)
            for msg in reversed(msgs):
                if msg["type"] == "STATUS":
                    payload = msg["payload"]
                    ts = datetime.fromtimestamp(msg["created_at"]).strftime("%H:%M:%S")

                    if "ciclo" in payload:
                        # STATUS de ciclo analítico
                        nivel   = payload.get("nivel", "?")
                        resumen = payload.get("resumen", "—")
                        ciclo   = payload.get("ciclo", "?")
                        vivo    = _sentinel_proc and _sentinel_proc.poll() is None
                        estado_str = "[green]corriendo[/green]" if vivo else "[yellow]detenido[/yellow]"
                        color_nivel = "red" if nivel == "critical" else ("yellow" if nivel == "warning" else "green")
                        console.print(Panel(
                            f"Proceso: {estado_str}\n"
                            f"Ciclo: {ciclo} — Nivel: [{color_nivel}]{nivel.upper()}[/{color_nivel}]\n"
                            f"Resumen: {resumen}\n"
                            f"Última actualización: {ts}",
                            title="[bold cyan]🔍 Centinela[/]",
                            border_style="cyan",
                        ))
                    else:
                        # STATUS de arranque / parada
                        estado_raw = payload.get("estado", "desconocido")
                        pid = payload.get("pid", "")
                        pid_str = f" (PID {pid})" if pid else ""
                        console.print(Panel(
                            f"Estado: [bold]{estado_raw}[/bold]{pid_str}\n"
                            f"Última actualización: {ts}",
                            title="[bold cyan]🔍 Centinela[/]",
                            border_style="cyan",
                        ))
                    return
        except Exception:
            pass

    vivo = _sentinel_proc and _sentinel_proc.poll() is None
    estado = f"[green]Corriendo (PID {_sentinel_pid})[/green]" if vivo else "[yellow]Detenido[/yellow]"
    console.print(Panel(
        f"Estado del proceso: {estado}\n"
        "[dim]Sin datos de ciclo en el bus todavía.[/dim]",
        title="[bold cyan]🔍 Centinela[/]",
        border_style="cyan",
    ))


def _procesar_alertas_sentinel(memoria, source_telegram=False) -> None:
    """Verifica alertas pendientes del centinela y las muestra/envía por Telegram."""
    if not memoria or not memoria._conn:
        return
    try:
        msgs = memoria.leer_mensajes_sentinel(source_filter="sentinel", solo_no_leidos=True)
        ids_leidos = []
        for msg in msgs:
            if msg["type"] == "ALERT":
                payload = msg["payload"]
                nivel   = payload.get("nivel", "?").upper()
                resumen = payload.get("resumen", "")
                anomalias = payload.get("anomalias", [])
                ts = datetime.fromtimestamp(msg["created_at"]).strftime("%H:%M:%S")

                color = "red" if nivel == "CRITICAL" else "yellow"
                anomalias_str = "\n".join(f"  • {a}" for a in anomalias[:5])

                console.print(Panel(
                    f"[bold]Nivel:[/bold] [{color}]{nivel}[/{color}]\n"
                    f"[bold]Resumen:[/bold] {resumen}\n"
                    f"[bold]Anomalías:[/bold]\n{anomalias_str}\n"
                    f"[dim]Detectado: {ts}[/dim]",
                    title=f"[bold {color}]🚨 Alerta del Centinela[/]",
                    border_style=color,
                ))

                # Reenviar por Telegram si está activo
                if _telegram_bot and _telegram_bot.is_running():
                    emoji = "🔴" if nivel == "CRITICAL" else "⚠️"
                    msg_tg = (
                        f"{emoji} *Alerta: {nivel}*\n"
                        f"{resumen}\n\n"
                        + "\n".join(f"• {a}" for a in anomalias[:5])
                    )
                    _telegram_bot.send_alert(msg_tg)

            ids_leidos.append(msg["id"])

        if ids_leidos:
            memoria.marcar_leidos_sentinel(ids_leidos)
    except Exception:
        pass


# =============================================================================
# Comandos del CLI
# =============================================================================

def _cmd_ayuda() -> bool:
    tabla = Table(title="Comandos del agente v2.0", border_style="cyan", show_header=True)
    tabla.add_column("Comando",     style="cyan bold", no_wrap=True)
    tabla.add_column("Descripción", style="white")

    comandos = [
        ("/auto",              "Activa/desactiva modo autónomo"),
        ("/confirm",           "Alias de /auto"),
        ("/task <descripción>","Ejecuta una tarea compleja en modo autónomo (agentic loop)"),
        ("/web <query>",       "Búsqueda web manual (DuckDuckGo)"),
        ("/switch <motor>",    "Cambia el motor de IA en caliente"),
        ("/engines",           "Lista motores disponibles"),
        ("/model",             "Selecciona modelo LM Studio"),
        ("/sentinel start",    "Inicia el centinela de fondo"),
        ("/sentinel stop",     "Detiene el centinela"),
        ("/sentinel status",   "Estado actual del centinela"),
        ("/telegram status",   "Estado del bot de Telegram"),
        ("/export",            "Guarda la sesión como .md"),
        ("/clear",             "Limpia el historial de conversación"),
        ("/memory stats",      "Estadísticas de la memoria semántica"),
        ("/memory purge",      "Purga memorias expiradas por TTL"),
        ("/memory clear",      "Borra el namespace actual (con confirmación)"),
        ("/ayuda",             "Esta pantalla"),
        ("Ctrl+C",             "Salir"),
        ("↑ / ↓",             "Navegar historial de comandos"),
    ]
    for cmd, desc in comandos:
        tabla.add_row(cmd, desc)
    console.print(tabla)
    return True


def _cmd_engines(agente_actual) -> bool:
    disponibles = motores_disponibles()
    tabla = Table(title="Motores de IA disponibles", border_style="magenta", show_header=True)
    tabla.add_column("Clave",  style="magenta",   no_wrap=True)
    tabla.add_column("Nombre", style="bold white", no_wrap=True)
    tabla.add_column("Estado", style="green",      no_wrap=True)

    for clave, meta in disponibles.items():
        activo = "✓ ACTIVO" if meta["nombre"] in agente_actual.nombre_motor else ""
        tabla.add_row(clave, meta["nombre"], activo)
    console.print(tabla)
    return True


# =============================================================================
# Bucle de procesamiento de turno
# =============================================================================

def _procesar_turno(
    agente,
    historial: HistorialCanonico,
    require_confirmation: bool,
    memoria=None,
    pregunta_usuario: str = "",
    telegram_chat_id: int | None = None,
) -> None:
    """
    Bucle de razonamiento: envía al LLM, procesa tool calls, itera.
    """
    for iteracion in range(MAX_ITERACIONES):
        respuesta = agente.enviar_turno(historial, HERRAMIENTAS)

        # ── Sin tool calls: respuesta final ──────────────────────────────────
        if not respuesta.tiene_tool_calls:
            if respuesta.texto:
                console.print(
                    Panel(
                        respuesta.texto,
                        title=f"[bold cyan]🤖 {agente.nombre_motor}[/]",
                        border_style="cyan",
                    )
                )
                historial.agregar_asistente(respuesta.texto)

                # Enviar por Telegram si el mensaje vino de allí
                if telegram_chat_id and _telegram_bot and _telegram_bot.is_running():
                    _telegram_bot.send_message(telegram_chat_id, respuesta.texto)

                # Guardar en memoria
                if memoria is not None and memoria.activa:
                    texto_resp = respuesta.texto.strip()[:1200]
                    if len(texto_resp) > 80:
                        try:
                            pregunta_corta = pregunta_usuario.strip()[:300]
                            contenido_mem = (
                                f"P: {pregunta_corta}\nR: {texto_resp}"
                                if pregunta_corta else texto_resp
                            )
                            memoria.guardar(contenido=contenido_mem, tipo="respuesta_agente")
                        except Exception:
                            pass
            return

        # ── Con tool calls ────────────────────────────────────────────────────
        tool_calls_raw = [
            {
                "id":       tc.call_id,
                "type":     "function",
                "function": {
                    "name":      tc.nombre,
                    "arguments": json.dumps(tc.argumentos),
                },
            }
            for tc in respuesta.tool_calls
        ]
        historial.agregar_asistente(respuesta.texto, tool_calls=tool_calls_raw)

        if respuesta.texto:
            console.print(f"[dim italic]  💭 {respuesta.texto}[/dim italic]")

        for tc in respuesta.tool_calls:
            # Manejo de aprobación via Telegram en modo seguro
            tg_chat = telegram_chat_id
            req_conf = require_confirmation

            if req_conf and tg_chat and _telegram_bot and _telegram_bot.is_running():
                # Pedir aprobación por Telegram
                if tc.nombre == "execute_local_bash":
                    cmd_preview = tc.argumentos.get("comando", "")[:200]
                    aprobado = _telegram_bot.pedir_aprobacion(cmd_preview, tg_chat)
                    req_conf = not aprobado  # Si aprobó → sin confirmación extra en CLI

            resultado = ejecutar_tool(
                tc_nombre=tc.nombre,
                tc_argumentos=tc.argumentos,
                require_confirmation=req_conf,
                memoria=memoria,
            )

            historial.agregar_resultado_tool(
                tool_call_id=tc.call_id,
                nombre=tc.nombre,
                resultado=resultado,
            )

            if memoria is not None:
                try:
                    memoria.guardar_si_exitoso(tc.nombre, tc.argumentos, resultado)
                except Exception:
                    pass

    console.print(f"[yellow]  ⚠ Se alcanzó el límite de {MAX_ITERACIONES} iteraciones.[/yellow]")


# =============================================================================
# Bucle principal del agente
# =============================================================================

def bucle_agente(motor_inicial: str, model_id_inicial: str | None) -> None:
    global _telegram_bot

    # ── Inicializar motor ─────────────────────────────────────────────────────
    console.print(f"  ⚙ Iniciando motor [bold]{motor_inicial}[/]...", end=" ")
    try:
        agente = crear_agente(motor_inicial, model_id_inicial)
        agente.inicializar()
        console.print("[green]✓[/]")
    except Exception as e:
        console.print(f"[red]✗[/]\n  [red]Error:[/] {e}")
        console.print("  [yellow]Intentando fallback a LM Studio...[/]")
        agente = intentar_fallback_local()
        if agente is None:
            console.print("[bold red]  ✗ No se pudo inicializar ningún motor.[/bold red]")
            return

    require_confirmation: bool = cfg.REQUIRE_CONFIRMATION
    motor_actual: str = motor_inicial
    # Generar system prompt con fecha actual al arrancar la sesión
    historial = HistorialCanonico(system_prompt=get_system_prompt())

    # ── Memoria semántica ─────────────────────────────────────────────────────
    console.print("  ⚙ Iniciando memoria semántica...", end=" ")
    memoria = crear_memoria(motor_actual)
    if memoria.activa:
        console.print(f"[green]✓[/] [dim](provider: {memoria._provider})[/dim]")
    else:
        console.print("[yellow]desactivada[/]")

    # ── Telegram ──────────────────────────────────────────────────────────────
    if cfg.TELEGRAM_ENABLED and cfg.TELEGRAM_BOT_TOKEN:
        console.print("  ⚙ Iniciando Telegram bot...", end=" ")
        from telegram_bot import iniciar_bot
        _telegram_bot = iniciar_bot()
        if _telegram_bot.is_running():
            console.print("[green]✓[/]")
        else:
            console.print("[yellow]desactivado[/]")
            _telegram_bot = None

    # ── Centinela automático ──────────────────────────────────────────────────
    if cfg.SENTINEL_ENABLED:
        console.print("  ⚙ Iniciando centinela de fondo...", end=" ")
        ok = _sentinel_start(memoria)
        if not ok:
            console.print("[yellow]⚠ No se pudo iniciar el centinela.[/yellow]")

    # ── Mostrar estado inicial ────────────────────────────────────────────────
    _mostrar_estado(agente, require_confirmation, memoria)

    console.print(
        Panel(
            "[dim]Escribí tu pregunta o pedido. "
            "Usá [bold]/ayuda[/] para ver los comandos. "
            "[bold]Ctrl+C[/] para salir.[/dim]",
            border_style="dim",
        )
    )
    console.print()

    # ── Bucle de chat ─────────────────────────────────────────────────────────
    while True:
        # Verificar alertas del centinela al inicio de cada turno (no bloquea)
        _procesar_alertas_sentinel(memoria)

        # Verificar mensajes de Telegram entrantes (no bloquea)
        telegram_msg = None
        if _telegram_bot and _telegram_bot.is_running():
            telegram_msg = _telegram_bot.get_message(timeout=0.0)

        # Determinar el input: Telegram tiene prioridad si hay mensaje pendiente
        if telegram_msg:
            user_input = telegram_msg.text
            telegram_chat_id = telegram_msg.chat_id
            console.print(
                f"\n[bold blue]📱 Telegram[/bold blue] "
                f"[dim](chat {telegram_chat_id}):[/dim] {user_input}"
            )
        else:
            telegram_chat_id = None
            try:
                user_input = Prompt.ask(
                    f"[bold green]◆[/] [bold white]You[/]",
                    console=console,
                ).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n\n[cyan]  Hasta luego. 👋[/cyan]\n")
                _cleanup(memoria)
                break

        if not user_input:
            continue

        # ── Comandos especiales ────────────────────────────────────────────────
        cmd = user_input.lower().strip()

        if cmd in ("/ayuda", "/help"):
            _cmd_ayuda()
            continue

        if cmd in ("/auto", "/confirm"):
            require_confirmation = not require_confirmation
            if not require_confirmation:
                console.print(Panel(
                    "⚠️  [bold yellow]MODO AUTÓNOMO ACTIVADO[/bold yellow]\n"
                    "[dim]El agente ejecutará comandos sin preguntar.[/dim]",
                    border_style="yellow",
                ))
            else:
                console.print(Panel(
                    "🛡️  [bold green]MODO SEGURO ACTIVADO[/bold green]\n"
                    "[dim]Se requerirá confirmación (Y/n) para cada comando.[/dim]",
                    border_style="green",
                ))
            continue

        if cmd in ("/engines", "/motores", "/motor"):
            _cmd_engines(agente)
            continue

        if cmd.startswith("/switch "):
            nuevo_motor = user_input[8:].strip().lower()
            agente_nuevo, motor_actual_nuevo = _switch_motor(nuevo_motor, agente, motor_actual)
            if agente_nuevo:
                agente = agente_nuevo
                motor_actual = motor_actual_nuevo
                memoria.cerrar()
                memoria = crear_memoria(motor_actual)
                estado_mem = "[green]✓[/]" if memoria.activa else "[yellow]desactivada[/]"
                console.print(f"  🧠 Memoria: {estado_mem}")
            continue

        if cmd == "/model" and motor_actual == "local":
            model_id_nuevo = menu_modelo_local()
            if model_id_nuevo:
                console.print(f"  ⚙ Cargando modelo [bold]{model_id_nuevo}[/]...", end=" ")
                try:
                    agente = crear_agente("local", model_id_nuevo)
                    agente.inicializar()
                    console.print("[green]✓[/]")
                except Exception as e:
                    console.print(f"[red]✗ Error: {e}[/]")
            continue

        if cmd == "/export":
            _exportar_sesion(historial)
            continue

        if cmd == "/clear":
            historial.limpiar(preservar_system=True)
            console.print("[green]  ✓ Historial limpiado.[/]")
            continue

        if cmd == "/memory stats":
            _cmd_memory_stats(memoria)
            continue

        if cmd == "/memory clear":
            _cmd_memory_clear(memoria)
            continue

        if cmd == "/memory purge":
            from memory_consolidator import purgar_memorias_ttl
            n = purgar_memorias_ttl(memoria)
            console.print(f"[green]  ✓ {n} entrada(s) expirada(s) eliminada(s).[/green]")
            continue

        # ── Comandos del centinela ─────────────────────────────────────────────
        if cmd == "/sentinel start":
            _sentinel_start(memoria)
            continue
        if cmd == "/sentinel stop":
            _sentinel_stop(memoria)
            continue
        if cmd in ("/sentinel", "/sentinel status"):
            _sentinel_status(memoria)
            continue

        # ── Telegram status ────────────────────────────────────────────────────
        if cmd in ("/telegram", "/telegram status"):
            if _telegram_bot and _telegram_bot.is_running():
                ids_str = ", ".join(str(i) for i in _telegram_bot.allowed_ids) or "(ninguno registrado)"
                console.print(Panel(
                    f"[green]✓ Bot activo[/green]\n"
                    f"Chat IDs autorizados: {ids_str}",
                    title="[bold blue]📱 Telegram[/]",
                    border_style="blue",
                ))
            else:
                console.print(Panel(
                    "[yellow]Bot desactivado[/yellow]\n"
                    "Configurá TELEGRAM_BOT_TOKEN y TELEGRAM_ENABLED=True en .env",
                    title="[bold blue]📱 Telegram[/]",
                    border_style="yellow",
                ))
            continue

        # ── Búsqueda web manual ────────────────────────────────────────────────
        if cmd.startswith("/web "):
            query = user_input[5:].strip()
            if query:
                from tools_web import buscar_web
                resultado_web = buscar_web(query, guardar_en_memoria=memoria)
                console.print(Panel(
                    resultado_web[:3000],
                    title=f"[bold blue]🌐 Web: {query[:50]}[/]",
                    border_style="blue",
                ))
            continue

        # ── Modo tarea autónoma (/task) ────────────────────────────────────────
        if cmd.startswith("/task "):
            tarea = user_input[6:].strip()
            if not tarea:
                console.print("[yellow]  Uso: /task <descripción de la tarea>[/yellow]")
                continue

            console.print(Panel(
                f"[bold]Tarea:[/bold] {tarea}\n"
                f"[dim]Iniciando modo autónomo extendido...[/dim]",
                title="[bold cyan]🎯 Tarea Autónoma[/]",
                border_style="cyan",
            ))

            # Crear historial nuevo para la tarea con el contexto de la tarea
            historial_tarea = HistorialCanonico(system_prompt=get_system_prompt())

            # Inyectar memoria relevante
            if memoria.activa:
                recuerdos = memoria.buscar(tarea)
                if recuerdos:
                    bloque = formatear_contexto_memoria(recuerdos)
                    tarea_enriquecida = f"{bloque}\n\n{tarea}"
                    console.print(f"  [dim]🧠 {len(recuerdos)} recuerdo(s) inyectado(s).[/dim]")
                else:
                    tarea_enriquecida = tarea
            else:
                tarea_enriquecida = tarea

            historial_tarea.agregar_usuario(tarea_enriquecida)

            telegram_send_fn = None
            if telegram_chat_id and _telegram_bot and _telegram_bot.is_running():
                telegram_send_fn = lambda txt: _telegram_bot.send_message(telegram_chat_id, txt)

            runner = AgenticTaskRunner(
                agente=agente,
                memoria=memoria,
                require_confirmation=require_confirmation,
                console=console,
                telegram_send=telegram_send_fn,
            )

            try:
                resultado_tarea = runner.ejecutar(historial_tarea, tarea)
                console.print(Panel(
                    resultado_tarea,
                    title=f"[bold cyan]🎯 Resultado: {tarea[:50]}[/]",
                    border_style="cyan",
                ))
                # Agregar al historial principal también
                historial.agregar_usuario(f"/task {tarea}")
                historial.agregar_asistente(resultado_tarea)
            except Exception as e:
                console.print(f"[bold red]  ✗ Error en la tarea: {e}[/bold red]")
            console.print()
            continue

        # ── Mensaje normal al LLM ──────────────────────────────────────────────
        texto_para_llm = user_input
        if memoria.activa:
            recuerdos = memoria.buscar(user_input)
            if recuerdos:
                bloque_memoria = formatear_contexto_memoria(recuerdos)
                texto_para_llm = f"{bloque_memoria}\n\n{user_input}"
                console.print(f"  [dim]🧠 {len(recuerdos)} recuerdo(s) relevante(s) inyectado(s).[/dim]")

        historial.agregar_usuario(texto_para_llm)
        console.print()

        try:
            _procesar_turno(
                agente, historial, require_confirmation, memoria,
                pregunta_usuario=user_input,
                telegram_chat_id=telegram_chat_id,
            )
        except Exception as e:
            err_str = str(e).lower()
            # ── Error 400: contexto demasiado largo ───────────────────────────
            if "400" in str(e) and ("context" in err_str or "exceeded" in err_str or "length" in err_str):
                console.print(
                    "[yellow]  ⚠ Contexto demasiado largo. Reduciendo historial y reintentando...[/yellow]"
                )
                # Conservar system prompt + últimos 6 mensajes (3 turnos)
                historial.reducir(mantener_ultimos=6)
                try:
                    _procesar_turno(
                        agente, historial, require_confirmation, memoria,
                        pregunta_usuario=user_input,
                        telegram_chat_id=telegram_chat_id,
                    )
                except Exception as e2:
                    console.print(f"[bold red]  ✗ Error tras reducir contexto:[/] {e2}")
            else:
                console.print(f"[bold red]  ✗ Error del agente:[/] {e}")
                console.print("  [yellow]Intentando fallback a LM Studio...[/]")
                fallback = intentar_fallback_local()
                if fallback:
                    agente = fallback
                    motor_actual = "local"
                    memoria.cerrar()
                    memoria = crear_memoria(motor_actual)
                    console.print("[green]  ✓ Cambiado a LM Studio.[/]")
                else:
                    console.print("[red]  ✗ Fallback fallido.[/]")

        console.print()


# =============================================================================
# Helpers
# =============================================================================

def _cleanup(memoria) -> None:
    """Limpieza al salir."""
    try:
        memoria.cerrar()
    except Exception:
        pass
    if _telegram_bot:
        try:
            _telegram_bot.stop()
        except Exception:
            pass
    if _sentinel_proc and _sentinel_proc.poll() is None:
        try:
            _sentinel_stop()
        except Exception:
            pass


def _switch_motor(nuevo_motor: str, agente_actual, motor_actual: str):
    disponibles = motores_disponibles()
    if nuevo_motor not in disponibles:
        console.print(
            f"[red]  Motor '{nuevo_motor}' no disponible.[/]\n"
            f"  Disponibles: {list(disponibles.keys())}"
        )
        return None, motor_actual

    console.print(f"  ⚙ Cambiando a [bold]{nuevo_motor}[/]...", end=" ")
    try:
        nuevo = crear_agente(nuevo_motor)
        nuevo.inicializar()
        console.print("[green]✓[/]")
        console.print(f"  [cyan]Motor activo: {nuevo.nombre_motor}[/]")
        return nuevo, nuevo_motor
    except Exception as e:
        console.print(f"[red]✗[/]\n  [red]Error:[/] {e}")
        return None, motor_actual


def _mostrar_estado(agente, require_confirmation: bool, memoria=None) -> None:
    modo = (
        "[bold red]🛡 MODO SEGURO[/bold red] (confirmación requerida)"
        if require_confirmation
        else "[bold yellow]⚠ MODO AUTÓNOMO[/bold yellow] (sin confirmación)"
    )
    if memoria is not None and memoria.activa:
        mem_info = f"[green]✓ activa[/green] [dim](provider: {memoria._provider})[/dim]"
    elif memoria is not None:
        mem_info = "[yellow]desactivada[/yellow]"
    else:
        mem_info = "[dim]no disponible[/dim]"

    sentinel_estado = ""
    if _sentinel_proc and _sentinel_proc.poll() is None:
        sentinel_estado = "\n🔍 Centinela: [green]corriendo[/green]"
    elif cfg.SENTINEL_ENABLED:
        sentinel_estado = "\n🔍 Centinela: [yellow]detenido[/yellow]"

    telegram_estado = ""
    if _telegram_bot and _telegram_bot.is_running():
        telegram_estado = "\n📱 Telegram: [green]activo[/green]"
    elif cfg.TELEGRAM_ENABLED:
        telegram_estado = "\n📱 Telegram: [yellow]deshabilitado[/yellow]"

    herramientas_str = "bash · web · archivos · SSH · WoL"

    console.print(
        Panel(
            f"🤖 Motor: [bold cyan]{agente.nombre_motor}[/bold cyan]\n"
            f"🔧 Herramientas: {herramientas_str}\n"
            f"🔒 Modo: {modo}\n"
            f"🧠 Memoria: {mem_info}"
            f"{sentinel_estado}"
            f"{telegram_estado}",
            title="[bold]Estado del Agente v2.0[/]",
            border_style="blue",
        )
    )


def _cmd_memory_stats(memoria) -> None:
    stats = memoria.stats()
    if not stats.get("activa"):
        console.print(Panel(
            f"[yellow]Memoria desactivada[/yellow]\n[dim]{stats.get('razon', '')}[/dim]",
            title="[bold]🧠 Memoria Semántica[/]",
            border_style="yellow",
        ))
        return

    por_tipo_str = "\n".join(
        f"  • {tipo}: [cyan]{cnt}[/cyan]"
        for tipo, cnt in stats.get("por_tipo", {}).items()
    ) or "  [dim](sin entradas aún)[/dim]"

    sentinel_info = f"\n  📬 Mensajes sentinel pendientes: {stats.get('sentinel_pendientes', 0)}"

    console.print(Panel(
        f"[green]Activa[/green] — provider: [cyan]{stats['provider']}[/cyan]\n"
        f"Total: [bold]{stats['total']}[/bold] / {stats['max_entries']}\n"
        f"Por tipo:\n{por_tipo_str}{sentinel_info}\n"
        f"Archivo: [dim]{stats['db_path']}[/dim] ({stats.get('db_size_kb', 0)} KB)",
        title="[bold]🧠 Memoria Semántica[/]",
        border_style="cyan",
    ))


def _cmd_memory_clear(memoria) -> None:
    if not memoria.activa:
        console.print("[yellow]  ⚠ La memoria no está activa.[/yellow]")
        return
    try:
        confirm = Prompt.ask(
            "  [bold red]¿Borrar TODAS las memorias del provider actual?[/bold red] [dim](s/N)[/dim]",
            console=console,
        ).strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print("  [dim]Cancelado.[/dim]")
        return
    if confirm in ("s", "si", "sí", "y", "yes"):
        eliminadas = memoria.limpiar()
        console.print(f"[green]  ✓ {eliminadas} recuerdo(s) eliminado(s).[/green]")
    else:
        console.print("  [dim]Cancelado.[/dim]")


def _exportar_sesion(historial: HistorialCanonico) -> None:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sesion_{ts}.md"
    contenido = historial.exportar_markdown()
    try:
        Path(filename).write_text(contenido, encoding="utf-8")
        console.print(f"[green]  ✓ Sesión exportada a [bold]{filename}[/bold][/]")
    except Exception as e:
        console.print(f"[red]  ✗ Error al exportar: {e}[/]")


# =============================================================================
# Entry point
# =============================================================================

def main() -> None:
    mostrar_banner()
    try:
        motor, model_id = menu_motor()
        bucle_agente(motor, model_id)
    except KeyboardInterrupt:
        console.print("\n[cyan]  Hasta luego. 👋[/cyan]\n")
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
