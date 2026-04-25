# =============================================================================
# web_server.py — Servidor Web FastAPI para Linux Local AI Agent v3.0
#
# Expone:
#   GET  /                  → web/index.html
#   GET  /api/status        → estado de la sesión
#   GET  /api/system        → métricas del sistema (CPU/RAM/Disco)
#   GET  /api/models        → lista de modelos LM Studio
#   GET  /api/sentinel/log  → últimas N líneas del sentinel.log
#   GET  /api/memory/search → búsqueda en memoria
#   POST /api/switch        → cambiar motor
#   POST /api/sentinel      → start/stop
#   POST /api/memory/purge  → purgar TTL
#   POST /api/memory/clear  → borrar memoria
#   WS   /ws/chat           → WebSocket de chat (bidireccional streaming)
#   WS   /ws/events         → WebSocket de alertas push (sentinel, Telegram)
# =============================================================================

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import config as cfg
from agent_core import AgentSession

# ── Aplicación FastAPI ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Linux AI Agent Web UI",
    description="Interfaz web para el AI Sysadmin Autónomo",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Archivos estáticos ─────────────────────────────────────────────────────────
_WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")

# ── Sesión global del agente ───────────────────────────────────────────────────
_session: AgentSession | None = None
_session_motor: str = cfg.DEFAULT_ENGINE
_session_model_id: str | None = None

# ── WebSocket broadcast (eventos push al browser) ─────────────────────────────
_event_clients: set[WebSocket] = set()


async def _broadcast_event(evento: dict) -> None:
    """Envía un evento a todos los browsers conectados."""
    dead = set()
    for ws in list(_event_clients):
        try:
            await ws.send_json(evento)
        except Exception:
            dead.add(ws)
    _event_clients.difference_update(dead)


# ── Autenticación simple (opcional) ───────────────────────────────────────────
_WEB_PASSWORD = cfg.WEB_PASSWORD if hasattr(cfg, "WEB_PASSWORD") else ""


def _check_auth(authorization: Optional[str] = None) -> bool:
    if not _WEB_PASSWORD:
        return True
    if not authorization:
        return False
    # Espera header: "Bearer <password>"
    parts = authorization.split(" ", 1)
    return len(parts) == 2 and parts[1] == _WEB_PASSWORD


# =============================================================================
# Startup
# =============================================================================

@app.on_event("startup")
async def on_startup():
    global _session
    _session = AgentSession(_session_motor, _session_model_id)
    try:
        await _session.inicializar()
        print(f"  ✓ Agente inicializado: {_session.agente.nombre_motor}")
    except Exception as e:
        print(f"  ✗ Error inicializando agente: {e}")

    # Tarea background: polling de alertas del sentinel cada 30s
    asyncio.create_task(_sentinel_polling_task())


@app.on_event("shutdown")
async def on_shutdown():
    if _session and _session.memoria:
        try:
            _session.memoria.cerrar()
        except Exception:
            pass


# =============================================================================
# Rutas estáticas
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    index = _WEB_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Web UI no encontrada. Verificá la carpeta web/</h1>", status_code=500)


# =============================================================================
# API REST
# =============================================================================

@app.get("/api/status")
async def api_status():
    if not _session:
        raise HTTPException(503, "Sesión no inicializada")
    return JSONResponse(_session.get_status())


@app.get("/api/system")
async def api_system():
    """Métricas del sistema en tiempo real (CPU, RAM, disco, uptime)."""
    try:
        raw = await asyncio.to_thread(_get_system_metrics)
        return JSONResponse(raw)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/models")
async def api_models():
    """Lista de modelos LM Studio guardados."""
    models_file = Path(cfg.LM_MODELS_FILE) if hasattr(cfg, "LM_MODELS_FILE") else \
                  Path(__file__).parent / "lm_models.json"
    if models_file.exists():
        try:
            data = json.loads(models_file.read_text())
            return JSONResponse({"models": data.get("models", [])})
        except Exception:
            pass
    return JSONResponse({"models": []})


@app.get("/api/sentinel/log")
async def api_sentinel_log(lines: int = 50):
    """Últimas N líneas del archivo sentinel.log."""
    log_file = Path(__file__).parent / "sentinel.log"
    if not log_file.exists():
        return JSONResponse({"lines": []})
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        all_lines = content.strip().split("\n")
        return JSONResponse({"lines": all_lines[-lines:]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/memory/search")
async def api_memory_search(q: str = "", top_k: int = 5):
    """Búsqueda semántica en la memoria."""
    if not _session or not _session.memoria:
        return JSONResponse({"results": [], "error": "Memoria no disponible"})
    if not q.strip():
        return JSONResponse({"results": []})
    try:
        resultados = await asyncio.to_thread(_session.memoria.buscar, q, top_k)
        return JSONResponse({"results": resultados})
    except Exception as e:
        return JSONResponse({"results": [], "error": str(e)})


@app.post("/api/switch")
async def api_switch(body: dict):
    """Cambiar el motor de IA."""
    if not _session:
        raise HTTPException(503, "Sesión no inicializada")
    nuevo_motor = body.get("motor", "").strip().lower()
    if not nuevo_motor:
        raise HTTPException(400, "Campo 'motor' requerido")
    # Ejecutar el switch a través de la sesión
    result = {}
    async for evento in _session._cmd_switch(nuevo_motor):
        result = evento
    await _broadcast_event({"type": "status_update", "status": _session.get_status()})
    return JSONResponse(result)


@app.post("/api/sentinel")
async def api_sentinel(body: dict):
    """Control del centinela: start / stop."""
    if not _session:
        raise HTTPException(503, "Sesión no inicializada")
    accion = body.get("accion", "").lower()
    if accion == "start":
        from agent_core import _sentinel_start
        ok = await asyncio.to_thread(_sentinel_start, _session.memoria)
        return JSONResponse({"ok": ok, "text": "Centinela iniciado." if ok else "Error al iniciar."})
    elif accion == "stop":
        from agent_core import _sentinel_stop
        await asyncio.to_thread(_sentinel_stop, _session.memoria)
        return JSONResponse({"ok": True, "text": "Centinela detenido."})
    else:
        from agent_core import _sentinel_status_dict
        status = _sentinel_status_dict(_session.memoria)
        return JSONResponse(status)


@app.post("/api/memory/purge")
async def api_memory_purge():
    if not _session or not _session.memoria:
        return JSONResponse({"ok": False, "error": "Memoria no disponible"})
    from memory_consolidator import purgar_memorias_ttl
    n = await asyncio.to_thread(purgar_memorias_ttl, _session.memoria)
    return JSONResponse({"ok": True, "eliminadas": n})


@app.post("/api/memory/clear")
async def api_memory_clear():
    if not _session or not _session.memoria:
        return JSONResponse({"ok": False, "error": "Memoria no disponible"})
    n = await asyncio.to_thread(_session.memoria.limpiar)
    return JSONResponse({"ok": True, "eliminadas": n})


# =============================================================================
# WebSocket — Chat
# =============================================================================

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    if not _session:
        await websocket.send_json({"type": "error", "text": "Sesión no inicializada"})
        await websocket.close()
        return

    # Enviar estado inicial
    await websocket.send_json({
        "type": "connected",
        "status": _session.get_status(),
        "message": "Conectado al AI Sysadmin Agent v3.0"
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "text": "Formato JSON inválido"})
                continue

            msg_type = msg.get("type", "message")

            # Confirmación de tool call
            if msg_type == "confirm_result":
                confirm_id = msg.get("confirm_id", "")
                aprobado = bool(msg.get("approved", False))
                _session.resolver_confirmacion(confirm_id, aprobado)
                continue

            # Mensaje de chat normal
            if msg_type == "message":
                texto = msg.get("text", "").strip()
                if not texto:
                    continue

                # Streaming: enviar cada evento
                try:
                    async for evento in _session.procesar_mensaje(texto):
                        await websocket.send_json(evento)
                        # Después de done, broadcast status actualizado
                        if evento.get("type") == "done":
                            await _broadcast_event({
                                "type": "status_update",
                                "status": _session.get_status()
                            })
                except Exception as e:
                    await websocket.send_json({"type": "error", "text": str(e)})
                    await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


# =============================================================================
# WebSocket — Eventos push (alertas del sentinel, etc.)
# =============================================================================

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    _event_clients.add(websocket)
    try:
        # Mantener la conexión viva (el cliente envía pings, nosotros enviamos eventos)
        while True:
            # Esperar mensajes del cliente (pings de keepalive)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Enviar ping para mantener la conexión
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        _event_clients.discard(websocket)


# =============================================================================
# Background tasks
# =============================================================================

async def _sentinel_polling_task():
    """Revisa el bus del sentinel cada 30s y broadcast alertas al browser."""
    while True:
        await asyncio.sleep(30)
        if not _session or not _session.memoria:
            continue
        try:
            msgs = _session.memoria.leer_mensajes_sentinel(
                source_filter="sentinel", solo_no_leidos=True
            )
            if msgs:
                ids = [m["id"] for m in msgs]
                _session.memoria.marcar_leidos_sentinel(ids)
                for m in msgs:
                    payload = m.get("payload", {})
                    nivel = payload.get("nivel", "ok")
                    resumen = payload.get("resumen", "")
                    anomalias = payload.get("anomalias", 0)
                    if nivel != "ok" or anomalias > 0:
                        await _broadcast_event({
                            "type": "sentinel_alert",
                            "nivel": nivel,
                            "resumen": resumen,
                            "anomalias": anomalias,
                        })
        except Exception:
            pass


# =============================================================================
# Métricas del sistema
# =============================================================================

def _get_system_metrics() -> dict:
    """Lee métricas del sistema vía comandos bash (Linux) o psutil si disponible."""
    metrics: dict = {
        "cpu_percent": None,
        "ram_total_mb": None,
        "ram_used_mb": None,
        "ram_percent": None,
        "disk_total_gb": None,
        "disk_used_gb": None,
        "disk_percent": None,
        "uptime_seconds": None,
        "load_avg": None,
    }

    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot = psutil.boot_time()
        load = getattr(psutil, "getloadavg", lambda: (0, 0, 0))()
        metrics.update({
            "cpu_percent": round(cpu, 1),
            "ram_total_mb": round(ram.total / 1024 / 1024, 1),
            "ram_used_mb": round(ram.used / 1024 / 1024, 1),
            "ram_percent": round(ram.percent, 1),
            "disk_total_gb": round(disk.total / 1024**3, 1),
            "disk_used_gb": round(disk.used / 1024**3, 1),
            "disk_percent": round(disk.percent, 1),
            "uptime_seconds": int(time.time() - boot),
            "load_avg": [round(x, 2) for x in load],
        })
        return metrics
    except ImportError:
        pass

    # Fallback: comandos bash (Linux/Mac)
    try:
        # Uptime y load average
        result = subprocess.run(
            ["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            metrics["load_avg"] = [float(x) for x in parts[:3]]

        # RAM
        result = subprocess.run(
            ["free", "-m"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                metrics["ram_total_mb"] = float(parts[1])
                metrics["ram_used_mb"] = float(parts[2])
                metrics["ram_percent"] = round(float(parts[2]) / float(parts[1]) * 100, 1)

        # Disco
        result = subprocess.run(
            ["df", "-BG", "/"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                metrics["disk_total_gb"] = float(parts[1].replace("G", ""))
                metrics["disk_used_gb"] = float(parts[2].replace("G", ""))
                metrics["disk_percent"] = float(parts[4].replace("%", ""))

        # Uptime
        result = subprocess.run(
            ["cat", "/proc/uptime"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            metrics["uptime_seconds"] = int(float(result.stdout.split()[0]))

    except Exception:
        pass

    return metrics


# =============================================================================
# Entry point standalone
# =============================================================================

def iniciar_servidor(
    motor: str = cfg.DEFAULT_ENGINE,
    model_id: str | None = None,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = True,
) -> None:
    """
    Lanza el servidor web. Llamado desde main.py con --web o --all.
    """
    import uvicorn

    global _session_motor, _session_model_id
    _session_motor = motor
    _session_model_id = model_id

    _host = host or (cfg.WEB_HOST if hasattr(cfg, "WEB_HOST") else "0.0.0.0")
    _port = port or (cfg.WEB_PORT if hasattr(cfg, "WEB_PORT") else 7860)

    print(f"\n  🌐 Web UI iniciando en http://{_host}:{_port}")
    print(f"  📖 API docs en http://{_host}:{_port}/api/docs")

    if open_browser:
        import threading
        def _open():
            import time, webbrowser
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{_port}")
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        app,
        host=_host,
        port=_port,
        log_level="warning",
        access_log=False,
    )
