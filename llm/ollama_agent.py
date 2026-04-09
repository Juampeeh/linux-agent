# =============================================================================
# llm/ollama_agent.py — Adaptador para Ollama
# =============================================================================
#
# Ollama expone una API OpenAI-compatible en http://localhost:11434/v1
# No requiere API key. Soporta tool calling en modelos compatibles.
# =============================================================================

from __future__ import annotations
import json
import openai

from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico
from .tool_registry import to_openai_format
import config as cfg


class OllamaAgente(AgenteIA):
    """
    Adaptador para Ollama usando su API OpenAI-compatible.
    No requiere API key; apunta a cfg.OLLAMA_BASE_URL (default: localhost:11434).
    """

    def __init__(self) -> None:
        self._base_url = cfg.OLLAMA_BASE_URL
        self._model    = cfg.OLLAMA_MODEL
        self._client   = openai.OpenAI(
            base_url=self._base_url,
            api_key="ollama",
        )

    @property
    def nombre_motor(self) -> str:
        return f"Ollama [{self._model}]"

    def inicializar(self) -> None:
        """Verifica que Ollama esté corriendo."""
        try:
            self._client.models.list()
        except Exception as e:
            raise RuntimeError(
                f"No se puede conectar a Ollama en {self._base_url}.\n"
                f"¿Está corriendo? Iniciá con: ollama serve\n"
                f"Error: {e}"
            )

    def enviar_turno(
        self,
        historial: HistorialCanonico,
        herramientas: list[dict],
    ) -> RespuestaAgente:
        tools_openai = to_openai_format(herramientas)
        messages     = historial.to_openai()

        try:
            respuesta = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools_openai,
                tool_choice="auto",
                temperature=0.2,
            )
            return self._parsear_respuesta(respuesta)

        except openai.APIConnectionError as e:
            raise RuntimeError(
                f"No se puede conectar a Ollama en {self._base_url}: {e}\n"
                "Iniciá Ollama con: ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Error en Ollama: {e}") from e

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

        return RespuestaAgente(
            texto=mensaje.content or "",
            tool_calls=tool_calls,
        )
