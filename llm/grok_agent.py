# =============================================================================
# llm/grok_agent.py — Adaptador para Grok (xAI)
# =============================================================================
#
# Grok usa API 100% compatible con OpenAI apuntando a https://api.x.ai/v1
# Obtené tu key gratis en: https://console.x.ai
# =============================================================================

from __future__ import annotations
import json
import time
import openai

from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico
from .tool_registry import to_openai_format
import config as cfg

_GROK_BASE_URL   = "https://api.x.ai/v1"
_MAX_REINTENTOS  = 2
_ESPERA_BASE_SEG = 5


class GrokAgente(AgenteIA):
    """Adaptador para Grok (xAI) usando la librería openai compatible."""

    def __init__(self) -> None:
        if not cfg.GROK_API_KEY:
            raise ValueError(
                "GROK_API_KEY no configurada. "
                "Obtené tu key gratis en: https://console.x.ai\n"
                "Luego agregala al .env: GROK_API_KEY=xai-..."
            )
        self._client = openai.OpenAI(
            api_key=cfg.GROK_API_KEY,
            base_url=_GROK_BASE_URL,
        )
        self._model = cfg.GROK_MODEL

    @property
    def nombre_motor(self) -> str:
        return f"Grok [{self._model}]"

    def enviar_turno(
        self,
        historial: HistorialCanonico,
        herramientas: list[dict],
    ) -> RespuestaAgente:
        tools_openai = to_openai_format(herramientas)
        messages     = historial.to_openai()

        for intento in range(_MAX_REINTENTOS + 1):
            try:
                respuesta = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools_openai,
                    tool_choice="auto",
                    temperature=0.2,
                )
                return self._parsear_respuesta(respuesta)

            except openai.RateLimitError as e:
                if intento < _MAX_REINTENTOS:
                    espera = _ESPERA_BASE_SEG * (2 ** intento)
                    print(f"\n  ⏳ Rate limit Grok — esperando {espera}s (intento {intento+1})...")
                    time.sleep(espera)
                    continue
                raise RuntimeError(f"Rate limit Grok agotado: {e}")

            except openai.AuthenticationError:
                raise RuntimeError("GROK_API_KEY inválida. Verificá en https://console.x.ai")

            except openai.APIConnectionError as e:
                raise RuntimeError(f"Error de conexión con Grok (xAI): {e}")

    def _parsear_respuesta(self, respuesta) -> RespuestaAgente:
        mensaje = respuesta.choices[0].message

        if not mensaje.tool_calls:
            return RespuestaAgente(texto=mensaje.content or "")

        tool_calls = []
        for tc in mensaje.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                args = {}
            tool_calls.append(
                ToolCallCanonico(
                    call_id=tc.id,
                    nombre=tc.function.name,
                    argumentos=args,
                )
            )

        return RespuestaAgente(texto=mensaje.content or "", tool_calls=tool_calls)
