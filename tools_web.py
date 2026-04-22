# =============================================================================
# tools_web.py — Búsqueda web via DuckDuckGo (sin API key)
# Linux Local AI Agent v2.0
# =============================================================================

from __future__ import annotations
import json
import time
from typing import Optional

import config as cfg
from rich.console import Console
from rich.panel import Panel

console = Console()


def buscar_web(
    query: str,
    max_results: Optional[int] = None,
    guardar_en_memoria=None,  # MemoriaSemantica | None (evita import circular)
) -> str:
    """
    Realiza una búsqueda en DuckDuckGo y retorna los resultados formateados para el LLM.

    Parámetros
    ----------
    query           : Términos de búsqueda.
    max_results     : Número máximo de resultados (usa WEB_SEARCH_MAX_RESULTS si es None).
    guardar_en_memoria : Instancia de MemoriaSemantica para guardar los hallazgos útiles.

    Retorna
    -------
    String con los resultados formateados, listo para inyectar en el contexto del LLM.
    """
    if not cfg.WEB_SEARCH_ENABLED:
        return "Búsqueda web deshabilitada (WEB_SEARCH_ENABLED=False en .env)."

    n = max_results or cfg.WEB_SEARCH_MAX_RESULTS

    console.print(f"  [dim]🌐 Buscando en web: [italic]{query}[/italic]...[/dim]")

    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return (
                "Error: librería de búsqueda no instalada. "
                "Ejecutá: pip install ddgs"
            )

    resultados_raw: list[dict] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=n):
                resultados_raw.append(r)
                if len(resultados_raw) >= n:
                    break
    except Exception as e:
        return f"Error en la búsqueda web: {e}"

    if not resultados_raw:
        return f"No se encontraron resultados para: '{query}'"

    # ── Formatear para el LLM ──────────────────────────────────────────────────
    lineas = [f"Resultados de búsqueda web para: '{query}'\n"]
    for i, r in enumerate(resultados_raw, 1):
        titulo  = r.get("title", "Sin título")
        url     = r.get("href", "")
        snippet = r.get("body", "")[:400]  # Limitar snippet para no sobrecargar tokens
        lineas.append(f"[{i}] {titulo}")
        lineas.append(f"    URL: {url}")
        lineas.append(f"    {snippet}")
        lineas.append("")

    resultado_str = "\n".join(lineas)

    # ── Mostrar resumen en terminal ────────────────────────────────────────────
    resumen = f"Se encontraron {len(resultados_raw)} resultado(s) para '{query}'"
    console.print(Panel(
        resumen,
        title="[bold blue]🌐 Web Search[/]",
        border_style="blue",
    ))

    # ── Guardar en memoria si se proporcionó ──────────────────────────────────
    if guardar_en_memoria is not None and guardar_en_memoria.activa:
        try:
            # Solo guardar si hay resultados sustanciales
            if len(resultado_str) > 100:
                contenido_mem = (
                    f"Búsqueda web: '{query}'\n"
                    f"Resultados resumidos:\n{resultado_str[:800]}"
                )
                guardar_en_memoria.guardar(
                    contenido=contenido_mem,
                    tipo="web_research",
                    metadata={"query": query, "num_results": len(resultados_raw)},
                )
        except Exception:
            pass  # La memoria nunca rompe el flujo principal

    return resultado_str


def buscar_solucion_error(
    comando: str,
    error_output: str,
    guardar_en_memoria=None,
) -> str:
    """
    Helper especializado: busca solución a un error de comando Linux en la web.
    Construye una query optimizada a partir del error y devuelve resultados.

    Usado por el agentic loop cuando un comando falla.
    """
    # Extraer las líneas más relevantes del error (evitar ruido)
    lineas_error = [l.strip() for l in error_output.splitlines() if l.strip()]
    # Priorizar las últimas líneas (suelen ser el error concreto)
    fragmento_error = " ".join(lineas_error[-3:])[:200]

    query = f"linux {fragmento_error} solution fix"

    console.print(
        f"  [dim]🔍 Buscando solución para error de: [italic]{comando[:60]}[/italic]...[/dim]"
    )

    return buscar_web(
        query=query,
        max_results=3,  # Menos resultados para soluciones rápidas
        guardar_en_memoria=guardar_en_memoria,
    )
