# =============================================================================
# memory_consolidator.py — Consolidación inteligente de memoria via LLM
# Linux Local AI Agent v2.0
# =============================================================================

from __future__ import annotations
import logging
import time
from typing import TYPE_CHECKING

import config as cfg

if TYPE_CHECKING:
    from llm.base import AgenteIA
    from llm.memory import MemoriaSemantica

logger = logging.getLogger(__name__)

# Prompt para que el LLM consolide un episodio en una sola entrada de memoria
_PROMPT_CONSOLIDAR = """Eres un sistema de gestión de memoria. Tu tarea es condensar la siguiente secuencia de eventos en UNA SOLA entrada de memoria concisa, factual y útil para el futuro.

Reglas:
1. La entrada debe capturar el RESULTADO FINAL y la INFORMACIÓN ÚTIL (IP, rutas, comandos que funcionaron, soluciones encontradas).
2. NO incluyas logs crudos, errores intermedios ni pasos fallidos.
3. Formato ideal: 2-4 oraciones máximo. Empieza con el verbo de acción en pasado.
4. Si hay una IP, ruta, versión o configuración específica aprendida, inclúyela explícitamente.
5. Responde SOLO con el texto consolidado, sin prefijos ni metadata.

Eventos del episodio:
---
{eventos}
---

Resultado final:
{resolucion}

Entrada de memoria consolidada:"""


def consolidar_episodio(
    agente: "AgenteIA",
    eventos: list[str],
    resolucion: str,
    memoria: "MemoriaSemantica",
    tarea_original: str = "",
) -> str | None:
    """
    Usa el LLM activo para condensar una secuencia de eventos en una sola
    entrada de memoria tipo "insight". Guarda el resultado en la memoria.

    Parámetros
    ----------
    agente          : Instancia del agente LLM activo.
    eventos         : Lista de strings con los eventos/comandos del episodio.
    resolucion      : Resultado/conclusión final del episodio.
    memoria         : Instancia de MemoriaSemantica donde guardar el insight.
    tarea_original  : Descripción de la tarea que originó el episodio.

    Retorna
    -------
    El texto consolidado generado por el LLM, o None si falló.
    """
    if not cfg.MEMORY_CONSOLIDATE_ON_TASK:
        return None
    if not memoria.activa:
        return None
    if not eventos:
        return None

    # Limitar eventos para no sobrecargar el contexto
    eventos_texto = "\n".join(
        f"[{i+1}] {ev[:200]}" for i, ev in enumerate(eventos[-15:])
    )
    resolucion_texto = resolucion[:500]

    prompt = _PROMPT_CONSOLIDAR.format(
        eventos=eventos_texto,
        resolucion=resolucion_texto,
    )

    try:
        # Usar el LLM directamente sin historial (llamada puntual de consolidación)
        from llm.history import HistorialCanonico
        historial_temp = HistorialCanonico(
            system_prompt=(
                "Eres un sistema de gestión de memoria de un AI Agent. "
                "Responde ÚNICAMENTE con el texto solicitado, sin formato adicional."
            )
        )
        historial_temp.agregar_usuario(prompt)

        respuesta = agente.enviar_turno(historial_temp, [])  # Sin herramientas
        insight = respuesta.texto.strip()

        if not insight or len(insight) < 20:
            logger.debug("[Consolidación] LLM retornó insight vacío o muy corto.")
            return None

        # Guardar en memoria como insight
        metadata = {
            "tarea": tarea_original[:200],
            "num_eventos": len(eventos),
            "ts_consolidacion": time.time(),
        }
        guardado = memoria.guardar(
            contenido=insight,
            tipo="insight",
            metadata=metadata,
        )

        if guardado:
            logger.debug(f"[Consolidación] Insight guardado: {insight[:80]}...")
        return insight

    except Exception as e:
        logger.debug(f"[Consolidación] Error al consolidar episodio: {e}")
        return None


def purgar_memorias_ttl(memoria: "MemoriaSemantica") -> int:
    """
    Dispara la purga de memorias expiradas por TTL.
    Retorna el número de entradas eliminadas.
    """
    try:
        return memoria._purgar_ttl()
    except Exception as e:
        logger.debug(f"[Consolidación] Error en purga TTL: {e}")
        return 0


def fusionar_similares(
    memoria: "MemoriaSemantica",
    threshold: float = 0.92,
    tipo_filtro: str | None = None,
    max_fusiones: int = 20,
) -> int:
    """
    Detecta pares de memorias muy similares (similitud >= threshold) y
    elimina el duplicado más antiguo, manteniendo el más reciente.

    Retorna el número de duplicados eliminados.
    """
    if not memoria.activa or not memoria._conn:
        return 0

    eliminados = 0
    try:
        query = (
            "SELECT id, contenido, embedding, tipo, timestamp FROM memorias "
            "WHERE embedding_provider = ?"
        )
        params: list = [memoria._provider]
        if tipo_filtro:
            query += " AND tipo = ?"
            params.append(tipo_filtro)
        query += " ORDER BY timestamp DESC"

        filas = memoria._conn.execute(query, params).fetchall()

        import json
        import numpy as np

        ids_eliminados: set[int] = set()

        for i, (id_a, cont_a, emb_json_a, tipo_a, ts_a) in enumerate(filas):
            if id_a in ids_eliminados or eliminados >= max_fusiones:
                break
            try:
                emb_a = json.loads(emb_json_a)
            except Exception:
                continue

            for id_b, cont_b, emb_json_b, tipo_b, ts_b in filas[i + 1:]:
                if id_b in ids_eliminados:
                    continue
                if tipo_a != tipo_b:
                    continue
                try:
                    emb_b = json.loads(emb_json_b)
                    sim = memoria._coseno(emb_a, emb_b)
                    if sim >= threshold:
                        # Eliminar el más antiguo (ts_b < ts_a porque ordenamos DESC)
                        memoria._conn.execute(
                            "DELETE FROM memorias WHERE id = ?", (id_b,)
                        )
                        ids_eliminados.add(id_b)
                        eliminados += 1
                        logger.debug(
                            f"[Fusión] Duplicado eliminado (id={id_b}, sim={sim:.2f})"
                        )
                except Exception:
                    continue

        if eliminados > 0:
            memoria._conn.commit()
            logger.info(f"[Fusión] {eliminados} duplicado(s) eliminado(s) de la memoria.")

    except Exception as e:
        logger.debug(f"[Consolidación] Error en fusión de similares: {e}")

    return eliminados
