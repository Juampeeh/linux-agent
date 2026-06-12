# 📝 Plan de Acción: Resolución de Errores y Optimización (Faltantes)

A continuación se detalla el análisis de las problemáticas reportadas en el documento de faltantes, con una redacción mejorada y las posibles soluciones técnicas recomendadas para cada punto.

> **Estado al 6 de mayo de 2026 (v3.4):**
> - ✅ **Ítem 1** (Sync modelos Web/CLI) — **RESUELTO** en `web/app.js` v3.4: lista unificada LM Studio live + guardados, `current` siempre sincronizado
> - ✅ **Ítem 2** (bug `req_conf`) — **RESUELTO** en `agent_core.py` v3.2
> - ✅ **Ítem 5** (Agency-Agents) — **IMPLEMENTADO + VERIFICADO** en `agency_router.py` v3.2 (5 especialistas activos en VM)
> - ✅ **Bug: Auto-cancelación modo auto** — **RESUELTO** en `tools.py`, `tools_remote.py`, `agentic_loop.py` v3.3
> - ✅ **Bug: Selector modelo no persiste** — **RESUELTO** en `web/app.js` v3.4 (click en item completo, `_pendingModelId`, dot verde/gris)
> - ✅ **Bug: `current` siempre null** — **RESUELTO** en `agent_core.py` v3.4 (sync tras `inicializar()` y cada respuesta LLM)
> - ✅ **NUEVO: Botón ✕ Cancelar** — aparece durante procesamiento, cancela reconectando WS
> - 🔄 **Ítem 3** (latencia Web vs CLI) — Parcialmente mejorado; bottleneck en LM Studio (externo al agente)
> - ℹ️ **Ítem 4** (GPU AMD) — Documentado; configuración de LM Studio/ROCm (no requiere cambios de código)
>
> **Estado al 12 de junio de 2026 (v4.0):**
> - ✅ **Ítem 6** (Centinela no refleja estado) — **RESUELTO**: nuevo `GET /api/sentinel/status`, polling c/30s, broadcast por WebSocket events, botones Start/Stop usan API REST directa
> - ✅ **Ítem 7** (Historial se pierde al cambiar modelo) — **RESUELTO**: `cambiar_modelo()` nunca destruye el historial; confirmado que `switchModel()` en JS no reconecta WS
> - ✅ **Ítem 8** (Memoria no consolida en Web) — **RESUELTO**: auto-consolidación cada 5 min + botón "💾 Guardar Memoria" + endpoint `POST /api/memory/consolidate`
> - ✅ **Ítem 9** (Paneles laterales se cortan) — **RESUELTO**: paneles colapsables estilo acordeón con chevron, estado persistido en localStorage, scroll independiente del sidebar
> - ✅ **Ítem 10** (SQLite database is locked) — **RESUELTO**: `busy_timeout=60000` + WAL en todas las conexiones (memory.py, sentinel.py), reintentos 8x con 5s de espera
> - ✅ **Ítem 11** (Web UI cae silenciosa) — **RESUELTO**: `safeFetch()` wrapper global con toast de errores, manejo de 422/500, sentinel status update por events WS




---

## 4. Optimización de Inferencia y Rendimiento de GPU (Hardware AMD)

*   **Contexto Actualizado:** Ya no existen limitaciones de voltaje ni de potencia. Las GPUs pueden operar a su máximo esplendor sin restricciones energéticas.
    *   **Setup:** 2 x AMD Radeon RX 6700 XT (12GB c/u, 24GB total VRAM), Ryzen 7 5800XT.
*   **Posibles Soluciones para Optimización (Software y Carga) aprovechando la potencia total:**
    *   **Framework para AMD:** Asegurarse de que LM Studio u Ollama estén ejecutándose bajo el backend de aceleración **Vulkan** o soporte para **ROCm** (arquitectura HIP) para exprimir al máximo el rendimiento de las gráficas RDNA2 sin cuellos de botella en la CPU.
    *   **Tensor Splitting (Distribución de GPUs):** Aprovechar los 24GB totales de VRAM corriendo modelos grandes (ej. 30B+) distribuyendo las capas equitativamente entre ambas gráficas, ahora sin preocupación por picos de consumo (power spikes).
    *   **Overclock de VRAM (Opcional):** Dado que ya no hay restricciones, se puede probar aumentar ligeramente la frecuencia de la VRAM con 'Fast Timings', ya que el mayor cuello de botella en inferencia es el ancho de banda de memoria, no tanto el núcleo.



## 6. Sincronización del estado del Centinela en la Web UI

*   **Problemática:** El panel del centinela en la barra lateral derecha de la interfaz web muestra "Detenido" o no refleja el estado real del proceso en background (`sentinel.py`), especialmente cuando el demonio se inició de forma autónoma o paralela.
*   **Posible Solución:**
    *   Al cargar la página web (`index.html`), el backend (FastAPI) debe leer activamente si el proceso del centinela está vivo (verificando el archivo `.sentinel.pid`).
    *   Implementar un mecanismo en `web_server.py` que envíe eventos WebSocket al frontend informando cambios de estado del centinela para que la UI reaccione en tiempo real.

---

## 7. Persistencia del Historial al cambiar de Modelo

*   **Problemática:** Al cambiar el modelo de IA desde el panel lateral de LM Studio en la web, el sistema "olvida" la conversación que se venía teniendo o resetea el contexto.
*   **Posible Solución:**
    *   Desacoplar la instancia del `HistorialCanonico` (el contexto y la memoria temporal de la charla) de la instanciación del motor LLM.
    *   Al recibir un POST o evento a `/api/engine/model`, el servidor debe actualizar el parámetro de generación del `AgenteIA`, pero **no debe destruir la lista de mensajes en memoria** para la sesión activa.

---

## 8. Consolidación de Memoria Semántica en la Web UI

*   **Problemática:** En la consola (CLI), cuando se sale del programa o termina un comando largo, el episodio se "consolida" y guarda en la base de datos vectorial SQLite (`memory.db`). En la Web UI, como es una Single Page Application de uso continuo (nunca se cierra explícitamente enviando un "EOF"), la memoria semántica puede que no se esté consolidando de forma predecible.
    *   *Nota importante de diagnóstico:* La memoria no está completamente rota. En pruebas recientes, el agente demostró poder recordar perfectamente el contexto analizado en sesiones previas del mismo día (ej. topología de red, roles de Heimdall vs Pi-hole VM, proxy Nginx y advertencias de falta de sincronización de Whitelists en Pi-hole). Esto indica que el guardado subyacente funciona parcialmente en la Web UI, pero el *trigger* (cuándo o cómo se guarda al no haber un evento de "cierre") debe perfeccionarse.
*   **Posible Solución:**
    *   **Opción A (Recomendada/Ideal): Guardado Automático.** Auditar la ruta de código en `web_server.py` para asegurar que las llamadas a `memoria.guardar()` y `memory_consolidator.py` se estén ejecutando de forma autónoma. Diseñar una lógica de consolidación asíncrona: por ejemplo, guardar automáticamente el contexto después de N minutos de inactividad, o consolidar forzosamente al finalizar de procesar cada comando especial como una `/task` vía web.
    *   **Opción B: Guardado Manual.** Incorporar en la interfaz de usuario un botón explícito de "Guardar Memoria del Chat" o "Finalizar Chat" que envíe una señal al backend para gatillar la función de consolidación del historial antes de limpiar la pantalla.

---

## 9. Paneles Laterales Colapsables e Independientes (UI/UX)

*   **Problemática:** Los menús de la barra lateral derecha de la Web UI (Modelos, Sistema, Centinela, Memoria) se cortan o no entran enteros si la pantalla es chica a lo alto, al no contar con un scroll independiente ni la capacidad de minimizarse.
*   **Posible Solución:**
    *   **Paneles Colapsables:** Modificar el HTML y JS para que el usuario pueda minimizar cada bloque individualmente (ej. ocultar la extensa lista de modelos de LM Studio haciendo click en su título) estilo acordeón.
    *   **Scroll Independiente:** Aplicar estilos CSS (`overflow-y: auto`, `flex-shrink: 0`) al contenedor padre de la barra lateral. De esta forma, tendrá su propia barra de desplazamiento vertical independiente al área principal de chat, sin que se aplasten o distorsionen las tarjetas internas.

---

## 10. Estabilidad: Bloqueo Persistente en SQLite (Centinela)

*   **Problemática:** En el archivo `sentinel.log` de la VM, se detectan errores de tipo `database is locked` en momentos donde el proceso principal (servidor web u operaciones de background) mantiene SQLite ocupado. A pesar de tener habilitado el modo WAL y reintentos, el Centinela no logra enviar su mensaje al bus porque el bloqueo perdura más allá de su umbral de tolerancia (5 segundos).
*   **Posible Solución:**
    *   **Conexiones Efímeras:** Auditar y reestructurar la lógica de conexión en `agent_core.py` y `web_server.py` para asegurar que las consultas usen un bloque `with` (context manager) o cierren el cursor/conexión *inmediatamente* tras su uso.
    *   **Incremento del Timeout:** Configurar el `PRAGMA busy_timeout` o el timeout de la conexión a un valor mucho más alto (ej. `30000` o `60000` milisegundos) en todas las instancias que abren la base de datos (tanto en el agente como en el centinela).

---

## 11. Estabilidad: Caída Silenciosa de la Web UI (`JSON decode error`)

*   **Problemática:** Se reportó que la interfaz web "dejó de funcionar". Al investigar, se observó que el demonio `python web_server_start.py` seguía vivo y escuchando en el puerto 7860, pero la API estaba rebotando peticiones con un `422 Unprocessable Entity` (`JSON decode error`). Esto ocasiona que el navegador quede "congelado" esperando respuestas válidas.
*   **Posible Solución:**
    *   **Sanitización en el Frontend:** Revisar el código JavaScript (`app.js` u homólogo) para asegurar que nunca se envíe un payload con variables `undefined` o formatos JSON mal construidos. Ocurre comúnmente al enviar un estado inicial vacío (ej. cambiando de modelo sin tener uno seleccionado).
    *   **Manejo de Errores Robustos:** Implementar en el frontend un `.catch()` global o un control sobre los códigos HTTP que devuelva un `toast` o alerta visual al usuario indicando que hubo un error de comunicación, para evitar la sensación de que "dejó de funcionar" silenciosamente.
