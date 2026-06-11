#!/usr/bin/env python3
# =============================================================================
# sentinel.py — Modo Centinela Multi-Host (Daemon de Análisis Proactivo)
# Linux Local AI Agent v4.0
#
# Proceso independiente que monitorea el sistema local + hosts remotos
# (Heimdall, VM Pi-hole, etc.) via SSH en cada ciclo de análisis.
#
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

# ── Parsing de hosts remotos (standalone, sin importar config.py) ─────────────
from dataclasses import dataclass, field

@dataclass
class _HostConfig:
    """Configuración de un host remoto para el centinela."""
    name: str
    ip: str
    user: str
    password: str = ""
    ssh_key: str = ""
    services: list[str] = field(default_factory=list)
    log_paths: list[str] = field(default_factory=list)
    extra_checks: list[str] = field(default_factory=list)
    auto_repair: bool = True


def _parse_hosts() -> list[_HostConfig]:
    hosts = []
    for n in range(1, 11):
        prefix = f"SENTINEL_HOST_{n}_"
        name = os.getenv(f"{prefix}NAME", "")
        ip = os.getenv(f"{prefix}IP", "")
        if not name or not ip:
            continue
        hosts.append(_HostConfig(
            name=name, ip=ip,
            user=os.getenv(f"{prefix}USER", ""),
            password=os.getenv(f"{prefix}PASS", ""),
            ssh_key=os.getenv(f"{prefix}SSH_KEY", str(Path.home() / ".ssh" / "id_rsa")),
            services=[s.strip() for s in os.getenv(f"{prefix}SERVICES", "").split(",") if s.strip()],
            log_paths=[p.strip() for p in os.getenv(f"{prefix}LOG_PATHS", "").split(",") if p.strip()],
            extra_checks=[c.strip() for c in os.getenv(f"{prefix}EXTRA_CHECKS", "").split(",") if c.strip()],
            auto_repair=os.getenv(f"{prefix}AUTO_REPAIR", "True").lower() in ("true", "1", "yes"),
        ))
    return hosts


_REMOTE_HOSTS = _parse_hosts()

# Servicios que el centinela puede reiniciar automáticamente si están caídos
_REPARABLES = {
    "pihole-FTL", "nginx", "unbound", "crowdsec",
    "crowdsec-firewall-bouncer", "evebox", "suricata",
}

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
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=60.0)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=30000;")  # Esperar hasta 30s si está locked
        self._conn.executescript(_SCHEMA_SENTINEL)
        self._conn.commit()

    def enviar(self, source: str, type_: str, payload: dict | None = None) -> None:
        """Inserta un mensaje en el bus con reintentos ante lock."""
        for intento in range(5):
            try:
                self._conn.execute(
                    "INSERT INTO sentinel_messages (source, type, payload, created_at) VALUES (?,?,?,?)",
                    (source, type_, json.dumps(payload or {}), time.time()),
                )
                self._conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and intento < 4:
                    logger.debug(f"DB locked, reintento {intento + 1}/5...")
                    time.sleep(3)
                else:
                    logger.error(f"No se pudo enviar mensaje al bus (lock persistente): {e}")
                    return

    def leer_comandos(self) -> list[dict]:
        """Lee comandos no leídos de main → sentinel."""
        try:
            filas = self._conn.execute(
                "SELECT id, type, payload FROM sentinel_messages "
                "WHERE source='main' AND read=0 ORDER BY created_at ASC"
            ).fetchall()
        except sqlite3.OperationalError as e:
            logger.debug(f"Error leyendo comandos (DB lock): {e}")
            return []

        mensajes = []
        ids = []
        for row_id, type_, payload in filas:
            mensajes.append({"id": row_id, "type": type_, "payload": json.loads(payload or "{}")})
            ids.append(row_id)
        if ids:
            try:
                self._conn.execute(
                    f"UPDATE sentinel_messages SET read=1 WHERE id IN ({','.join('?'*len(ids))})",
                    ids,
                )
                self._conn.commit()
            except sqlite3.OperationalError as e:
                logger.debug(f"Error actualizando comandos leídos: {e}")
        return mensajes

    def purgar_viejos(self, horas: int = 48) -> None:
        cutoff = time.time() - horas * 3600
        try:
            self._conn.execute(
                "DELETE FROM sentinel_messages WHERE read=1 AND created_at<?", (cutoff,)
            )
            self._conn.commit()
        except sqlite3.OperationalError as e:
            logger.debug(f"No se pudo purgar mensajes viejos: {e}")

    def cerrar(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ── Análisis del sistema local ────────────────────────────────────────────────

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
    """Recopila métricas del sistema LOCAL via comandos bash livianos."""
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


# ── Conexión SSH a hosts remotos ─────────────────────────────────────────────

def _ssh_connect(host: _HostConfig, timeout: int = 15):
    """Crea y retorna una conexión SSH (paramiko) al host remoto."""
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": host.ip,
        "username": host.user,
        "timeout":  timeout,
    }

    # Autenticación: password tiene prioridad, luego SSH key
    if host.password:
        connect_kwargs["password"] = host.password
    else:
        key_file = Path(host.ssh_key).expanduser()
        if key_file.exists():
            connect_kwargs["key_filename"] = str(key_file)

    ssh.connect(**connect_kwargs)
    return ssh


def _ssh_exec(ssh, cmd: str, timeout: int = 10) -> str:
    """Ejecuta un comando via SSH y retorna el output."""
    try:
        _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        salida = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error and salida:
            salida += f"\n{error}"
        elif error:
            salida = error
        return salida[:3000] if salida else "(sin salida)"
    except Exception as e:
        return f"(error SSH: {e})"


def _verificar_servicios(ssh, services: list[str]) -> dict[str, str]:
    """Verifica el estado de cada servicio en la lista."""
    estados = {}
    for svc in services:
        estado = _ssh_exec(ssh, f"systemctl is-active {svc} 2>/dev/null")
        estados[svc] = estado.strip()
    return estados


def _recopilar_logs(ssh, log_paths: list[str], tail_lines: int = 50) -> dict[str, str]:
    """Lee las últimas líneas de cada log vía SSH."""
    logs = {}
    for log_path in log_paths:
        nombre = Path(log_path).name

        # Para eve.json de Suricata, filtrar solo alertas
        if "eve.json" in log_path:
            cmd = (
                f"tail -n 300 {log_path} 2>/dev/null | "
                f"grep -E '\"event_type\":\"alert\"' | tail -20 || "
                f"echo '(sin alertas recientes)'"
            )
        else:
            cmd = f"tail -n {tail_lines} {log_path} 2>/dev/null || echo '(log no disponible)'"

        salida = _ssh_exec(ssh, cmd)
        logs[nombre] = salida[:2000]
    return logs


def _ejecutar_checks_extra(ssh, checks: list[str]) -> dict[str, str]:
    """Ejecuta verificaciones especiales según la lista de checks."""
    resultados = {}

    for check in checks:
        if check == "zpool_status":
            resultados["zpool_status"] = _ssh_exec(ssh, "zpool status 2>/dev/null || echo '(ZFS no disponible)'")
            resultados["zpool_list"] = _ssh_exec(ssh, "zpool list 2>/dev/null || echo '(ZFS no disponible)'")

        elif check == "pihole_status":
            resultados["pihole_status"] = _ssh_exec(ssh, "pihole status 2>/dev/null || echo '(Pi-hole no disponible)'")

    return resultados


def _descubrir_suricata_logs(ssh) -> str | None:
    """Intenta encontrar la ubicación real de los logs de Suricata en el host."""
    # Buscar en las ubicaciones comunes
    rutas_posibles = [
        "/var/log/suricata/eve.json",
        "/mnt/heimdall-data/suricata/logs/eve.json",
        "/mnt/heimdall-data/suricata/eve.json",
    ]
    for ruta in rutas_posibles:
        check = _ssh_exec(ssh, f"test -f {ruta} && echo EXISTS || echo MISSING")
        if "EXISTS" in check:
            return ruta

    # Si no se encontró, buscar con find (limitado)
    resultado = _ssh_exec(ssh, "find /var/log /mnt -maxdepth 4 -name 'eve.json' -type f 2>/dev/null | head -1", timeout=5)
    if resultado and resultado != "(sin salida)" and not resultado.startswith("("):
        return resultado.strip()

    return None


def recopilar_estado_host_remoto(host: _HostConfig) -> dict | None:
    """Recopila estado completo de un host remoto via SSH."""
    try:
        ssh = _ssh_connect(host)
    except ImportError:
        logger.warning("paramiko no instalado — hosts remotos deshabilitados.")
        return None
    except Exception as e:
        logger.warning(f"Error conectando a {host.name} ({host.ip}): {e}")
        return {"_error": f"Conexión fallida: {e}", "_host": host.name}

    try:
        estado = {
            "_host": host.name,
            "_ip": host.ip,
        }

        # 1. Métricas del sistema
        estado["uptime"] = _ssh_exec(ssh, "uptime")
        estado["cpu_load"] = _ssh_exec(ssh, "cat /proc/loadavg")
        estado["memoria"] = _ssh_exec(ssh, "free -h | head -3")
        estado["disco"] = _ssh_exec(ssh, "df -h --output=source,size,used,avail,pcent | grep -v tmpfs | head -10")

        # 2. Estado de servicios
        if host.services:
            servicios = _verificar_servicios(ssh, host.services)
            estado["servicios"] = servicios

            # Detectar servicios caídos
            caidos = [svc for svc, st in servicios.items() if st != "active"]
            estado["servicios_caidos"] = caidos

        # 3. Logs
        log_paths = list(host.log_paths)

        # Discovery de Suricata si no está en los paths configurados
        if "suricata" in ",".join(host.services) and not any("eve.json" in p for p in log_paths):
            ruta_suricata = _descubrir_suricata_logs(ssh)
            if ruta_suricata:
                log_paths.append(ruta_suricata)
                logger.info(f"[{host.name}] Suricata eve.json encontrado en: {ruta_suricata}")

        if log_paths:
            estado["logs"] = _recopilar_logs(ssh, log_paths)

        # 4. Errores del journal
        estado["errores_journal"] = _ssh_exec(
            ssh,
            f"journalctl -p err --since '1 hour ago' --no-pager -q 2>/dev/null | tail -20 || echo '(journal no disponible)'"
        )

        # 5. Auth log (intentos de acceso)
        estado["auth_log"] = _ssh_exec(
            ssh,
            f"tail -n 30 /var/log/auth.log 2>/dev/null || journalctl _COMM=sshd --since '1 hour ago' --no-pager 2>/dev/null | tail -15 || echo '(auth log no disponible)'"
        )

        # 6. Checks extra (ZFS, Pi-hole, etc.)
        if host.extra_checks:
            extras = _ejecutar_checks_extra(ssh, host.extra_checks)
            estado.update(extras)

        ssh.close()
        return estado

    except Exception as e:
        logger.error(f"Error recopilando estado de {host.name}: {e}")
        try:
            ssh.close()
        except Exception:
            pass
        return {"_error": str(e), "_host": host.name}


# ── Auto-repair ──────────────────────────────────────────────────────────────

def _intentar_reparacion(host: _HostConfig, servicios_caidos: list[str]) -> list[str]:
    """Intenta reiniciar servicios caídos en un host remoto. Retorna lista de reparaciones."""
    if not host.auto_repair or not servicios_caidos:
        return []

    reparaciones = []
    try:
        ssh = _ssh_connect(host)
    except Exception as e:
        logger.error(f"No se pudo conectar a {host.name} para auto-repair: {e}")
        return []

    for svc in servicios_caidos:
        if svc not in _REPARABLES:
            logger.info(f"[{host.name}] Servicio {svc} caído pero NO es reparable automáticamente.")
            continue

        logger.warning(f"[{host.name}] Intentando reiniciar servicio caído: {svc}")
        resultado = _ssh_exec(ssh, f"sudo systemctl restart {svc} 2>&1", timeout=20)
        time.sleep(2)  # Esperar a que el servicio arranque
        nuevo_estado = _ssh_exec(ssh, f"systemctl is-active {svc} 2>/dev/null")

        if nuevo_estado.strip() == "active":
            msg = f"✅ [{host.name}] Servicio {svc} reiniciado exitosamente."
            logger.info(msg)
            reparaciones.append(msg)
        else:
            msg = f"❌ [{host.name}] No se pudo reiniciar {svc}. Estado: {nuevo_estado}. Output: {resultado[:200]}"
            logger.error(msg)
            reparaciones.append(msg)

    try:
        ssh.close()
    except Exception:
        pass

    return reparaciones


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
            "max_tokens": 1200,
            "stream": False,
        }
        if _LLM_MODEL:
            body["model"] = _LLM_MODEL

        with httpx.Client(timeout=90) as client:
            resp = client.post(
                f"{_LLM_URL}/chat/completions",
                json=body,
                headers={"Authorization": "Bearer lm-studio"},
            )
            # Manejar error 400 (No models loaded) para JIT fallback
            if resp.status_code == 400 and "no models loaded" in resp.text.lower():
                logger.info("LM Studio dormido (No models loaded). Intentando carga JIT autónoma...")
                fallback_model = None
                try:
                    models_path = _BASE_DIR / "llm" / "lm_models.json"
                    if models_path.exists():
                        import json as _json
                        datos_json = _json.loads(models_path.read_text(encoding="utf-8"))
                        modelos_guardados = datos_json.get("models", []) if isinstance(datos_json, dict) else []
                        if modelos_guardados:
                            fallback_model = modelos_guardados[0]
                except Exception:
                    pass

                if not fallback_model:
                    try:
                        import httpx as _hx
                        _models_resp = _hx.get(f"{_LLM_URL}/models", timeout=5)
                        if _models_resp.status_code == 200:
                            _mdata = _models_resp.json().get("data", [])
                            if _mdata:
                                fallback_model = _mdata[0]["id"]
                    except Exception:
                        pass

                if not fallback_model:
                    fallback_model = os.getenv("SENTINEL_LLM_MODEL") or os.getenv("LMSTUDIO_MODEL") or ""

                if fallback_model:
                    logger.info(f"Forzando carga del modelo: {fallback_model}")
                    body["model"] = fallback_model
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


_SYSTEM_SENTINEL = """Eres el analizador de sistema de un AI Sysadmin que monitorea una infraestructura de red doméstica.

Tu red tiene los siguientes componentes:
- **Sistema local** (VM del agente): donde corre este centinela
- **Heimdall** (PC física): servidor DNS primario con Pi-hole v6, Unbound (DoT→Quad9), Suricata (IDS/IPS), CrowdSec, EveBox, Nginx (reverse proxy). Almacenamiento ZFS RAIDZ2 (4×1TB) donde se guardan todos los logs.
- **VM Pi-hole** (VM backup): DNS secundario con la misma stack (Pi-hole, Unbound, Suricata, CrowdSec, EveBox, Nginx) pero en un disco virtual de 60GB.

Se te proporcionan métricas y logs de cada componente. Tu tarea es:
1. Identificar problemas, anomalías o situaciones que requieren atención
2. Priorizar por criticidad (un DNS caído es CRITICAL, un error ACPI es INFO)
3. Diferenciar problemas de cada host (no mezclar)
4. Para Suricata: reportar solo alertas reales, ignorar flow/stats
5. Para CrowdSec: reportar bans activos o ataques detectados
6. Para ZFS: verificar que el pool esté ONLINE y sin errores
7. Para Pi-hole: verificar que FTL esté escuchando y bloqueo activo

Responde en formato JSON estricto con esta estructura:
{
  "anomalias": [
    {"host": "nombre_host", "descripcion": "descripción concisa", "severidad": "critical|warning|info"}
  ],
  "nivel": "ok" | "warning" | "critical",
  "resumen": "Una sola oración describiendo el estado general de la red.",
  "acciones_sugeridas": ["acción concreta 1", "acción concreta 2"],
  "reparaciones_auto": ["servicio_a_reiniciar en host X"]
}

Si no hay anomalías, retorna nivel "ok" con lista vacía."""


def analizar_con_llm(estado_local: dict[str, str], estados_remotos: list[dict | None], reparaciones: list[str]) -> dict:
    """Envía el estado combinado de todos los hosts al LLM para análisis."""

    partes = ["=== SISTEMA LOCAL (VM Agente) ===\n"]
    for key, val in estado_local.items():
        partes.append(f"[{key.upper()}]\n{val[:400]}\n")

    for estado_remoto in estados_remotos:
        if not estado_remoto:
            continue
        host_name = estado_remoto.get("_host", "remoto")
        host_ip = estado_remoto.get("_ip", "?")

        if "_error" in estado_remoto:
            partes.append(f"\n=== HOST: {host_name} ({host_ip}) — ERROR CONEXIÓN ===\n")
            partes.append(f"{estado_remoto['_error']}\n")
            continue

        partes.append(f"\n=== HOST: {host_name.upper()} ({host_ip}) ===\n")
        for key, val in estado_remoto.items():
            if key.startswith("_"):
                continue
            if isinstance(val, dict):
                # Servicios
                partes.append(f"[{key.upper()}]\n")
                for k2, v2 in val.items():
                    partes.append(f"  {k2}: {v2}\n")
            elif isinstance(val, list):
                partes.append(f"[{key.upper()}]: {', '.join(str(v) for v in val) if val else '(ninguno)'}\n")
            else:
                partes.append(f"[{key.upper()}]\n{str(val)[:500]}\n")

    if reparaciones:
        partes.append("\n=== REPARACIONES AUTOMÁTICAS EJECUTADAS ===\n")
        for rep in reparaciones:
            partes.append(f"  {rep}\n")

    prompt = "\n".join(partes)
    prompt += "\n\nAnaliza el estado de todos los hosts y retorna el JSON de anomalías."

    respuesta_raw = _llamar_llm(prompt, system=_SYSTEM_SENTINEL)

    if not respuesta_raw:
        return {"nivel": "ok", "anomalias": [], "resumen": "Sin respuesta del LLM.", "acciones_sugeridas": []}

    try:
        texto = respuesta_raw.strip()
        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0].strip()
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0].strip()

        resultado = json.loads(texto)
        return resultado
    except json.JSONDecodeError:
        tiene_anomalia = any(
            word in respuesta_raw.lower()
            for word in ["error", "warning", "critical", "fail", "problema", "anomal", "caído", "down"]
        )
        return {
            "nivel": "warning" if tiene_anomalia else "ok",
            "anomalias": [{"host": "general", "descripcion": respuesta_raw[:300], "severidad": "warning"}] if tiene_anomalia else [],
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
        """Un ciclo completo de análisis multi-host."""
        self._ciclo += 1
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Ciclo {self._ciclo} iniciado ({ts})")

        # 1. Recopilar estado del sistema local
        estado_local = recopilar_estado_sistema()

        # 2. Recopilar estado de hosts remotos
        estados_remotos = []
        todas_reparaciones = []

        for host in _REMOTE_HOSTS:
            logger.info(f"Escaneando host remoto: {host.name} ({host.ip})")
            estado = recopilar_estado_host_remoto(host)
            estados_remotos.append(estado)

            # Auto-repair si hay servicios caídos
            if estado and isinstance(estado, dict) and "servicios_caidos" in estado:
                caidos = estado["servicios_caidos"]
                if caidos:
                    logger.warning(f"[{host.name}] Servicios caídos detectados: {caidos}")
                    reps = _intentar_reparacion(host, caidos)
                    todas_reparaciones.extend(reps)

        n_hosts = len([e for e in estados_remotos if e is not None])
        logger.info(f"Ciclo {self._ciclo}: {n_hosts} host(s) remoto(s) escaneados")

        # 3. Análisis con LLM
        resultado = analizar_con_llm(estado_local, estados_remotos, todas_reparaciones)
        nivel     = resultado.get("nivel", "ok")
        anomalias = resultado.get("anomalias", [])
        resumen   = resultado.get("resumen", "Sin resumen.")

        logger.info(f"Ciclo {self._ciclo}: nivel={nivel}, anomalías={len(anomalias)}")
        if anomalias:
            for a in anomalias:
                if isinstance(a, dict):
                    logger.warning(f"  ANOMALÍA [{a.get('host', '?')}]: {a.get('descripcion', a)}")
                else:
                    logger.warning(f"  ANOMALÍA: {a}")

        # 4. Publicar status en el bus
        status_payload = {
            "ciclo":    self._ciclo,
            "nivel":    nivel,
            "resumen":  resumen,
            "anomalias": anomalias,
            "hosts_escaneados": [h.name for h in _REMOTE_HOSTS],
            "reparaciones": todas_reparaciones,
            "ts":       ts,
        }
        self.db.enviar("sentinel", "STATUS", status_payload)

        # 5. Si hay anomalías de nivel warning/critical → ALERT + Telegram
        if nivel in ("warning", "critical") and anomalias:
            alert_payload = {
                "nivel":      nivel,
                "anomalias":  anomalias,
                "resumen":    resumen,
                "acciones":   resultado.get("acciones_sugeridas", []),
                "reparaciones": todas_reparaciones,
                "ts":         ts,
            }
            self.db.enviar("sentinel", "ALERT", alert_payload)

            # Notificar por Telegram
            nivel_emoji = "🔴" if nivel == "critical" else "⚠️"
            msg_tg = (
                f"{nivel_emoji} *Alerta del Centinela*\n"
                f"Nivel: *{nivel.upper()}*\n"
                f"Resumen: {resumen}\n\n"
            )

            for a in anomalias[:5]:
                if isinstance(a, dict):
                    host_a = a.get("host", "?")
                    desc_a = a.get("descripcion", str(a))
                    sev_a = a.get("severidad", "?")
                    msg_tg += f"• [{host_a}] ({sev_a}) {desc_a}\n"
                else:
                    msg_tg += f"• {a}\n"

            if todas_reparaciones:
                msg_tg += "\n*Reparaciones ejecutadas:*\n" + "\n".join(f"→ {r}" for r in todas_reparaciones[:3])

            if resultado.get("acciones_sugeridas"):
                msg_tg += "\n\n*Acciones sugeridas:*\n" + "\n".join(
                    f"→ {a}" for a in resultado["acciones_sugeridas"][:3]
                )
            _enviar_telegram(msg_tg)

        # 6. Purgar mensajes viejos del bus
        self.db.purgar_viejos()

    def run(self, once: bool = False) -> None:
        """Bucle principal del centinela."""
        hosts_str = ", ".join(f"{h.name}({h.ip})" for h in _REMOTE_HOSTS) if _REMOTE_HOSTS else "ninguno"
        logger.info(
            f"Centinela iniciado — intervalo: {_INTERVAL}s, "
            f"LLM: {_LLM_URL}, hosts remotos: [{hosts_str}]"
        )
        self.db.enviar("sentinel", "STATUS", {
            "estado": "started",
            "pid": os.getpid(),
            "hosts": [h.name for h in _REMOTE_HOSTS],
        })

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
    parser = argparse.ArgumentParser(description="AI Sysadmin Sentinel Daemon — Multi-Host")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar un solo ciclo de análisis y salir (modo debug).",
    )
    args = parser.parse_args()

    db = SentinelDB(_DB_PATH)
    sentinel = Sentinel(db)
    sentinel.run(once=args.once)
