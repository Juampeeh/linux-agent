#!/usr/bin/env python3
# =============================================================================
# sentinel.py — Modo Centinela (Daemon de Análisis Proactivo)
# Linux Local AI Agent v2.0
#
# Proceso independiente que monitorea el sistema en background.
# Comunicación con main.py via tabla sentinel_messages en memory.db
#
# Arranque:
#   python3 sentinel.py              # modo daemon
#   python3 sentinel.py --once      # ejecutar un solo ciclo y salir (debug)
#
# Comandos que acepta via sentinel_messages (source="main"):
#   CMD_PAUSE   → pausa el ciclo de análisis
#   CMD_RESUME  → reanuda el ciclo
#   CMD_STOP    → detiene el proceso
# =============================================================================

from __future__ import annotations
import sys
import os
import json
import time
import signal
import logging
import sqlite3
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# Asegurar que el path del proyecto esté disponible
_BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_BASE_DIR))

# ── Config standalone (sin importar config.py completo para robustez) ─────────
from dotenv import load_dotenv
load_dotenv(_BASE_DIR / ".env")

_DB_PATH             = str(_BASE_DIR / "memory.db")
_LLM_URL             = os.getenv("SENTINEL_LLM_URL", os.getenv("LMSTUDIO_BASE_URL", "http://192.168.0.142:1234/v1"))
_LLM_MODEL           = os.getenv("SENTINEL_LLM_MODEL", "")
_INTERVAL            = int(os.getenv("SENTINEL_INTERVAL_SECONDS", "300"))
_LOG_TAIL_LINES      = int(os.getenv("SENTINEL_LOG_TAIL_LINES", "100"))
_ANOMALY_THRESHOLD   = int(os.getenv("SENTINEL_ANOMALY_THRESHOLD", "3"))
_TELEGRAM_ENABLED    = os.getenv("TELEGRAM_ENABLED", "False").lower() in ("true", "1", "yes")
_TELEGRAM_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_IDS        = [
    int(x.strip()) for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",")
    if x.strip().isdigit()
]
_HEIMDALL_ENABLED    = os.getenv("HEIMDALL_ENABLED", "False").lower() in ("true", "1", "yes")
_HEIMDALL_HOST       = os.getenv("HEIMDALL_HOST", "")
_HEIMDALL_USER       = os.getenv("HEIMDALL_USER", "")
_HEIMDALL_SSH_KEY    = os.getenv("HEIMDALL_SSH_KEY", str(Path.home() / ".ssh" / "id_rsa"))
_HEIMDALL_LOG_PATHS  = [
    p.strip() for p in os.getenv(
        "HEIMDALL_LOG_PATHS",
        "/var/log/nginx/access.log,/var/log/suricata/eve.json,/var/log/pihole/pihole.log"
    ).split(",") if p.strip()
]

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][Sentinel] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(_BASE_DIR / "sentinel.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("sentinel")

# ── Bus de mensajes ──────────────────────────────────────────────────────────
_SCHEMA_SENTINEL = """
CREATE TABLE IF NOT EXISTS memorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido TEXT NOT NULL,
    embedding TEXT NOT NULL DEFAULT '[]',
    tipo TEXT NOT NULL,
    embedding_provider TEXT NOT NULL DEFAULT 'sentinel',
    timestamp REAL NOT NULL,
    metadata TEXT DEFAULT '{}',
    access_count INTEGER DEFAULT 1,
    last_seen REAL
);
CREATE TABLE IF NOT EXISTS sentinel_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT    NOT NULL,
    type       TEXT    NOT NULL,
    payload    TEXT    DEFAULT '{}',
    created_at REAL    NOT NULL,
    read       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sentinel_unread ON sentinel_messages(read, source);
"""


class SentinelDB:
    """Capa de acceso al bus de mensajes SQLite."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA_SENTINEL)
        self._conn.commit()

    def enviar(self, source: str, type_: str, payload: dict | None = None) -> None:
        self._conn.execute(
            "INSERT INTO sentinel_messages (source, type, payload, created_at) VALUES (?,?,?,?)",
            (source, type_, json.dumps(payload or {}), time.time()),
        )
        self._conn.commit()

    def leer_comandos(self) -> list[dict]:
        """Lee comandos no leídos de main → sentinel."""
        filas = self._conn.execute(
            "SELECT id, type, payload FROM sentinel_messages "
            "WHERE source='main' AND read=0 ORDER BY created_at ASC"
        ).fetchall()
        mensajes = []
        ids = []
        for row_id, type_, payload in filas:
            mensajes.append({"id": row_id, "type": type_, "payload": json.loads(payload or "{}")})
            ids.append(row_id)
        if ids:
            self._conn.execute(
                f"UPDATE sentinel_messages SET read=1 WHERE id IN ({','.join('?'*len(ids))})",
                ids,
            )
            self._conn.commit()
        return mensajes

    def purgar_viejos(self, horas: int = 48) -> None:
        cutoff = time.time() - horas * 3600
        self._conn.execute(
            "DELETE FROM sentinel_messages WHERE read=1 AND created_at<?", (cutoff,)
        )
        self._conn.commit()

    def cerrar(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ── Análisis del sistema ──────────────────────────────────────────────────────

def _run_cmd(cmd: str, timeout: int = 15) -> str:
    """Ejecuta un comando bash y retorna el output (sin exception)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n{result.stderr.strip()}"
        return output or "(sin salida)"
    except subprocess.TimeoutExpired:
        return f"(timeout: {cmd[:50]})"
    except Exception as e:
        return f"(error: {e})"


def recopilar_estado_sistema() -> dict[str, str]:
    """Recopila métricas del sistema via comandos bash livianos."""
    return {
        "cpu_load":    _run_cmd("cat /proc/loadavg"),
        "memoria":     _run_cmd("free -h | head -3"),
        "disco":       _run_cmd("df -h --output=source,size,used,avail,pcent | grep -v tmpfs | head -10"),
        "uptime":      _run_cmd("uptime"),
        "procesos_top": _run_cmd("ps aux --sort=-%cpu | head -6"),
        "red":         _run_cmd("ss -tunlp 2>/dev/null | head -20"),
        "errores_sys": _run_cmd(f"journalctl -p err -n {_LOG_TAIL_LINES // 2} --no-pager -q 2>/dev/null | tail -30"),
        "auth_log":    _run_cmd(f"tail -n {_LOG_TAIL_LINES // 2} /var/log/auth.log 2>/dev/null || tail -n {_LOG_TAIL_LINES // 2} /var/log/secure 2>/dev/null || echo '(auth log no disponible)'"),
        "syslog":      _run_cmd(f"tail -n {_LOG_TAIL_LINES // 2} /var/log/syslog 2>/dev/null || journalctl -n {_LOG_TAIL_LINES // 2} --no-pager -q 2>/dev/null | tail -30"),
    }


def recopilar_logs_heimdall() -> dict[str, str] | None:
    """Recopila logs de la PC Heimdall via SSH (si está habilitado)."""
    if not _HEIMDALL_ENABLED or not _HEIMDALL_HOST:
        return None

    try:
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": _HEIMDALL_HOST,
            "username": _HEIMDALL_USER,
            "timeout":  15,
        }
        key_file = Path(_HEIMDALL_SSH_KEY).expanduser()
        if key_file.exists():
            connect_kwargs["key_filename"] = str(key_file)
        ssh.connect(**connect_kwargs)

        logs = {}
        for log_path in _HEIMDALL_LOG_PATHS:
            if not log_path.strip():
                continue
            nombre = Path(log_path).name
            _, stdout, stderr = ssh.exec_command(
                f"tail -n {_LOG_TAIL_LINES} {log_path} 2>/dev/null || echo '(no disponible)'",
                timeout=10,
            )
            salida = stdout.read().decode("utf-8", errors="replace").strip()
            logs[nombre] = salida[:3000] if salida else "(vacío)"

        ssh.close()
        return logs

    except ImportError:
        logger.warning("paramiko no instalado — Heimdall deshabilitado.")
        return None
    except Exception as e:
        logger.warning(f"Error conectando a Heimdall ({_HEIMDALL_HOST}): {e}")
        return None


# ── LLM directo (sin framework del agente) ───────────────────────────────────

def _llamar_llm(prompt: str, system: str | None = None) -> str:
    """Llama al LLM via API OpenAI-compatible directamente con httpx."""
    try:
        import httpx

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 800,
            "stream": False,
        }
        if _LLM_MODEL:
            body["model"] = _LLM_MODEL

        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{_LLM_URL}/chat/completions",
                json=body,
                headers={"Authorization": "Bearer lm-studio"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.debug(f"Error llamando al LLM: {e}")
        return ""


_SYSTEM_SENTINEL = """Eres el analizador de sistema de un AI Sysadmin. Se te proporcionan métricas y logs del sistema.
Tu tarea es identificar problemas, anomalías o situaciones que requieren atención.

Responde en formato JSON estricto con esta estructura:
{
  "anomalias": ["descripción concisa de cada problema detectado"],
  "nivel": "ok" | "warning" | "critical",
  "resumen": "Una sola oración describiendo el estado general del sistema.",
  "acciones_sugeridas": ["acción concreta 1", "acción concreta 2"]
}

Si no hay anomalías, retorna nivel "ok" con lista vacía."""


def analizar_con_llm(estado: dict[str, str], logs_heimdall: dict | None) -> dict:
    """Envía el estado del sistema al LLM para análisis. Retorna dict con resultado."""

    # Construir prompt compacto (sin saturar el contexto del LLM)
    partes = ["=== ESTADO DEL SISTEMA ===\n"]
    for key, val in estado.items():
        partes.append(f"[{key.upper()}]\n{val[:500]}\n")

    if logs_heimdall:
        partes.append("\n=== LOGS HEIMDALL ===\n")
        for nombre, contenido in logs_heimdall.items():
            partes.append(f"[{nombre}]\n{contenido[:800]}\n")

    prompt = "\n".join(partes)
    prompt += "\n\nAnaliza el estado anterior y retorna el JSON de anomalías."

    respuesta_raw = _llamar_llm(prompt, system=_SYSTEM_SENTINEL)

    if not respuesta_raw:
        return {"nivel": "ok", "anomalias": [], "resumen": "Sin respuesta del LLM.", "acciones_sugeridas": []}

    try:
        # Extraer JSON de la respuesta (puede venir con markdown ```json)
        texto = respuesta_raw.strip()
        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0].strip()
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0].strip()

        resultado = json.loads(texto)
        return resultado
    except json.JSONDecodeError:
        # Si no es JSON válido, crear respuesta básica
        tiene_anomalia = any(
            word in respuesta_raw.lower()
            for word in ["error", "warning", "critical", "fail", "problema", "anomal"]
        )
        return {
            "nivel": "warning" if tiene_anomalia else "ok",
            "anomalias": [respuesta_raw[:300]] if tiene_anomalia else [],
            "resumen": respuesta_raw[:200],
            "acciones_sugeridas": [],
        }


# ── Notificación Telegram ─────────────────────────────────────────────────────

def _enviar_telegram(texto: str) -> None:
    """Envía un mensaje via Telegram Bot API directamente con httpx."""
    if not _TELEGRAM_ENABLED or not _TELEGRAM_TOKEN or not _TELEGRAM_IDS:
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage"
        for chat_id in _TELEGRAM_IDS:
            try:
                httpx.post(
                    url,
                    json={
                        "chat_id":    chat_id,
                        "text":       texto[:4000],
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Error enviando Telegram a {chat_id}: {e}")
    except Exception as e:
        logger.debug(f"Error en envío Telegram: {e}")


# ── Ciclo principal del centinela ─────────────────────────────────────────────

class Sentinel:
    def __init__(self, db: SentinelDB) -> None:
        self.db       = db
        self._paused  = False
        self._running = True
        self._ciclo   = 0

        # Configurar signal handlers para terminación limpia
        signal.signal(signal.SIGTERM, self._handle_stop)
        signal.signal(signal.SIGINT,  self._handle_stop)

    def _handle_stop(self, signum, frame) -> None:
        logger.info(f"Señal {signum} recibida. Deteniendo centinela...")
        self._running = False

    def _procesar_comandos(self) -> None:
        """Lee y ejecuta comandos del bus."""
        comandos = self.db.leer_comandos()
        for cmd in comandos:
            tipo = cmd["type"]
            if tipo == "CMD_PAUSE":
                self._paused = True
                logger.info("Centinela pausado por comando de main.py")
                self.db.enviar("sentinel", "STATUS", {"estado": "paused"})
            elif tipo == "CMD_RESUME":
                self._paused = False
                logger.info("Centinela reanudado.")
                self.db.enviar("sentinel", "STATUS", {"estado": "running"})
            elif tipo == "CMD_STOP":
                logger.info("Centinela detenido por comando de main.py")
                self._running = False

    def _ejecutar_ciclo(self) -> None:
        """Un ciclo completo de análisis."""
        self._ciclo += 1
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Ciclo {self._ciclo} iniciado ({ts})")

        # 1. Recopilar estado del sistema
        estado = recopilar_estado_sistema()
        logs_heimdall = recopilar_logs_heimdall() if _HEIMDALL_ENABLED else None

        # 2. Análisis con LLM
        resultado = analizar_con_llm(estado, logs_heimdall)
        nivel     = resultado.get("nivel", "ok")
        anomalias = resultado.get("anomalias", [])
        resumen   = resultado.get("resumen", "Sin resumen.")

        logger.info(f"Ciclo {self._ciclo}: nivel={nivel}, anomalías={len(anomalias)}")
        if anomalias:
            for a in anomalias:
                logger.warning(f"  ANOMALÍA: {a}")

        # 3. Publicar status en el bus
        self.db.enviar("sentinel", "STATUS", {
            "ciclo":    self._ciclo,
            "nivel":    nivel,
            "resumen":  resumen,
            "anomalias": anomalias,
            "ts":       ts,
        })

        # 4. Si hay anomalías de nivel warning/critical → ALERT
        if nivel in ("warning", "critical") and anomalias:
            alert_payload = {
                "nivel":      nivel,
                "anomalias":  anomalias,
                "resumen":    resumen,
                "acciones":   resultado.get("acciones_sugeridas", []),
                "ts":         ts,
            }
            self.db.enviar("sentinel", "ALERT", alert_payload)

            # Notificar por Telegram
            nivel_emoji = "🔴" if nivel == "critical" else "⚠️"
            msg_tg = (
                f"{nivel_emoji} *Alerta del Centinela*\n"
                f"Nivel: *{nivel.upper()}*\n"
                f"Resumen: {resumen}\n\n"
                + "\n".join(f"• {a}" for a in anomalias[:5])
            )
            if resultado.get("acciones_sugeridas"):
                msg_tg += "\n\n*Acciones sugeridas:*\n" + "\n".join(
                    f"→ {a}" for a in resultado["acciones_sugeridas"][:3]
                )
            _enviar_telegram(msg_tg)

        # 5. Purgar mensajes viejos del bus
        self.db.purgar_viejos()

    def run(self, once: bool = False) -> None:
        """Bucle principal del centinela."""
        logger.info(
            f"Centinela iniciado — intervalo: {_INTERVAL}s, "
            f"LLM: {_LLM_URL}, Heimdall: {'sí' if _HEIMDALL_ENABLED else 'no'}"
        )
        self.db.enviar("sentinel", "STATUS", {"estado": "started", "pid": os.getpid()})

        while self._running:
            self._procesar_comandos()

            if not self._paused:
                try:
                    self._ejecutar_ciclo()
                except Exception as e:
                    logger.error(f"Error en ciclo {self._ciclo}: {e}")
                    self.db.enviar("sentinel", "INFO", {"error": str(e), "ciclo": self._ciclo})

            if once:
                break

            # Esperar el intervalo siguiente, chequeando comandos cada 5s
            tiempo_restante = _INTERVAL
            while tiempo_restante > 0 and self._running:
                paso = min(5, tiempo_restante)
                time.sleep(paso)
                tiempo_restante -= paso
                self._procesar_comandos()

        logger.info("Centinela detenido.")
        self.db.enviar("sentinel", "STATUS", {"estado": "stopped"})
        self.db.cerrar()


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Sysadmin Sentinel Daemon")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar un solo ciclo de análisis y salir (modo debug).",
    )
    args = parser.parse_args()

    db = SentinelDB(_DB_PATH)
    sentinel = Sentinel(db)
    sentinel.run(once=args.once)
