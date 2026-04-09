# =============================================================================
# llm/gemini_agent.py — Adaptador para Google Gemini
# =============================================================================

from __future__ import annotations
import json
from google import genai
from google.genai import types

from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico
from .tool_registry import to_gemini_format
import config as cfg


class GeminiAgente(AgenteIA):
    """Adaptador para Google Gemini usando el SDK google-genai."""

    def __init__(self) -> None:
        if not cfg.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY no configurada. "
                "Obtené tu key en: https://aistudio.google.com/apikey"
            )
        self._client = genai.Client(api_key=cfg.GEMINI_API_KEY)
        self._model  = cfg.GEMINI_MODEL

    @property
    def nombre_motor(self) -> str:
        return f"Google Gemini [{self._model}]"

    def enviar_turno(
        self,
        historial: HistorialCanonico,
        herramientas: list[dict],
    ) -> RespuestaAgente:
        system_instruction, history = historial.to_gemini()

        # Convertir herramientas a formato Gemini
        tool_defs = to_gemini_format(herramientas)
        gemini_tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(**t) for t in tool_defs
                ]
            )
        ]

        # Separar el último mensaje del historial (el que enviamos ahora)
        contents = history  # Gemini acepta el historial completo

        try:
            respuesta = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction or None,
                    tools=gemini_tools,
                    temperature=0.2,
                ),
            )
            return self._parsear_respuesta(respuesta)

        except Exception as e:
            raise RuntimeError(f"Error en Google Gemini: {e}") from e

    def _parsear_respuesta(self, respuesta) -> RespuestaAgente:
        texto = ""
        tool_calls = []

        for part in respuesta.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                texto += part.text
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append(
                    ToolCallCanonico(
                        call_id=fc.name,  # Gemini no tiene un ID numérico; usamos el nombre
                        nombre=fc.name,
                        argumentos=dict(fc.args) if fc.args else {},
                    )
                )

        return RespuestaAgente(texto=texto, tool_calls=tool_calls)
