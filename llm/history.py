# =============================================================================
# llm/history.py — Historial canónico: normaliza mensajes entre distintas APIs
# =============================================================================

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class MensajeCanónico:
    rol:       Literal["system", "user", "assistant", "tool"]
    contenido: str | list[dict]           # str para texto, list para Gemini multi-part
    # Campos para mensajes de tool call (assistant) y resultados (tool)
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str = ""
    nombre_herramienta: str = ""


class HistorialCanonico:
    """
    Almacena mensajes en formato canónico y los serializa al formato
    requerido por cada API (OpenAI, Gemini).
    """

    def __init__(self, system_prompt: str = "") -> None:
        self._mensajes: list[MensajeCanónico] = []
        if system_prompt:
            self._mensajes.append(
                MensajeCanónico(rol="system", contenido=system_prompt)
            )

    # ── Mutación ───────────────────────────────────────────────────────────────

    def agregar_usuario(self, texto: str) -> None:
        self._mensajes.append(MensajeCanónico(rol="user", contenido=texto))

    def agregar_asistente(self, texto: str, tool_calls: list[dict] | None = None) -> None:
        self._mensajes.append(
            MensajeCanónico(
                rol="assistant",
                contenido=texto,
                tool_calls=tool_calls or [],
            )
        )

    def agregar_resultado_tool(
        self,
        tool_call_id: str,
        nombre: str,
        resultado: str,
    ) -> None:
        self._mensajes.append(
            MensajeCanónico(
                rol="tool",
                contenido=resultado,
                tool_call_id=tool_call_id,
                nombre_herramienta=nombre,
            )
        )

    def limpiar(self, preservar_system: bool = True) -> None:
        """Limpia el historial, opcionalmente preservando el system prompt."""
        if preservar_system and self._mensajes and self._mensajes[0].rol == "system":
            self._mensajes = [self._mensajes[0]]
        else:
            self._mensajes = []

    def reducir(self, mantener_ultimos: int = 6) -> None:
        """
        Recorta el historial para reducir el contexto ante un error 400.
        Preserva el system prompt y los últimos N mensajes.
        Nunca deja un mensaje 'tool' sin su 'assistant' correspondiente.
        """
        tiene_system = self._mensajes and self._mensajes[0].rol == "system"
        base = [self._mensajes[0]] if tiene_system else []
        resto = self._mensajes[1:] if tiene_system else self._mensajes[:]

        # Recortar a los últimos N mensajes
        recortados = resto[-mantener_ultimos:]

        # Asegurar que no empiece con un mensaje 'tool' huérfano
        while recortados and recortados[0].rol == "tool":
            recortados = recortados[1:]

        self._mensajes = base + recortados

    # ── Serialización OpenAI ──────────────────────────────────────────────────

    def to_openai(self) -> list[dict[str, Any]]:
        """Convierte a list[dict] compatible con OpenAI / LM Studio / Grok / Ollama."""
        result = []
        for msg in self._mensajes:
            if msg.rol == "tool":
                result.append({
                    "role":         "tool",
                    "tool_call_id": msg.tool_call_id,
                    "name":         msg.nombre_herramienta,
                    "content":      msg.contenido,
                })
            elif msg.rol == "assistant" and msg.tool_calls:
                d: dict[str, Any] = {"role": "assistant", "content": msg.contenido or None}
                d["tool_calls"] = msg.tool_calls
                result.append(d)
            else:
                result.append({"role": msg.rol, "content": msg.contenido})
        return result

    # ── Serialización Gemini ──────────────────────────────────────────────────

    def to_gemini(self) -> tuple[str, list[dict]]:
        """
        Retorna (system_instruction, history) para la API de Gemini.
        history: list de dicts {"role": "user"|"model", "parts": [...]}
        """
        system_instruction = ""
        history = []

        for msg in self._mensajes:
            if msg.rol == "system":
                system_instruction = msg.contenido  # type: ignore
                continue

            role = "model" if msg.rol == "assistant" else "user"

            if msg.rol == "tool":
                # Resultado de tool → lo adjuntamos al "user" como contexto
                history.append({
                    "role": "user",
                    "parts": [{"text": f"[Tool result for {msg.nombre_herramienta}]: {msg.contenido}"}],
                })
                continue

            if isinstance(msg.contenido, str):
                history.append({"role": role, "parts": [{"text": msg.contenido}]})
            else:
                history.append({"role": role, "parts": msg.contenido})

        return system_instruction, history

    # ── Serialización Anthropic ───────────────────────────────────────────────

    def to_anthropic(self) -> tuple[str, list[dict]]:
        """
        Retorna (system_prompt, messages) para la API de Anthropic.
        """
        system_prompt = ""
        messages = []

        for msg in self._mensajes:
            if msg.rol == "system":
                system_prompt = msg.contenido  # type: ignore[arg-type]
                continue

            if msg.rol == "tool":
                messages.append({
                    "role":    "user",
                    "content": [
                        {
                            "type":        "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content":     msg.contenido,
                        }
                    ],
                })
                continue

            if msg.rol == "assistant" and msg.tool_calls:
                content: list[dict] = []
                if msg.contenido:
                    content.append({"type": "text", "text": msg.contenido})
                for tc in msg.tool_calls:
                    import json as _json
                    content.append({
                        "type":  "tool_use",
                        "id":    tc["id"],
                        "name":  tc["function"]["name"],
                        "input": _json.loads(tc["function"]["arguments"]),
                    })
                messages.append({"role": "assistant", "content": content})
                continue

            messages.append({"role": msg.rol, "content": msg.contenido})

        return system_prompt, messages

    # ── Utilidades ────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._mensajes)

    def ultimos(self, n: int) -> list[MensajeCanónico]:
        return self._mensajes[-n:]

    def exportar_markdown(self) -> str:
        """Exporta el historial como un string Markdown."""
        lines = ["# Sesión Linux Agent\n"]
        for msg in self._mensajes:
            if msg.rol == "system":
                continue
            if msg.rol == "user":
                lines.append(f"## 👤 Usuario\n{msg.contenido}\n")
            elif msg.rol == "assistant":
                lines.append(f"## 🤖 Agente\n{msg.contenido or '*(tool call)*'}\n")
            elif msg.rol == "tool":
                lines.append(f"### 🔧 Tool Result `{msg.nombre_herramienta}`\n```\n{msg.contenido}\n```\n")
        return "\n".join(lines)
