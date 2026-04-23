# =============================================================================
# llm/tool_registry.py — Definición de herramientas disponibles para el LLM v2.0
# =============================================================================

from __future__ import annotations
from datetime import datetime

# ── System prompt v2.0 (con fecha dinámica) ───────────────────────────────────

def get_system_prompt() -> str:
    """Genera el system prompt con la fecha y hora actual inyectada."""
    ahora = datetime.now()
    fecha_str = ahora.strftime("%A %d de %B de %Y")
    hora_str  = ahora.strftime("%H:%M")
    # Nombres de días/meses en español
    dias   = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
              "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"}
    meses  = {"January": "enero", "February": "febrero", "March": "marzo", "April": "abril",
              "May": "mayo", "June": "junio", "July": "julio", "August": "agosto",
              "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"}
    for en, es in {**dias, **meses}.items():
        fecha_str = fecha_str.replace(en, es)

    return f"""Eres un agente experto en administración de sistemas Linux y un Sysadmin Autónomo.
Tienes acceso a múltiples herramientas para interactuar con el sistema, buscar información en internet,
leer/escribir archivos, y ejecutar comandos en hosts remotos.

FECHA Y HORA ACTUAL: {fecha_str}, {hora_str} (hora local del servidor).
USA ESTA FECHA cuando el usuario pregunte sobre noticias, eventos, actualizaciones, o cualquier
cosa relacionada con el tiempo. Nunca digas que no sabés la fecha; la tenés arriba.

Herramientas disponibles:
- execute_local_bash: Ejecuta comandos bash en el sistema local.
- web_search: Busca información en internet (DuckDuckGo, sin API key).
- read_file: Lee el contenido de un archivo del sistema.
- write_file: Escribe contenido en un archivo del sistema.
- execute_ssh: Ejecuta un comando en un host remoto via SSH.
- wake_on_lan: Enciende un equipo remoto enviando un magic packet WoL.

Reglas de comportamiento:
1. Cuando el usuario te pida hacer algo en el sistema, usa la herramienta adecuada.
2. Preferí execute_local_bash para tareas del sistema; read_file/write_file para archivos.
3. Usá web_search cuando necesites información que no tenés: documentación, noticias actuales,
   soluciones a errores, configuraciones específicas, versiones de paquetes, etc.
4. Analizá cuidadosamente el output de cada herramienta antes de continuar.
5. Si un comando falla, diagnosticá el error. Si no sabés la solución, buscá en web.
6. Preferí comandos seguros y no destructivos. Nunca hagas `rm -rf /` ni similares sin confirmación.
7. Responde siempre en el mismo idioma que el usuario.
8. Sé conciso y directo. No repitas el output literalmente; interpretá y resumí.
9. Cuando el mensaje incluya un bloque [MEMORIA], son recuerdos de sesiones anteriores.
   Úsalos como contexto para elegir mejores soluciones. No los menciones explícitamente.
10. En modo autónomo (/task), si un paso falla, intentá resolverlo solo antes de rendirte.
    El usuario espera que seas persistente y creativo en la resolución de problemas.
11. BÚSQUEDAS WEB: cuando el usuario pida noticias recientes, buscá con la fecha actual que ya
    conocés (e.g. "noticias 22 abril 2026"). Incluí SIEMPRE la fecha de las noticias en tu respuesta.
"""

# Constante compatible con imports existentes (se regenera en cada llamada)
SYSTEM_PROMPT = get_system_prompt()

# ── Herramientas disponibles ──────────────────────────────────────────────────

HERRAMIENTAS: list[dict] = [
    {
        "nombre":      "execute_local_bash",
        "descripcion": (
            "Ejecuta un comando bash en el sistema Linux local. "
            "Retorna stdout y stderr combinados, más el exit code. "
            "Úsala para explorar el sistema, instalar paquetes, gestionar servicios, "
            "verificar procesos, comprobar red, etc."
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
    },
    {
        "nombre":      "web_search",
        "descripcion": (
            "Busca información en internet usando DuckDuckGo (sin API key, 100% gratuito). "
            "Úsala cuando necesites: documentación de un paquete, solución a un error de sistema, "
            "configuración de un servicio, versiones actuales de software, mejores prácticas, etc. "
            "Retorna títulos, URLs y snippets de los resultados más relevantes."
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "query": {
                    "type":        "string",
                    "description": "Términos de búsqueda en inglés o español.",
                },
                "max_results": {
                    "type":        "integer",
                    "description": "Número máximo de resultados (default: 5, máximo: 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "nombre":      "read_file",
        "descripcion": (
            "Lee el contenido de un archivo del sistema de archivos local. "
            "Más eficiente que usar cat via bash para archivos de configuración, logs, scripts. "
            "Maneja encoding automáticamente. Retorna el contenido truncado si es muy grande."
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Ruta absoluta o relativa al archivo a leer.",
                },
                "inicio_linea": {
                    "type":        "integer",
                    "description": "Línea desde la que empezar a leer (1-indexed, opcional).",
                },
                "fin_linea": {
                    "type":        "integer",
                    "description": "Línea hasta la que leer (1-indexed, opcional).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "nombre":      "write_file",
        "descripcion": (
            "Escribe o actualiza el contenido de un archivo del sistema. "
            "Úsala para crear/editar archivos de configuración, scripts, etc. "
            "Más seguro que redirection (>) via bash porque muestra preview y pide confirmación. "
            "Crea los directorios necesarios automáticamente."
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Ruta al archivo de destino.",
                },
                "content": {
                    "type":        "string",
                    "description": "Contenido completo a escribir en el archivo.",
                },
                "modo": {
                    "type":        "string",
                    "description": "'w' para sobreescribir (default) o 'a' para appendear al final.",
                    "enum":        ["w", "a"],
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "nombre":      "execute_ssh",
        "descripcion": (
            "Ejecuta un comando en un host remoto de la red via SSH. "
            "Útil para administrar otros servidores sin abrir una sesión interactiva. "
            "Usa clave privada SSH (~/.ssh/id_rsa) por defecto."
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "host": {
                    "type":        "string",
                    "description": "IP o hostname del host remoto.",
                },
                "user": {
                    "type":        "string",
                    "description": "Usuario SSH para autenticarse.",
                },
                "comando": {
                    "type":        "string",
                    "description": "Comando a ejecutar en el host remoto.",
                },
                "key_path": {
                    "type":        "string",
                    "description": "Ruta a la clave privada SSH (opcional, default: ~/.ssh/id_rsa).",
                },
                "password": {
                    "type":        "string",
                    "description": "Contraseña SSH (opcional, alternativa a key_path).",
                },
                "port": {
                    "type":        "integer",
                    "description": "Puerto SSH (default: 22).",
                },
            },
            "required": ["host", "user", "comando"],
        },
    },
    {
        "nombre":      "wake_on_lan",
        "descripcion": (
            "Enciende un equipo remoto enviando un magic packet Wake-on-LAN por broadcast. "
            "El equipo debe tener WoL habilitado en su BIOS/UEFI y en su interfaz de red. "
            "El resultado es inmediato: el packet se envía pero el equipo puede tardar "
            "unos segundos en arrancar."
        ),
        "parametros": {
            "type": "object",
            "properties": {
                "mac_address": {
                    "type":        "string",
                    "description": "Dirección MAC del equipo (formato: AA:BB:CC:DD:EE:FF).",
                },
                "broadcast": {
                    "type":        "string",
                    "description": "IP de broadcast (default: configurado en WOL_BROADCAST del .env).",
                },
            },
            "required": ["mac_address"],
        },
    },
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
