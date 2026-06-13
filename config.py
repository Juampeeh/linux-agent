# =============================================================================
# config.py — Variables de configuración del Linux Local AI Agent v2.0
# =============================================================================

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
_BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(_BASE_DIR / ".env")

# ── LM Studio ─────────────────────────────────────────────────────────────────
LMSTUDIO_BASE_URL: str    = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.0.142:1234/v1")
LMSTUDIO_MODEL: str       = os.getenv("LMSTUDIO_MODEL", "")
LMSTUDIO_EMBED_MODEL: str = os.getenv("LMSTUDIO_EMBED_MODEL", "")  # vacío = usa el modelo activo
LM_MODELS_FILE: str       = str(_BASE_DIR / "lm_models.json")

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL: str       = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "")  # vacío = usa OLLAMA_MODEL

# ── Google Gemini ─────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── OpenAI ChatGPT ────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Grok (xAI) ────────────────────────────────────────────────────────────────
GROK_API_KEY: str = os.getenv("GROK_API_KEY", "")
GROK_MODEL: str   = os.getenv("GROK_MODEL", "grok-3-mini")

# ── Anthropic Claude ──────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str   = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

# ── Comportamiento del agente ─────────────────────────────────────────────────
REQUIRE_CONFIRMATION: bool = os.getenv("REQUIRE_CONFIRMATION", "True").lower() in ("true", "1", "yes")
COMMAND_TIMEOUT: int       = int(os.getenv("COMMAND_TIMEOUT", "60"))
DEFAULT_ENGINE: str        = os.getenv("DEFAULT_ENGINE", "local")
MAX_OUTPUT_CHARS: int      = int(os.getenv("MAX_OUTPUT_CHARS", "15000"))

# ── Memoria semántica ─────────────────────────────────────────────────────────
MEMORY_ENABLED: bool              = os.getenv("MEMORY_ENABLED", "True").lower() in ("true", "1", "yes")
MEMORY_DB_PATH: str               = str(_BASE_DIR / "memory.db")
MEMORY_TOP_K: int                 = int(os.getenv("MEMORY_TOP_K", "3"))
MEMORY_THRESHOLD: float           = float(os.getenv("MEMORY_THRESHOLD", "0.75"))
MEMORY_MAX_ENTRIES: int           = int(os.getenv("MEMORY_MAX_ENTRIES", "2000"))
# MEMORY_SHARED_EMBED=True obliga a TODOS los motores a usar LM Studio para embeddings.
MEMORY_SHARED_EMBED: bool         = os.getenv("MEMORY_SHARED_EMBED", "False").lower() in ("true", "1", "yes")
# Similitud mínima para considerar un par como duplicado y evitar guardarlo
MEMORY_DEDUP_THRESHOLD: float     = float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.90"))
# TTL en horas para entradas de tipo "log_crudo" — se auto-eliminan tras este tiempo
MEMORY_LOG_TTL_HOURS: int         = int(os.getenv("MEMORY_LOG_TTL_HOURS", "24"))
# Si True, el LLM activo consolida el episodio completo al terminar una tarea /task
MEMORY_CONSOLIDATE_ON_TASK: bool  = os.getenv("MEMORY_CONSOLIDATE_ON_TASK", "True").lower() in ("true", "1", "yes")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_ENABLED: bool  = os.getenv("TELEGRAM_ENABLED", "False").lower() in ("true", "1", "yes")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Lista de chat_ids permitidos (separados por coma). Vacío = cualquiera (NO recomendado)
_raw_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "")
TELEGRAM_ALLOWED_IDS: list[int] = [
    int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()
]

# ── Centinela ─────────────────────────────────────────────────────────────────
SENTINEL_ENABLED: bool          = os.getenv("SENTINEL_ENABLED", "False").lower() in ("true", "1", "yes")
SENTINEL_INTERVAL_SECONDS: int  = int(os.getenv("SENTINEL_INTERVAL_SECONDS", "300"))
SENTINEL_LOG_TAIL_LINES: int    = int(os.getenv("SENTINEL_LOG_TAIL_LINES", "100"))
SENTINEL_ANOMALY_THRESHOLD: int = int(os.getenv("SENTINEL_ANOMALY_THRESHOLD", "3"))
# URL del LLM que usa el centinela (por defecto LM Studio — no requiere API key)
SENTINEL_LLM_URL: str           = os.getenv("SENTINEL_LLM_URL", LMSTUDIO_BASE_URL)
SENTINEL_LLM_MODEL: str         = os.getenv("SENTINEL_LLM_MODEL", "")  # vacío = autodetectar

# ── Hosts remotos del Centinela (multi-host) ──────────────────────────────────
# Cada host se define con SENTINEL_HOST_N_* donde N es un número (1, 2, 3...)
# Variables por host:
#   SENTINEL_HOST_N_NAME     — nombre identificador (ej: heimdall, vm-pihole)
#   SENTINEL_HOST_N_IP       — dirección IP
#   SENTINEL_HOST_N_USER     — usuario SSH
#   SENTINEL_HOST_N_PASS     — contraseña SSH (vacío = usar key)
#   SENTINEL_HOST_N_SSH_KEY  — ruta a clave SSH (default: ~/.ssh/id_rsa)
#   SENTINEL_HOST_N_SERVICES — servicios a monitorear separados por coma
#   SENTINEL_HOST_N_LOG_PATHS— rutas de logs separadas por coma
#   SENTINEL_HOST_N_EXTRA_CHECKS — checks extra: zpool_status, pihole_status
#   SENTINEL_HOST_N_AUTO_REPAIR  — True/False: reiniciar servicios caídos

from dataclasses import dataclass, field

@dataclass
class SentinelHostConfig:
    """Configuración de un host remoto para el centinela."""
    name: str
    ip: str
    user: str
    password: str = ""
    ssh_key: str = ""
    services: list[str] = field(default_factory=list)
    log_paths: list[str] = field(default_factory=list)
    extra_checks: list[str] = field(default_factory=list)
    auto_repair: bool = True


def _parse_sentinel_hosts() -> list[SentinelHostConfig]:
    """Parsea hosts remotos del centinela desde variables de entorno."""
    hosts = []
    for n in range(1, 11):  # Hasta 10 hosts
        prefix = f"SENTINEL_HOST_{n}_"
        name = os.getenv(f"{prefix}NAME", "")
        ip = os.getenv(f"{prefix}IP", "")
        if not name or not ip:
            continue  # No hay más hosts definidos
        hosts.append(SentinelHostConfig(
            name=name,
            ip=ip,
            user=os.getenv(f"{prefix}USER", ""),
            password=os.getenv(f"{prefix}PASS", ""),
            ssh_key=os.getenv(f"{prefix}SSH_KEY", str(Path.home() / ".ssh" / "id_rsa")),
            services=[s.strip() for s in os.getenv(f"{prefix}SERVICES", "").split(",") if s.strip()],
            log_paths=[p.strip() for p in os.getenv(f"{prefix}LOG_PATHS", "").split(",") if p.strip()],
            extra_checks=[c.strip() for c in os.getenv(f"{prefix}EXTRA_CHECKS", "").split(",") if c.strip()],
            auto_repair=os.getenv(f"{prefix}AUTO_REPAIR", "True").lower() in ("true", "1", "yes"),
        ))

    # ── Retrocompatibilidad con HEIMDALL_* legacy ─────────────────────────
    if not any(h.name == "heimdall" for h in hosts):
        legacy_enabled = os.getenv("HEIMDALL_ENABLED", "False").lower() in ("true", "1", "yes")
        legacy_host = os.getenv("HEIMDALL_HOST", "")
        if legacy_enabled and legacy_host:
            hosts.append(SentinelHostConfig(
                name="heimdall",
                ip=legacy_host,
                user=os.getenv("HEIMDALL_USER", ""),
                ssh_key=os.getenv("HEIMDALL_SSH_KEY", str(Path.home() / ".ssh" / "id_rsa")),
                log_paths=[p.strip() for p in os.getenv(
                    "HEIMDALL_LOG_PATHS",
                    "/var/log/nginx/access.log,/var/log/suricata/eve.json,/var/log/pihole/pihole.log"
                ).split(",") if p.strip()],
            ))

    return hosts


SENTINEL_HOSTS: list[SentinelHostConfig] = _parse_sentinel_hosts()

# ── Web UI (v3.0) ─────────────────────────────────────────────────────────────
WEB_ENABLED: bool      = os.getenv("WEB_ENABLED", "False").lower() in ("true", "1", "yes")
WEB_PORT: int          = int(os.getenv("WEB_PORT", "7860"))
WEB_HOST: str          = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PASSWORD: str      = os.getenv("WEB_PASSWORD", "")        # vacío = sin autenticación
WEB_OPEN_BROWSER: bool = os.getenv("WEB_OPEN_BROWSER", "True").lower() in ("true", "1", "yes")

# ── Búsqueda web ──────────────────────────────────────────────────────────────
WEB_SEARCH_ENABLED: bool    = os.getenv("WEB_SEARCH_ENABLED", "True").lower() in ("true", "1", "yes")
WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

# ── Herramientas remotas ──────────────────────────────────────────────────────
WOL_BROADCAST: str       = os.getenv("WOL_BROADCAST", "192.168.0.255")
SSH_DEFAULT_TIMEOUT: int = int(os.getenv("SSH_DEFAULT_TIMEOUT", "30"))

# ── Agentic Loop ──────────────────────────────────────────────────────────────
AGENTIC_MAX_RETRIES: int      = int(os.getenv("AGENTIC_MAX_RETRIES", "5"))
AGENTIC_USE_WEB_ON_FAIL: bool = os.getenv("AGENTIC_USE_WEB_ON_FAIL", "True").lower() in ("true", "1", "yes")
AGENTIC_MAX_ITERATIONS: int   = int(os.getenv("AGENTIC_MAX_ITERATIONS", "30"))

# ── Registro de motores disponibles ──────────────────────────────────────────
MOTORES_DISPONIBLES: dict[str, dict] = {
    "local": {
        "nombre":       "LM Studio (Local/Red)",
        "descripcion":  f"API OpenAI-compatible · endpoint: {LMSTUDIO_BASE_URL}",
        "requiere_key": False,
    },
    "ollama": {
        "nombre":       "Ollama (Local)",
        "descripcion":  f"Modelos locales via Ollama · {OLLAMA_BASE_URL}",
        "requiere_key": False,
    },
    "gemini": {
        "nombre":       "Google Gemini",
        "descripcion":  f"Gemini API Cloud · modelo: {GEMINI_MODEL}",
        "requiere_key": True,
    },
    "chatgpt": {
        "nombre":       "OpenAI ChatGPT",
        "descripcion":  f"OpenAI API · modelo: {OPENAI_MODEL}",
        "requiere_key": True,
    },
    "grok": {
        "nombre":       "Grok (xAI)",
        "descripcion":  f"xAI API · modelo: {GROK_MODEL}",
        "requiere_key": True,
    },
    "claude": {
        "nombre":       "Anthropic Claude",
        "descripcion":  f"Anthropic API · modelo: {ANTHROPIC_MODEL}",
        "requiere_key": True,
    },
}
