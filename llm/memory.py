# =============================================================================
# llm/memory.py — Memoria Semántica Persistente Vectorial
#
# Almacenamiento: SQLite builtin (cero deps extra, un único .db portable)
# Embeddings:     API /v1/embeddings del motor activo (sin modelos locales en memoria)
# Similitud:      Coseno con numpy (dep transitiva de openai, ya en el entorno)
#
# Namespaces de vectores:
#   "local"  → LM Studio + Ollama comparten espacio (OpenAI-compat /v1/embeddings)
#   "gemini" → Gemini API (text-embedding-004)
#   "openai" → OpenAI API (text-embedding-3-small)
#   None     → Grok, Anthropic — sin API de embeddings → memoria desactivada
# =============================================================================

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import config as cfg

logger = logging.getLogger(__name__)

# ── Disponibilidad de numpy ───────────────────────────────────────────────────
try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False
    logger.warning("[Memoria] numpy no disponible — memoria desactivada.")

# ── Mapa motor → proveedor de embeddings ─────────────────────────────────────
# Motores en el mismo grupo comparten namespace (sus vectores son comparables).
# None = motor sin API de embeddings → memoria desactivada para esa sesión.
# Con MEMORY_SHARED_EMBED=True todos los motores usan el namespace 'local'
# (LM Studio) para que la memoria sea compartida entre todos los agentes.
_PROVIDER_MAP: dict[str, str | None] = {
    "local":   "local",   # LM Studio  → /v1/embeddings OpenAI-compat
    "ollama":  "local",   # Ollama     → mismo namespace que LM Studio
    "chatgpt": "openai",  # OpenAI API → text-embedding-3-small
    "gemini":  "gemini",  # Gemini API → text-embedding-004
    "grok":    None,      # xAI aún no tiene endpoints de embeddings públicos
    "claude":  None,      # Anthropic no tiene API de embeddings
}

# ── Esquema SQLite ────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS memorias (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido          TEXT    NOT NULL,
    embedding          TEXT    NOT NULL,
    tipo               TEXT    NOT NULL,
    embedding_provider TEXT    NOT NULL,
    timestamp          REAL    NOT NULL,
    metadata           TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_provider ON memorias(embedding_provider);
CREATE INDEX IF NOT EXISTS idx_tipo     ON memorias(tipo);
"""


# =============================================================================
# Clase principal
# =============================================================================

class MemoriaSemantica:
    """
    Memoria semántica persistente para el Linux Local AI Agent.

    • Vectoriza texto via la API del motor LLM activo (sin modelos en Python).
    • Persiste en SQLite (archivo único, portable, sin contenedores).
    • Calcula similitud coseno con numpy.
    • Degrada silenciosamente si el motor no soporta embeddings o falla la DB.
    """

    def __init__(
        self,
        motor_key: str,
        base_url:  str | None = None,
        api_key:   str | None = None,
        model_id:  str | None = None,
        db_path:   str | None = None,
    ) -> None:
        self.motor_key  = motor_key
        self._base_url  = base_url
        self._api_key   = api_key
        self._model_id  = model_id
        self._db_path   = db_path or cfg.MEMORY_DB_PATH

        # MEMORY_SHARED_EMBED: redirige todos los motores a LM Studio para
        # embeddings, unificando el namespace vectorial entre todos los agentes.
        if cfg.MEMORY_SHARED_EMBED and motor_key not in ("local", "ollama"):
            self._provider = "local"
            self._base_url = cfg.LMSTUDIO_BASE_URL
            self._model_id = cfg.LMSTUDIO_EMBED_MODEL or None
            logger.debug(f"[Memoria] MEMORY_SHARED_EMBED activo: {motor_key} → LM Studio embeddings")
        else:
            self._provider = _PROVIDER_MAP.get(motor_key)  # None → sin soporte

        self._conn: sqlite3.Connection | None = None

        # La memoria está activa solo si:
        # 1. Está habilitada en config
        # 2. El motor tiene un proveedor de embeddings
        # 3. numpy está disponible
        self.activa = (
            cfg.MEMORY_ENABLED
            and self._provider is not None
            and _NUMPY_OK
        )

        if self.activa:
            self._init_db()

    # ── Inicialización DB ─────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Abre o crea la base de datos SQLite."""
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except Exception as e:
            logger.warning(f"[Memoria] No se pudo inicializar la DB: {e}")
            self.activa = False

    # ── Obtención de embeddings ───────────────────────────────────────────────

    def get_embedding(self, texto: str) -> list[float] | None:
        """
        Obtiene el embedding del texto via la API del motor activo.
        Retorna None si falla (el agente continúa sin memoria para esa operación).
        """
        if not self.activa or not self._provider:
            return None
        try:
            if self._provider == "local":
                return self._embed_openai_compat(texto)
            elif self._provider == "openai":
                return self._embed_openai_compat(
                    texto,
                    base_url="https://api.openai.com/v1",
                    api_key=self._api_key,
                    model="text-embedding-3-small",
                )
            elif self._provider == "gemini":
                return self._embed_gemini(texto)
            return None
        except Exception as e:
            logger.debug(f"[Memoria] Error en get_embedding: {e}")
            return None

    def _embed_openai_compat(
        self,
        texto:    str,
        base_url: str | None = None,
        api_key:  str | None = None,
        model:    str | None = None,
    ) -> list[float] | None:
        """Embedding via endpoint OpenAI-compatible (/v1/embeddings)."""
        import openai

        client = openai.OpenAI(
            base_url=base_url or self._base_url,
            api_key=api_key or "lm-studio",
            timeout=30,
        )
        # LM Studio usa el modelo actualmente cargado si no se especifica uno.
        # Pasamos el configurado (puede ser vacío → LM Studio elige automáticamente).
        resp = client.embeddings.create(
            input=texto,
            model=model or self._model_id or "text-embedding",
        )
        return resp.data[0].embedding

    def _embed_gemini(self, texto: str) -> list[float] | None:
        """Embedding via Gemini Embeddings API (text-embedding-004)."""
        import httpx

        url = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
        body = {
            "model":   "models/text-embedding-004",
            "content": {"parts": [{"text": texto}]},
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                url,
                json=body,
                params={"key": self._api_key},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]

    # ── Similitud coseno ──────────────────────────────────────────────────────

    @staticmethod
    def _coseno(a: list[float], b: list[float]) -> float:
        """Similitud coseno entre dos vectores (0.0–1.0). Requiere numpy."""
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))

    # ── Buscar ────────────────────────────────────────────────────────────────

    def buscar(
        self,
        query:     str,
        top_k:     int | None   = None,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Vectoriza la query y retorna hasta top_k recuerdos del namespace
        actual cuya similitud coseno supere el threshold.
        """
        if not self.activa or not self._conn:
            return []

        top_k     = top_k     if top_k     is not None else cfg.MEMORY_TOP_K
        threshold = threshold if threshold is not None else cfg.MEMORY_THRESHOLD

        query_vec = self.get_embedding(query)
        if query_vec is None:
            return []

        try:
            cursor = self._conn.execute(
                "SELECT contenido, embedding, tipo, metadata "
                "FROM memorias WHERE embedding_provider = ?",
                (self._provider,),
            )
            filas = cursor.fetchall()
        except Exception as e:
            logger.debug(f"[Memoria] Error en SELECT: {e}")
            return []

        scored: list[dict[str, Any]] = []
        for contenido, emb_json, tipo, meta_json in filas:
            try:
                emb = json.loads(emb_json)
                sim = self._coseno(query_vec, emb)
                if sim >= threshold:
                    scored.append({
                        "contenido": contenido,
                        "tipo":      tipo,
                        "similitud": round(sim, 3),
                        "metadata":  json.loads(meta_json or "{}"),
                    })
            except Exception:
                continue

        scored.sort(key=lambda x: x["similitud"], reverse=True)
        return scored[:top_k]

    # ── Guardar ───────────────────────────────────────────────────────────────

    def guardar(
        self,
        contenido: str,
        tipo:      str,
        metadata:  dict | None = None,
    ) -> bool:
        """Vectoriza el contenido y lo persiste en SQLite."""
        if not self.activa or not self._conn:
            return False

        emb = self.get_embedding(contenido)
        if emb is None:
            return False

        try:
            self._conn.execute(
                """INSERT INTO memorias
                   (contenido, embedding, tipo, embedding_provider, timestamp, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    contenido,
                    json.dumps(emb),
                    tipo,
                    self._provider,
                    time.time(),
                    json.dumps(metadata or {}),
                ),
            )
            self._conn.commit()
            self._purgar_si_necesario()
            return True
        except Exception as e:
            logger.debug(f"[Memoria] Error guardando: {e}")
            return False

    def _purgar_si_necesario(self) -> None:
        """Elimina las entradas más antiguas si se supera MEMORY_MAX_ENTRIES."""
        try:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM memorias WHERE embedding_provider = ?",
                (self._provider,),
            ).fetchone()[0]
            if count > cfg.MEMORY_MAX_ENTRIES:
                exceso = count - cfg.MEMORY_MAX_ENTRIES
                self._conn.execute(
                    """DELETE FROM memorias WHERE id IN (
                        SELECT id FROM memorias
                        WHERE embedding_provider = ?
                        ORDER BY timestamp ASC LIMIT ?
                    )""",
                    (self._provider, exceso),
                )
                self._conn.commit()
        except Exception:
            pass

    def guardar_si_exitoso(
        self,
        nombre_tool: str,
        argumentos:  dict,
        resultado:   str,
    ) -> None:
        """
        Extrae y guarda un aprendizaje tras ejecutar una tool con éxito.
        Heurística liviana (sin llamada extra al LLM):
          - Solo para 'execute_local_bash'
          - Considera exitoso si 'exit_code: 0' está en el resultado, o si el
            resultado tiene sustancia y no contiene palabras de error comunes.
        """
        if not self.activa:
            return
        if nombre_tool != "execute_local_bash":
            return

        comando = argumentos.get("comando", "").strip()
        if not comando:
            return

        # Determinar si el resultado fue exitoso
        exitoso = False
        if "exit_code: 0" in resultado or "exit_code:0" in resultado:
            exitoso = True
        else:
            resultado_lower = resultado.lower()
            palabras_error = [
                "error", "failed", "failure", "no se pudo", "not found",
                "command not found", "permission denied", "cannot", "traceback",
            ]
            tiene_error = any(w in resultado_lower for w in palabras_error)
            if not tiene_error and len(resultado.strip()) >= 10:
                exitoso = True

        if not exitoso:
            return

        # Construir contenido canónico del recuerdo
        lineas_output = resultado.splitlines()[:6]
        resumen_output = "\n".join(lineas_output)
        if len(resultado.splitlines()) > 6:
            resumen_output += "\n(...)"

        contenido = (
            f"Comando bash exitoso: `{comando}`\n"
            f"Output:\n{resumen_output}"
        )

        self.guardar(
            contenido=contenido,
            tipo="comando_exitoso",
            metadata={"comando": comando},
        )

    # ── Estadísticas y gestión ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Retorna estadísticas de la DB para el proveedor actual."""
        if not self.activa or not self._conn:
            motor_info = _PROVIDER_MAP.get(self.motor_key)
            if motor_info is None:
                razon = f"El motor '{self.motor_key}' no soporta embeddings (Grok/Claude)."
            elif not _NUMPY_OK:
                razon = "numpy no está instalado."
            elif not cfg.MEMORY_ENABLED:
                razon = "MEMORY_ENABLED=False en .env"
            else:
                razon = "Error de inicialización de la DB."
            return {"activa": False, "razon": razon}

        try:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM memorias WHERE embedding_provider = ?",
                (self._provider,),
            ).fetchone()[0]

            por_tipo: dict[str, int] = {}
            for row in self._conn.execute(
                "SELECT tipo, COUNT(*) FROM memorias "
                "WHERE embedding_provider = ? GROUP BY tipo",
                (self._provider,),
            ):
                por_tipo[row[0]] = row[1]

            db_size_kb = Path(self._db_path).stat().st_size // 1024

            return {
                "activa":      True,
                "provider":    self._provider,
                "motor":       self.motor_key,
                "total":       total,
                "por_tipo":    por_tipo,
                "db_path":     self._db_path,
                "db_size_kb":  db_size_kb,
                "max_entries": cfg.MEMORY_MAX_ENTRIES,
            }
        except Exception as e:
            return {"activa": False, "razon": str(e)}

    def limpiar(self) -> int:
        """
        Elimina todas las memorias del proveedor actual.
        Retorna el número de entradas eliminadas.
        """
        if not self.activa or not self._conn:
            return 0
        try:
            cursor = self._conn.execute(
                "DELETE FROM memorias WHERE embedding_provider = ?",
                (self._provider,),
            )
            self._conn.commit()
            return cursor.rowcount
        except Exception:
            return 0

    def cerrar(self) -> None:
        """Cierra la conexión a la DB."""
        if self._conn:
            self._conn.close()
            self._conn = None


# =============================================================================
# Factory
# =============================================================================

def crear_memoria(motor_key: str) -> "MemoriaSemantica":
    """
    Factory que crea una MemoriaSemantica correctamente configurada
    para el motor activo (URLs, API keys, modelo de embeddings).
    """
    base_url: str | None = None
    api_key:  str | None = None
    model_id: str | None = None

    if motor_key == "local":
        base_url = cfg.LMSTUDIO_BASE_URL
        model_id = cfg.LMSTUDIO_EMBED_MODEL or None  # Vacío → LM Studio elige el activo

    elif motor_key == "ollama":
        base_url = cfg.OLLAMA_BASE_URL
        model_id = cfg.OLLAMA_EMBED_MODEL or cfg.OLLAMA_MODEL or None

    elif motor_key == "chatgpt":
        api_key  = cfg.OPENAI_API_KEY
        model_id = "text-embedding-3-small"

    elif motor_key == "gemini":
        api_key = cfg.GEMINI_API_KEY

    # grok, claude → provider=None → activa=False automáticamente

    return MemoriaSemantica(
        motor_key=motor_key,
        base_url=base_url,
        api_key=api_key,
        model_id=model_id,
    )


# =============================================================================
# Helpers para inyección de contexto
# =============================================================================

def formatear_contexto_memoria(recuerdos: list[dict[str, Any]]) -> str:
    """
    Convierte una lista de recuerdos en un bloque de texto para inyectar
    silenciosamente en el prompt del usuario.
    """
    if not recuerdos:
        return ""

    lineas = ["[MEMORIA — contexto de sesiones anteriores]"]
    for r in recuerdos:
        sim_pct = int(r["similitud"] * 100)
        lineas.append(f"• [{r['tipo']} | {sim_pct}% relevante]\n  {r['contenido']}")

    return "\n".join(lineas)
