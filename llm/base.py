# =============================================================================
# llm/base.py — Clases base del sistema de agentes IA
# =============================================================================

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallCanonico:
    """Representa una llamada a herramienta en formato canónico."""
    call_id: str
    nombre:  str
    argumentos: dict[str, Any] = field(default_factory=dict)


@dataclass
class RespuestaAgente:
    """Respuesta normalizada del agente (texto libre + tool calls opcionales)."""
    texto:      str = ""
    tool_calls: list[ToolCallCanonico] = field(default_factory=list)

    @property
    def tiene_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class AgenteIA(ABC):
    """Interfaz base para todos los adaptadores de motor IA."""

    @property
    @abstractmethod
    def nombre_motor(self) -> str:
        """Nombre legible del motor, ej: 'LM Studio [llama3]'"""

    @abstractmethod
    def enviar_turno(
        self,
        historial: "HistorialCanonico",  # type: ignore[name-defined]
        herramientas: list[dict],
    ) -> RespuestaAgente:
        """Envía el historial al LLM y retorna la respuesta canónica."""

    def inicializar(self) -> None:
        """Hook opcional de inicialización (ping, carga de modelo, etc.)."""
