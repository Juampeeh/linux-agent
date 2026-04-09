# 🤖 Linux Local AI Agent

Agente de inteligencia artificial autónomo que se ejecuta **directamente en Linux**, con interfaz de chat en terminal (CLI) e integración multi-motor de IA.

> A diferencia de un SSH Agent, este agente corre **dentro de la máquina que controla**, usando `subprocess` para ejecutar bash localmente.

---

## ✨ Características

- **CLI interactiva y premiun** usando `rich` con colores, paneles y banners
- **6 motores de IA soportados** — cambiables en caliente sin reiniciar
- **Tool Calling real** — el LLM decide y ejecuta comandos bash autónomamente
- **Modo autónomo / modo seguro** — toggle con `/auto` en cualquier momento
- **Timeout configurable** por comando
- **Exportación de sesiones** como Markdown
- **Setup automático** con `setup.py`

---

## 🚀 Inicio rápido

```bash
# 1. Clonar el repositorio
git clone https://github.com/JuampeehSA/linux-agent.git
cd linux-agent

# 2. Ejecutar el instalador automático
python3 setup.py

# 3. Activar entorno virtual e iniciar
source venv/bin/activate
python main.py
```

---

## 🧠 Motores de IA soportados

| Motor | Requiere Key | Endpoint |
|-------|-------------|---------|
| **LM Studio** | No | `http://192.168.0.142:1234/v1` (configurable) |
| **Ollama** | No | `http://localhost:11434/v1` |
| **Google Gemini** | Sí | `GEMINI_API_KEY` |
| **OpenAI ChatGPT** | Sí | `OPENAI_API_KEY` |
| **Grok (xAI)** | Sí | `GROK_API_KEY` |
| **Anthropic Claude** | Sí | `ANTHROPIC_API_KEY` |

---

## 🔧 Arquitectura

```
linux_agent/
├── main.py               # CLI interactivo: banner + bucle de chat
├── config.py             # Variables de entorno (.env)
├── tools.py              # execute_local_bash (subprocess + rich output)
├── setup.py              # Instalador automático
├── lm_models.json        # Lista persistente de modelos LM Studio
│
└── llm/                  # Motor IA (patrón Strategy)
    ├── base.py            # Clases base: AgenteIA, RespuestaAgente, ToolCallCanonico
    ├── history.py         # HistorialCanonico (normaliza entre APIs)
    ├── router.py          # Factory + motores_disponibles() + fallback automático
    ├── tool_registry.py   # Schema JSON de herramientas
    ├── lmstudio_agent.py  # LM Studio (OpenAI-compatible + carga remota)
    ├── ollama_agent.py    # Ollama (OpenAI-compatible)
    ├── gemini_agent.py    # Google Gemini
    ├── openai_agent.py    # OpenAI ChatGPT
    ├── grok_agent.py      # Grok (xAI)
    └── anthropic_agent.py # Anthropic Claude
```

---

## 💬 Comandos del chat

| Comando | Descripción |
|---------|-------------|
| `/auto` | Toggle entre modo autónomo y modo seguro |
| `/confirm` | Alias de `/auto` |
| `/switch <motor>` | Cambia el motor en caliente (ej: `/switch gemini`) |
| `/engines` | Lista motores disponibles y cuál está activo |
| `/model` | Selecciona modelo LM Studio |
| `/export` | Guarda la sesión como archivo `.md` |
| `/clear` | Limpia el historial de conversación |
| `/ayuda` | Muestra todos los comandos |
| `Ctrl+C` | Sale del agente |

---

## ⚙️ Variables de entorno (.env)

```ini
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1
LMSTUDIO_MODEL=           # vacío = autodetectar

OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3

GEMINI_API_KEY=
OPENAI_API_KEY=
GROK_API_KEY=
ANTHROPIC_API_KEY=

REQUIRE_CONFIRMATION=True  # True = pedir Y antes de ejecutar
COMMAND_TIMEOUT=30
DEFAULT_ENGINE=local
MAX_OUTPUT_CHARS=4000
```

---

## 🔒 Modos de seguridad

**Modo Seguro** (default): el agente muestra el comando propuesto y espera confirmación `Y/n` antes de ejecutarlo.

**Modo Autónomo**: el agente ejecuta comandos sin interrupción. Activar con `/auto` en el chat.

```
🛡️ MODO SEGURO ACTIVADO → escribe /auto para cambiar
⚠️  MODO AUTÓNOMO ACTIVADO → el agente ejecuta sin preguntar
```

---

## 📦 Dependencias

```
openai>=1.0.0          # LM Studio + ChatGPT + Grok (API compatible)
google-genai>=1.0.0    # Gemini SDK
anthropic>=0.40.0      # Claude SDK
python-dotenv>=1.0.0
rich>=13.0.0           # CLI con estilo
httpx>=0.27.0          # Carga remota de modelos en LM Studio
prompt_toolkit>=3.0.0
```

---

## 🧪 Tests

```bash
# En la VM
source venv/bin/activate
python test_agent.py
```

Los tests cubren: imports, bash execution, timeout, conexión LM Studio, y tool call E2E.

---

## 📄 Licencia

MIT — libre uso y modificación.
