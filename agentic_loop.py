# =============================================================================
# agentic_loop.py — Bucle Autónomo de Resolución de Tareas
# Linux Local AI Agent v2.0
#
# Cuando el agente recibe una tarea compleja (via /task) o detecta errores
# consecutivos en modo autónomo, este bucle:
#   1. Descompone y ejecuta subtareas
#   2. Si un paso falla → busca en memoria → busca en web → reintenta
#   3. Al finalizar → consolida el episodio en un solo "insight" en memoria
# =============================================================================

from __future__ import annotations
import json
import time
import logging
from typing import TYPE_CHECKING, Callable

import config as cfg
from llm.tool_registry import HERRAMIENTAS

if TYPE_CHECKING:
    from llm.base import AgenteIA
    from llm.history import HistorialCanonico
    from llm.memory import MemoriaSemantica

logger = logging.getLogger(__name__)

# Iteraciones máximas absolutas en el agentic loop
_MAX_ITER_ABSOLUTO = 30


def ejecutar_tool(
    tc_nombre: str,
    tc_argumentos: dict,
    require_confirmation: bool,
    memoria: "MemoriaSemantica | None" = None,
) -> str:
    """
    Ejecuta cualquiera de las tools disponibles según el nombre.
    Centraliza el dispatch de tools para main.py y agentic_loop.py.
    """
    from tools import ejecutar_bash
    from tools_web import buscar_web
    from tools_files import leer_archivo, escribir_archivo
    from tools_remote import ejecutar_ssh, wake_on_lan

    if tc_nombre == "execute_local_bash":
        return ejecutar_bash(
            tc_argumentos.get("comando", ""),
            require_confirmation=require_confirmation,
        )

    elif tc_nombre == "web_search":
        return buscar_web(
            query=tc_argumentos.get("query", ""),
            max_results=min(tc_argumentos.get("max_results", cfg.WEB_SEARCH_MAX_RESULTS), 10),
            guardar_en_memoria=memoria,
        )

    elif tc_nombre == "read_file":
        return leer_archivo(
            path=tc_argumentos.get("path", ""),
            inicio_linea=tc_argumentos.get("inicio_linea"),
            fin_linea=tc_argumentos.get("fin_linea"),
        )

    elif tc_nombre == "write_file":
        return escribir_archivo(
            path=tc_argumentos.get("path", ""),
            content=tc_argumentos.get("content", ""),
            modo=tc_argumentos.get("modo", "w"),
            require_confirmation=require_confirmation,
        )

    elif tc_nombre == "execute_ssh":
        return ejecutar_ssh(
            host=tc_argumentos.get("host", ""),
            user=tc_argumentos.get("user", ""),
            comando=tc_argumentos.get("comando", ""),
            key_path=tc_argumentos.get("key_path"),
            password=tc_argumentos.get("password"),
            port=tc_argumentos.get("port", 22),
            require_confirmation=require_confirmation,
        )

    elif tc_nombre == "wake_on_lan":
        return wake_on_lan(
            mac_address=tc_argumentos.get("mac_address", ""),
            broadcast=tc_argumentos.get("broadcast"),
        )

    else:
        return f"Herramienta '{tc_nombre}' no reconocida."


class AgenticTaskRunner:
    """
    Ejecuta una tarea de forma autónoma con reintentos inteligentes.

    Flujo por iteración:
    1. Enviar al LLM con contexto actual (tarea + historial + contexto adicional)
    2. Ejecutar tool calls
    3. Si hay error (bash con exit_code != 0 o herramienta fallida):
       a. Buscar en memoria local experiencias similares
       b. Si no hay info suficiente → web_search (si AGENTIC_USE_WEB_ON_FAIL)
       c. Agregar info encontrada al contexto y reintentar
    4. Si el LLM genera respuesta sin tool calls → fin (éxito o renuncia)
    5. Si se llega a AGENTIC_MAX_RETRIES errores consecutivos → detener
    6. Al terminar → consolidar episodio en memoria
    """

    def __init__(
        self,
        agente: "AgenteIA",
        memoria: "MemoriaSemantica",
        require_confirmation: bool,
        console=None,
        telegram_send: Callable[[str], None] | None = None,
    ) -> None:
        self.agente               = agente
        self.memoria              = memoria
        self.require_confirmation = require_confirmation
        self.max_retries          = cfg.AGENTIC_MAX_RETRIES
        self.max_iteraciones      = cfg.AGENTIC_MAX_ITERATIONS
        self.usar_web             = cfg.AGENTIC_USE_WEB_ON_FAIL
        self.telegram_send        = telegram_send  # Callback para notificar por Telegram

        # Rich console (inyectada desde main.py para no crear otra instancia)
        if console is None:
            from rich.console import Console
            self.console = Console()
        else:
            self.console = console

        # Estado interno del episodio
        self._eventos_episodio: list[str] = []
        self._errores_consecutivos = 0
        self._iteracion_actual = 0

    def ejecutar(
        self,
        historial: "HistorialCanonico",
        tarea: str,
    ) -> str:
        """
        Punto de entrada principal. Ejecuta la tarea con reintentos inteligentes.

        Parámetros
        ----------
        historial : Historial de conversación actual (se modifica in-place).
        tarea     : Descripción de la tarea en lenguaje natural.

        Retorna
        -------
        String con el resultado final (éxito, fracaso, o resumen).
        """
        self.console.print(
            f"\n  [bold cyan]🔁 Modo Tarea Autónoma[/bold cyan] — "
            f"[dim]max {self.max_iteraciones} iter · {self.max_retries} reintentos[/dim]"
        )

        if self.telegram_send:
            self.telegram_send(f"🔁 *Iniciando tarea autónoma:*\n{tarea}")

        contexto_adicional: list[str] = []
        resultado_final = ""
        self._errores_consecutivos = 0
        self._iteracion_actual = 0
        self._eventos_episodio = [f"Tarea: {tarea}"]

        for iteracion in range(min(self.max_iteraciones, _MAX_ITER_ABSOLUTO)):
            self._iteracion_actual = iteracion + 1

            # Inyectar contexto adicional acumulado si hay
            if contexto_adicional:
                bloque = (
                    "[CONTEXTO ADICIONAL — información encontrada para continuar la tarea]\n"
                    + "\n\n".join(contexto_adicional)
                    + "\n\nTomá en cuenta esto y continuá con la tarea."
                )
                historial.agregar_usuario(bloque)
                contexto_adicional = []

            self.console.print(
                f"  [dim]⚙ Iteración {self._iteracion_actual}/{self.max_iteraciones}...[/dim]"
            )

            # ── Llamar al LLM ──────────────────────────────────────────────
            try:
                respuesta = self.agente.enviar_turno(historial, HERRAMIENTAS)
            except Exception as e:
                self.console.print(f"  [red]✗ Error del LLM en iter {self._iteracion_actual}: {e}[/red]")
                resultado_final = f"Error del LLM: {e}"
                break

            # ── Respuesta sin tool calls = fin de tarea ────────────────────
            if not respuesta.tiene_tool_calls:
                if respuesta.texto:
                    resultado_final = respuesta.texto
                    historial.agregar_asistente(respuesta.texto)
                    self._eventos_episodio.append(f"Resultado final: {respuesta.texto[:300]}")
                break

            # ── Mostrar razonamiento si hay ────────────────────────────────
            if respuesta.texto:
                self.console.print(f"  [dim italic]  💭 {respuesta.texto[:200]}[/dim italic]")

            # ── Registrar tool calls en historial ────────────────────────
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

            # ── Ejecutar cada tool call ───────────────────────────────────
            hay_fallo_en_este_turno = False

            for tc in respuesta.tool_calls:
                resultado_tool = ejecutar_tool(
                    tc_nombre=tc.nombre,
                    tc_argumentos=tc.argumentos,
                    require_confirmation=self.require_confirmation,
                    memoria=self.memoria,
                )

                historial.agregar_resultado_tool(
                    tool_call_id=tc.call_id,
                    nombre=tc.nombre,
                    resultado=resultado_tool,
                )

                # Registrar evento en el episodio
                evento_str = (
                    f"Tool: {tc.nombre}({list(tc.argumentos.keys())}) → "
                    f"{resultado_tool[:200]}"
                )
                self._eventos_episodio.append(evento_str)

                # ── Guardar aprendizaje en memoria ────────────────────────
                if self.memoria:
                    try:
                        self.memoria.guardar_si_exitoso(tc.nombre, tc.argumentos, resultado_tool)
                    except Exception:
                        pass

                # ── Detectar fallo ────────────────────────────────────────
                if self._es_fallo(tc.nombre, resultado_tool):
                    hay_fallo_en_este_turno = True
                    self._errores_consecutivos += 1

                    self.console.print(
                        f"  [yellow]⚠ Fallo detectado "
                        f"(consecutivos: {self._errores_consecutivos}/{self.max_retries})[/yellow]"
                    )

                    if self._errores_consecutivos >= self.max_retries:
                        self.console.print(
                            f"  [bold red]✗ Límite de reintentos alcanzado. Deteniendo tarea.[/bold red]"
                        )
                        resultado_final = (
                            f"La tarea fue detenida tras {self._errores_consecutivos} "
                            f"fallos consecutivos sin resolución."
                        )
                        self._consolidar(tarea, resultado_final)
                        if self.telegram_send:
                            self.telegram_send(
                                f"⚠️ *Tarea detenida:* {tarea}\n"
                                f"Motivo: {self._errores_consecutivos} fallos consecutivos."
                            )
                        return resultado_final

                    # Buscar ayuda (memoria + web)
                    info = self._buscar_ayuda(tc.nombre, tc.argumentos, resultado_tool)
                    if info:
                        contexto_adicional.append(info)
                else:
                    # Éxito: reiniciar contador de errores
                    self._errores_consecutivos = 0

        # ── Fin del loop ──────────────────────────────────────────────────
        if not resultado_final:
            resultado_final = f"Tarea completada (límite de {self.max_iteraciones} iteraciones)."

        self._consolidar(tarea, resultado_final)

        if self.telegram_send:
            self.telegram_send(
                f"✅ *Tarea completada:* {tarea}\n\n"
                f"Resultado: {resultado_final[:500]}"
            )

        return resultado_final

    def _es_fallo(self, nombre_tool: str, resultado: str) -> bool:
        """Determina si el resultado de una tool indica un fallo."""
        resultado_lower = resultado.lower()

        if nombre_tool == "execute_local_bash":
            # Fallo explícito por exit code
            if "exit code: 0" in resultado_lower or "exit code:0" in resultado_lower:
                return False
            # Fallo por exit code distinto de 0
            for i in range(1, 256):
                if f"exit code: {i}" in resultado_lower:
                    return True
            return False

        elif nombre_tool == "web_search":
            return "error" in resultado_lower and "resultados" not in resultado_lower

        elif nombre_tool in ("read_file", "write_file"):
            return resultado_lower.startswith("error:")

        elif nombre_tool == "execute_ssh":
            return "error ssh" in resultado_lower or "fallo de autenticación" in resultado_lower

        return False

    def _buscar_ayuda(
        self,
        nombre_tool: str,
        argumentos: dict,
        resultado_fallido: str,
    ) -> str | None:
        """
        Busca información para resolver el fallo:
        1. Primero en la memoria semántica local.
        2. Si no hay suficiente info, busca en la web.
        """
        partes_ayuda: list[str] = []

        # 1. Buscar en memoria
        if self.memoria and self.memoria.activa:
            query_memoria = f"error {nombre_tool} {resultado_fallido[:150]}"
            recuerdos = self.memoria.buscar(query_memoria, top_k=2, threshold=0.70)
            if recuerdos:
                recuerdos_str = "\n".join(
                    f"- [{r['tipo']}] {r['contenido'][:200]}" for r in recuerdos
                )
                partes_ayuda.append(
                    f"[De la memoria del agente]\n{recuerdos_str}"
                )
                self.console.print(
                    f"  [dim]🧠 {len(recuerdos)} recuerdo(s) relevante(s) encontrado(s).[/dim]"
                )

        # 2. Buscar en web si está habilitado y hay un error de bash
        if self.usar_web and nombre_tool == "execute_local_bash":
            comando = argumentos.get("comando", "")
            try:
                from tools_web import buscar_solucion_error
                resultado_web = buscar_solucion_error(
                    comando=comando,
                    error_output=resultado_fallido,
                    guardar_en_memoria=self.memoria,
                )
                if resultado_web and "error" not in resultado_web.lower()[:30]:
                    partes_ayuda.append(f"[Búsqueda web]\n{resultado_web[:600]}")
            except Exception as e:
                logger.debug(f"[AgenticLoop] Error en búsqueda web de ayuda: {e}")

        return "\n\n".join(partes_ayuda) if partes_ayuda else None

    def _consolidar(self, tarea: str, resolucion: str) -> None:
        """Consolida el episodio en un insight de memoria."""
        if not self._eventos_episodio:
            return
        try:
            from memory_consolidator import consolidar_episodio
            consolidar_episodio(
                agente=self.agente,
                eventos=self._eventos_episodio,
                resolucion=resolucion,
                memoria=self.memoria,
                tarea_original=tarea,
            )
        except Exception as e:
            logger.debug(f"[AgenticLoop] Error en consolidación: {e}")
