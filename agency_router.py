# =============================================================================
# agency_router.py — Router Dinámico de Personalidades (Agency-Agents)
# Linux Local AI Agent v3.1
#
# Lee archivos .md del directorio 'agency_prompts/' y los inyecta como
# system_prompt enriquecido según el tipo de tarea detectada.
#
# Uso:
#   from agency_router import obtener_personalidad, AGENTES_DISPONIBLES
#   prompt = obtener_personalidad("hay un error en los logs del sistema")
# =============================================================================

from __future__ import annotations

import re
from pathlib import Path

# ── Directorio de prompts de Agency-Agents ────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent / "agency_prompts"

# ── Mapa de agentes disponibles ───────────────────────────────────────────────
# Formato: { "clave": { "archivo": "...", "nombre": "...", "descripcion": "..." } }
AGENTES_DISPONIBLES: dict[str, dict] = {
    "sre": {
        "archivo": "engineering-sre.md",
        "nombre":  "🛡️  SRE (Site Reliability Engineer)",
        "descripcion": "Incidentes, SLOs, error budgets, observabilidad, latencia",
    },
    "devops": {
        "archivo": "engineering-devops-automator.md",
        "nombre":  "⚙️  DevOps Automator",
        "descripcion": "CI/CD, Docker, automatización de infraestructura, despliegues",
    },
    "security": {
        "archivo": "engineering-security-engineer.md",
        "nombre":  "🔒 Security Engineer",
        "descripcion": "Firewall, permisos, auditoría, vulnerabilidades, hardening",
    },
    "incident": {
        "archivo": "engineering-incident-response-commander.md",
        "nombre":  "🚨 Incident Response Commander",
        "descripcion": "Incidentes críticos en producción, post-mortems, coordinación",
    },
    "infra": {
        "archivo": "support-infrastructure-maintainer.md",
        "nombre":  "🏢 Infrastructure Maintainer",
        "descripcion": "Mantenimiento general del sistema, backups, monitoreo, uptime",
    },
}

# ── Reglas de routing por palabras clave ─────────────────────────────────────
# Orden: más específico primero. El primer match gana.
_ROUTING_RULES: list[tuple[str, re.Pattern]] = [
    # Incidentes críticos (antes que SRE para mayor especificidad)
    ("incident", re.compile(
        r'\b(caída|caido|caido|down|outage|producción|crit|sev[12]|'
        r'emergencia|urgente|post[\-\s]?mortem|todos los usuarios|impacto total)\b',
        re.IGNORECASE
    )),
    # Seguridad
    ("security", re.compile(
        r'\b(seguridad|security|firewall|ufw|iptables|ssh[\s\-]?key|'
        r'permiso|chmod|chown|sudo|vulnerabilidad|exploit|audit|fail2ban|'
        r'malware|brute.?force|intrusion|selinux|apparmor|cve|patch|parche)\b',
        re.IGNORECASE
    )),
    # SRE (rendimiento, observabilidad, latencia)
    ("sre", re.compile(
        r'\b(latencia|latency|lento|lenta|lentitud|timeout|error rate|'
        r'slo|sla|error budget|observabilidad|métrica|metric|tracing|'
        r'uptime|downtime|disponibilidad|alto|memoria ram|cpu alto|'
        r'cuellos?.?de.?botella|bottleneck|p99|p95|throughput)\b',
        re.IGNORECASE
    )),
    # DevOps / Automatización
    ("devops", re.compile(
        r'\b(docker|container|kubernetes|k8s|ci/?cd|pipeline|deploy|'
        r'despliegue|ansible|terraform|github.?action|jenkins|cron|'
        r'automati|script|automatiza|daemon|servicio|systemd|service)\b',
        re.IGNORECASE
    )),
    # Infraestructura / Mantenimiento general
    ("infra", re.compile(
        r'\b(disco|disk|espacio|space|storage|backup|respaldo|monitoreo|'
        r'monitoring|log|journal|health|salud|actuali|update|upgrade|'
        r'manteni|rendimiento|performance|servidor|server|vm|virtual)\b',
        re.IGNORECASE
    )),
]


def detectar_agente(texto: str) -> str | None:
    """
    Analiza el texto y retorna la clave del agente más apropiado.
    Retorna None si no se detecta ningún match.
    """
    for clave, patron in _ROUTING_RULES:
        if patron.search(texto):
            return clave
    return None


def cargar_prompt_agente(clave: str) -> str | None:
    """
    Lee el archivo .md del agente indicado por su clave.
    Retorna el contenido del prompt o None si no existe.
    """
    agente = AGENTES_DISPONIBLES.get(clave)
    if not agente:
        return None
    ruta = _PROMPTS_DIR / agente["archivo"]
    try:
        return ruta.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def obtener_personalidad(texto: str, forzar_agente: str | None = None) -> tuple[str | None, str | None]:
    """
    Detecta el agente apropiado y carga su prompt.

    Args:
        texto: El mensaje o tarea del usuario.
        forzar_agente: Si se especifica, usa ese agente ignorando la detección automática.

    Returns:
        (clave_agente, prompt_md) — ambos None si no hay match o no se encontró el archivo.
    """
    clave = forzar_agente or detectar_agente(texto)
    if not clave:
        return None, None
    prompt = cargar_prompt_agente(clave)
    return clave, prompt


def listar_agentes() -> str:
    """Retorna una descripción de todos los agentes disponibles para mostrar al usuario."""
    lineas = ["**Agentes especializados disponibles (Agency-Agents):**\n"]
    for clave, meta in AGENTES_DISPONIBLES.items():
        lineas.append(f"- `{clave}` — {meta['nombre']}\n  _{meta['descripcion']}_")
    lineas.append("\nUso: `/agente <clave>` o simplemente describí tu problema y el sistema lo seleccionará automáticamente.")
    return "\n".join(lineas)
