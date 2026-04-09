# =============================================================================
# llm/openai_agent.py — Adaptador para OpenAI ChatGPT
# =============================================================================

from __future__ import annotations
import json
import time
import openai

from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico
from .tool_registry import to_openai_format
import config as cfg

_MAX_REINTENTOS  = 2
_ESPERA_BASE_SEG = 5


class OpenAIAgente(AgenteIA):
    """Adaptador para la API oficial de OpenAI (ChatGPT)."""

    def __init__(self) -> None:
        if not cfg.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY no configurada. "
                "Obtené tu key en: https://platform.openai.com/api-keys"
            )
        self._client  = openai.OpenAI(api_key=cfg.OPENAI_API_KEY)
        self._model   = cfg.OPENAI_MODEL

    @property
    def nombre_motor(self) -> str:
        return f"OpenAI ChatGPT [{self._model}]"

    def enviar_turno(
        self,
        historial: HistorialCanonico,
        herramientas: list[dict],
    ) -> RespuestaAgente:
        tools_openai = to_openai_format(herramientas)
        messages     = historial.to_openai()

        ultimo_error = None
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
                ultimo_error = e
                if intento < _MAX_REINTENTOS:
                    espera = _ESPERA_BASE_SEG * (2 ** intento)
                    print(f"\n  ⏳ Rate limit OpenAI — esperando {espera}s...")
                    time.sleep(espera)
                    continue
                raise RuntimeError(f"Rate limit agotado: {e}")

            except openai.AuthenticationError:
                raise RuntimeError("OPENAI_API_KEY inválida.")

            except openai.APIConnectionError as e:
                raise RuntimeError(f"Error de conexión con OpenAI: {e}")

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
