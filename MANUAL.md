# 📖 Manual de Usuario — Linux Local AI Agent

> **Versión:** 1.0.1 | **Plataforma:** Ubuntu Linux (VM/físico) + Windows (desarrollo)
> **Repositorio:** https://github.com/Juampeeh/linux-agent

---

## Tabla de contenidos

1. [Inicio rápido](#1-inicio-rápido)
2. [Modo seguro vs. modo autónomo](#2-modo-seguro-vs-modo-autónomo)
3. [Comandos del CLI](#3-comandos-del-cli)
4. [Configurar motores de IA](#4-configurar-motores-de-ia)
   - 4.1 [LM Studio en red LAN](#41-lm-studio-en-red-lan)
   - 4.2 [Ollama en Ubuntu (local)](#42-ollama-en-ubuntu-local)
   - 4.3 [Ollama en red LAN](#43-ollama-en-red-lan)
   - 4.4 [Google Gemini (API Key)](#44-google-gemini-api-key)
   - 4.5 [Grok xAI (API Key)](#45-grok-xai-api-key)
   - 4.6 [OpenAI ChatGPT (API Key)](#46-openai-chatgpt-api-key)
   - 4.7 [Anthropic Claude (API Key)](#47-anthropic-claude-api-key)
5. [Cambiar motor en caliente](#5-cambiar-motor-en-caliente)
6. [Editar configuración (.env)](#6-editar-configuración-env)
7. [Ejecutar sin entorno virtual (venv)](#7-ejecutar-sin-entorno-virtual-venv)
8. [Mantener el proyecto actualizado (Git)](#8-mantener-el-proyecto-actualizado-git)
9. [Referencia de archivos](#9-referencia-de-archivos)
10. [Solución de problemas](#10-solución-de-problemas)

---

## 1. Inicio rápido

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

---

## 2. Modo seguro vs. modo autónomo

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

## 3. Comandos del CLI

| Comando | Descripción |
|---------|-------------|
| `/auto` | Toggle modo autónomo ↔ seguro |
| `/confirm` | Alias de `/auto` |
| `/switch <motor>` | Cambia el motor de IA en caliente |
| `/engines` | Lista motores disponibles y activo |
| `/model` | Selecciona modelo específico de LM Studio |
| `/export` | Guarda la sesión como archivo `.md` |
| `/clear` | Limpia el historial de conversación |
| `/ayuda` o `/help` | Tabla de ayuda |
| `Ctrl+C` | Salir |

### Ejemplos

```bash
◆ You: /engines          # ver qué motores están disponibles
◆ You: /switch gemini    # cambiar a Gemini sin reiniciar
◆ You: /switch local     # volver a LM Studio
◆ You: /auto             # activar modo autónomo
◆ You: /export           # guardar sesión como markdown
```

---

## 4. Configurar motores de IA

Toda la configuración se hace en `~/linux_agent/.env`:

```bash
nano ~/linux_agent/.env
# Después de editar: Ctrl+X → Y → Enter para guardar
# Reiniciar el agente: Ctrl+C → python main.py
```

---

### 4.1 LM Studio en red LAN

**Caso típico:** LM Studio corre en otra PC de la red (ej: `192.168.0.142`), la VM accede a él por LAN.

#### En la PC con LM Studio:
1. Abrir LM Studio → pestaña **Local Server** (ícono `<>`)
2. Clic en **Start Server**
3. En **Server Settings** → activar **"Serve on Local Network"**
4. El servidor queda en `http://0.0.0.0:1234/v1`
5. Cargar un modelo: clic en el modelo deseado → **Load**

> **Sobre la carga del modelo:** cuando seleccionás un modelo del menú del agente,
> este intenta pre-cargarlo. Si el modelo tarda más de lo esperado, el agente muestra
> un aviso **pero continúa igual** — LM Studio lo cargará automáticamente con el primer
> mensaje. No es un error, solo es información.

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

### 4.2 Ollama en Ubuntu (local)

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

### 4.3 Ollama en red LAN

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

### 4.4 Google Gemini (API Key)

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

### 4.5 Grok xAI (API Key)

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

### 4.6 OpenAI ChatGPT (API Key)

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

### 4.7 Anthropic Claude (API Key)

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

## 5. Cambiar motor en caliente

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

## 6. Editar configuración (.env)

```bash
nano ~/linux_agent/.env
```

### Referencia completa del `.env`

```env
# ── Motor local ────────────────────────────────────────────────────────────────
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1   # IP:puerto de LM Studio
LMSTUDIO_MODEL=                                   # vacío = autodetectar
OLLAMA_BASE_URL=http://localhost:11434/v1          # URL de Ollama
OLLAMA_MODEL=llama3                                # modelo de Ollama

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
```

> Después de editar el `.env` hay que **reiniciar el agente** (`Ctrl+C` → `python main.py`).

---

## 7. Ejecutar sin entorno virtual (venv)

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

## 8. Mantener el proyecto actualizado (Git)

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

## 9. Referencia de archivos

```
~/linux_agent/
├── main.py               # Entry point — ejecutar para iniciar el agente
├── config.py             # Lee variables del .env para toda la app
├── tools.py              # execute_local_bash: ejecuta comandos bash
├── install_system.py     # Instala deps en Python del sistema (sin venv)
├── setup.py              # Instalador automático (primera vez)
├── test_agent.py         # Suite de tests (12 tests)
├── .env                  # ⚠ Configuración real (nunca subir a git)
├── .env.example          # Plantilla con todos los valores posibles
├── .gitignore            # Archivos excluidos del repositorio
├── requirements.txt      # Dependencias Python del agente
├── requirements-dev.txt  # Deps de dev: paramiko (solo Windows)
├── lm_models.json        # Lista de modelos LM Studio guardados
├── README.md             # Documentación pública del repo
├── MANUAL.md             # Este manual
├── PROJECT_CONTEXT.md    # Contexto técnico para LLMs
│
├── llm/                  # Módulo de adaptadores LLM
│   ├── base.py           # Clases abstractas
│   ├── history.py        # Historial canónico multi-API
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

## 10. Solución de problemas

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

### ❌ El modelo de LM Studio muestra "Timeout" al cargar

Esto es **normal y no es un error**. Significa que el modelo tardó más de lo esperado
en aparecer como activo, pero el agente **continúa de todas formas**.
LM Studio cargará el modelo automáticamente cuando llegue el primer mensaje.

Si querés evitar el aviso, cargá el modelo manualmente en LM Studio antes de
iniciar el agente.

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

### 🔄 Reiniciar el agente

```bash
# Ctrl+C para salir, luego:
python main.py           # si venv está activo
# o
python3 main.py          # si instalaste deps en sistema
```

---

*Manual Linux Local AI Agent v1.0.1 — https://github.com/Juampeeh/linux-agent*
