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
MAX_OUTPUT_CHARS: int      = int(os.getenv("MAX_OUTPUT_CHARS", "4000"))

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

# ── Heimdall (fase 2 — deshabilitado por defecto) ─────────────────────────────
HEIMDALL_ENABLED: bool        = os.getenv("HEIMDALL_ENABLED", "False").lower() in ("true", "1", "yes")
HEIMDALL_HOST: str            = os.getenv("HEIMDALL_HOST", "")
HEIMDALL_USER: str            = os.getenv("HEIMDALL_USER", "")
HEIMDALL_SSH_KEY: str         = os.getenv("HEIMDALL_SSH_KEY", str(Path.home() / ".ssh" / "id_rsa"))
HEIMDALL_LOG_PATHS: list[str] = [
    p.strip() for p in os.getenv(
        "HEIMDALL_LOG_PATHS",
        "/var/log/nginx/access.log,/var/log/suricata/eve.json,/var/log/pihole/pihole.log"
    ).split(",") if p.strip()
]

# ── Búsqueda web ──────────────────────────────────────────────────────────────
WEB_SEARCH_ENABLED: bool    = os.getenv("WEB_SEARCH_ENABLED", "True").lower() in ("true", "1", "yes")
WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

# ── Herramientas remotas ──────────────────────────────────────────────────────
WOL_BROADCAST: str       = os.getenv("WOL_BROADCAST", "192.168.0.255")
SSH_DEFAULT_TIMEOUT: int = int(os.getenv("SSH_DEFAULT_TIMEOUT", "30"))

# ── Agentic Loop ──────────────────────────────────────────────────────────────
AGENTIC_MAX_RETRIES: int      = int(os.getenv("AGENTIC_MAX_RETRIES", "5"))
AGENTIC_USE_WEB_ON_FAIL: bool = os.getenv("AGENTIC_USE_WEB_ON_FAIL", "True").lower() in ("true", "1", "yes")
AGENTIC_MAX_ITERATIONS: int   = int(os.getenv("AGENTIC_MAX_ITERATIONS", "20"))

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
