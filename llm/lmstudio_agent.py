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
_TIMEOUT_CARGA_S  = 180  # máx segundos esperando que LM Studio cargue un modelo
_TIMEOUT_INFER_S  = 120  # timeout para cada llamada de inferencia (modelos grandes son lentos)


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
            timeout=_TIMEOUT_INFER_S,
        )

    @property
    def nombre_motor(self) -> str:
        modelo = self._model_id or "autodetectar"
        return f"LM Studio [{modelo}]"

    def inicializar(self) -> None:
        """Verifica conexión y carga el modelo si es necesario."""
        if self._model_id:
            # Intentar carga, pero nunca fallar: LM Studio carga el modelo
            # automáticamente en el primer request de inferencia.
            try:
                self._cargar_modelo_si_necesario()
            except RuntimeError as e:
                print(f"\n  ⚠ Aviso de carga: {e}")
                print("  → Continuando igual: LM Studio cargará el modelo al primer mensaje.")
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
        """
        Si el modelo no está en la lista de modelos activos, intenta cargarlo
        vía la API nativa de LM Studio (>= 0.3.x).

        Si la carga tarda más de _TIMEOUT_CARGA_S o la API no está disponible,
        lanza RuntimeError (controlado en inicializar() para ser no-fatal).
        El modelo se cargará igualmente en el primer request de inferencia.
        """
        # ── Verificar si ya está cargado ──────────────────────────────────────
        try:
            modelos = self._client.models.list()
            cargados = [m.id for m in modelos.data]
            if self._model_id in cargados:
                return  # Ya está activo
        except Exception:
            pass  # No se puede verificar; continuar de todos modos

        # ── Intentar carga vía API nativa de LM Studio ────────────────────────
        base = self._base_url.rstrip("/").removesuffix("/v1").rstrip("/")
        load_url = f"{base}/api/v0/models/load"
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(load_url, json={"identifier": self._model_id})
                if resp.status_code >= 400:
                    # API nativa no disponible o modelo no existe — no fatal
                    raise RuntimeError(
                        f"API de carga respondió HTTP {resp.status_code} para '{self._model_id}'. "
                        "LM Studio cargará el modelo en el primer mensaje."
                    )
        except httpx.ConnectError:
            raise RuntimeError(
                f"No se puede conectar a LM Studio en {self._base_url}. "
                "¿Está corriendo y accesible en la red?"
            )

        # ── Polling: esperar hasta que aparezca en /v1/models ─────────────────
        print(f"  ⏳ Esperando que LM Studio cargue '{self._model_id}'", end="", flush=True)
        inicio = time.time()
        while time.time() - inicio < _TIMEOUT_CARGA_S:
            time.sleep(4)
            print(".", end="", flush=True)
            try:
                modelos = self._client.models.list()
                if self._model_id in [m.id for m in modelos.data]:
                    print(" ✓")
                    return
            except Exception:
                continue

        raise RuntimeError(
            f"El modelo '{self._model_id}' no apareció disponible en {_TIMEOUT_CARGA_S}s. "
            "LM Studio lo cargará al primer mensaje de inferencia."
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
