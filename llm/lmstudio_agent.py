# =============================================================================
# llm/lmstudio_agent.py — Adaptador para LM Studio
# =============================================================================

from __future__ import annotations
import time
import json
import openai
import httpx

from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico
from .tool_registry import to_openai_format
import config as cfg

_MAX_REINTENTOS   = 2
_ESPERA_BASE_SEG  = 3
_TIMEOUT_CARGA_S  = 60   # máx segundos esperando que LM Studio cargue un modelo


class LMStudioAgente(AgenteIA):
    """
    Adaptador para LM Studio.
    Usa la API compatible con OpenAI en cfg.LMSTUDIO_BASE_URL.
    Si se provee model_id, intenta cargar ese modelo vía la API nativa de LM Studio.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self._base_url  = cfg.LMSTUDIO_BASE_URL
        self._model_id  = model_id or cfg.LMSTUDIO_MODEL or None
        self._client    = openai.OpenAI(
            base_url=self._base_url,
            api_key="lm-studio",
        )

    @property
    def nombre_motor(self) -> str:
        modelo = self._model_id or "autodetectar"
        return f"LM Studio [{modelo}]"

    def inicializar(self) -> None:
        """Verifica conexión y carga el modelo si es necesario."""
        if self._model_id:
            self._cargar_modelo_si_necesario()
        else:
            # Autodetectar modelo activo
            self._model_id = self._autodetectar_modelo()

    def _autodetectar_modelo(self) -> str | None:
        """Consulta /v1/models y retorna el primer modelo disponible."""
        try:
            modelos = self._client.models.list()
            ids = [m.id for m in modelos.data]
            if ids:
                return ids[0]
        except Exception:
            pass
        return None

    def _cargar_modelo_si_necesario(self) -> None:
        """Si el modelo no está cargado, lo carga vía API nativa de LM Studio."""
        # Verificar si ya está cargado
        try:
            modelos = self._client.models.list()
            cargados = [m.id for m in modelos.data]
            if self._model_id in cargados:
                return  # Ya está cargado
        except Exception:
            return  # Si no se puede verificar, intentamos igual

        # Intentar carga vía API nativa
        base = self._base_url.rstrip("/v1").rstrip("/")
        load_url = f"{base}/api/v0/models/load"
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(load_url, json={"identifier": self._model_id})
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"LM Studio no pudo cargar el modelo '{self._model_id}' "
                        f"(HTTP {resp.status_code}). "
                        "Verificá que el modelo exista y que LM Studio >= 0.3.x esté activo."
                    )
        except httpx.ConnectError:
            raise RuntimeError(
                f"No se puede conectar a LM Studio en {self._base_url}. "
                "¿Está corriendo?"
            )

        # Polling hasta que aparezca en /v1/models
        print(f"  ⏳ Cargando modelo '{self._model_id}' en LM Studio", end="", flush=True)
        inicio = time.time()
        while time.time() - inicio < _TIMEOUT_CARGA_S:
            time.sleep(3)
            print(".", end="", flush=True)
            try:
                modelos = self._client.models.list()
                if self._model_id in [m.id for m in modelos.data]:
                    print(" ✓")
                    return
            except Exception:
                continue
        raise RuntimeError(
            f"Timeout: el modelo '{self._model_id}' no se cargó en {_TIMEOUT_CARGA_S}s."
        )

    def enviar_turno(
        self,
        historial: HistorialCanonico,
        herramientas: list[dict],
    ) -> RespuestaAgente:
        tools_openai = to_openai_format(herramientas)
        messages     = historial.to_openai()

        kwargs: dict = {
            "messages":     messages,
            "tools":        tools_openai,
            "tool_choice":  "auto",
            "temperature":  0.2,
        }
        if self._model_id:
            kwargs["model"] = self._model_id
        else:
            kwargs["model"] = "local-model"  # LM Studio ignora este valor

        ultimo_error = None
        for intento in range(_MAX_REINTENTOS + 1):
            try:
                respuesta = self._client.chat.completions.create(**kwargs)
                return self._parsear_respuesta(respuesta)

            except openai.APIConnectionError as e:
                ultimo_error = e
                if intento < _MAX_REINTENTOS:
                    time.sleep(_ESPERA_BASE_SEG)
                    continue
                raise RuntimeError(
                    f"No se puede conectar a LM Studio en {self._base_url}: {e}"
                )
            except Exception as e:
                raise RuntimeError(f"Error en LM Studio: {e}") from e

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
