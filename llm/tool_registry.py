# =============================================================================
# llm/tool_registry.py — Definición de herramientas disponibles para el LLM
# =============================================================================

from __future__ import annotations

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un agente experto en administración de sistemas Linux.
Tienes acceso a la herramienta `execute_local_bash` para ejecutar comandos bash
directamente en el sistema Linux donde estás corriendo.

Reglas de comportamiento:
1. Cuando el usuario te pida hacer algo en el sistema, usa la herramienta para ejecutarlo.
2. Analiza cuidadosamente el output de cada comando antes de continuar.
3. Si un comando falla, diagnostica el error y propón una solución.
4. Prefiere comandos seguros y no destructivos. Nunca hagas `rm -rf /` ni similares sin que el usuario lo confirme explícitamente.
5. Responde siempre en el mismo idioma que el usuario.
6. Sé conciso y directo. No repitas el output del comando literalmente; interpreta y resume.
"""

# ── Herramientas disponibles ──────────────────────────────────────────────────

HERRAMIENTAS: list[dict] = [
    {
        "nombre":      "execute_local_bash",
        "descripcion": (
            "Ejecuta un comando bash en el sistema Linux local. "
            "Retorna el stdout y stderr combinados, más el exit code. "
            "Úsala para explorar el sistema, instalar paquetes, gestionar servicios, etc."
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "comando": {
                    "type":        "string",
                    "description": "El comando bash a ejecutar. Puede incluir pipes, redirects, etc.",
                }
            },
            "required": ["comando"],
        },
    }
]


# ── Conversores de formato ────────────────────────────────────────────────────

def to_openai_format(herramientas: list[dict]) -> list[dict]:
    """Convierte la lista de herramientas al formato OpenAI function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name":        h["nombre"],
                "description": h["descripcion"],
                "parameters":  h["parametros"],
            },
        }
        for h in herramientas
    ]


def to_gemini_format(herramientas: list[dict]) -> list[dict]:
    """Convierte al formato de function declarations de Gemini."""
    return [
        {
            "name":        h["nombre"],
            "description": h["descripcion"],
            "parameters":  h["parametros"],
        }
        for h in herramientas
    ]


def to_anthropic_format(herramientas: list[dict]) -> list[dict]:
    """Convierte al formato de tools de Anthropic."""
    return [
        {
            "name":         h["nombre"],
            "description":  h["descripcion"],
            "input_schema": h["parametros"],
        }
        for h in herramientas
    ]
