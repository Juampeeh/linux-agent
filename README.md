# Linux Local AI Agent

<div align="center">

```
██╗     ██╗███╗   ██╗██╗   ██╗██╗  ██╗      █████╗  ██████╗ ███████╗███╗   ██╗████████╗
██║     ██║████╗  ██║██║   ██║╚██╗██╔╝     ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
██║     ██║██╔██╗ ██║██║   ██║ ╚███╔╝      ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
██║     ██║██║╚██╗██║██║   ██║ ██╔██╗      ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
███████╗██║██║ ╚████║╚██████╔╝██╔╝ ██╗     ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
```

**Agente autónomo de Linux con soporte multi-LLM**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ¿Qué es?

**Linux Local AI Agent** es un agente de IA que corre directamente en un sistema Linux y puede ejecutar comandos bash de forma autónoma según lo que le pedís. Admite múltiples motores de LLM (locales y en la nube) intercambiables en caliente desde la CLI.

### Características

- 🤖 **Multi-motor**: LM Studio, Ollama, Gemini, OpenAI (ChatGPT), Grok (xAI), Anthropic (Claude)
- 🔧 **Tool calling nativo**: el LLM decide qué comandos ejecutar y los corre via `subprocess`
- 🛡️ **Modo seguro / autónomo**: confirmación por comando o ejecución libre (toggle en runtime)
- 🔄 **Hot-swap de motor**: cambiá el LLM sin reiniciar el agente (`/switch gemini`)
- 📝 **Historial exportable**: exportá la sesión como markdown con `/export`
- 🌐 **LM Studio en red LAN**: conectate a un LM Studio corriendo en otra PC de la red

---

## Arquitectura

```
linux_agent/
├── main.py               # Entry point: banner + menú + bucle de chat
├── config.py             # Variables desde .env (dotenv)
├── tools.py              # execute_local_bash (subprocess)
├── setup.py              # Instalador automático (venv + deps + .env)
├── test_agent.py         # Suite de tests integral
└── llm/
    ├── base.py           # Clases abstractas: AgenteIA, RespuestaAgente
    ├── history.py        # HistorialCanonico (OpenAI / Gemini / Anthropic)
    ├── router.py         # Factory de agentes + fallback automático
    ├── tool_registry.py  # Definición de herramientas + conversores de formato
    ├── lmstudio_agent.py # Adaptador LM Studio (OpenAI-compatible)
    ├── ollama_agent.py   # Adaptador Ollama
    ├── gemini_agent.py   # Adaptador Google Gemini
    ├── openai_agent.py   # Adaptador OpenAI ChatGPT
    ├── grok_agent.py     # Adaptador Grok (xAI)
    └── anthropic_agent.py# Adaptador Anthropic Claude
```

---

## Instalación

### Opción A: Setup automático (recomendado)

```bash
git clone https://github.com/JuampeehSA/linux-agent.git
cd linux-agent
python3 setup.py
```

El setup interactivo creará el `venv`, instalará dependencias y configurará el `.env`.

### Opción B: Manual

```bash
git clone https://github.com/JuampeehSA/linux-agent.git
cd linux-agent

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
nano .env  # Completar los valores necesarios
```

---

## Configuración (.env)

```env
# ── Motor local (LM Studio en red LAN) ───────────────────────────────────────
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1
LMSTUDIO_MODEL=                     # vacío = autodetectar

# ── Ollama (local) ────────────────────────────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3

# ── APIs en la nube (opcionales, agregar según necesidad) ─────────────────────
GEMINI_API_KEY=                      # https://aistudio.google.com/apikey
OPENAI_API_KEY=                      # https://platform.openai.com/api-keys
GROK_API_KEY=                        # https://console.x.ai
ANTHROPIC_API_KEY=                   # https://console.anthropic.com

# ── Comportamiento ────────────────────────────────────────────────────────────
REQUIRE_CONFIRMATION=True            # False = modo autónomo
COMMAND_TIMEOUT=30                   # segundos por comando
MAX_OUTPUT_CHARS=4000                # límite de output al LLM
```

> **Nota:** El `.env` nunca se sube a git (está en `.gitignore`).

---

## Uso

```bash
source venv/bin/activate
python main.py
```

1. Seleccionás el motor de IA en el menú
2. Escribís tu pedido en lenguaje natural
3. El agente usa la herramienta `execute_local_bash` para cumplirlo

### Comandos del CLI

| Comando | Descripción |
|---------|-------------|
| `/auto` | Toggle modo autónomo (sin confirmación) |
| `/switch <motor>` | Cambia motor en caliente (ej: `/switch gemini`) |
| `/engines` | Lista motores disponibles |
| `/model` | Selecciona modelo LM Studio |
| `/export` | Exporta la sesión como `.md` |
| `/clear` | Limpia el historial |
| `/ayuda` | Muestra ayuda |
| `Ctrl+C` | Salir |

---

## Motores soportados

| Motor | Clave | Requiere key | Notas |
|-------|-------|-------------|-------|
| LM Studio | `local` | No | API OpenAI-compatible, puede ser en red LAN |
| Ollama | `ollama` | No | Modelos locales via Ollama |
| Google Gemini | `gemini` | Sí | `GEMINI_API_KEY` en `.env` |
| OpenAI ChatGPT | `chatgpt` | Sí | `OPENAI_API_KEY` en `.env` |
| Grok (xAI) | `grok` | Sí | `GROK_API_KEY` en `.env` |
| Anthropic Claude | `claude` | Sí | `ANTHROPIC_API_KEY` en `.env` |

---

## Tests

```bash
source venv/bin/activate
python test_agent.py
```

Prueba: imports, ejecución de bash, conexión a LM Studio, tool call E2E.

---

## Deploy remoto (desde Windows)

Para desplegar en una VM remota via SSH:

```bash
# 1. Instalar dependencias de deploy
pip install paramiko python-dotenv

# 2. Configurar credenciales en .env (sección VM Remota)
#    VM_HOST, VM_PORT, VM_USER, VM_PASS, REMOTE_DIR

# 3. Deploy
python deploy_to_vm.py
```

---

## Licencia

MIT — Libre para uso personal y comercial.
