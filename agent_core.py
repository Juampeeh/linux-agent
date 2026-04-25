# =============================================================================
# agent_core.py — Núcleo del agente desacoplado de la interfaz (CLI/Web)
# Linux Local AI Agent v3.0
#
# Provee AgentSession: un contenedor de sesión que procesa mensajes y emite
# eventos estructurados. Usado tanto por main.py (CLI) como por web_server.py.
# =============================================================================

from __future__ import annotations

import json
import asyncio
import uuid
from typing import AsyncGenerator, Callable, TYPE_CHECKING

import config as cfg
from llm.router import crear_agente, motores_disponibles, intentar_fallback_local
from llm.history import HistorialCanonico
from llm.tool_registry import HERRAMIENTAS, get_system_prompt
from llm.memory import crear_memoria
from agentic_loop import ejecutar_tool, AgenticTaskRunner

if TYPE_CHECKING:
    from llm.base import AgenteIA
    from llm.memory import MemoriaSemantica

# ── Tipos de eventos emitidos por AgentSession.procesar_mensaje() ─────────────
# {"type": "thinking",     "text": "..."}         — pensamiento intermedio del LLM
# {"type": "tool_call",    "tool": "...", "args": {...}, "display": "..."}
# {"type": "tool_confirm", "tool": "...", "display": "...", "confirm_id": "uuid"}
# {"type": "tool_result",  "result": "...", "tool": "..."}
# {"type": "text_chunk",   "text": "..."}         — fragmento de respuesta final
# {"type": "text",         "text": "..."}         — respuesta final completa
# {"type": "done"}
# {"type": "error",        "text": "..."}
# {"type": "info",         "text": "..."}         — mensajes de estado/info
# {"type": "mode_change",  "seguro": bool}
# {"type": "motor_change", "motor": "..."}

MAX_ITERACIONES = 10


class AgentSession:
    """
    Sesión del agente: encapsula el LLM, historial, memoria y estado de la sesión.
    Diseñada para ser compartida entre CLI y Web (thread-safe para lecturas, 
    no para escrituras concurrentes — una sesión por usuario).
    """

    def __init__(self, motor: str = cfg.DEFAULT_ENGINE, model_id: str | None = None):
        self.motor: str = motor
        self.model_id: str | None = model_id
        self.require_confirmation: bool = cfg.REQUIRE_CONFIRMATION

        self.agente: AgenteIA | None = None
        self.historial: HistorialCanonico | None = None
        self.memoria: MemoriaSemantica | None = None

        # Cola de confirmaciones pendientes: confirm_id → asyncio.Future
        self._pending_confirms: dict[str, asyncio.Future] = {}

        self._lock = asyncio.Lock()

    # ── Inicialización ─────────────────────────────────────────────────────────

    async def inicializar(self) -> dict:
        """
        Inicializa el agente, historial y memoria.
        Retorna dict con estado inicial para enviar al cliente.
        """
        try:
            self.agente = crear_agente(self.motor, self.model_id)
            self.agente.inicializar()
        except Exception as e:
            self.agente = intentar_fallback_local()
            if self.agente is None:
                raise RuntimeError(f"No se pudo inicializar ningún motor: {e}") from e
            self.motor = "local"

        self.historial = HistorialCanonico(system_prompt=get_system_prompt())
        self.memoria = crear_memoria(self.motor)

        return self.get_status()

    # ── Estado público ─────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Retorna el estado actual de la sesión como dict serializable."""
        mem_stats: dict = {}
        if self.memoria:
            try:
                mem_stats = self.memoria.stats()
            except Exception:
                pass

        sentinel_pid = _read_sentinel_pid()
        sentinel_alive = _sentinel_alive(sentinel_pid)

        return {
            "motor": self.agente.nombre_motor if self.agente else "no inicializado",
            "motor_key": self.motor,
            "motores_disponibles": motores_disponibles(),
            "require_confirmation": self.require_confirmation,
            "memoria": {
                "activa": bool(self.memoria and self.memoria.activa),
                "provider": getattr(self.memoria, "_provider", None) if self.memoria else None,
                "stats": mem_stats,
            },
            "sentinel": {
                "pid": sentinel_pid,
                "corriendo": sentinel_alive,
            },
            "version": "3.0.0",
        }

    # ── Procesamiento de mensajes ──────────────────────────────────────────────

    async def procesar_mensaje(
        self,
        texto: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Procesa un mensaje del usuario y emite eventos estructurados.
        Maneja comandos especiales (/auto, /switch, /clear, etc.) y
        delega al LLM los mensajes normales.
        """
        texto_strip = texto.strip()
        cmd = texto_strip.lower()

        # ── Comandos especiales ────────────────────────────────────────────────
        if cmd in ("/ayuda", "/help"):
            yield {"type": "info", "text": _ayuda_texto()}
            yield {"type": "done"}
            return

        if cmd in ("/auto", "/confirm"):
            self.require_confirmation = not self.require_confirmation
            modo = "SEGURO 🛡" if self.require_confirmation else "AUTÓNOMO ⚡"
            yield {"type": "mode_change", "seguro": self.require_confirmation,
                   "text": f"Modo cambiado a: {modo}"}
            yield {"type": "done"}
            return

        if cmd == "/clear":
            if self.historial:
                self.historial.limpiar(preservar_system=True)
            yield {"type": "info", "text": "✓ Historial limpiado."}
            yield {"type": "done"}
            return

        if cmd == "/memory stats":
            stats = self.memoria.stats() if self.memoria else {}
            yield {"type": "memory_stats", "stats": stats}
            yield {"type": "done"}
            return

        if cmd == "/memory purge":
            if self.memoria:
                from memory_consolidator import purgar_memorias_ttl
                n = purgar_memorias_ttl(self.memoria)
                yield {"type": "info", "text": f"✓ {n} entrada(s) expirada(s) eliminadas."}
            yield {"type": "done"}
            return

        if cmd == "/memory clear":
            if self.memoria:
                n = self.memoria.limpiar()
                yield {"type": "info", "text": f"✓ {n} recuerdo(s) eliminado(s)."}
            yield {"type": "done"}
            return

        if cmd.startswith("/switch "):
            nuevo_motor = texto_strip[8:].strip().lower()
            async for evento in self._cmd_switch(nuevo_motor):
                yield evento
            return

        if cmd == "/engines":
            disponibles = motores_disponibles()
            yield {"type": "engines", "motores": disponibles,
                   "activo": self.motor}
            yield {"type": "done"}
            return

        if cmd == "/sentinel start":
            ok = _sentinel_start(self.memoria)
            yield {"type": "sentinel_update",
                   "corriendo": ok,
                   "text": "Centinela iniciado." if ok else "Error al iniciar centinela."}
            yield {"type": "done"}
            return

        if cmd == "/sentinel stop":
            _sentinel_stop(self.memoria)
            yield {"type": "sentinel_update", "corriendo": False,
                   "text": "Centinela detenido."}
            yield {"type": "done"}
            return

        if cmd in ("/sentinel", "/sentinel status"):
            info = _sentinel_status_dict(self.memoria)
            yield {"type": "sentinel_status", **info}
            yield {"type": "done"}
            return

        if cmd.startswith("/web "):
            query = texto_strip[5:].strip()
            from tools_web import buscar_web
            resultado = await asyncio.to_thread(
                buscar_web, query, guardar_en_memoria=self.memoria
            )
            yield {"type": "web_result", "query": query, "result": resultado}
            yield {"type": "done"}
            return

        if cmd.startswith("/task "):
            tarea = texto_strip[6:].strip()
            async for evento in self._procesar_task(tarea):
                yield evento
            return

        # ── Mensaje normal al LLM ──────────────────────────────────────────────
        async for evento in self._procesar_llm(texto_strip):
            yield evento

    # ── Procesamiento LLM ─────────────────────────────────────────────────────

    async def _procesar_llm(self, texto: str) -> AsyncGenerator[dict, None]:
        """Procesa un mensaje normal: envía al LLM e itera tool calls."""
        if not self.agente or not self.historial:
            yield {"type": "error", "text": "El agente no está inicializado."}
            yield {"type": "done"}
            return

        # Actualizar system prompt con fecha actual — recrear historial preservando mensajes
        # _mensajes[0] siempre es el system prompt
        if self.historial._mensajes:
            self.historial._mensajes[0].contenido = get_system_prompt()

        self.historial.agregar_usuario(texto)

        respuesta_final = ""

        for iteracion in range(MAX_ITERACIONES):
            try:
                respuesta = await asyncio.to_thread(
                    self.agente.enviar_turno, self.historial, HERRAMIENTAS
                )
            except Exception as e:
                err_str = str(e)
                if "400" in err_str and any(
                    k in err_str.lower() for k in ("context", "exceeded", "length")
                ):
                    self.historial.reducir(mantener_ultimos=6)
                    try:
                        respuesta = await asyncio.to_thread(
                            self.agente.enviar_turno, self.historial, HERRAMIENTAS
                        )
                    except Exception as e2:
                        yield {"type": "error", "text": str(e2)}
                        yield {"type": "done"}
                        return
                else:
                    yield {"type": "error", "text": err_str}
                    yield {"type": "done"}
                    return

            # Sin tool calls: respuesta final
            if not respuesta.tiene_tool_calls:
                if respuesta.texto:
                    respuesta_final = respuesta.texto
                    yield {"type": "text", "text": respuesta.texto}
                    self.historial.agregar_asistente(respuesta.texto)
                    # Guardar en memoria
                    if self.memoria and self.memoria.activa and len(respuesta.texto) > 80:
                        try:
                            contenido_mem = f"P: {texto[:300]}\nR: {respuesta.texto[:1200]}"
                            await asyncio.to_thread(
                                self.memoria.guardar, contenido_mem, "respuesta_agente"
                            )
                        except Exception:
                            pass
                yield {"type": "done"}
                return

            # Con tool calls
            tool_calls_raw = [
                {"id": tc.call_id, "type": "function",
                 "function": {"name": tc.nombre, "arguments": json.dumps(tc.argumentos)}}
                for tc in respuesta.tool_calls
            ]
            self.historial.agregar_asistente(respuesta.texto, tool_calls=tool_calls_raw)

            if respuesta.texto:
                yield {"type": "thinking", "text": respuesta.texto}

            for tc in respuesta.tool_calls:
                display = _describir_tool(tc.nombre, tc.argumentos)

                # Solicitar confirmación si corresponde
                req_conf = self.require_confirmation
                if req_conf and tc.nombre in ("execute_local_bash", "write_file", "execute_ssh"):
                    confirm_id = str(uuid.uuid4())[:8]
                    future: asyncio.Future = asyncio.get_event_loop().create_future()
                    self._pending_confirms[confirm_id] = future

                    yield {
                        "type": "tool_confirm",
                        "tool": tc.nombre,
                        "display": display,
                        "confirm_id": confirm_id,
                        "args": tc.argumentos,
                    }

                    try:
                        aprobado = await asyncio.wait_for(future, timeout=120.0)
                    except asyncio.TimeoutError:
                        aprobado = False
                    finally:
                        self._pending_confirms.pop(confirm_id, None)

                    if not aprobado:
                        resultado = "Comando cancelado por el usuario."
                        yield {"type": "tool_result", "tool": tc.nombre,
                               "result": resultado, "cancelled": True}
                        self.historial.agregar_resultado_tool(tc.call_id, tc.nombre, resultado)
                        continue
                    req_conf = False  # Ya confirmado

                # Notificar tool call
                yield {"type": "tool_call", "tool": tc.nombre,
                       "display": display, "args": tc.argumentos}

                # Ejecutar (en thread para no bloquear)
                resultado = await asyncio.to_thread(
                    ejecutar_tool,
                    tc.nombre, tc.argumentos, req_conf, self.memoria,
                )

                yield {"type": "tool_result", "tool": tc.nombre, "result": resultado}
                self.historial.agregar_resultado_tool(tc.call_id, tc.nombre, resultado)

                if self.memoria:
                    try:
                        await asyncio.to_thread(
                            self.memoria.guardar_si_exitoso, tc.nombre, tc.argumentos, resultado
                        )
                    except Exception:
                        pass

        yield {"type": "info", "text": f"⚠ Límite de {MAX_ITERACIONES} iteraciones alcanzado."}
        yield {"type": "done"}

    # ── Tarea autónoma ─────────────────────────────────────────────────────────

    async def _procesar_task(self, tarea: str) -> AsyncGenerator[dict, None]:
        """Ejecuta una tarea en modo agentic loop con streaming de progreso."""
        if not self.agente or not self.memoria:
            yield {"type": "error", "text": "El agente no está inicializado."}
            yield {"type": "done"}
            return

        yield {"type": "task_start", "tarea": tarea}

        historial_tarea = HistorialCanonico(system_prompt=get_system_prompt())
        historial_tarea.agregar_usuario(tarea)

        # AgenticTaskRunner usa console internamente — creamos uno sin output
        from rich.console import Console
        from io import StringIO
        null_console = Console(file=StringIO(), highlight=False)

        runner = AgenticTaskRunner(
            agente=self.agente,
            memoria=self.memoria,
            require_confirmation=False,  # /task siempre autónomo
            console=null_console,
        )

        try:
            resultado = await asyncio.to_thread(runner.ejecutar, historial_tarea, tarea)
            yield {"type": "task_result", "tarea": tarea, "result": resultado}
            # Agregar al historial principal
            if self.historial:
                self.historial.agregar_usuario(f"/task {tarea}")
                self.historial.agregar_asistente(resultado)
        except Exception as e:
            yield {"type": "error", "text": f"Error en la tarea: {e}"}

        yield {"type": "done"}

    # ── Switch de motor ────────────────────────────────────────────────────────

    async def _cmd_switch(self, nuevo_motor: str) -> AsyncGenerator[dict, None]:
        disponibles = motores_disponibles()
        if nuevo_motor not in disponibles:
            yield {"type": "error",
                   "text": f"Motor '{nuevo_motor}' no disponible. Opciones: {list(disponibles.keys())}"}
            yield {"type": "done"}
            return

        try:
            nuevo = await asyncio.to_thread(crear_agente, nuevo_motor)
            await asyncio.to_thread(nuevo.inicializar)
            self.agente = nuevo
            self.motor = nuevo_motor
            if self.memoria:
                self.memoria.cerrar()
            self.memoria = crear_memoria(nuevo_motor)
            yield {"type": "motor_change", "motor": nuevo.nombre_motor,
                   "motor_key": nuevo_motor, "text": f"Motor cambiado a: {nuevo.nombre_motor}"}
        except Exception as e:
            yield {"type": "error", "text": f"Error al cambiar motor: {e}"}

        yield {"type": "done"}

    # ── Confirmaciones ─────────────────────────────────────────────────────────

    def resolver_confirmacion(self, confirm_id: str, aprobado: bool) -> bool:
        """Resuelve una confirmación pendiente. Retorna True si existía."""
        future = self._pending_confirms.get(confirm_id)
        if future and not future.done():
            future.set_result(aprobado)
            return True
        return False


# =============================================================================
# Helpers de sentinel (sin import circular con main.py)
# =============================================================================

def _read_sentinel_pid() -> int | None:
    import os
    from pathlib import Path
    pid_file = Path(__file__).parent / ".sentinel.pid"
    try:
        return int(pid_file.read_text().strip())
    except Exception:
        return None


def _sentinel_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        import os
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _sentinel_start(memoria) -> bool:
    import subprocess
    import sys
    from pathlib import Path
    sentinel_py = Path(__file__).parent / "sentinel.py"
    if not sentinel_py.exists():
        return False
    pid = _read_sentinel_pid()
    if _sentinel_alive(pid):
        return True  # Ya corriendo
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(
                [sys.executable, str(sentinel_py)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
            )
        else:
            proc = subprocess.Popen(
                [sys.executable, str(sentinel_py)],
                start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return proc.pid is not None
    except Exception:
        return False


def _sentinel_stop(memoria) -> None:
    pid = _read_sentinel_pid()
    if not _sentinel_alive(pid):
        return
    try:
        import os, signal
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    try:
        from pathlib import Path
        (Path(__file__).parent / ".sentinel.pid").unlink(missing_ok=True)
    except Exception:
        pass


def _sentinel_status_dict(memoria) -> dict:
    """Lee el último ciclo del centinela desde el bus SQLite."""
    pid = _read_sentinel_pid()
    corriendo = _sentinel_alive(pid)
    resumen = "Sin datos."
    nivel = "desconocido"
    ultima_act = None

    if memoria and hasattr(memoria, "leer_mensajes_sentinel"):
        try:
            msgs = memoria.leer_mensajes_sentinel(source_filter="sentinel", solo_no_leidos=False)
            if msgs:
                ultimo = msgs[-1]
                payload = ultimo.get("payload", {})
                resumen = payload.get("resumen", resumen)
                nivel = payload.get("nivel", nivel)
                ultima_act = ultimo.get("created_at")
        except Exception:
            pass

    return {
        "corriendo": corriendo,
        "pid": pid,
        "nivel": nivel,
        "resumen": resumen,
        "ultima_actualizacion": ultima_act,
    }


# =============================================================================
# Helpers internos
# =============================================================================

def _describir_tool(nombre: str, args: dict) -> str:
    """Genera una descripción legible de la tool call para mostrar en UI."""
    if nombre == "execute_local_bash":
        return f"$ {args.get('comando', '')}"
    if nombre == "web_search":
        return f"🔎 {args.get('query', '')}"
    if nombre == "read_file":
        return f"📂 {args.get('path', '')}"
    if nombre == "write_file":
        return f"✏️ {args.get('path', '')} ({args.get('modo', 'w')})"
    if nombre == "execute_ssh":
        return f"🔌 ssh {args.get('user', '')}@{args.get('host', '')} $ {args.get('comando', '')}"
    if nombre == "wake_on_lan":
        return f"🌐 WoL → {args.get('mac_address', '')}"
    if nombre == "memory_search":
        return f"🧠 buscar: {args.get('query', '')}"
    if nombre == "memory_get_details":
        return f"🧠 detalle ID: {args.get('id_memoria', '')}"
    return nombre


def _ayuda_texto() -> str:
    return """**Comandos disponibles:**
- `/auto` — Toggle modo autónomo ↔ seguro
- `/switch <motor>` — Cambiar motor (local, gemini, chatgpt, claude, grok, ollama)
- `/engines` — Ver motores disponibles
- `/task <descripción>` — Ejecutar tarea en modo autónomo (Agentic Loop)
- `/web <query>` — Búsqueda web manual
- `/sentinel start/stop/status` — Control del centinela
- `/memory stats` — Estadísticas de memoria
- `/memory purge` — Purgar memorias expiradas
- `/memory clear` — Borrar toda la memoria del motor actual
- `/clear` — Limpiar historial de conversación
- `/export` — Exportar sesión (solo CLI)
- `/ayuda` — Esta ayuda"""
