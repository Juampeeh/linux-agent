# =============================================================================
# config.py — Variables de configuración del Linux Local AI Agent
# =============================================================================

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
_BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(_BASE_DIR / ".env")

# ── LM Studio ─────────────────────────────────────────────────────────────────
LMSTUDIO_BASE_URL: str   = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.0.142:1234/v1")
LMSTUDIO_MODEL: str      = os.getenv("LMSTUDIO_MODEL", "")
LMSTUDIO_EMBED_MODEL: str = os.getenv("LMSTUDIO_EMBED_MODEL", "")  # vacío = usa el modelo activo
LM_MODELS_FILE: str      = str(_BASE_DIR / "lm_models.json")

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
MEMORY_ENABLED: bool    = os.getenv("MEMORY_ENABLED", "True").lower() in ("true", "1", "yes")
MEMORY_DB_PATH: str     = str(_BASE_DIR / "memory.db")
MEMORY_TOP_K: int       = int(os.getenv("MEMORY_TOP_K", "3"))
MEMORY_THRESHOLD: float = float(os.getenv("MEMORY_THRESHOLD", "0.75"))
MEMORY_MAX_ENTRIES: int = int(os.getenv("MEMORY_MAX_ENTRIES", "2000"))

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
