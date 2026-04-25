# NEXT_STEPS_HANDOFF.md — AI Sysadmin Agent v2.1

> Documento de continuidad de sesión. Actualizado: 25 Abril 2026.

---

## ✅ Estado actual — v2.1 (TODO completado)

### Implementaciones confirmadas y testeadas en VM (192.168.0.162)

| Feature | Estado | Commit |
|---------|--------|--------|
| Sentinel daemon persistente (PID file) | ✅ | `6ff4742` |
| JIT Fallback de modelo en sentinel | ✅ | `6ff4742` |
| Progressive Disclosure — `resumen_corto` en DB | ✅ | `6ff4742` |
| Tools `memory_search` + `memory_get_details` | ✅ | `6ff4742` |
| Dispatch de memory tools en `agentic_loop.py` | ✅ | `6ff4742` |
| Eliminación del auto-RAG en `main.py` | ✅ | `6ff4742` |
| `MANUAL.md` actualizado a v2.1 | ✅ | local |
| `PROJECT_CONTEXT.md` reescrito v2.1 | ✅ | local |
| Suite de 19 tests pasando en VM | ✅ | VM verificado |
| Gemma `google/gemma-4-26b-a4b` funcionando | ✅ | VM verificado |

---

## 🔧 Pendientes conocidos

### 1. Push de documentación a GitHub
`MANUAL.md` y `PROJECT_CONTEXT.md` actualizados en esta sesión localmente.
Pendiente subir a la VM y pushear a GitHub:

```bash
# Desde Windows, subir docs a VM y commitear:
python deploy_to_vm.py   # o sync.py
# Luego desde VM:
git add MANUAL.md "linux agent PROJECT_CONTEXT.md"
git commit -m "docs(v2.1): MANUAL y PROJECT_CONTEXT actualizados"
git push
```

### 2. Sentinel JIT — fallback hardcodeado
Si `lm_models.json` está vacío Y `SENTINEL_LLM_MODEL` no está en `.env`, el fallback usa
`"llama-3.2-3b-instruct"` que puede no existir. Solución recomendada: poner en `.env`:
```env
SENTINEL_LLM_MODEL=google/gemma-4-26b-a4b
```

---

## 💡 Ideas futuras (sin implementar)

### Prioridad Alta
1. **Auto-inicio del sentinel con systemd** — unit de systemd que arranque `sentinel.py`
   automáticamente al bootear la VM sin abrir el agente:
   ```ini
   # /etc/systemd/system/linux-agent-sentinel.service
   [Service]
   ExecStart=/home/test/linux_agent/venv/bin/python /home/test/linux_agent/sentinel.py
   Restart=on-failure
   User=test
   ```

2. **`/memory search <query>` como comando CLI manual** — buscar en la memoria propia
   sin preguntar al LLM.

3. **`resumen_corto` generado automáticamente por LLM** — al guardar en memoria,
   si hay LLM disponible, generar el resumen con 1 llamada extra corta.

### Prioridad Media
4. **Dashboard web liviano** — `flask` sirviendo una página con estado del sentinel,
   últimas alertas y estadísticas de memoria.

5. **Heimdall (Fase 2)** — cuando estés listo:
   1. SSH sin contraseña desde VM → Heimdall
   2. `HEIMDALL_ENABLED=True` en `.env`
   3. Ver sección 18 del MANUAL.md

6. **Export de memoria** — `/memory export` para backup en JSON/Markdown.

### Prioridad Baja
7. **Multi-proyecto** — `--project nombre` para namespaces de memoria separados.

8. **Importación de contexto** — `/context load <archivo.md>` para memorizar docs de proyecto.

---

## 📋 Para retomar el trabajo en próxima sesión

1. Leer este archivo para entender el estado
2. Revisar `linux agent PROJECT_CONTEXT.md` para arquitectura detallada
3. VM: `ssh test@192.168.0.162` (pw: `12344321`), proyecto en `/home/test/linux_agent/`
4. LM Studio: `192.168.0.142:1234` — modelo preferido: `google/gemma-4-26b-a4b`
5. Bot Telegram: `@aldkcifnbot`, tu chat_id: `458419035`
6. Git último commit: `6ff4742` — v2.1 Progressive Disclosure
