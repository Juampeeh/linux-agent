# =============================================================================
# llm/anthropic_agent.py — Adaptador para Anthropic Claude
# =============================================================================

from __future__ import annotations
import json
import anthropic

from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico
from .tool_registry import to_anthropic_format
import config as cfg


class AnthropicAgente(AgenteIA):
    """Adaptador para Anthropic Claude usando el SDK oficial."""

    def __init__(self) -> None:
        if not cfg.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY no configurada. "
                "Obtené tu key en: https://console.anthropic.com"
            )
        self._client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        self._model  = cfg.ANTHROPIC_MODEL

    @property
    def nombre_motor(self) -> str:
        return f"Anthropic Claude [{self._model}]"

    def enviar_turno(
        self,
        historial: HistorialCanonico,
        herramientas: list[dict],
    ) -> RespuestaAgente:
        system_prompt, messages = historial.to_anthropic()
        tools_anthropic = to_anthropic_format(herramientas)

        try:
            respuesta = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools_anthropic,
            )
            return self._parsear_respuesta(respuesta)

        except anthropic.AuthenticationError:
            raise RuntimeError("ANTHROPIC_API_KEY inválida. Verificá en https://console.anthropic.com")

        except anthropic.RateLimitError as e:
            raise RuntimeError(f"Rate limit de Anthropic: {e}")

        except Exception as e:
            raise RuntimeError(f"Error en Anthropic Claude: {e}") from e

    def _parsear_respuesta(self, respuesta) -> RespuestaAgente:
        texto      = ""
        tool_calls = []

        for block in respuesta.content:
            if block.type == "text":
                texto += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallCanonico(
                        call_id=block.id,
                        nombre=block.name,
                        argumentos=block.input or {},
                    )
                )

        return RespuestaAgente(texto=texto, tool_calls=tool_calls)
