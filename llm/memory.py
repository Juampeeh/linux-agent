# =============================================================================
# llm/memory.py — Memoria Semántica Persistente Vectorial v2.0
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
#
# v2.0 — Nuevas capacidades:
#   - Deduplicación: antes de guardar, verifica similitud > MEMORY_DEDUP_THRESHOLD
#   - TTL: entradas tipo "log_crudo" se auto-eliminan tras MEMORY_LOG_TTL_HOURS horas
#   - Bus sentinel: tabla sentinel_messages para comunicación entre procesos
#   - Nuevos tipos: "web_research", "env_map", "log_crudo", "insight", "alerta"
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
_PROVIDER_MAP: dict[str, str | None] = {
    "local":   "local",   # LM Studio  → /v1/embeddings OpenAI-compat
    "ollama":  "local",   # Ollama     → mismo namespace que LM Studio
    "chatgpt": "openai",  # OpenAI API → text-embedding-3-small
    "gemini":  "gemini",  # Gemini API → text-embedding-004
    "grok":    None,      # xAI sin endpoints de embeddings públicos
    "claude":  None,      # Anthropic sin API de embeddings
}

# ── Tipos de memoria y sus TTLs ───────────────────────────────────────────────
# TTL en horas (0 = sin expiración). Los "log_crudo" se purgan automáticamente.
_TIPO_TTL_HORAS: dict[str, int] = {
    "log_crudo":      cfg.MEMORY_LOG_TTL_HOURS,  # Logs crudos: expiran pronto
    "web_research":   72,   # Investigación web: 3 días
    "alerta":         48,   # Alertas del centinela: 2 días
    "respuesta_agente": 0,  # Sin expiración
    "comando_exitoso":  0,  # Sin expiración
    "preferencia":      0,  # Sin expiración
    "configuracion":    0,  # Sin expiración
    "env_map":          0,  # Sin expiración (mapa del entorno)
    "insight":          0,  # Sin expiración (conclusiones consolidadas)
}

# ── Esquema SQLite ────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS memorias (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido          TEXT    NOT NULL,
    resumen_corto      TEXT    NOT NULL DEFAULT '',
    embedding          TEXT    NOT NULL,
    tipo               TEXT    NOT NULL,
    embedding_provider TEXT    NOT NULL,
    timestamp          REAL    NOT NULL,
    metadata           TEXT    DEFAULT '{}',
    access_count       INTEGER DEFAULT 1,
    last_seen          REAL
);
CREATE INDEX IF NOT EXISTS idx_provider ON memorias(embedding_provider);
CREATE INDEX IF NOT EXISTS idx_tipo     ON memorias(tipo);
CREATE INDEX IF NOT EXISTS idx_timestamp ON memorias(timestamp);

-- Bus de mensajes para comunicación main <-> sentinel
CREATE TABLE IF NOT EXISTS sentinel_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,   -- "main" | "sentinel"
    type        TEXT    NOT NULL,   -- CMD_PAUSE|CMD_RESUME|CMD_STOP|ALERT|INFO|STATUS
    payload     TEXT    DEFAULT '{}',
    created_at  REAL    NOT NULL,
    read        INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sentinel_unread ON sentinel_messages(read, source);
"""


# =============================================================================
# Clase principal
# =============================================================================

class MemoriaSemantica:
    """
    Memoria semántica persistente para el Linux Local AI Agent v2.0.

    • Vectoriza texto via la API del motor LLM activo (sin modelos en Python).
    • Persiste en SQLite (archivo único, portable, sin contenedores).
    • Calcula similitud coseno con numpy.
    • Degrada silenciosamente si el motor no soporta embeddings o falla la DB.
    • v2.0: Deduplicación, TTL por tipo, bus de mensajes para el centinela.
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
            logger.debug(f"[Memoria] MEMORY_SHARED_EMBED: {motor_key} → LM Studio embeddings")
        else:
            self._provider = _PROVIDER_MAP.get(motor_key)  # None → sin soporte

        self._conn: sqlite3.Connection | None = None

        self.activa = (
            cfg.MEMORY_ENABLED
            and self._provider is not None
            and _NUMPY_OK
        )

        if self.activa:
            self._init_db()
            # Purgar TTL al arrancar (no bloquea el inicio)
            try:
                self._purgar_ttl()
            except Exception:
                pass

    # ── Inicialización DB ─────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Abre o crea la base de datos SQLite con el esquema v2.0."""
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path, 
                check_same_thread=False, 
                timeout=30.0
            )
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            # Migración: agregar columnas nuevas si la DB es anterior a v2.0
            self._migrar_schema()
        except Exception as e:
            logger.warning(f"[Memoria] No se pudo inicializar la DB: {e}")
            self.activa = False

    def _migrar_schema(self) -> None:
        """Agrega columnas nuevas a tablas existentes (migración no destructiva)."""
        if not self._conn:
            return
        try:
            cols = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(memorias)")
            }
            if "resumen_corto" not in cols:
                self._conn.execute(
                    "ALTER TABLE memorias ADD COLUMN resumen_corto TEXT NOT NULL DEFAULT ''"
                )
            if "access_count" not in cols:
                self._conn.execute(
                    "ALTER TABLE memorias ADD COLUMN access_count INTEGER DEFAULT 1"
                )
            if "last_seen" not in cols:
                self._conn.execute(
                    "ALTER TABLE memorias ADD COLUMN last_seen REAL"
                )
            self._conn.commit()
        except Exception:
            pass

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
        Actualiza access_count y last_seen de los recuerdos encontrados.
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
                "SELECT id, contenido, resumen_corto, embedding, tipo, metadata "
                "FROM memorias WHERE embedding_provider = ?",
                (self._provider,),
            )
            filas = cursor.fetchall()
        except Exception as e:
            logger.debug(f"[Memoria] Error en SELECT: {e}")
            return []

        scored: list[dict[str, Any]] = []
        ids_encontrados: list[int] = []

        for row_id, contenido, resumen_corto, emb_json, tipo, meta_json in filas:
            try:
                emb = json.loads(emb_json)
                sim = self._coseno(query_vec, emb)
                if sim >= threshold:
                    scored.append({
                        "id":            row_id,
                        "contenido":     contenido,
                        "resumen_corto": resumen_corto,
                        "tipo":          tipo,
                        "similitud": round(sim, 3),
                        "metadata":  json.loads(meta_json or "{}"),
                    })
                    ids_encontrados.append(row_id)
            except Exception:
                continue

        scored.sort(key=lambda x: x["similitud"], reverse=True)
        resultados = scored[:top_k]

        # Actualizar access_count y last_seen para los recuerdos devueltos
        if resultados:
            try:
                now = time.time()
                for r in resultados:
                    self._conn.execute(
                        "UPDATE memorias SET access_count = access_count + 1, "
                        "last_seen = ? WHERE id = ?",
                        (now, r["id"]),
                    )
                self._conn.commit()
            except Exception:
                pass

        return resultados

    def obtener_detalle(self, id_memoria: int) -> str | None:
        """Retorna el contenido completo de una memoria dado su ID."""
        if not self.activa or not self._conn:
            return None
        try:
            cursor = self._conn.execute(
                "SELECT contenido FROM memorias WHERE id = ? AND embedding_provider = ?",
                (id_memoria, self._provider),
            )
            fila = cursor.fetchone()
            if fila:
                return fila[0]
            return None
        except Exception as e:
            logger.debug(f"[Memoria] Error al obtener detalle (id={id_memoria}): {e}")
            return None

    # ── Guardar con deduplicación ─────────────────────────────────────────────

    def guardar(
        self,
        contenido: str,
        tipo:      str,
        metadata:  dict | None = None,
        resumen_corto: str = "",
    ) -> bool:
        """
        Vectoriza el contenido y lo persiste en SQLite.

        v2.0: Antes de insertar, verifica si ya existe algo muy similar
        (similitud > MEMORY_DEDUP_THRESHOLD). Si es así, actualiza el registro
        existente en lugar de crear un duplicado.
        """
        if not self.activa or not self._conn:
            return False

        emb = self.get_embedding(contenido)
        if emb is None:
            return False

        # ── Deduplicación ─────────────────────────────────────────────────────
        try:
            cursor = self._conn.execute(
                "SELECT id, embedding FROM memorias "
                "WHERE embedding_provider = ? AND tipo = ?",
                (self._provider, tipo),
            )
            for row_id, emb_json in cursor.fetchall():
                try:
                    existente_emb = json.loads(emb_json)
                    sim = self._coseno(emb, existente_emb)
                    if sim >= cfg.MEMORY_DEDUP_THRESHOLD:
                        # Es un duplicado: actualizar timestamp y contador
                        self._conn.execute(
                            "UPDATE memorias SET timestamp = ?, access_count = access_count + 1, "
                            "last_seen = ? WHERE id = ?",
                            (time.time(), time.time(), row_id),
                        )
                        self._conn.commit()
                        logger.debug(
                            f"[Memoria] Dedup: similitud {sim:.2f} con entrada existente "
                            f"(id={row_id}). Actualizado en lugar de insertar."
                        )
                        return True  # Retorna True: el recuerdo está "actualizado"
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Memoria] Error en dedup check: {e}")

        # ── Insertar nuevo recuerdo ───────────────────────────────────────────
        try:
            now = time.time()
            self._conn.execute(
                """INSERT INTO memorias
                   (contenido, resumen_corto, embedding, tipo, embedding_provider, timestamp, metadata,
                    access_count, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    contenido,
                    resumen_corto,
                    json.dumps(emb),
                    tipo,
                    self._provider,
                    now,
                    json.dumps(metadata or {}),
                    now,
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
                # Eliminar primero log_crudo y alerta (más prescindibles),
                # luego las más antiguas por timestamp
                self._conn.execute(
                    """DELETE FROM memorias WHERE id IN (
                        SELECT id FROM memorias
                        WHERE embedding_provider = ?
                        ORDER BY
                            CASE tipo
                                WHEN 'log_crudo' THEN 0
                                WHEN 'alerta' THEN 1
                                WHEN 'web_research' THEN 2
                                ELSE 3
                            END ASC,
                            timestamp ASC
                        LIMIT ?
                    )""",
                    (self._provider, exceso),
                )
                self._conn.commit()
        except Exception:
            pass

    def _purgar_ttl(self) -> int:
        """Elimina entradas expiradas según su tipo. Retorna cantidad eliminadas."""
        if not self._conn:
            return 0
        eliminadas = 0
        now = time.time()
        try:
            for tipo, ttl_horas in _TIPO_TTL_HORAS.items():
                if ttl_horas > 0:
                    expira_antes_de = now - (ttl_horas * 3600)
                    cursor = self._conn.execute(
                        "DELETE FROM memorias WHERE tipo = ? AND timestamp < ?",
                        (tipo, expira_antes_de),
                    )
                    eliminadas += cursor.rowcount
            if eliminadas > 0:
                self._conn.commit()
                logger.debug(f"[Memoria] TTL: {eliminadas} entrada(s) expirada(s) eliminada(s).")
        except Exception as e:
            logger.debug(f"[Memoria] Error en TTL purge: {e}")
        return eliminadas

    def guardar_si_exitoso(
        self,
        nombre_tool: str,
        argumentos:  dict,
        resultado:   str,
    ) -> None:
        """
        Extrae y guarda un aprendizaje tras ejecutar una tool con éxito.
        v2.0: Soporte para web_search además de execute_local_bash.
        """
        if not self.activa:
            return

        if nombre_tool == "execute_local_bash":
            comando = argumentos.get("comando", "").strip()
            if not comando:
                return

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

            lineas_output = resultado.splitlines()[:6]
            resumen_output = "\n".join(lineas_output)
            if len(resultado.splitlines()) > 6:
                resumen_output += "\n(...)"

            contenido = (
                f"Comando bash exitoso: `{comando}`\n"
                f"Output:\n{resumen_output}"
            )
            self.guardar(contenido=contenido, tipo="comando_exitoso", metadata={"comando": comando})

    # ── Bus de mensajes sentinel ──────────────────────────────────────────────

    def enviar_mensaje_sentinel(
        self,
        source: str,
        type_: str,
        payload: dict | None = None,
    ) -> bool:
        """
        Escribe un mensaje en el bus sentinel (tabla sentinel_messages).

        Parámetros
        ----------
        source  : "main" o "sentinel"
        type_   : "CMD_PAUSE", "CMD_RESUME", "CMD_STOP", "ALERT", "INFO", "STATUS"
        payload : Datos adicionales del mensaje (dict serializable a JSON)
        """
        # La tabla sentinel_messages existe aunque la memoria esté desactivada
        # (el centinela puede correr sin embeddings)
        conn = self._conn
        if conn is None:
            try:
                conn = sqlite3.connect(cfg.MEMORY_DB_PATH, check_same_thread=False)
                conn.executescript(_SCHEMA)
                conn.commit()
            except Exception as e:
                logger.debug(f"[Sentinel Bus] Error abriendo DB: {e}")
                return False

        try:
            conn.execute(
                "INSERT INTO sentinel_messages (source, type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (source, type_, json.dumps(payload or {}), time.time()),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.debug(f"[Sentinel Bus] Error enviando mensaje: {e}")
            return False

    def leer_mensajes_sentinel(
        self,
        source_filter: str | None = None,
        solo_no_leidos: bool = True,
    ) -> list[dict]:
        """
        Lee mensajes del bus sentinel. Filtra por source si se especifica.
        Por defecto solo retorna mensajes no leídos.
        """
        conn = self._conn
        if conn is None:
            try:
                conn = sqlite3.connect(cfg.MEMORY_DB_PATH, check_same_thread=False)
            except Exception:
                return []

        try:
            query = "SELECT id, source, type, payload, created_at FROM sentinel_messages"
            params: list = []
            condiciones = []

            if solo_no_leidos:
                condiciones.append("read = 0")
            if source_filter:
                condiciones.append("source = ?")
                params.append(source_filter)

            if condiciones:
                query += " WHERE " + " AND ".join(condiciones)
            query += " ORDER BY created_at ASC"

            cursor = conn.execute(query, params)
            mensajes = []
            for row in cursor.fetchall():
                mensajes.append({
                    "id":         row[0],
                    "source":     row[1],
                    "type":       row[2],
                    "payload":    json.loads(row[3] or "{}"),
                    "created_at": row[4],
                })
            return mensajes
        except Exception as e:
            logger.debug(f"[Sentinel Bus] Error leyendo mensajes: {e}")
            return []

    def marcar_leidos_sentinel(self, ids: list[int]) -> None:
        """Marca los mensajes sentinel como leídos."""
        conn = self._conn
        if conn is None or not ids:
            return
        try:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE sentinel_messages SET read = 1 WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()
        except Exception:
            pass

    def purgar_mensajes_sentinel_antiguos(self, horas: int = 48) -> None:
        """Elimina mensajes sentinel leídos y antiguos para no acumular basura."""
        conn = self._conn
        if conn is None:
            return
        try:
            cutoff = time.time() - (horas * 3600)
            conn.execute(
                "DELETE FROM sentinel_messages WHERE read = 1 AND created_at < ?",
                (cutoff,),
            )
            conn.commit()
        except Exception:
            pass

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

            # Stats del bus sentinel
            sentinel_pendientes = self._conn.execute(
                "SELECT COUNT(*) FROM sentinel_messages WHERE read = 0"
            ).fetchone()[0]

            return {
                "activa":               True,
                "provider":             self._provider,
                "motor":                self.motor_key,
                "total":                total,
                "por_tipo":             por_tipo,
                "db_path":              self._db_path,
                "db_size_kb":           db_size_kb,
                "max_entries":          cfg.MEMORY_MAX_ENTRIES,
                "sentinel_pendientes":  sentinel_pendientes,
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
        model_id = cfg.LMSTUDIO_EMBED_MODEL or None

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
