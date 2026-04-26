# 📖 Manual de Usuario — Linux Local AI Agent

> **Versión:** 3.0.0 | **Plataforma:** Ubuntu Linux (VM/físico) + Windows (desarrollo)
> **Repositorio:** https://github.com/Juampeeh/linux-agent

---

## Tabla de contenidos

1. [Instalación desde cero](#1-instalación-desde-cero)
2. [Inicio rápido](#2-inicio-rápido)
3. [Modo seguro vs. modo autónomo](#3-modo-seguro-vs-modo-autónomo)
4. [Comandos del CLI](#4-comandos-del-cli)
5. [Configurar motores de IA](#5-configurar-motores-de-ia)
   - 5.1 [LM Studio en red LAN](#51-lm-studio-en-red-lan)
   - 5.2 [Ollama en Ubuntu (local)](#52-ollama-en-ubuntu-local)
   - 5.3 [Ollama en red LAN](#53-ollama-en-red-lan)
   - 5.4 [Google Gemini (API Key)](#54-google-gemini-api-key)
   - 5.5 [Grok xAI (API Key)](#55-grok-xai-api-key)
   - 5.6 [OpenAI ChatGPT (API Key)](#56-openai-chatgpt-api-key)
   - 5.7 [Anthropic Claude (API Key)](#57-anthropic-claude-api-key)
6. [Cambiar motor en caliente](#6-cambiar-motor-en-caliente)
7. [Editar configuración (.env)](#7-editar-configuración-env)
8. [Ejecutar sin entorno virtual (venv)](#8-ejecutar-sin-entorno-virtual-venv)
9. [Mantener el proyecto actualizado (Git)](#9-mantener-el-proyecto-actualizado-git)
10. [Referencia de archivos](#10-referencia-de-archivos)
11. [Memoria Semántica](#11-memoria-semántica)
12. [Solución de problemas](#12-solución-de-problemas)
13. [Búsqueda Web (v2.0)](#13-búsqueda-web-v20)
14. [Herramientas de Archivos y SSH (v2.0)](#14-herramientas-de-archivos-y-ssh-v20)
15. [Modo Tarea Autónoma — /task (v2.0)](#15-modo-tarea-autónoma--task-v20)
16. [Centinela de Fondo (v2.0)](#16-centinela-de-fondo-v20)
17. [Telegram — Alertas y Control Remoto (v2.0)](#17-telegram--alertas-y-control-remoto-v20)
18. [Heimdall — Monitoreo Remoto (Fase 2)](#18-heimdall--monitoreo-remoto-fase-2)
19. [Web UI — Interfaz Web (v3.0)](#19-web-ui--interfaz-web-v30)
20. [Referencia de Variables WEB_*](#20-referencia-de-variables-web)

---

## 1. Instalación desde cero

> **Esta sección es para instalar el agente en una Ubuntu nueva** (VM, VPS, servidor físico).
> Si el agente ya está instalado, pasá directo a la [sección 2](#2-inicio-rápido).

### Prerequisitos mínimos

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip
```

> Ubuntu 24.04+ ya trae Python 3.12 instalado. El comando anterior solo
> asegura que git, venv y pip estén disponibles.

---

### Método A — Setup automático con venv (recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/Juampeeh/linux-agent.git
cd linux-agent

# 2. Ejecutar el instalador interactivo
python3 setup.py
```

El setup te va a preguntar:
- **URL de LM Studio** → ingresá `http://IP_DE_TU_PC:1234/v1` (ej: `http://192.168.0.142:1234/v1`)
- **¿Confirmar antes de ejecutar comandos?** → `True` (recomendado) o `False`
- **API Keys** de Gemini, OpenAI, Grok, Claude → presioná Enter para omitir las que no uses

```bash
# 3. Iniciar el agente
source venv/bin/activate
python main.py
```

**Eso es todo.** El agente está listo.

---

### Método B — Sin venv (Python del sistema)

Para poder ejecutar `python3 main.py` directamente sin activar el venv:

```bash
# 1. Clonar
git clone https://github.com/Juampeeh/linux-agent.git
cd linux-agent

# 2. Instalar deps en el Python del sistema
#    (detecta Ubuntu 24.04+ y usa --break-system-packages automáticamente)
python3 install_system.py

# 3. Configurar el .env
cp .env.example .env
nano .env
# Editar al menos: LMSTUDIO_BASE_URL y/o las API keys que uses

# 4. Iniciar
python3 main.py
```

---

### Lo mínimo que hay que editar en `.env`

Abrir con `nano .env` y ajustar solo lo que aplique:

```env
# Si LM Studio corre en otra PC de la red:
LMSTUDIO_BASE_URL=http://192.168.0.XXX:1234/v1

# Si LM Studio corre en la misma máquina:
LMSTUDIO_BASE_URL=http://localhost:1234/v1

# APIs de nube (solo las que tenés):
GEMINI_API_KEY=AIza...
GROK_API_KEY=xai-...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

El resto ya tiene valores por defecto correctos (`COMMAND_TIMEOUT=60`, `REQUIRE_CONFIRMATION=True`, etc.).

---

### Diagrama del flujo de instalación

```
Ubuntu (nueva instancia)
         ↓
sudo apt install git python3 python3-venv python3-pip
         ↓
git clone https://github.com/Juampeeh/linux-agent.git && cd linux-agent
         ↓
    ┌────────────────────────────────────┐
    │  ¿Con venv o sin venv?             │
    └──────────┬─────────────┬──────────┘
               ↓             ↓
        python3 setup.py   python3 install_system.py
               ↓             ↓
        source venv/bin/  cp .env.example .env
          activate &       nano .env
        python main.py           ↓
                         python3 main.py
```

---

### Instalación para Ubuntu sin sudo configurado

Si el usuario del sistema no tiene permisos sudo:

```bash
# Opción 1 — hacerlo como root primero:
su root
apt update && apt install -y git python3 python3-venv python3-pip
exit

# Opción 2 — agregar el usuario a sudoers (requiere reiniciar sesión):
su root -c "usermod -aG sudo $(logname)"
exit  # cerrar sesión y volver a entrar
```

---

## 2. Inicio rápido

### Conectarse a la VM y arrancar el agente

```bash
# Desde Windows (PowerShell) o cualquier terminal:
ssh test@192.168.0.162

# En la VM, activar el entorno virtual:
cd ~/linux_agent
source venv/bin/activate

# Iniciar el agente:
python main.py
```

> **¿Por qué `python` y no `python3`?**
> En Ubuntu, el comando `python` no existe por defecto — solo `python3`.
> Al activar el venv (`source venv/bin/activate`), el entorno crea el alias `python`
> apuntando al Python del venv. Fuera del venv siempre usá `python3`.

### Lo que verás al arrancar

```
1. Banner ASCII "LINUX AGENT"
2. Menú de selección de motor de IA:
   1. LM Studio (Local/Red)     → sin API key
   2. Ollama (Local)            → sin API key
   3. Google Gemini             → requiere GEMINI_API_KEY
   4. OpenAI ChatGPT            → requiere OPENAI_API_KEY
   5. Grok (xAI)               → requiere GROK_API_KEY
   6. Anthropic Claude          → requiere ANTHROPIC_API_KEY

3. Panel de estado inicial con modo activo
4. Prompt de chat listo para escribir
```

> **Nota:** Solo aparecen en el menú los motores con su `API_KEY` configurada.
> LM Studio y Ollama siempre aparecen (no necesitan API key).

> **Flechas ↑↓:** Podés usar las flechas del teclado para navegar por el historial
> de comandos de la sesión y sesiones anteriores (guardado en `~/.linux_agent_history`).

---

## 3. Modo seguro vs. modo autónomo

Este es **el control más importante** del agente. Determina si puede ejecutar comandos bash sin pedirte permiso.

### 🛡️ Modo seguro (por defecto)

- **Indicador:** panel con `🔒 Modo: 🛡 MODO SEGURO`
- Pausa y pregunta **`¿Ejecutar este comando? [Y/n]`** antes de cada comando
  - `Enter` o `Y` → ejecuta
  - `n` → cancela (el agente lo registra pero no ejecuta)

### ⚠️ Modo autónomo

- **Indicador:** panel amarillo `⚠ MODO AUTÓNOMO ACTIVADO`
- Ejecuta comandos directamente sin confirmar
- Ideal para tareas largas (`sudo apt install`, instalaciones, scripts)
- ⚠️ El agente puede ejecutar comandos destructivos sin aviso

### Toggle en tiempo real

```
◆ You: /auto
```

Escribe `/auto` en cualquier momento para alternar entre modos. `/confirm` es un alias.

### Configurar el modo por defecto

```env
# En ~/linux_agent/.env:
REQUIRE_CONFIRMATION=True    # Arranca en modo seguro (recomendado)
REQUIRE_CONFIRMATION=False   # Arranca en modo autónomo
```

---

## 4. Comandos del CLI

| Comando | Descripción |
|---------|-------------|
| `/auto` | Toggle modo autónomo ↔ seguro |
| `/confirm` | Alias de `/auto` |
| `/task <descripción>` | Ejecuta una tarea compleja en modo autónomo (Agentic Loop) |
| `/web <query>` | Búsqueda web manual (DuckDuckGo) |
| `/switch <motor>` | Cambia el motor de IA en caliente (sin reiniciar) |
| `/engines` | Lista motores disponibles y activo |
| `/model` | Selecciona modelo específico de LM Studio |
| `/sentinel start` | Inicia el centinela en background (persistente) |
| `/sentinel stop` | Envía señal de stop al centinela |
| `/sentinel status` | Ver estado actual, último ciclo y alertas |
| `/telegram status` | Ver estado del bot de Telegram |
| `/export` | Guarda la sesión como archivo `.md` |
| `/clear` | Limpia el historial de conversación |
| `/memory stats` | Muestra estadísticas de la memoria semántica |
| `/memory purge` | Purga memorias expiradas por TTL |
| `/memory clear` | Borra los recuerdos del motor actual (pide confirmación) |
| `/ayuda` o `/help` | Tabla de ayuda |
| `Ctrl+C` | Salir |
| `↑ / ↓` | Navegar historial de comandos (cross-sesión vía readline) |

### Ejemplos

```bash
◆ You: /engines          # ver qué motores están disponibles
◆ You: /switch gemini    # cambiar a Gemini sin reiniciar
◆ You: /switch local     # volver a LM Studio
◆ You: /model            # cambiar modelo de LM Studio en caliente
◆ You: /auto             # activar modo autónomo
◆ You: /export           # guardar sesión como markdown
◆ You: /memory stats     # ver cuántos recuerdos tiene el agente
◆ You: /memory clear     # borrar todos los recuerdos del motor actual
```

---

## 5. Configurar motores de IA

Toda la configuración se hace en `~/linux_agent/.env`:

```bash
nano ~/linux_agent/.env
# Después de editar: Ctrl+X → Y → Enter para guardar
# Reiniciar el agente: Ctrl+C → python main.py
```

---

### 5.1 LM Studio en red LAN

**Caso típico:** LM Studio corre en otra PC de la red (ej: `192.168.0.142`), la VM accede a él por LAN.

#### En la PC con LM Studio:
1. Abrir LM Studio → pestaña **Local Server** (ícono `<>`)
2. Clic en **Start Server**
3. En **Server Settings** → activar **"Serve on Local Network"**
4. El servidor queda en `http://0.0.0.0:1234/v1`
5. Cargar un modelo: clic en el modelo deseado → **Load**

> **Sobre la carga del modelo:** el agente registra el modelo seleccionado y lo envía
> en el primer request al LLM. Si el modelo no está cargado en LM Studio, el agente
> espera hasta 60s con reintentos. Si otro modelo está activo, lo detecta y lo usa
> automáticamente mostrando un aviso. El arranque es siempre inmediato.

#### En `.env` de la VM:

```env
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1
LMSTUDIO_MODEL=                    # vacío = autodetectar el modelo activo
```

#### Para apuntar a otra IP de LM Studio:

```env
# LM Studio en otra PC con IP distinta:
LMSTUDIO_BASE_URL=http://192.168.0.50:1234/v1

# LM Studio en la propia VM (instalación local):
LMSTUDIO_BASE_URL=http://localhost:1234/v1

# LM Studio con puerto personalizado:
LMSTUDIO_BASE_URL=http://192.168.0.142:8080/v1
```

#### Verificar conexión desde la VM:

```bash
curl http://192.168.0.142:1234/v1/models
```

---

### 5.2 Ollama en Ubuntu (local)

**Caso típico:** instalar Ollama en la misma VM Ubuntu para tener un LLM local sin GPU externa.

#### Instalación:

```bash
# Un solo comando:
curl -fsSL https://ollama.com/install.sh | sh

# Verificar servicio:
systemctl status ollama

# Descargar modelos (recomendados por tamaño/capacidad):
ollama pull llama3              # Llama 3 8B — general (~5 GB)
ollama pull qwen2.5:7b          # Qwen 2.5 7B — excelente para código (~5 GB)
ollama pull phi3                # Phi-3 mini  — muy liviano (~2.3 GB)
ollama pull mistral             # Mistral 7B  — bueno en general (~4 GB)
ollama pull deepseek-r1:7b      # DeepSeek R1 — razonamiento (~5 GB)

# Listar modelos instalados:
ollama list

# Probar directamente:
ollama run llama3
```

#### En `.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3             # debe coincidir con un modelo instalado
```

#### Iniciar Ollama si está parado:

```bash
sudo systemctl start ollama
sudo systemctl enable ollama    # arrancar automáticamente con el sistema
```

---

### 5.3 Ollama en red LAN

**Caso típico:** Ollama corre en otra PC de la LAN con GPU, accedido desde la VM.

#### En la PC con Ollama (configurar para escuchar en red):

```bash
# Linux — configuración permanente:
sudo systemctl edit ollama
# Agregar en el archivo que se abre:
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
# Guardar (Ctrl+X → Y) y reiniciar:
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

#### En `.env` de la VM:

```env
OLLAMA_BASE_URL=http://192.168.0.XXX:11434/v1    # IP de la PC con Ollama
OLLAMA_MODEL=llama3
```

#### Verificar desde la VM:

```bash
curl http://192.168.0.XXX:11434/api/tags
```

---

### 5.4 Google Gemini (API Key)

1. Ir a https://aistudio.google.com/apikey
2. **Create API Key** → copiar (empieza con `AIza...`)

```env
GEMINI_API_KEY=AIzaSy...tu-key-aqui
GEMINI_MODEL=gemini-2.0-flash         # rápido y gratuito (recomendado)
# GEMINI_MODEL=gemini-1.5-pro         # más potente
```

```bash
◆ You: /switch gemini
```

---

### 5.5 Grok xAI (API Key)

1. Ir a https://console.x.ai → iniciar sesión con cuenta de X
2. **API Keys → Create API Key** → copiar (empieza con `xai-...`)

```env
GROK_API_KEY=xai-...tu-key-aqui
GROK_MODEL=grok-3-mini                # económico (recomendado)
# GROK_MODEL=grok-3                   # más potente
```

```bash
◆ You: /switch grok
```

---

### 5.6 OpenAI ChatGPT (API Key)

1. Ir a https://platform.openai.com/api-keys
2. **Create new secret key** → copiar (empieza con `sk-...`)

```env
OPENAI_API_KEY=sk-...tu-key-aqui
OPENAI_MODEL=gpt-4o-mini              # económico y capaz (recomendado)
# OPENAI_MODEL=gpt-4o                 # el más potente
```

```bash
◆ You: /switch chatgpt
```

---

### 5.7 Anthropic Claude (API Key)

1. Ir a https://console.anthropic.com → **API Keys → Create Key**
2. Copiar (empieza con `sk-ant-...`)

```env
ANTHROPIC_API_KEY=sk-ant-...tu-key-aqui
ANTHROPIC_MODEL=claude-3-5-haiku-20241022   # rápido y económico (recomendado)
# ANTHROPIC_MODEL=claude-sonnet-4-5         # balanceado
# ANTHROPIC_MODEL=claude-opus-4-5           # el más potente
```

```bash
◆ You: /switch claude
```

---

## 6. Cambiar motor en caliente

Cambiá el motor de IA **sin reiniciar** con `/switch`. El historial se mantiene.

```bash
◆ You: /switch local     # LM Studio
◆ You: /switch ollama    # Ollama
◆ You: /switch gemini    # Google Gemini
◆ You: /switch chatgpt   # OpenAI
◆ You: /switch grok      # Grok (xAI)
◆ You: /switch claude    # Anthropic Claude
◆ You: /engines          # ver todos los disponibles
```

---

## 7. Editar configuración (.env)

```bash
nano ~/linux_agent/.env
```

### Referencia completa del `.env`

```env
# ── Motor local ────────────────────────────────────────────────────────────────
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1   # IP:puerto de LM Studio
LMSTUDIO_MODEL=                                   # vacío = autodetectar
LMSTUDIO_EMBED_MODEL=                             # vacío = usa el modelo activo
OLLAMA_BASE_URL=http://localhost:11434/v1          # URL de Ollama
OLLAMA_MODEL=llama3                                # modelo de Ollama
OLLAMA_EMBED_MODEL=                               # vacío = usa OLLAMA_MODEL

# ── APIs de nube (agregar las que uses) ───────────────────────────────────────
GEMINI_API_KEY=                    # Google Gemini
GEMINI_MODEL=gemini-2.0-flash
OPENAI_API_KEY=                    # OpenAI ChatGPT
OPENAI_MODEL=gpt-4o-mini
GROK_API_KEY=                      # Grok xAI
GROK_MODEL=grok-3-mini
ANTHROPIC_API_KEY=                 # Anthropic Claude
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# ── Comportamiento ─────────────────────────────────────────────────────────────
REQUIRE_CONFIRMATION=True          # True=modo seguro | False=autónomo
COMMAND_TIMEOUT=60                 # segundos máx por comando bash
DEFAULT_ENGINE=local               # motor al iniciar
MAX_OUTPUT_CHARS=4000              # límite de output enviado al LLM

# ── Memoria semántica ──────────────────────────────────────────────────────────
MEMORY_ENABLED=True                # True = activa la memoria entre sesiones
MEMORY_TOP_K=3                     # recuerdos a inyectar por consulta
MEMORY_THRESHOLD=0.75              # similitud mínima (0.0–1.0)
MEMORY_MAX_ENTRIES=2000            # límite de entradas en DB
```

> Después de editar el `.env` hay que **reiniciar el agente** (`Ctrl+C` → `python main.py`).

---

## 8. Ejecutar sin entorno virtual (venv)

Por defecto el agente requiere activar el venv porque las dependencias solo están
instaladas ahí. Hay dos formas de evitar esto:

### Opción A — Instalar deps en el Python del sistema (recomendado)

```bash
cd ~/linux_agent
python3 install_system.py
```

El script detecta automáticamente si estás en Ubuntu 24.04+ (que requiere
`--break-system-packages`) y lo maneja solo. Al terminar podés ejecutar:

```bash
cd ~/linux_agent
python3 main.py
```

> **Nota Ubuntu 24.04+:** si `install_system.py` falla con "externally-managed-environment",
> instalá manualmente con:
> ```bash
> pip3 install --break-system-packages -r ~/linux_agent/requirements.txt
> ```

### Opción B — Alias permanente en `.bashrc`

Agrega una línea a tu `.bashrc` para no tener que activar el venv manualmente:

```bash
# Agregar el alias:
echo "alias linux-agent='cd ~/linux_agent && source venv/bin/activate && python main.py'" >> ~/.bashrc
source ~/.bashrc

# Usar el agente con un solo comando:
linux-agent
```

### Opción C — Lanzador con script shell

```bash
# Crear el lanzador:
cat > ~/run_agent.sh << 'EOF'
#!/bin/bash
cd ~/linux_agent
source venv/bin/activate
python main.py
EOF
chmod +x ~/run_agent.sh

# Ejecutar:
~/run_agent.sh
```

### ¿Por qué Ubuntu no tiene el comando `python`?

En Ubuntu 22.04+ el comando `python` no existe por defecto — solo `python3`.
Esto es una decisión de Debian/Ubuntu para evitar ambigüedad entre Python 2 y 3.

Para crear el alias de sistema (para todos los usuarios):

```bash
sudo apt install -y python-is-python3
# Ahora `python` apunta a python3
python --version  # Python 3.x.x
```

---

## 9. Mantener el proyecto actualizado (Git)

El proyecto tiene dos flujos de actualización desde Windows:

```
[Windows VS Code]  →  deploy_to_vm.py  →  [VM Ubuntu ~/linux_agent]
[Windows VS Code]  →  github_push.py   →  [GitHub]
```

### Sincronización completa en un comando (desde Windows)

```powershell
# Todo: deploy a VM + tests + push a GitHub
python sync.py --token ghp_...tu-token...

# Solo deploy a VM (sin GitHub):
python sync.py --no-git

# Solo GitHub (sin deploy a VM):
python sync.py --token ghp_... --git-only

# Deploy rápido sin correr tests:
python sync.py --token ghp_... --skip-tests
```

### Push manual desde la VM (sin Windows)

Si editás algo directamente en la VM y querés sincronizar con GitHub:

```bash
cd ~/linux_agent
git add -A
git commit -m "fix: descripción breve del cambio"
git push origin main
# Usuario: Juampeeh
# Contraseña: tu token ghp_...
```

### Guardar el token para no escribirlo cada vez

```bash
# En la VM — guarda credenciales para futuros push:
git config --global credential.helper store

# El primer push pedirá usuario y token:
git push origin main
# → Usuario: Juampeeh
# → Contraseña: ghp_...tu-token...
# Los próximos push no pedirán nada.
```

### Actualizar desde GitHub (pull)

```bash
cd ~/linux_agent
git pull origin main
```

### Ver historial de cambios

```bash
git log --oneline -10      # últimos 10 commits
git status                 # cambios sin commitear
git diff                   # ver qué cambió
```

---

## 10. Referencia de archivos

```
~/linux_agent/
├── main.py               # Entry point — ejecutar para iniciar el agente
├── config.py             # Lee variables del .env para toda la app
├── tools.py              # execute_local_bash: ejecuta comandos bash
├── install_system.py     # Instala deps en Python del sistema (sin venv)
├── setup.py              # Instalador automático (primera vez)
├── test_agent.py         # Suite de tests (19 tests)
├── .env                  # ⚠ Configuración real (nunca subir a git)
├── .env.example          # Plantilla con todos los valores posibles
├── .gitignore            # Archivos excluidos del repositorio
├── requirements.txt      # Dependencias Python del agente
├── requirements-dev.txt  # Deps de dev: paramiko (solo Windows)
├── lm_models.json        # Lista de modelos LM Studio guardados
├── memory.db             # ⚠ DB de memoria semántica (auto-generado, gitignored)
├── README.md             # Documentación pública del repo
├── MANUAL.md             # Este manual
├── PROJECT_CONTEXT.md    # Contexto técnico para LLMs
│
├── llm/                  # Módulo de adaptadores LLM
│   ├── base.py           # Clases abstractas
│   ├── history.py        # Historial canónico multi-API
│   ├── memory.py         # Memoria semántica: SQLite + embeddings + coseno
│   ├── router.py         # Factory + fallback automático
│   ├── tool_registry.py  # Definición de herramientas
│   ├── lmstudio_agent.py # Adaptador LM Studio
│   ├── ollama_agent.py   # Adaptador Ollama
│   ├── gemini_agent.py   # Adaptador Google Gemini
│   ├── openai_agent.py   # Adaptador OpenAI
│   ├── grok_agent.py     # Adaptador Grok (xAI)
│   └── anthropic_agent.py# Adaptador Anthropic Claude
│
├── deploy_to_vm.py       # [Windows] Sube archivos a VM via SSH/SFTP
├── github_push.py        # [Windows] Publica en GitHub
├── run_tests_on_vm.py    # [Windows] Ejecuta tests en VM via SSH
└── sync.py               # [Windows] Deploy + Tests + GitHub en un comando
```

---

## 11. Memoria Semántica

El agente tiene **memoria persistente entre sesiones**. Guarda pares de pregunta+respuesta
en una base de datos vectorial local (`memory.db`). En sesiones futuras, busca recuerdos
similares a la consulta actual y los inyecta como contexto para el LLM.

### ¿Cómo funciona?

```
Usuario escribe: "recordas la IP de Webmin?"
        ↓
El agente vectoriza esa consulta con el modelo de embeddings
        ↓
Busca en memory.db los vectores más similares
        ↓
Encuentra: "P: ¿en qué IP está Webmin?\nR: 192.168.0.162 puerto 10000"
        ↓
Inyecta ese contexto → el LLM responde con la IP real sin necesidad de buscarla de nuevo
```

### Qué se guarda en memoria

| Tipo | Qué guarda | Cuándo |
|------|-----------|--------|
| `respuesta_agente` | Par Q&A: pregunta del usuario + respuesta del agente (> 80 chars) | Al terminar cada respuesta |
| `comando_exitoso` | Comando bash exitoso + primeras líneas del output | Tras cada `execute_local_bash` con exit_code 0 |

> **Formato Q&A:** guardar la pregunta junto con la respuesta hace que futuros queries
> similares a la pregunta original, O relacionados con el contenido de la respuesta,
> encuentren el recuerdo con alta similitud semántica.

### Panel de estado

Al arrancar, el panel inicial muestra el estado de la memoria:

```
🤖 Motor: LM Studio [google/gemma-4-26b-a4b]
🔧 Herramientas: execute_local_bash
🔒 Modo: 🛡 MODO SEGURO (confirmación requerida)
🧠 Memoria: ✓ activa (provider: local)
```

Cuando un recuerdo es inyectado se muestra brevemente:
```
  🧠 1 recuerdo(s) relevante(s) inyectado(s).
```

### Comandos de memoria

```bash
◆ You: /memory stats    # ver cuántos recuerdos hay y tamaño de la DB
◆ You: /memory clear    # borrar todos los recuerdos del motor actual
```

### Motores con soporte de memoria

| Motor | Memoria | Namespace | Modelo de embeddings |
|-------|---------|-----------|---------------------|
| LM Studio | ✅ activa | `local` | `LMSTUDIO_EMBED_MODEL` (ej: `nomic-embed-text-v1.5`) |
| Ollama | ✅ activa | `local` | `OLLAMA_EMBED_MODEL` o el modelo activo |
| Google Gemini | ✅ activa | `gemini` | `text-embedding-004` (automático) |
| OpenAI ChatGPT | ✅ activa | `openai` | `text-embedding-3-small` (automático) |
| Grok xAI | ❌ desactivada | — | Sin API de embeddings disponible |
| Anthropic Claude | ❌ desactivada | — | Sin API de embeddings disponible |

> **LM Studio y Ollama comparten el namespace `local`** — sus recuerdos son mutuamente
> accesibles. Gemini y OpenAI tienen namespaces separados porque sus modelos de
> embeddings generan vectores en espacios matemáticamente distintos.

> **LM Studio:** Para que la memoria funcione hay que tener cargado un modelo de embeddings.
> El recomendado (y verificado) es `nomic-embed-text-v1.5`. Configurarlo en `.env`:
> ```env
> LMSTUDIO_EMBED_MODEL=text-embedding-nomic-embed-text-v1.5
> ```

### Memoria compartida entre TODOS los motores

Si querés que Gemini, OpenAI, etc. compartan recuerdos con LM Studio:

```env
# En .env:
MEMORY_SHARED_EMBED=True   # Todos los motores usan LM Studio para embeddings
```

> ⚠️ Requiere que LM Studio esté corriendo aunque uses un motor cloud.

### Configuración avanzada

```env
MEMORY_ENABLED=True          # False = desactivar completamente
MEMORY_TOP_K=3               # cuántos recuerdos inyectar (más = más contexto, más tokens)
MEMORY_THRESHOLD=0.75        # similitud mínima (0.85+ = más preciso, 0.65- = más recall)
MEMORY_MAX_ENTRIES=2000      # máximo de entradas (las más antiguas se auto-purgan)
MEMORY_SHARED_EMBED=False    # True = namespace único para todos los motores
```

### Ubicación de la base de datos

```bash
# Ver el archivo de la DB:
ls -lh ~/linux_agent/memory.db

# Hacer un backup:
cp ~/linux_agent/memory.db ~/linux_agent/memory_backup.db

# Borrar toda la memoria (equivalente a /memory clear pero directo):
rm ~/linux_agent/memory.db
```

> `memory.db` está en `.gitignore` y **nunca se sube a GitHub**. Es personal de cada instalación.


---

## 12. Solución de problemas

### ❌ El estado del centinela o los logs muestran un horario diferente (ej: 3 horas adelantado)

Esto sucede porque la máquina virtual (Ubuntu) está configurada en la zona horaria UTC por defecto, mientras que tu ubicación local (ej: Argentina) es UTC-3.

**Solución:** Ejecutá el siguiente comando en la terminal SSH de tu VM para establecer la zona horaria correcta:
```bash
sudo timedatectl set-timezone America/Argentina/Buenos_Aires
```

### ❌ `python: command not found` al intentar iniciar sin venv

```bash
# Solución 1 — instalar alias de sistema:
sudo apt install -y python-is-python3

# Solución 2 — usar python3 directamente:
python3 main.py

# Solución 3 — activar el venv primero (siempre funciona):
source ~/linux_agent/venv/bin/activate
python main.py
```

### ❌ El agente se cuelga con un comando

Algunos comandos no son compatibles con la ejecución no-interactiva que usa el agente:

| Comando problemático | Alternativa |
|---------------------|-------------|
| `python` (sin args) | No aplicable — el agente no puede iniciar un REPL |
| `vim`, `nano` | Usar `cat` para leer, `tee` para escribir |
| `top`, `htop` | Usar `ps aux` o `ps aux --sort=-%cpu head` |
| `less`, `more` | Usar `cat archivo \| head -50` |
| `grep -r patrón ~/` | Agregar `--include="*.py"` y limitar scope |
| `find / -name x` | Limitar con `find /etc -name x` o `find /home -name x` |
| `ls -R ~/` | Usar `ls ~/linux_agent` (directorio específico) |

> El agente muestra una advertencia ⚠ antes de ejecutar comandos potencialmente
> problemáticos, pero igualmente los ejecutará con el timeout configurado.

### ❌ Timeout del comando

```env
# En .env — aumentar si necesitás más tiempo:
COMMAND_TIMEOUT=120    # 2 minutos
COMMAND_TIMEOUT=300    # 5 minutos (para instalaciones largas)
```

### ❌ El output está truncado

```env
# En .env — aumentar el límite de caracteres al LLM:
MAX_OUTPUT_CHARS=8000
```

> ⚠ Aumentar demasiado puede llenar el contexto del LLM y causar respuestas
> incoherentes o cortes. Valor recomendado: entre 4000 y 8000.

### ❌ "No se puede conectar a LM Studio"

```bash
# Verificar desde la VM:
curl http://192.168.0.142:1234/v1/models

# Si no responde:
# 1. LM Studio debe estar corriendo en la PC
# 2. Activar "Serve on Local Network" en LM Studio
# 3. Firewall de Windows: permitir puerto 1234
#    (Panel de control → Firewall → Reglas de entrada → Puerto 1234 TCP/UDP)
# 4. Verificar que la IP en .env sea correcta
```

### ❌ "No se puede conectar a Ollama"

```bash
systemctl status ollama
sudo systemctl start ollama
curl http://localhost:11434/api/tags     # debe listar modelos
```

### ❌ Un motor de nube no aparece en el menú

Los motores de nube solo aparecen si tienen su `API_KEY` configurada y **no vacía**
en el `.env`. Verificá:

```bash
grep API_KEY ~/linux_agent/.env
# Si aparece vacío: GEMINI_API_KEY=
# Agregá la key: GEMINI_API_KEY=AIzaSy...
```

### ❌ El LLM no ejecuta comandos (no genera tool calls)

Algunos modelos locales pequeños no soportan bien function calling. Opciones:

1. Usar un modelo más capaz: `Qwen2.5-Coder-32B`, `Gemma-4-27B`, `DeepSeek-Coder-6.7B`
2. Ser más explícito: *"Ejecutá el comando `df -h` para ver el espacio en disco"*
3. Cambiar a un motor de nube: `/switch gemini`

### ❌ La memoria no se activa (🧠 desactivada)

1. **LM Studio/Ollama:** Asegurate de tener un modelo de embeddings cargado y configurado:
   ```env
   LMSTUDIO_EMBED_MODEL=text-embedding-nomic-embed-text-v1.5
   ```
2. **Grok/Claude:** Estos motores no tienen API de embeddings — la memoria está siempre desactivada, es esperado.
3. **MEMORY_ENABLED=False en .env:** Ponerlo en `True`.

### 🔄 Reiniciar el agente

```bash
# Ctrl+C para salir, luego:
python main.py           # si venv está activo
# o
python3 main.py          # si instalaste deps en sistema
```

---

## 13. Búsqueda Web (v2.0)

El agente puede buscar en internet usando **DuckDuckGo** — sin API key, sin costo, 100% privado.

### Cómo el LLM lo usa automáticamente

Cuando el LLM detecta que necesita información que no tiene (documentación, versiones, soluciones a errores), invoca la herramienta `web_search` internamente. No ves ningún comando especial, se integra natüralmente.

Ejemplos de triggers:
- "Cómo instalo nginx en Ubuntu 24.04?"
- "Qué hace el error `E: Package not found`?"
- "Cuál es la última versión de Docker?"

### Búsqueda manual con /web

```
/web linux systemd timer service example
```

Muestra los resultados directamente sin invocar al LLM.

### Configuración

```env
WEB_SEARCH_ENABLED=True      # Habilitar/deshabilitar búsqueda
WEB_SEARCH_MAX_RESULTS=5     # Número de resultados por búsqueda
```

> **Nota:** Si `WEB_SEARCH_ENABLED=False`, el agente puede igualmente pedirte que busques y te diga qué buscar, pero no ejecutará la búsqueda solo.

---

## 14. Herramientas de Archivos y SSH (v2.0)

### Leer y escribir archivos

El agente puede leer y escribir archivos del sistema directamente (más eficiente y seguro que usar `cat` / redirect via bash):

- **`read_file(path)`** — lee el contenido con syntax highlight en terminal
- **`write_file(path, content, modo)`** — escribe con preview + confirmación en modo seguro

Ejemplos de pedidos al agente:
- "Leé el archivo /etc/nginx/nginx.conf"
- "Creá un script en /home/test/backup.sh con este contenido: ..."

### Ejecutar comandos en hosts remotos (SSH)

```
[Usuario] Reiniá el servicio nginx en el servidor 192.168.0.100 (user: admin)
[Agenté] Voy a ejecutar 'systemctl restart nginx' en admin@192.168.0.100...
```

El agente usa `execute_ssh` internamente. En modo seguro pide confirmación. Usa `~/.ssh/id_rsa` por defecto o podés pasar la ruta en el pedido.

### Wake-on-LAN

Enciende equipos remotos con:
- "Encendé la PC con MAC AA:BB:CC:DD:EE:FF"

Requiere que el equipo tenga Wake-on-LAN activo en la BIOS.

Configuración:
```env
WOL_BROADCAST=192.168.0.255
SSH_DEFAULT_TIMEOUT=30
```

---

## 15. Modo Tarea Autónoma — /task (v2.0)

El modo `/task` activa el **Agentic Loop**: el agente trabaja de forma autónoma con reintentos inteligentes.

### Uso

```
/task Instalá y configurá un servidor NGINX con SSL autofirmado y aseguráte de que quede activo
```

### Cómo funciona

1. El agente descompone la tarea en pasos
2. Ejecuta cada paso con las herramientas disponibles
3. Si un paso **falla**: busca en memoria local → busca en web → reintenta
4. Si supera `AGENTIC_MAX_RETRIES` errores consecutivos, se detiene y te explica qué pasó
5. Al terminar, el LLM **consolida el episodio** en un insight de memoria (últil para próximas tareas similares)

### Configuración

```env
AGENTIC_MAX_RETRIES=5        # Fallos consecutivos máximos antes de abandoar
AGENTIC_USE_WEB_ON_FAIL=True # Buscar en web cuando un paso bash falla
AGENTIC_MAX_ITERATIONS=20    # Máx de iteraciones del LLM por tarea
MEMORY_CONSOLIDATE_ON_TASK=True # Consolida el episodio al terminar /task
```

> **Modo seguro en /task:** Si `REQUIRE_CONFIRMATION=True`, el agente sigue pidiendo confirmación para cada comando peligroso. Usa `/auto` para desactivarla si querés que corra sin parar.

---

## 16. Centinela de Fondo (v2.0)

El **Centinela** es un proceso daemon que analiza el sistema periódicamente en background y te alerta si detecta anomalías.

### Activar en .env (inicio automático)

```env
SENTINEL_ENABLED=True
SENTINEL_INTERVAL_SECONDS=300   # Cada 5 minutos
SENTINEL_LOG_TAIL_LINES=100     # Cuántas líneas de log analizar
```

### Activar/desactivar en caliente

```
/sentinel start    # Inicia el centinela en background
/sentinel stop     # Detiene el centinela
/sentinel status   # Ver estado actual y última alerta
```

### Qué monitorea

- **CPU** load average (`/proc/loadavg`)
- **Memoria** `free -h`
- **Disco** `df -h`
- **Errores del sistema** `journalctl -p err`
- **Logs de autenticación** `/var/log/auth.log`
- **Syslog** `/var/log/syslog`

En cada ciclo envía el estado al LLM local (LM Studio o Ollama) para análisis. Si detecta anomalías:
1. Aparece un panel de alerta en la terminal
2. Se envía una alerta por Telegram (si está configurado)

### Logs del centinela

```bash
tail -f /home/test/linux_agent/sentinel.log
```

---

## 17. Telegram — Alertas y Control Remoto (v2.0)

El bot de Telegram permite recibir alertas del centinela y enviarle pedidos al agente desde el teléfono.

### Configuración inicial (10 minutos)

**Paso 1: Crear el bot**
1. Abrí Telegram y buscá `@BotFather`
2. Enviá `/newbot` y seguí las instrucciones
3. Copiá el token que te da (formato: `1234567890:ABCdefGHI...`)

**Paso 2: Configurar en .env**
```env
TELEGRAM_ENABLED=True
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...
TELEGRAM_ALLOWED_IDS=      # Dejar vació por ahora
```

**Paso 3: Registrar tu chat_id**
1. Iniciá el agente: `python main.py`
2. El agente dirá que el bot está esperando registro
3. Abrí Telegram, buscá tu bot y enviá cualquier mensaje
4. El bot te responde: "Tu chat ID es: `123456789`"
5. Agregá ese ID al .env:

```env
TELEGRAM_ALLOWED_IDS=123456789
```

**Paso 4:** Reiniciá el agente. Listo.

### Funcionalidades

| Acción | Cómo |
|--------|-------|
| Alertas del centinela | Automáticas cuando se detecta anomalía |
| Enviar pedido al agente | Escribí cualquier texto en el chat |
| Ver estado | `/status` |
| Aprobación de comandos (modo seguro) | Bot envía botones Sí/No en el teléfono |
| Ver estado del centinela | `/sentinel` |

> **Seguridad:** Solo los chat IDs en `TELEGRAM_ALLOWED_IDS` pueden interactuar con el bot. Si está vacío, el primer usuario que escriba queda registrado (solo útil durante setup).

---

## 18. Heimdall — Monitoreo Remoto (Fase 2)

> ⚠️ **Está deshabilitado por defecto.** Activarlo solo cuando el servidor Heimdall esté configurado con SSH sin contraseña.

El centinela puede conectarse por SSH a tu PC Heimdall (servidor con Pi-hole, Nginx, Suricata, CrowdSec, etc.) y analizar sus logs junto con los del servidor principal.

### Configuración

**Paso 1: Configurar SSH sin contraseña desde la VM**
```bash
# En la VM:
ssh-keygen -t rsa -b 4096   # Si no tenés clave
ssh-copy-id usuario@ip-heimdall
```

**Paso 2: Configurar en .env**
```env
HEIMDALL_ENABLED=True
HEIMDALL_HOST=192.168.0.X      # IP de tu PC Heimdall
HEIMDALL_USER=tu-usuario
HEIMDALL_SSH_KEY=~/.ssh/id_rsa  # Clave SSH (generalmente es la default)
HEIMDALL_LOG_PATHS=/var/log/nginx/access.log,/var/log/suricata/eve.json,/var/log/pihole/pihole.log
```

**Paso 3:** Reiniciá el agente o el centinela. Ahora en cada ciclo del centinela, Heimdall también será analizado.

## 19. Memoria Progresiva / Progressive Disclosure (v2.1)

En v2.1 la arquitectura de memoria cambio de un sistema **RAG automático** (que inyectaba textos al contexto y los saturaba) a un sistema de **revelación progresiva** donde el propio agente elige cuándo y qué recordar.

### ¿Qué cambió?

| Aspecto | v2.0 (antes) | v2.1 (ahora) |
|---------|-------------|-------------|
| **Inyección** | Automática: textos completos al contexto | Bajo demanda: solo cuando el agente usa tools |
| **Tamaño** | Bloques grandes (→ Context Overflow 400) | Resumen corto primero, detalle solo si necesita |
| **Control** | Del sistema (siempre se inyecta) | Del agente (decide si buscar y qué leer) |
| **Tokens** | Alto consumo por defecto | Mínimo: solo lo relevante |

### Herramientas de memoria disponibles para el agente

El agente ahora tiene dos herramientas de memoria que puede usar autónomamente:

```
memory_search  → Busca en la memoria por similitud semántica.
                  Retorna: ID | Tipo | Similitud | Resumen corto
                  (gasta pocos tokens — no devuelve el contenido completo)

memory_get_details → Obtiene el contenido COMPLETO de un recuerdo por ID.
                      Usar solo después de memory_search cuando el resumen
                      indica que ese recuerdo tiene la info exacta.
```

### Flujo de uso (automático)

```
Usuario: "Recordás cómo configuré nginx antes?"
         ↓
[Agente decide buscar en memoria]
         ↓
memory_search("nginx configuración")
→ ID:14 | env_map | 0.92 | "nginx config reverse proxy puerto 80"
         ↓
[El resumen alcanza? Sí.]
→ El agente responde directamente.

# O si necesita detalle:
memory_get_details(14)
→ Contenido completo del recuerdo
```

### Configuración

No requiere cambios en `.env`. Funciona automáticamente con la memoria existente.

> **Nota:** Si venías de v2.0, la columna `resumen_corto` se agrega automáticamente
> a la DB existente sin perder ningún dato al primer arranque (migración no destructiva).

---

## 20. Centinela Persistente y Autónomo (v2.1)

En v2.1 el centinela es un **daemon verdaderamente persistente** — sobrevive al cierre del chat y se gestiona con un archivo PID.

### Persistencia real

```bash
# Iniciarlo (queda vivo aunque cierres la terminal del agente):
/sentinel start
# → "Centinela iniciado como daemon (PID: 12345)"

# El archivo /home/test/linux_agent/.sentinel.pid guarda el PID.
# Si abrís de nuevo el agente, detecta automáticamente que ya está corriendo.

# Para detenerlo explícitamente:
/sentinel stop
```

### Inicio automático

```env
# En .env — para que arranque solo al iniciar el agente:
SENTINEL_ENABLED=True
```

### Autonomía de modelo LLM (JIT Fallback)

Si LM Studio no tiene ningún modelo cargado cuando el centinela intenta analizar, **ahora no falla**:

1. Detecta el error 400 (`No models loaded`)
2. Lee `lm_models.json` para ver qué modelos tenés configurados
3. Intenta forzar la carga del primero de la lista
4. Si no hay lista, usa el modelo de `.env` (`SENTINEL_LLM_MODEL`) o un fallback genérico

```env
# Para fijar el modelo del centinela explícitamente:
SENTINEL_LLM_MODEL=google/gemma-4-26b-a4b

# URL del LLM para el centinela (por defecto usa LMSTUDIO_BASE_URL):
SENTINEL_LLM_URL=http://192.168.0.142:1234/v1
```

### Logs del centinela

```bash
tail -f /home/test/linux_agent/sentinel.log
```

---

## 19. Web UI — Interfaz Web (v3.0)

Desde v3.0, el agente incluye una interfaz web completa que permite interactuar
desde cualquier browser en la red local (o internet con configuración adicional).
El CLI existente **no se modifica** — ambas interfaces funcionan en paralelo.

### Iniciar la Web UI

```bash
# Solo Web UI (el CLI no se inicia)
python3 main.py --web

# CLI + Web UI en paralelo
python3 main.py --all

# Con puerto personalizado
python3 main.py --web --port 8080

# Sin abrir el browser automáticamente
python3 main.py --web --no-browser
```

Una vez iniciada, abrir en el browser:
```
http://<ip-del-servidor>:7860
http://192.168.0.162:7860   ← ejemplo con la VM de siempre
```

### Funcionalidades de la Web UI

| Feature | Descripción |
|---------|-------------|
| **Chat en tiempo real** | WebSocket bidireccional, respuestas en streaming |
| **Tool call cards** | Cada herramienta que usa el agente se muestra como tarjeta colapsable |
| **Modal de confirmación** | En modo seguro, un popup pide aprobación antes de ejecutar comandos bash |
| **Panel de sistema** | CPU, RAM, Disco, Uptime, Load average (actualizado cada 15s) |
| **Panel del centinela** | Estado, último ciclo, botón start/stop, log en modal |
| **Panel de memoria** | Stats de la DB, búsqueda semántica, purgar TTL |
| **Selector de motor** | Cambiar motor de IA desde un dropdown sin reiniciar |
| **Comandos rápidos** | Botones `/auto`, `/clear`, `/memory stats`, `/sentinel status`, `/ayuda` |
| **Notificaciones push** | Alertas del centinela (anomalías) aparecen como toast automáticamente |
| **Responsive** | Funciona en celular (el panel lateral se oculta en pantallas pequeñas) |

### Arquitectura de la Web UI

```
Browser (PC/celular)
    │
    │  HTTP / WebSocket (:7860)
    ▼
┌──────────────────────────────────────┐
│  web_server.py  (FastAPI)           │
│  WS /ws/chat → streaming chat      │
│  WS /ws/events → alertas push      │
│  GET /api/status, /api/system       │
│  POST /api/switch, /api/sentinel    │
└──────────────────────────────────────┘
    │ usa
    ▼
┌──────────────────────────────────────┐
│  agent_core.py  (AgentSession)      │
│  — LLM, historial, memoria, tools  │
│  — procesar_mensaje() async gen     │
└──────────────────────────────────────┘
    │ usa (sin cambios)
    ▼
  llm/, tools*.py, sentinel.py,
  agentic_loop.py, memory.py
```

### Nuevos archivos (v3.0)

| Archivo | Descripción |
|---------|-------------|
| `agent_core.py` | Núcleo del agente desacoplado (AgentSession async) |
| `web_server.py` | Servidor FastAPI con WebSockets y API REST |
| `web/index.html` | Estructura HTML de la UI |
| `web/style.css` | Estilos dark mode premium (Inter + JetBrains Mono) |
| `web/app.js` | Lógica frontend vanilla JS (WebSocket, modales, métricas) |
| `web_server_start.py` | Helper para lanzar el servidor (generado en VM) |

### Flujo de confirmación (modo seguro)

Cuando el agente quiere ejecutar `execute_local_bash`, `write_file` o `execute_ssh`
en modo seguro, el browser muestra un **modal de confirmación**:

```
┌───────────────────────────────────────┐
│ Confirmar: execute_local_bash         │
│ El agente quiere ejecutar:             │
│ $ hostname                             │
│                                        │
│  [✅ Ejecutar]  [❌ Cancelar]           │
└───────────────────────────────────────┘
```

Si no respondes en 120 segundos, el comando se cancela automáticamente.

---

## 20. Referencia de Variables WEB_*

Agregar al `.env` para configurar la Web UI:

```env
# ── Web UI (v3.0) ──────────────────────────────────
WEB_ENABLED=False       # True para habilitar con la flag --web
WEB_PORT=7860           # Puerto del servidor
WEB_HOST=0.0.0.0        # Escucha en toda la red (0.0.0.0) o solo local (127.0.0.1)
WEB_PASSWORD=           # Vacío = sin auth; algo = requerir esa clave
WEB_OPEN_BROWSER=True   # Abrir browser automáticamente al iniciar
```

### Acceso desde internet

Si querés acceder a la UI desde fuera de tu LAN:
1. Agregar `WEB_PASSWORD=tu_clave_secreta` al `.env`
2. Abrir el puerto 7860 en el router (NAT/port forwarding)
3. O usar **Tailscale/WireGuard** (más seguro, sin abrir puertos)

---

*Manual Linux Local AI Agent v3.0.0 — https://github.com/Juampeeh/linux-agent*
