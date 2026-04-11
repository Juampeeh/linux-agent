# 📖 Manual de Usuario — Linux Local AI Agent

> **Versión:** 1.0.0 | **Plataforma:** Ubuntu Linux (VM/físico) + Windows (desarrollo)
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
7. [Mantener el proyecto actualizado (Git)](#7-mantener-el-proyecto-actualizado-git)
8. [Referencia de archivos](#8-referencia-de-archivos)
9. [Solución de problemas](#9-solución-de-problemas)

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
   (Solo aparecen los que tienen key configurada)

3. Panel de estado inicial con modo activo
4. Prompt de chat listo para escribir
```

> **Nota:** Solo verás en el menú los motores que tenés disponibles.  
> LM Studio y Ollama siempre aparecen (no necesitan API key).  
> Los motores de nube solo aparecen si tienen su `API_KEY` en el `.env`.

---

## 2. Modo seguro vs. modo autónomo

Este es **el control más importante** del agente. Determina si el agente puede ejecutar comandos bash sin pedirte permiso.

### 🛡️ Modo seguro (por defecto)

- **Estado:** el agente **pregunta antes de ejecutar** cada comando
- **Indicador visual:** panel azul con `🔒 Modo: 🛡 MODO SEGURO`
- **Comportamiento al ejecutar:** muestra el comando y pregunta `¿Ejecutar este comando? [Y/n]`
  - Presionar **Enter** o **Y** → ejecuta el comando
  - Escribir **n** → cancela el comando (el agente lo registra pero no lo ejecuta)

```
╭──────────────── Estado del Agente ────────────────╮
│ 🤖 Motor: LM Studio [gemma-4-26b]                 │
│ 🔧 Herramientas: execute_local_bash               │
│ 🔒 Modo: 🛡 MODO SEGURO (confirmación requerida)  │
╰───────────────────────────────────────────────────╯
```

### ⚠️ Modo autónomo

- **Estado:** el agente **ejecuta sin preguntar**
- **Indicador visual:** panel amarillo con `⚠ MODO AUTÓNOMO`
- **Cuándo usarlo:** tareas largas donde confiás en el agente (instalaciones, configuraciones)
- **⚠️ Precaución:** el agente puede ejecutar comandos destructivos sin confirmación

```
╭──────────────────────────────────╮
│ ⚠️ MODO AUTÓNOMO ACTIVADO        │
│ El agente ejecutará sin preguntar │
╰──────────────────────────────────╯
```

### Cómo activar/desactivar

```
◆ You: /auto
```

El comando `/auto` es un **toggle** — alterna entre modo seguro y autónomo cada vez que lo escribís.

También funciona `/confirm` (alias de `/auto`).

### Configurar el modo por defecto en `.env`

```env
# Modo seguro al iniciar (recomendado):
REQUIRE_CONFIRMATION=True

# Modo autónomo al iniciar (¡usar con cuidado!):
REQUIRE_CONFIRMATION=False
```

---

## 3. Comandos del CLI

Todos los comandos empiezan con `/`. Se escriben directamente en el prompt del chat.

| Comando | Descripción |
|---------|-------------|
| `/auto` | Toggle modo autónomo ↔ modo seguro |
| `/confirm` | Alias de `/auto` |
| `/switch <motor>` | Cambia el motor de IA en caliente |
| `/engines` | Lista todos los motores disponibles y cuál está activo |
| `/model` | Selecciona modelo específico de LM Studio |
| `/export` | Guarda la sesión actual como archivo `.md` |
| `/clear` | Limpia el historial de conversación |
| `/ayuda` o `/help` | Muestra la tabla de ayuda |
| `Ctrl+C` | Sale del agente |

### Ejemplos de uso

```bash
# Ver qué motores están disponibles y cuál está activo:
◆ You: /engines

# Cambiar a Gemini en caliente (sin reiniciar):
◆ You: /switch gemini

# Cambiar a LM Studio:
◆ You: /switch local

# Cambiar a Ollama:
◆ You: /switch ollama

# Activar modo autónomo para una tarea larga:
◆ You: /auto
◆ You: instala nginx y configura un sitio básico

# Exportar la sesión para guardar el historial:
◆ You: /export
```

---

## 4. Configurar motores de IA

Toda la configuración se hace en el archivo `.env` ubicado en `~/linux_agent/.env`.

```bash
# Abrir el .env en la VM:
nano ~/linux_agent/.env
```

Después de editar el `.env`, **reiniciá el agente** para que tome los nuevos valores.

---

### 4.1 LM Studio en red LAN

**Caso típico:** LM Studio corre en otra PC de la red (ej: PC con GPU en `192.168.0.142`).

#### En la PC con LM Studio:
1. Abrir LM Studio
2. Ir a **Local Server** (ícono de servidor)
3. Activar el servidor: **Start Server**
4. En **Server Settings**: habilitar "**Serve on Local Network**"
5. El servidor queda en `http://0.0.0.0:1234/v1` (accesible desde la LAN)
6. Cargar un modelo haciendo clic en él

#### En el `.env` de la VM:
```env
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1
LMSTUDIO_MODEL=                    # vacío = autodetectar el modelo activo
```

#### Para seleccionar un modelo específico:
```env
LMSTUDIO_MODEL=google/gemma-4-26b-a4b
```

O desde el chat, usar `/model` para elegir interactivamente.

#### Verificar conexión desde la VM:
```bash
cd ~/linux_agent
source venv/bin/activate
python -c "
import openai, config
c = openai.OpenAI(base_url=config.LMSTUDIO_BASE_URL, api_key='lm-studio')
models = c.models.list()
print('Modelos disponibles:', [m.id for m in models.data])
"
```

---

### 4.2 Ollama en Ubuntu (local)

**Caso típico:** instalar Ollama directamente en la VM Ubuntu para tener un LLM local sin GPU externa.

#### Instalación de Ollama en la VM:

```bash
# 1. Instalar Ollama (un solo comando):
curl -fsSL https://ollama.com/install.sh | sh

# 2. Verificar que esté corriendo:
systemctl status ollama

# 3. Descargar un modelo (ejemplos):
ollama pull llama3              # Llama 3 8B (recomendado, ~5GB)
ollama pull mistral             # Mistral 7B
ollama pull qwen2.5:7b          # Qwen 2.5 7B (muy bueno para código)
ollama pull deepseek-r1:7b      # DeepSeek R1 (razonamiento)
ollama pull phi3                # Phi-3 mini (muy liviano, ~2.3GB)

# 4. Listar modelos instalados:
ollama list

# 5. Probar un modelo directamente:
ollama run llama3
```

#### Configurar en `.env`:
```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3              # debe coincidir con un modelo instalado
```

#### Iniciar Ollama si no está corriendo:
```bash
# Como servicio (arranca automáticamente con el sistema):
sudo systemctl enable ollama
sudo systemctl start ollama

# O manualmente:
ollama serve
```

---

### 4.3 Ollama en red LAN

**Caso típico:** Ollama corre en otra PC de la LAN con GPU, y querés accederlo desde la VM.

#### En la PC con Ollama (configurar para escuchar en red):

```bash
# Opción A: variable de entorno (temporal)
OLLAMA_HOST=0.0.0.0 ollama serve

# Opción B: configurar permanentemente (Linux)
sudo systemctl edit ollama
# Agregar en el archivo:
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
# Guardar y reiniciar:
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

#### En el `.env` de la VM:
```env
# Apuntar a la IP de la PC con Ollama en la LAN:
OLLAMA_BASE_URL=http://192.168.0.XXX:11434/v1
OLLAMA_MODEL=llama3
```

#### Verificar desde la VM:
```bash
curl http://192.168.0.XXX:11434/api/tags
```

---

### 4.4 Google Gemini (API Key)

#### Obtener la key (gratis):
1. Ir a https://aistudio.google.com/apikey
2. Hacer clic en **Create API Key**
3. Copiar la key (empieza con `AIza...`)

#### Configurar en `.env`:
```env
GEMINI_API_KEY=AIzaSy...tu-key-aqui...
GEMINI_MODEL=gemini-2.0-flash       # recomendado (gratis, rápido)
# Otras opciones:
# GEMINI_MODEL=gemini-1.5-pro       # más potente
# GEMINI_MODEL=gemini-2.0-flash-thinking-experimental  # razonamiento
```

#### Activar en el chat:
```bash
◆ You: /switch gemini
```

---

### 4.5 Grok xAI (API Key)

#### Obtener la key:
1. Ir a https://console.x.ai
2. Crear cuenta / iniciar sesión con cuenta de X
3. Ir a **API Keys** → **Create API Key**
4. Copiar la key (empieza con `xai-...`)

#### Configurar en `.env`:
```env
GROK_API_KEY=xai-...tu-key-aqui...
GROK_MODEL=grok-3-mini              # recomendado (más económico)
# Otras opciones:
# GROK_MODEL=grok-3                 # más potente
# GROK_MODEL=grok-3-mini-fast       # el más rápido
```

#### Activar en el chat:
```bash
◆ You: /switch grok
```

---

### 4.6 OpenAI ChatGPT (API Key)

#### Obtener la key:
1. Ir a https://platform.openai.com/api-keys
2. Hacer clic en **Create new secret key**
3. Copiar la key (empieza con `sk-...`)

#### Configurar en `.env`:
```env
OPENAI_API_KEY=sk-...tu-key-aqui...
OPENAI_MODEL=gpt-4o-mini            # recomendado (económico y muy capaz)
# Otras opciones:
# OPENAI_MODEL=gpt-4o               # el más potente
# OPENAI_MODEL=o3-mini              # razonamiento
```

#### Activar en el chat:
```bash
◆ You: /switch chatgpt
```

---

### 4.7 Anthropic Claude (API Key)

#### Obtener la key:
1. Ir a https://console.anthropic.com
2. Ir a **API Keys** → **Create Key**
3. Copiar la key (empieza con `sk-ant-...`)

#### Configurar en `.env`:
```env
ANTHROPIC_API_KEY=sk-ant-...tu-key-aqui...
ANTHROPIC_MODEL=claude-3-5-haiku-20241022   # recomendado (rápido y económico)
# Otras opciones:
# ANTHROPIC_MODEL=claude-sonnet-4-5         # balanceado
# ANTHROPIC_MODEL=claude-opus-4-5           # el más potente
```

#### Activar en el chat:
```bash
◆ You: /switch claude
```

---

## 5. Cambiar motor en caliente

Podés cambiar el motor de IA **sin reiniciar el agente** con `/switch`. El historial de la conversación se mantiene.

```bash
◆ You: /switch local     # → LM Studio
◆ You: /switch ollama    # → Ollama
◆ You: /switch gemini    # → Google Gemini
◆ You: /switch chatgpt   # → OpenAI
◆ You: /switch grok      # → Grok (xAI)
◆ You: /switch claude    # → Anthropic Claude
```

Para ver qué motores están disponibles (configurados):
```bash
◆ You: /engines
```

---

## 6. Editar configuración (.env)

El archivo `.env` en `~/linux_agent/.env` controla toda la configuración del agente.

```bash
# Abrir con nano (simple):
nano ~/linux_agent/.env

# O con vim:
vim ~/linux_agent/.env
```

### Referencia completa del `.env`

```env
# ── Motor local ────────────────────────────────────────
LMSTUDIO_BASE_URL=http://192.168.0.142:1234/v1  # IP:puerto de LM Studio
LMSTUDIO_MODEL=                                  # vacío = autodetectar
OLLAMA_BASE_URL=http://localhost:11434/v1         # URL de Ollama
OLLAMA_MODEL=llama3                               # modelo de Ollama

# ── APIs de nube ───────────────────────────────────────
GEMINI_API_KEY=                    # Google Gemini
GEMINI_MODEL=gemini-2.0-flash
OPENAI_API_KEY=                    # OpenAI ChatGPT
OPENAI_MODEL=gpt-4o-mini
GROK_API_KEY=                      # Grok xAI
GROK_MODEL=grok-3-mini
ANTHROPIC_API_KEY=                 # Anthropic Claude
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# ── Comportamiento ─────────────────────────────────────
REQUIRE_CONFIRMATION=True          # True=modo seguro | False=autónomo
COMMAND_TIMEOUT=30                 # segundos máx por comando bash
DEFAULT_ENGINE=local               # motor al iniciar
MAX_OUTPUT_CHARS=4000              # límite de output al LLM
```

> **Importante:** Después de editar el `.env` hay que **reiniciar el agente** (`Ctrl+C` → `python main.py`).

---

## 7. Mantener el proyecto actualizado (Git)

El proyecto tiene dos flujos de actualización:

```
[Windows - VS Code]  →  deploy_to_vm.py  →  [VM Ubuntu]
[Windows - VS Code]  →  github_push.py   →  [GitHub]
```

### 7.1 Sincronización completa (VM + GitHub)

Desde Windows, con el proyecto `Linux Agent` abierto:

```powershell
# 1. Subir cambios a la VM:
python deploy_to_vm.py

# 2. Publicar cambios en GitHub:
python github_push.py --token ghp_...tu-token...
```

O usar el script combinado (más cómodo):
```powershell
python sync.py --token ghp_...tu-token...
```

### 7.2 Solo actualizar la VM

```powershell
python deploy_to_vm.py
```

### 7.3 Solo publicar en GitHub (desde la VM)

Si estás conectado a la VM y querés hacer push directamente:

```bash
# En la VM:
cd ~/linux_agent
git add -A
git commit -m "feat: descripción del cambio"

# Push (usar el token como contraseña):
git push origin main
# Usuario: Juampeeh
# Contraseña: el token PAT (ghp_...)
```

### 7.4 Guardar el token en la VM (para no escribirlo cada vez)

```bash
# En la VM, configurar credential helper:
git config --global credential.helper store

# Hacer el primer push (solo este pedirá usuario/contraseña):
cd ~/linux_agent
git push origin main
# Escribir usuario: Juampeeh
# Escribir contraseña: ghp_...tu-token...
# El token queda guardado en ~/.git-credentials (formato plano)
```

> **Nota de seguridad:** `credential.helper store` guarda el token en texto plano en `~/.git-credentials`. Aceptable en VM privada. Si preferís más seguridad, usá `cache` (temporal en memoria).

### 7.5 Ver historial de commits

```bash
# En la VM:
cd ~/linux_agent
git log --oneline -10      # últimos 10 commits
git status                 # cambios pendientes
git diff                   # ver cambios sin commitear
```

### 7.6 Actualizar desde GitHub (pull)

Si modificaste algo directamente en GitHub o desde otra máquina:

```bash
# En la VM:
cd ~/linux_agent
git pull origin main
```

---

## 8. Referencia de archivos

```
~/linux_agent/
├── main.py               # Entry point — ejecutar esto para iniciar el agente
├── config.py             # Lee variables del .env para toda la app
├── tools.py              # execute_local_bash: ejecuta comandos bash
├── setup.py              # Instalador automático (primera instalación)
├── test_agent.py         # Suite de tests de verificación
├── .env                  # ⚠ Configuración real (nunca subir a git)
├── .env.example          # Plantilla del .env (sin valores reales)
├── .gitignore            # Archivos excluidos del repositorio
├── requirements.txt      # Dependencias Python del agente
├── requirements-dev.txt  # Deps adicionales para scripts de deploy (Windows)
├── lm_models.json        # Lista de modelos LM Studio guardados
│
├── llm/                  # Módulo de adaptadores LLM
│   ├── base.py           # Clases abstractas: AgenteIA, RespuestaAgente
│   ├── history.py        # Historial canónico multi-API
│   ├── router.py         # Factory + fallback automático
│   ├── tool_registry.py  # Definición de herramientas para LLM
│   ├── lmstudio_agent.py # Adaptador LM Studio
│   ├── ollama_agent.py   # Adaptador Ollama
│   ├── gemini_agent.py   # Adaptador Google Gemini
│   ├── openai_agent.py   # Adaptador OpenAI
│   ├── grok_agent.py     # Adaptador Grok (xAI)
│   └── anthropic_agent.py# Adaptador Anthropic Claude
│
├── deploy_to_vm.py       # [Windows] Sube archivos a la VM via SSH/SFTP
├── github_push.py        # [Windows] Publica en GitHub via API + git
├── run_tests_on_vm.py    # [Windows] Ejecuta tests en la VM via SSH
└── sync.py               # [Windows] Deploy + GitHub en un solo comando
```

---

## 9. Solución de problemas

### ❌ "No se puede conectar a LM Studio"

```bash
# Verificar desde la VM:
curl http://192.168.0.142:1234/v1/models

# Si no responde:
# 1. Verificar que LM Studio esté corriendo en la PC
# 2. Verificar que "Serve on Local Network" esté activado en LM Studio
# 3. Verificar que el firewall de Windows permita el puerto 1234
#    (Panel de control → Firewall → Reglas de entrada → Puerto 1234)
# 4. Verificar que la IP en .env sea correcta
```

### ❌ "No se puede conectar a Ollama"

```bash
# Verificar estado del servicio:
systemctl status ollama

# Iniciar si está parado:
sudo systemctl start ollama

# Ver qué modelos tiene instalados:
ollama list

# Verificar endpoint:
curl http://localhost:11434/api/tags
```

### ❌ "API Key inválida" (Gemini / OpenAI / Grok / Claude)

```bash
# Verificar que el .env tiene la key correcta:
cat ~/linux_agent/.env | grep API_KEY

# Reiniciar el agente después de editar:
# Ctrl+C → python main.py
```

### ❌ El agente no aparece en el menú un motor de nube

Los motores de nube solo aparecen si tienen su `API_KEY` configurada en el `.env`. Si la key está vacía, el motor no se muestra en el menú.

### ❌ "Timeout del comando"

El timeout por defecto es 30 segundos. Para comandos que tardan más (instalaciones, compilaciones):

```env
# En .env:
COMMAND_TIMEOUT=120    # 2 minutos
```

### ❌ El LLM no genera tool calls (no ejecuta comandos)

Algunos modelos locales más pequeños tienen dificultades con function calling. Soluciones:
1. Usar un modelo más capaz en LM Studio (ej: Qwen2.5-Coder-32B)
2. Ser más explícito en el prompt: *"Ejecutá el comando `ls -la` para listar archivos"*
3. Cambiar a un motor de nube más confiable: `/switch gemini`

### ❌ El output del comando está truncado

El máximo es 4000 caracteres por defecto para no sobrecargar el contexto del LLM.

```env
MAX_OUTPUT_CHARS=8000   # aumentar si necesitás más output
```

### 🔄 Reiniciar el agente limpiamente

```bash
# Ctrl+C para salir
# Luego:
source venv/bin/activate
python main.py
```

---

*Manual generado para Linux Local AI Agent v1.0 — https://github.com/Juampeeh/linux-agent*
