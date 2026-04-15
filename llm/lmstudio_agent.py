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

_MAX_REINTENTOS    = 2    # reintentos por error de conexión
_ESPERA_BASE_SEG   = 3    # segundos entre reintentos de conexión
_REINTENTOS_CARGA  = 4    # reintentos cuando LM Studio aún está cargando el modelo
_ESPERA_CARGA_S    = 15   # segundos entre reintentos de carga (LM Studio tarda en levantar)
_TIMEOUT_INFER_S   = 120  # timeout para cada llamada de inferencia (modelos grandes son lentos)

# Patrones que identifican modelos de embeddings (no válidos para inferencia de chat)
_EMBEDDING_KEYWORDS = ("embed", "embedding", "nomic", "reranker", "bge-", "e5-")


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
        """Verifica conexión. Si no hay model_id definido, autodetecta el activo."""
        if not self._model_id:
            self._model_id = self._autodetectar_modelo()
        # NO disparamos carga: /api/v0/models/load no funciona en LM Studio moderno.
        # El modelo se cargará en el primer request de inferencia si está seleccionado
        # en la UI de LM Studio, o se usará el que haya activo (ver enviar_turno).

    def _autodetectar_modelo(self) -> str | None:
        """
        Consulta /v1/models y retorna el primer modelo de chat disponible.
        Excluye modelos de embeddings que no sirven para inferencia.
        """
        try:
            modelos = self._client.models.list()
            ids = [m.id for m in modelos.data]
            # Preferir modelos que NO sean de embeddings
            ids_chat = [
                mid for mid in ids
                if not any(kw in mid.lower() for kw in _EMBEDDING_KEYWORDS)
            ]
            if ids_chat:
                return ids_chat[0]
            if ids:  # Fallback: usar el primero aunque sea (sin filtro)
                return ids[0]
        except Exception:
            pass
        return None

    def _cargar_modelo_si_necesario(self) -> None:
        """
        Dispara la carga del modelo vía API nativa de LM Studio (fire-and-forget).
        NO verifica el catálogo de modelos: /v1/models lista TODOS los modelos
        disponibles, no sólo los activos, así que no es indicador confiable de carga.
        Si la API de carga no existe o falla, LM Studio lo cargará en el primer
        request de inferencia (con un breve delay que se maneja en enviar_turno).
        """
        base = self._base_url.rstrip("/").removesuffix("/v1").rstrip("/")
        load_url = f"{base}/api/v0/models/load"
        try:
            with httpx.Client(timeout=10) as client:
                client.post(load_url, json={"identifier": self._model_id})
        except Exception:
            pass  # Silencioso — el error 'No models loaded' se maneja en enviar_turno()

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
        carga_avisada = False
        total_reintentos = _MAX_REINTENTOS + _REINTENTOS_CARGA + 1
        for intento in range(total_reintentos):
            try:
                respuesta = self._client.chat.completions.create(**kwargs)
                # ✔ Éxito — si LM Studio usó un modelo distinto al solicitado, sincronizar
                modelo_real = getattr(respuesta, "model", None)
                if modelo_real and modelo_real != kwargs.get("model"):
                    self._model_id = modelo_real
                    kwargs["model"] = modelo_real
                return self._parsear_respuesta(respuesta)

            except openai.APIConnectionError as e:
                ultimo_error = e
                if intento < _MAX_REINTENTOS:
                    time.sleep(_ESPERA_BASE_SEG)
                    continue
                raise RuntimeError(
                    f"No se puede conectar a LM Studio en {self._base_url}: {e}"
                )

            except openai.BadRequestError as e:
                # LM Studio no tiene el modelo solicitado cargado.
                # Estrategia: esperar que cargue; a partir del 2do intento también
                # probar con el modelo que LM Studio tenga activo en ese momento.
                if "No models loaded" in str(e) and intento < _REINTENTOS_CARGA:
                    if not carga_avisada:
                        print(
                            f"\n  ⏳ LM Studio no tiene '{self._model_id}' cargado — "
                            f"esperando {_ESPERA_CARGA_S}s...",
                            flush=True,
                        )
                        carga_avisada = True
                    else:
                        print(
                            f"  ⏳ Aún cargando... (intento {intento}/{_REINTENTOS_CARGA})",
                            flush=True,
                        )
                    time.sleep(_ESPERA_CARGA_S)

                    # A partir del 2do intento: también intentar con cualquier
                    # modelo activo en LM Studio (puede ser uno distinto al pedido)
                    if intento >= 1:
                        try:
                            kwargs_any = {**kwargs, "model": "local-model"}
                            resp_any = self._client.chat.completions.create(**kwargs_any)
                            # Funcionó — LM Studio tiene algún modelo activo
                            modelo_real = getattr(resp_any, "model", None)
                            if modelo_real and not any(
                                kw in modelo_real.lower() for kw in _EMBEDDING_KEYWORDS
                            ):
                                if modelo_real != self._model_id:
                                    print(
                                        f"  ℹ Modelo activo en LM Studio: {modelo_real} "
                                        f"(el solicitado '{self._model_id}' no está cargado)",
                                        flush=True,
                                    )
                                    self._model_id = modelo_real
                                    kwargs["model"] = modelo_real
                            return self._parsear_respuesta(resp_any)
                        except Exception:
                            pass  # No hay ningún modelo activo aún, seguir esperando
                    continue

                # Reintentos agotados o error distinto de "No models loaded"
                if "No models loaded" in str(e):
                    raise RuntimeError(
                        f"LM Studio no pudo cargar ningún modelo tras {_REINTENTOS_CARGA} intentos.\n"
                        "  → Cargá el modelo manualmente en LM Studio UI y volvé a intentar."
                    ) from e
                raise RuntimeError(f"Error en LM Studio: {e}") from e

            except Exception as e:
                raise RuntimeError(f"Error en LM Studio: {e}") from e

    def _parsear_respuesta(self, respuesta) -> RespuestaAgente:
        mensaje = respuesta.choices[0].message

        # Algunos modelos "thinking" (Nemotron, Gemma, DeepSeek-R1) ponen la
        # respuesta en reasoning_content y dejan content vacío. Usamos el que
        # tenga contenido; priorizamos content si ambos están presentes.
        content    = (mensaje.content or "").strip()
        reasoning  = getattr(mensaje, "reasoning_content", None) or ""
        reasoning  = reasoning.strip()
        texto = content or reasoning  # content tiene prioridad; fallback a reasoning

        if not mensaje.tool_calls:
            return RespuestaAgente(texto=texto)

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
            texto=texto,
            tool_calls=tool_calls,
        )
