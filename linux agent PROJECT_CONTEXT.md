# PROJECT_CONTEXT.md — Linux Local AI Agent

> **Documento de contexto para LLMs.**  
> Si estás leyendo esto, es para que entiendas la arquitectura y el estado del proyecto
> antes de ayudar con modificaciones, debugging o extensiones.

---

## ¿Qué es este proyecto?

**Linux Local AI Agent** es un agente de IA autónomo que corre en Ubuntu Linux y puede ejecutar comandos bash, buscar en internet, leer/escribir archivos, conectarse por SSH a hosts remotos, monitorear el sistema en segundo plano (Centinela) y recibir/enviar mensajes por Telegram. Usa un sistema de *function/tool calling* donde el LLM decide qué herramientas invocar en respuesta a pedidos en lenguaje natural.

**Repo GitHub:** https://github.com/Juampeeh/linux-agent  
**VM principal:** `ssh test@192.168.0.162` (pw: `12344321`)  
**LM Studio en LAN:** `http://192.168.0.142:1234/v1` (modelo preferido: `google/gemma-4-26b-a4b`)  
**Ruta en VM:** `/home/test/linux_agent/`  
**Ruta en Windows:** `d:\VS proyects\Linux Agent\`

---

## Stack técnico

- **Python 3.10+**
- **rich** → CLI con colores, paneles, tablas, prompts
- **openai** → cliente para LM Studio, Ollama, Grok, OpenAI (API compatible)
- **google-genai** → cliente oficial para Gemini
- **anthropic** → cliente oficial para Claude
- **python-dotenv** → carga de `.env`
- **httpx** → llamadas HTTP para carga de modelos LM Studio y embeddings
- **numpy** → similitud coseno para la capa de memoria vectorial
- **sqlite3** → (builtin) almacenamiento de la memoria semántica
- **subprocess** → ejecución de comandos bash locales (streaming + timeout)
- **paramiko** → SSH/SFTP (deploy desde Windows + herramienta execute_ssh del agente)
- **ddgs / duckduckgo_search** → búsquedas web sin API key (DuckDuckGo)
- **python-telegram-bot** → bot Telegram para alertas y control remoto
- **wakeonlan** → paquetes Wake-on-LAN

---

## Arquitectura del proyecto (v3.4)

```
linux_agent/
├── main.py               ← Entry point. Banner + menú motor + bucle chat + sentinel control
├── config.py             ← Carga .env, expone 40+ constantes tipadas
├── agent_core.py         ← AgentSession v3.4: permisos 3-modo (smart/safe/auto), sync model_id, Agency routing
├── agency_router.py      ← 🔢 NUEVO Router de personalidades Agency-Agents (auto-detección + /agente <clave>)
├── tools.py              ← execute_local_bash(): subprocess + streaming + timeout + modos bool|str
├── tools_web.py          ← web_search(): DuckDuckGo via ddgs, sin API key
├── tools_files.py        ← read_file() + write_file() con preview/confirmación
├── tools_remote.py       ← execute_ssh() via paramiko, wake_on_lan(), modos bool|str
├── sentinel.py           ← Daemon independiente v4.0: análisis Multi-Host (N-Nodos vía SSH) + Auto-Repair + LLM + WAL
├── agentic_loop.py       ← AgenticTaskRunner: /task con reintentos + memoria + web (firma bool|str)
├── memory_consolidator.py← Consolida episodios en memoria al terminar /task
├── telegram_bot.py       ← Bot async Telegram: polling + InlineKeyboard + alertas
├── web_server.py         ← FastAPI v3.4: REST + WS chat + WS eventos + timeout 8s LM Studio
├── web_server_start.py   ← Launcher del servidor web (usado en producción con nohup)
├── setup.py              ← Instalador automático (venv + deps + .env)
├── install_system.py     ← Instala deps en Python del sistema (sin venv)
├── test_agent.py         ← Suite de 19 tests: imports, bash, E2E LLM, memoria
│
├── agency_prompts/       ← 🔢 NUEVO Prompts especializados (Agency-Agents adaptados)
│   ├── engineering-sre.md
│   ├── engineering-devops-automator.md
│   ├── engineering-security-engineer.md
│   ├── engineering-incident-response-commander.md
│   └── support-infrastructure-maintainer.md
│
├── llm/
│   ├── base.py           ← ABC: AgenteIA, RespuestaAgente, ToolCallCanonico
│   ├── history.py        ← HistorialCanonico + reducir() con anclaje de último prompt
│   ├── memory.py         ← MemoriaSemantica v2.1: SQLite WAL + coseno + embeddings + TTL
│   ├── router.py         ← crear_agente(), motores_disponibles(), fallback
│   ├── tool_registry.py  ← HERRAMIENTAS[8 tools], SYSTEM_PROMPT dinámico, conversores
│   ├── lmstudio_agent.py ← Adaptador LM Studio (OpenAI-compatible, JIT retry, model sync)
│   ├── ollama_agent.py   ← Adaptador Ollama (OpenAI-compatible)
│   ├── gemini_agent.py   ← Adaptador Google Gemini (SDK nativo)
│   ├── openai_agent.py   ← Adaptador OpenAI ChatGPT (SDK nativo)
│   ├── grok_agent.py     ← Adaptador Grok xAI (OpenAI-compatible)
│   └── anthropic_agent.py← Adaptador Anthropic Claude (SDK nativo)
│
├── web/                  ← Activos de la Web UI v3.4 (servidos desde /static)
│   ├── index.html        ← SPA: chat + selector modelo unificado + botón Cancelar + quick-cmds
│   ├── style.css         ← Dark + glassmorphism + cancel-btn + model-live-dot + responsive
│   └── app.js            ← WS chat, cancel via WS close, selector modelo completo (live+saved)
│
├── scripts/
│   ├── start_services.sh ← Inicia Web UI + Centinela (sin CLI)
│   ├── start_agent_cli.sh← Inicia el agente CLI (python main.py)
│   ├── setup_autostart.sh← Instala servicio systemd + shortcuts desktop en la VM
│   └── linux-agent.service← Unidad systemd para autostart al boot (Web + Sentinel)
│
├── deploy_to_vm.py       ← [Windows] Sube archivos a VM via SSH/SFTP + tests
├── github_push.py        ← [Windows] Crea repo en GitHub API + git push desde VM
├── vm_cmd.py             ← [Windows] Ejecuta comandos SSH en VM con output UTF-8
├── sync.py               ← [Windows] deploy + tests + GitHub en un comando
│
├── .env                  ← ⚠ GITIGNORED. Credenciales reales.
├── .env.example          ← Plantilla comentada del .env
├── requirements.txt      ← Deps del agente
├── lm_models.json        ← Lista persistente de modelos LM Studio del usuario
├── memory.db             ← ⚠ GITIGNORED. SQLite WAL con memoria semántica vectorial
└── sentinel.log          ← Log del centinela (append-only)
```

---

## Flujo de ejecución (v2.1)

```
main.py
  └─ mostrar_banner()
  └─ menu_motor()              → elige motor (local/ollama/gemini/...)
  └─ bucle_agente(motor)
        └─ crear_agente(motor) → router.py → instancia el adaptador correcto
        └─ agente.inicializar()
        └─ crear_memoria(motor) → llm/memory.py → instancia MemoriaSemantica (modo WAL)
        └─ [si SENTINEL_ENABLED] → _sentinel_start() como daemon PID-tracked
        └─ [bucle while True]
              └─ _procesar_alertas_sentinel() → verifica bus SQLite (no bloquea)
              └─ PromptSession.prompt()  → input del usuario (prompt_toolkit, historial persistente)
              └─ /comandos especiales → procesados directo (no van al LLM)
              └─ historial.agregar_usuario(user_input)   ← sin inyección RAG (v2.1)
              └─ _procesar_turno(agente, historial, require_confirmation, memoria)
                    └─ [loop MAX_ITERACIONES=10]
                          └─ agente.enviar_turno(historial, HERRAMIENTAS[8])
                                └─ RespuestaAgente(texto, tool_calls)
                          └─ if tool_calls:
                                └─ ejecutar_tool(tc.nombre, tc.argumentos, ..., memoria)
                                      └─ execute_local_bash → tools.py
                                      └─ web_search       → tools_web.py
                                      └─ read_file        → tools_files.py
                                      └─ write_file       → tools_files.py
                                      └─ execute_ssh      → tools_remote.py
                                      └─ wake_on_lan      → tools_remote.py
                                      └─ memory_search    → memoria.buscar()     [v2.1]
                                      └─ memory_get_details → memoria.obtener_detalle() [v2.1]
                                └─ historial.agregar_resultado_tool(...)
                                └─ memoria.guardar_si_exitoso(tool, args, resultado)
                          └─ else: mostrar respuesta final, break
```

### Diferencia clave v2.0 → v2.1: Progressive Disclosure de Memoria

En v2.0, antes de enviar cada mensaje al LLM se buscaba en memoria y se inyectaba el texto completo de los recuerdos. Esto causaba Context Overflow (Error 400) con consultas que necesitaban varias búsquedas web.

En v2.1, **no hay inyección automática de RAG**. El agente recibe solo el mensaje del usuario. Cuando necesita contexto de sesiones pasadas, él decide invocar `memory_search` (obtiene resúmenes ligeros) y luego `memory_get_details` solo si necesita el contenido completo.

---

## Clases clave

### `AgenteIA` (abstract — `llm/base.py`)
```python
class AgenteIA(ABC):
    @property
    @abstractmethod
    def nombre_motor(self) -> str: ...

    @abstractmethod
    def enviar_turno(self, historial: HistorialCanonico, herramientas: list[dict]) -> RespuestaAgente: ...

    def inicializar(self) -> None: ...  # hook opcional
```

### `RespuestaAgente` (`llm/base.py`)
```python
@dataclass
class RespuestaAgente:
    texto: str = ""
    tool_calls: list[ToolCallCanonico] = field(default_factory=list)

    @property
    def tiene_tool_calls(self) -> bool: ...
```

### `HistorialCanonico` (`llm/history.py`)
Almacena mensajes en formato interno y los serializa a 3 formatos:
- `.to_openai()` → `list[dict]` para OpenAI / LM Studio / Grok / Ollama
- `.to_gemini()` → `(system_instruction, history)` para SDK de Gemini
- `.to_anthropic()` → `(system_prompt, messages)` para SDK de Anthropic
- `.reducir(mantener_ultimos=6)` → trim de historial ante Context Overflow

---

## Herramientas disponibles para el LLM (v2.1 — 8 tools)

```python
HERRAMIENTAS = [
    "execute_local_bash",   # bash en el sistema local (streaming + timeout)
    "web_search",           # DuckDuckGo sin API key
    "read_file",            # leer archivo del sistema con syntax highlight
    "write_file",           # escribir/append archivo (confirmación en modo seguro)
    "execute_ssh",          # comando bash en host remoto via paramiko
    "wake_on_lan",          # magic packet para encender equipos remotos
    "memory_search",        # [v2.1] búsqueda semántica → retorna ID + resumen_corto
    "memory_get_details",   # [v2.1] carga contenido completo por ID
]
```

La herramienta se convierte al formato de cada API:
- `to_openai_format()` → para OpenAI/LM Studio/Grok/Ollama
- `to_gemini_format()` → para Gemini SDK
- `to_anthropic_format()` → para Anthropic SDK

---

## Memoria Semántica Persistente — v2.1 (`llm/memory.py`)

### Tecnología
- **Almacenamiento:** `sqlite3` builtin (`memory.db`, portable, gitignored)
- **Embeddings:** `/v1/embeddings` del motor activo (LM Studio: `nomic-embed-text-v1.5` → 768 dims)
- **Similitud:** coseno con `numpy`. Sub-5ms sobre corpus de hasta 2000 entradas.
- **Migración automática:** agrega columnas nuevas sin perder datos existentes

### Schema de la tabla `memorias`
```sql
CREATE TABLE memorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido TEXT NOT NULL,        -- texto completo del recuerdo
    resumen_corto TEXT,             -- [v2.1] resumen de 1-2 frases para búsquedas ligeras
    embedding BLOB NOT NULL,        -- vector float32 serializado
    tipo TEXT,                      -- ver tabla de tipos abajo
    metadata TEXT,                  -- JSON adicional
    embedding_provider TEXT,        -- namespace del vector
    created_at REAL,                -- Unix timestamp
    expires_at REAL,                -- NULL = permanente; TTL para logs crudos
    accesses INTEGER DEFAULT 0      -- contador de accesos
);
```

### Tipos de memoria
| Tipo | Qué guarda | TTL |
|------|-----------|-----|
| `respuesta_agente` | Par Q&A: pregunta + respuesta (>80 chars) | Permanente |
| `comando_exitoso` | Bash exitoso + primeras líneas del output | Permanente |
| `web_research` | Hallazgos de búsquedas web útiles | Configurable |
| `env_map` | Mapa del entorno: IPs, rutas, configs descubiertas | Permanente |
| `insight` | Episodio consolidado por LLM al terminar /task | Permanente |
| `log_crudo` | Logs de sistema analizados por el centinela | 24h (auto-purga) |

### API de la clase `MemoriaSemantica`
```python
from llm.memory import crear_memoria

memoria = crear_memoria(motor_key="local")  # factory principal
memoria.activa          # bool — False si el motor no soporta embeddings

# Core
emb = memoria.get_embedding("texto")                    # list[float] | None
memoria.guardar(contenido, tipo, metadata, resumen_corto)  # persiste en SQLite
memoria.buscar(query, top_k=3, threshold=0.75)          # list[dict] con id, similitud, resumen_corto
memoria.obtener_detalle(id_memoria)                     # str — contenido completo por ID [v2.1]
memoria.guardar_si_exitoso(tool, args, resultado)        # hook post-tool

# Gestión
stats = memoria.stats()                     # dict con total, por_tipo, db_size_kb
memoria.purgar_expirados()                  # borra memorias con expires_at vencido
memoria.limpiar()                           # borra memorias del provider actual
memoria.cerrar()                            # cierra conexión SQLite

# Bus centinela
memoria.enviar_mensaje_sentinel(source, type_, payload)
memoria.leer_mensajes_sentinel(source_filter, solo_no_leidos)
memoria.marcar_leidos_sentinel(ids)
```

### Namespaces de vectores
| Motor | Provider | Embeddings |
|-------|----------|------------|
| `local` (LM Studio) | `"local"` | `/v1/embeddings` OpenAI-compat |
| `ollama` | `"local"` | `/v1/embeddings` OpenAI-compat (mismo namespace) |
| `chatgpt` | `"openai"` | `text-embedding-3-small` |
| `gemini` | `"gemini"` | `text-embedding-004` |
| `grok` | `None` | Sin API de embeddings → memoria desactivada |
| `claude` | `None` | Sin API de embeddings → memoria desactivada |

---

## Centinela (`sentinel.py`) — v4.0 Multi-Host

Proceso daemon independiente rediseñado para escanear *N* servidores remotos además de la VM local:

- **Multi-Host:** Escanea N-hosts por SSH definidos en `.env` (ej: Heimdall físico + VM Pi-hole).
- **Auto-Repair:** Intenta `systemctl restart` automáticamente si detecta servicios críticos caídos (pihole, nginx, etc.).
- **Filtrado JSON:** Filtra masivos `eve.json` de Suricata localmente vía bash remoto para evitar Context Overflow.
- **Comunicación:** bus de mensajes via tabla `sentinel_messages` en `memory.db` (con retry system para evitar lock de DB).
- **Persistencia:** archivo `.sentinel.pid` para rastreo cross-sesión.
- **Desvinculación:** `DETACHED_PROCESS` (Windows) / `start_new_session=True` (Linux).
- **JIT Fallback:** si LM Studio tira 400 "No models loaded":
  1. Lee `lm_models.json` → toma el primer modelo
  2. Fallback a `SENTINEL_LLM_MODEL` del `.env`
  3. Fallback a `llama-3.2-3b-instruct` como último recurso

```bash
# Uso desde CLI:
/sentinel start   # lanza como daemon
/sentinel stop    # mata el proceso por PID
/sentinel status  # lee el último ciclo del bus SQLite

# Uso directo:
python sentinel.py          # loop continuo (produción)
python sentinel.py --once   # un solo ciclo (testing)
```

---

## Variables de entorno (`.env`) — v2.1 completo

| Variable | Default | Descripción |
|----------|---------|-------------|
| `LMSTUDIO_BASE_URL` | `http://192.168.0.142:1234/v1` | URL LM Studio |
| `LMSTUDIO_MODEL` | `""` | Modelo chat (vacío=autodetectar) |
| `LMSTUDIO_EMBED_MODEL` | `""` | Modelo embeddings LM Studio |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | URL Ollama |
| `OLLAMA_MODEL` | `llama3` | Modelo Ollama |
| `OLLAMA_EMBED_MODEL` | `""` | Modelo embeddings Ollama |
| `GEMINI_API_KEY` | `""` | Key Gemini |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini |
| `OPENAI_API_KEY` | `""` | Key OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modelo OpenAI |
| `GROK_API_KEY` | `""` | Key Grok xAI |
| `GROK_MODEL` | `grok-3-mini` | Modelo Grok |
| `ANTHROPIC_API_KEY` | `""` | Key Anthropic |
| `ANTHROPIC_MODEL` | `claude-3-5-haiku-20241022` | Modelo Claude |
| `REQUIRE_CONFIRMATION` | `True` | Confirmar comandos bash |
| `COMMAND_TIMEOUT` | `60` | Timeout bash en segundos |
| `DEFAULT_ENGINE` | `local` | Motor al arrancar |
| `MAX_OUTPUT_CHARS` | `4000` | Límite chars output al LLM |
| `MEMORY_ENABLED` | `True` | Activa memoria semántica |
| `MEMORY_TOP_K` | `3` | Recuerdos a retornar por búsqueda |
| `MEMORY_THRESHOLD` | `0.75` | Similitud mínima (0.0–1.0) |
| `MEMORY_MAX_ENTRIES` | `2000` | Límite de entradas (auto-purga) |
| `MEMORY_SHARED_EMBED` | `False` | Usar LM Studio para embeddings de todos los motores |
| `MEMORY_CONSOLIDATE_ON_TASK` | `True` | Consolidar episodio al terminar /task |
| `SENTINEL_ENABLED` | `False` | Iniciar centinela al arrancar |
| `SENTINEL_INTERVAL_SECONDS` | `300` | Frecuencia del ciclo del centinela |
| `SENTINEL_LOG_TAIL_LINES` | `100` | Líneas de log a analizar por ciclo |
| `SENTINEL_LLM_URL` | (usa LMSTUDIO_BASE_URL) | URL del LLM para el centinela |
| `SENTINEL_LLM_MODEL` | `""` | Modelo fijo para el centinela (vacío=JIT auto) |
| `SENTINEL_HEIMDALL_ENABLED` | `False` | Monitoreo remoto de Heimdall |
| `TELEGRAM_ENABLED` | `False` | Activar bot Telegram |
| `TELEGRAM_BOT_TOKEN` | `""` | Token del BotFather |
| `TELEGRAM_ALLOWED_IDS` | `""` | Chat IDs permitidos (separados por coma) |
| `WEB_SEARCH_ENABLED` | `True` | Activar búsqueda web |
| `WEB_SEARCH_MAX_RESULTS` | `5` | Resultados por búsqueda |
| `WOL_BROADCAST` | `192.168.0.255` | Broadcast para Wake-on-LAN |
| `SSH_DEFAULT_TIMEOUT` | `30` | Timeout SSH en segundos |
| `AGENTIC_MAX_RETRIES` | `5` | Fallos máximos en /task |
| `AGENTIC_USE_WEB_ON_FAIL` | `True` | Buscar en web si un paso bash falla |
| `AGENTIC_MAX_ITERATIONS` | `20` | Iteraciones máximas en /task |
| `VM_HOST` | `192.168.0.162` | IP VM (solo scripts Windows) |
| `VM_PORT` | `22` | Puerto SSH (solo scripts Windows) |
| `VM_USER` | `test` | Usuario SSH (solo scripts Windows) |
| `VM_PASS` | — | Contraseña SSH (solo scripts Windows) |
| `REMOTE_DIR` | `/home/test/linux_agent` | Ruta en VM |
| `GITHUB_USER` | `Juampeeh` | Username GitHub |
| `GITHUB_EMAIL` | `Juampeeh@hotmail.com` | Email GitHub |
| `GITHUB_REPO` | `linux-agent` | Nombre del repositorio |

---

## Comandos del CLI (completo)

| Comando | Descripción |
|---------|-------------|
| `/auto` | Toggle modo autónomo ↔ seguro |
| `/confirm` | Alias de `/auto` |
| `/task <descripción>` | Agentic Loop con reintentos inteligentes |
| `/web <query>` | Búsqueda web manual (DuckDuckGo) |
| `/switch <motor>` | Cambia motor de IA en caliente |
| `/engines` | Lista motores disponibles y activo |
| `/model` | Selecciona modelo LM Studio |
| `/sentinel start/stop/status` | Control del daemon centinela |
| `/telegram status` | Estado del bot Telegram |
| `/export` | Guarda sesión como `.md` |
| `/clear` | Limpia historial de conversación |
| `/memory stats` | Estadísticas de la memoria semántica |
| `/memory purge` | Purga memorias expiradas por TTL |
| `/memory clear` | Borra memorias del provider actual |
| `/ayuda` | Tabla de ayuda completa |
| `Ctrl+C` | Salir (el centinela sigue vivo si está activo) |
| `↑ / ↓` | Navegar historial de comandos (readline) |

---

## Estado actual (Abril 2026 — v3.0)

- ✅ **Web UI v3.0** — FastAPI + WebSocket en puerto `7860`, accesible desde LAN
- ✅ **Confirmaciones inteligentes** — En la Web UI: escribir `ok`/`y`/`n` en el chat aprueba/rechaza la ejecución sin hacer clic
- ✅ **Memoria SQLite en modo WAL** — Múltiples procesos simultáneos (web + CLI + sentinel) sin bloqueos de DB
- ✅ **prompt_toolkit en CLI** — Navegación multilínea completa por SSH (igual que PowerShell)
- ✅ **Anclaje de contexto** — `reducir()` preserva siempre el último prompt del usuario ante Context Overflow
- ✅ **Advertencia proactiva al LLM** — Al leer archivos grandes, el LLM recibe instrucción de usar grep/rangos
- ✅ **JIT Fallback mejorado en Sentinel** — Consulta la API de LM Studio para obtener el modelo activo real
- ✅ **Scripts de mantenimiento Windows** — `vm_diagnostics.py` y `vm_fix.py` para diagnóstico y reparación remota
- ✅ **19/19 tests** pasando en VM `192.168.0.162`
- ✅ **LM Studio** conectado en `192.168.0.142:1234` — modelos activos: `google/gemma-4-31b`, `google/gemma-4-26b-a4b`, `nvidia/nemotron-3-nano-4b`
- ✅ **8 herramientas** disponibles para el LLM (bash, web, archivos, SSH, WoL, memoria x2)
- ✅ **GitHub** publicado: https://github.com/Juampeeh/linux-agent
- ✅ **Progressive Disclosure** — memoria bajo demanda sin Context Overflow
- ✅ **Sentinel daemon v4.0** — Multi-Host, monitorea local, Heimdall (ZFS/Pi-hole principal) y VM Pi-hole (backup) concurrentemente.
- ✅ **Auto-Repair del Centinela** — Reinicia automáticamente servicios críticos sin preguntar.
- ✅ **Telegram bot** — alertas automáticas
- ✅ **Agentic Loop** `/task` con reintentos: memoria → web → reintento
- ✅ **Streaming bash** con `select` + timeout global
- ✅ **System prompt dinámico** con fecha/hora del sistema inyectada
- ⬜ Ollama en VM no probado (no instalado en la VM de prueba)

---

## Comportamiento LM Studio — carga de modelos

`/api/v0/models/load` **no funciona** en la versión actual de LM Studio.
`inicializar()` ya **no** dispara esta llamada. Flujo real:

1. `enviar_turno()` envía el request con el `model_id` seleccionado
2. Si LM Studio responde OK → retorna la respuesta
3. Si LM Studio retorna `BadRequestError: "No models loaded"`:
   - **Intento 0**: espera 15s, muestra mensaje `⏳`
   - **Intento ≥1**: también prueba con `model="local-model"` (cualquier modelo activo)
4. Tras `_REINTENTOS_CARGA=4` intentos (~60s): `RuntimeError` claro al usuario.

---

## Cómo agregar un nuevo motor LLM

1. Crear `llm/nuevo_agent.py` extendiendo `AgenteIA`
2. Registrar en `config.py` → `MOTORES_DISPONIBLES`
3. Agregar en `llm/router.py` → `crear_agente()` y `motores_disponibles()`
4. Agregar variables en `.env.example`
5. Agregar en `deploy_to_vm.py` → `FILES_TO_UPLOAD`

---

## Cómo agregar una nueva herramienta

1. Implementar la función en `tools*.py`
2. Agregar definición en `llm/tool_registry.py` → `HERRAMIENTAS[]`
3. Agregar el dispatch en `agentic_loop.py` → `ejecutar_tool()`
4. Actualizar `SYSTEM_PROMPT` en `tool_registry.py` para que el agente sepa que existe
