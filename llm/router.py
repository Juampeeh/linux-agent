# =============================================================================
# llm/router.py — Factory de agentes + lógica de motores disponibles
# =============================================================================

from __future__ import annotations
import config as cfg
from .base import AgenteIA


def motores_disponibles() -> dict[str, dict]:
    """
    Retorna solo los motores que tienen su API key configurada (o no la necesitan).
    El motor 'local' (LM Studio) y 'ollama' siempre están disponibles.
    """
    disponibles: dict[str, dict] = {}
    for clave, meta in cfg.MOTORES_DISPONIBLES.items():
        if not meta["requiere_key"]:
            disponibles[clave] = meta
        elif clave == "gemini" and cfg.GEMINI_API_KEY:
            disponibles[clave] = meta
        elif clave == "chatgpt" and cfg.OPENAI_API_KEY:
            disponibles[clave] = meta
        elif clave == "grok" and cfg.GROK_API_KEY:
            disponibles[clave] = meta
        elif clave == "claude" and cfg.ANTHROPIC_API_KEY:
            disponibles[clave] = meta
    return disponibles


def crear_agente(motor: str, model_id: str | None = None) -> AgenteIA:
    """
    Factory: instancia y retorna el adaptador correcto según el motor.

    Parámetros
    ----------
    motor    : "local" | "ollama" | "gemini" | "chatgpt" | "grok" | "claude"
    model_id : Solo para motor="local". Modelo específico a usar/cargar.
               Si es None, se usa autodetección o LMSTUDIO_MODEL del .env.

    Lanza ValueError si el motor no está soportado o no tiene key.
    """
    # Importaciones diferidas para no fallar en import si faltan libs opcionales
    motor = motor.strip().lower()

    if motor == "local":
        from .lmstudio_agent import LMStudioAgente
        return LMStudioAgente(model_id=model_id)

    elif motor == "ollama":
        from .ollama_agent import OllamaAgente
        return OllamaAgente()

    elif motor == "gemini":
        if not cfg.GEMINI_API_KEY:
            raise ValueError(
                "Motor 'gemini' no disponible: GEMINI_API_KEY no está configurada en .env\n"
                "  → Obtené tu key en: https://aistudio.google.com/apikey"
            )
        from .gemini_agent import GeminiAgente
        return GeminiAgente()

    elif motor == "chatgpt":
        if not cfg.OPENAI_API_KEY:
            raise ValueError(
                "Motor 'chatgpt' no disponible: OPENAI_API_KEY no está configurada en .env\n"
                "  → Obtené tu key en: https://platform.openai.com/api-keys"
            )
        from .openai_agent import OpenAIAgente
        return OpenAIAgente()

    elif motor == "grok":
        if not cfg.GROK_API_KEY:
            raise ValueError(
                "Motor 'grok' no disponible: GROK_API_KEY no está configurada en .env\n"
                "  → Obtené tu key gratis en: https://console.x.ai"
            )
        from .grok_agent import GrokAgente
        return GrokAgente()

    elif motor == "claude":
        if not cfg.ANTHROPIC_API_KEY:
            raise ValueError(
                "Motor 'claude' no disponible: ANTHROPIC_API_KEY no está configurada en .env\n"
                "  → Obtené tu key en: https://console.anthropic.com"
            )
        from .anthropic_agent import AnthropicAgente
        return AnthropicAgente()

    else:
        disponibles = list(motores_disponibles().keys())
        raise ValueError(
            f"Motor '{motor}' no reconocido.\n"
            f"Motores disponibles: {disponibles}"
        )


def intentar_fallback_local() -> "AgenteIA | None":
    """
    Intenta crear un agente LM Studio como fallback de emergencia.
    Retorna None si tampoco está disponible.
    """
    try:
        from .lmstudio_agent import LMStudioAgente
        agente = LMStudioAgente()
        agente.inicializar()
        return agente
    except Exception:
        return None
