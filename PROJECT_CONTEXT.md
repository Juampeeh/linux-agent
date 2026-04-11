# PROJECT_CONTEXT.md — Linux Local AI Agent

> **Documento de contexto para LLMs.**  
> Si estás leyendo esto, es para que entiendas la arquitectura y el estado del proyecto
> antes de ayudar con modificaciones, debugging o extensiones.

---

## ¿Qué es este proyecto?

**Linux Local AI Agent** es un agente de IA interactivo que corre en Ubuntu Linux y puede ejecutar comandos bash directamente en el sistema. Usa un sistema de tool calling (function calling) donde el LLM decide qué comandos ejecutar en respuesta a pedidos en lenguaje natural del usuario.

**Repo GitHub:** https://github.com/Juampeeh/linux-agent  
**VM principal:** `ssh test@192.168.0.162` (pw: `12344321`)  
**LM Studio en LAN:** `http://192.168.0.142:1234/v1`  
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
- **httpx** → llamadas HTTP para carga de modelos LM Studio
- **subprocess** → ejecución de comandos bash locales
- **paramiko** → SSH/SFTP para scripts de deploy desde Windows (solo dev)

---

## Arquitectura del proyecto

```
linux_agent/
├── main.py               ← Entry point. Banner + menú de motor + bucle de chat
├── config.py             ← Carga .env, expone constantes tipadas
├── tools.py              ← execute_local_bash(): subprocess + confirmación
├── setup.py              ← Instalador automático (venv + deps + .env)
├── test_agent.py         ← Suite de tests (12 tests: imports, bash, E2E LLM)
│
├── llm/
│   ├── __init__.py
│   ├── base.py           ← ABC: AgenteIA, RespuestaAgente, ToolCallCanonico
│   ├── history.py        ← HistorialCanonico (serializa a OpenAI/Gemini/Anthropic)
│   ├── router.py         ← crear_agente(), motores_disponibles(), fallback
│   ├── tool_registry.py  ← HERRAMIENTAS[], SYSTEM_PROMPT, conversores de formato
│   ├── lmstudio_agent.py ← Adaptador LM Studio (OpenAI-compatible)
│   ├── ollama_agent.py   ← Adaptador Ollama (OpenAI-compatible)
│   ├── gemini_agent.py   ← Adaptador Google Gemini (SDK nativo)
│   ├── openai_agent.py   ← Adaptador OpenAI ChatGPT (SDK nativo)
│   ├── grok_agent.py     ← Adaptador Grok xAI (OpenAI-compatible)
│   └── anthropic_agent.py← Adaptador Anthropic Claude (SDK nativo)
│
├── deploy_to_vm.py       ← [Windows] Sube archivos a VM via SSH/SFTP + tests
├── github_push.py        ← [Windows] Crea repo en GitHub API + git push desde VM
├── run_tests_on_vm.py    ← [Windows] Ejecuta test_agent.py en VM via SSH
├── sync.py               ← [Windows] deploy + tests + GitHub en un comando
│
├── .env                  ← ⚠ GITIGNORED. Credenciales reales. No commitear.
├── .env.example          ← Plantilla comentada del .env
├── requirements.txt      ← Deps del agente (openai, rich, google-genai, etc.)
├── requirements-dev.txt  ← Deps de dev: paramiko (solo Windows)
├── lm_models.json        ← Lista persistente de modelos LM Studio del usuario
├── README.md             ← Documentación pública
└── MANUAL.md             ← Manual de usuario completo
```

---

## Flujo de ejecución

```
main.py
  └─ mostrar_banner()
  └─ menu_motor()              → elige motor (local/ollama/gemini/...)
  └─ bucle_agente(motor)
        └─ crear_agente(motor) → router.py → instancia el adaptador correcto
        └─ agente.inicializar()
        └─ [bucle while True]
              └─ Prompt.ask()  → input del usuario
              └─ /comandos especiales → procesados directo
              └─ historial.agregar_usuario(texto)
              └─ _procesar_turno(agente, historial, require_confirmation)
                    └─ [loop MAX_ITERACIONES=10]
                          └─ agente.enviar_turno(historial, HERRAMIENTAS)
                                └─ RespuestaAgente(texto, tool_calls)
                          └─ if tool_calls:
                                └─ ejecutar_bash(comando, require_confirmation)
                                └─ historial.agregar_resultado_tool(...)
                          └─ else: mostrar respuesta final, break
```

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

### `ToolCallCanonico` (`llm/base.py`)
```python
@dataclass
class ToolCallCanonico:
    call_id: str
    nombre: str
    argumentos: dict[str, Any]
```

### `HistorialCanonico` (`llm/history.py`)
Almacena mensajes en formato interno y los serializa a 3 formatos:
- `.to_openai()` → `list[dict]` para OpenAI / LM Studio / Grok / Ollama
- `.to_gemini()` → `(system_instruction, history)` para SDK de Gemini
- `.to_anthropic()` → `(system_prompt, messages)` para SDK de Anthropic

```python
historial = HistorialCanonico(system_prompt=SYSTEM_PROMPT)
historial.agregar_usuario("texto")
historial.agregar_asistente("texto", tool_calls=[...])
historial.agregar_resultado_tool(tool_call_id, nombre, resultado)
historial.limpiar(preservar_system=True)
historial.exportar_markdown()
```

---

## Herramientas disponibles para el LLM

Solo hay una herramienta por ahora (`llm/tool_registry.py`):

```python
HERRAMIENTAS = [{
    "nombre": "execute_local_bash",
    "descripcion": "Ejecuta un comando bash en el sistema Linux local...",
    "parametros": {
        "type": "object",
        "properties": {
            "comando": {"type": "string", "description": "El comando bash a ejecutar"}
        },
        "required": ["comando"]
    }
}]
```

La herramienta se convierte al formato de cada API:
- `to_openai_format()` → para OpenAI/LM Studio/Grok/Ollama
- `to_gemini_format()` → para Gemini SDK
- `to_anthropic_format()` → para Anthropic SDK

---

## Variables de entorno (`.env`)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `LMSTUDIO_BASE_URL` | `http://192.168.0.142:1234/v1` | URL LM Studio |
| `LMSTUDIO_MODEL` | `""` | Modelo específico (vacío=autodetectar) |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | URL Ollama |
| `OLLAMA_MODEL` | `llama3` | Modelo Ollama |
| `GEMINI_API_KEY` | `""` | Key Gemini (activa el motor si hay valor) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Modelo Gemini |
| `OPENAI_API_KEY` | `""` | Key OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modelo OpenAI |
| `GROK_API_KEY` | `""` | Key Grok xAI |
| `GROK_MODEL` | `grok-3-mini` | Modelo Grok |
| `ANTHROPIC_API_KEY` | `""` | Key Anthropic |
| `ANTHROPIC_MODEL` | `claude-3-5-haiku-20241022` | Modelo Claude |
| `REQUIRE_CONFIRMATION` | `True` | Confirmar comandos bash |
| `COMMAND_TIMEOUT` | `30` | Timeout bash en segundos |
| `DEFAULT_ENGINE` | `local` | Motor al arrancar |
| `MAX_OUTPUT_CHARS` | `4000` | Límite chars output al LLM |
| `VM_HOST` | `192.168.0.162` | IP VM (solo scripts Windows) |
| `VM_PORT` | `22` | Puerto SSH (solo scripts Windows) |
| `VM_USER` | `test` | Usuario SSH (solo scripts Windows) |
| `VM_PASS` | — | Contraseña SSH (solo scripts Windows) |
| `REMOTE_DIR` | `/home/test/linux_agent` | Ruta en VM |
| `GITHUB_USER` | `Juampeeh` | Username GitHub |
| `GITHUB_EMAIL` | `Juampeeh@hotmail.com` | Email GitHub |
| `GITHUB_REPO` | `linux-agent` | Nombre del repositorio |

---

## Cómo agregar un nuevo motor LLM

1. Crear `llm/nuevo_agent.py` extendiendo `AgenteIA`:
```python
from .base import AgenteIA, RespuestaAgente, ToolCallCanonico
from .history import HistorialCanonico

class NuevoAgente(AgenteIA):
    @property
    def nombre_motor(self) -> str:
        return "Nombre del motor"

    def inicializar(self) -> None:
        # verificar conexión / key
        pass

    def enviar_turno(self, historial, herramientas) -> RespuestaAgente:
        # llamar a la API
        # retornar RespuestaAgente(texto=..., tool_calls=[...])
        pass
```

2. Registrar en `config.py` → `MOTORES_DISPONIBLES`
3. Agregar en `llm/router.py` → `crear_agente()` y `motores_disponibles()`
4. Agregar variables en `.env.example`
5. Agregar en `deploy_to_vm.py` → `FILES_TO_UPLOAD`

---

## Estado actual (Abril 2026)

- ✅ **12/12 tests** pasando en VM `192.168.0.162`
- ✅ **LM Studio** conectado en `192.168.0.142:1234` con 14+ modelos disponibles
- ✅ **Tool Call E2E** verificado con `google/gemma-4-26b-a4b`
- ✅ **GitHub** publicado: https://github.com/Juampeeh/linux-agent
- ✅ **`COMMAND_TIMEOUT` = 60s** (subido de 30s)
- ✅ **Carga de modelo LM Studio no-fatal** — si el modelo tarda en cargar, el agente
  continúa y LM Studio lo carga en el primer request de inferencia
- ✅ **`_TIMEOUT_INFER_S` = 120s** — timeout del cliente OpenAI para modelos grandes
- ✅ **`install_system.py`** — instala deps en Python del sistema (sin venv)
- ✅ **Detección de comandos interactivos** en `tools.py` — avisa antes de ejecutar
  comandos que pueden bloquearse (`vim`, `grep -r ~/`, `ls -R ~/`, etc.)
- ⬜ Ollama en VM no instalado (no se probó aún)
- ⬜ APIs de nube (Gemini/Grok/OpenAI/Claude) configurables pero no testeadas en esta VM

## Comportamiento LM Studio — carga de modelos

Cuando el usuario selecciona un modelo del menú (`lm_models.json`), `inicializar()` llama
a `_cargar_modelo_si_necesario()`. Esta función:
1. Verifica si el modelo ya está en `/v1/models` → si sí, retorna
2. Intenta cargar via `/api/v0/models/load` (API nativa LM Studio >= 0.3.x)
3. Hace polling hasta que aparezca en `/v1/models` (máx 180s)
4. Si hay timeout o error HTTP → **lanza `RuntimeError`**, pero `inicializar()` lo captura
   y continúa con un aviso. El agente arranca de todas formas.

Esto evita que el usuario quede bloqueado cuando LM Studio no soporta la API de carga
o cuando el modelo tarda más de lo esperado.
