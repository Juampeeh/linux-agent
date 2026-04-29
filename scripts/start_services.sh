#!/bin/bash
# =============================================================================
# start_services.sh — Inicia Web UI + Centinela del Linux Agent
#
# NO inicia el agente CLI (python main.py). Solo levanta:
#   - Web Server en puerto 7860
#   - Centinela de monitoreo en background
#
# Uso:  bash ~/linux_agent/scripts/start_services.sh
# =============================================================================

AGENT_DIR="$HOME/linux_agent"
LOG_FILE="$AGENT_DIR/server.log"
PYTHON="$AGENT_DIR/venv/bin/python"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║   🤖 Linux AI Agent — Servicios      ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Verificar venv ─────────────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo -e "${RED}❌ Entorno virtual no encontrado en $AGENT_DIR/venv${NC}"
    echo -e "   Ejecutá primero: cd $AGENT_DIR && python3 setup.py"
    exit 1
fi

# ── Matar procesos previos ─────────────────────────────────────────────────────
echo -e "${YELLOW}→ Deteniendo instancias previas...${NC}"
pkill -f "web_server_start.py" 2>/dev/null || true
pkill -f "web_server.py"       2>/dev/null || true
sleep 2

# ── Verificar que el puerto quedó libre ────────────────────────────────────────
if ss -tlnp | grep -q ':7860'; then
    echo -e "${YELLOW}⚠ Puerto 7860 ocupado, forzando liberación...${NC}"
    fuser -k 7860/tcp 2>/dev/null || true
    sleep 2
fi

# ── Iniciar Web Server ─────────────────────────────────────────────────────────
echo -e "${CYAN}→ Iniciando Web Server...${NC}"
cd "$AGENT_DIR"
nohup "$PYTHON" web_server_start.py >> "$LOG_FILE" 2>&1 &
WEB_PID=$!

# ── Esperar que el servidor esté listo ─────────────────────────────────────────
echo -n "  Esperando que el servidor responda"
READY=false
for i in $(seq 1 20); do
    sleep 1
    echo -n "."
    if curl -s http://localhost:7860/api/status > /dev/null 2>&1; then
        READY=true
        break
    fi
done
echo ""

if [ "$READY" = false ]; then
    echo -e "${RED}❌ El servidor no respondió en 20 segundos.${NC}"
    echo -e "   Revisá el log: tail -f $LOG_FILE"
    exit 1
fi

LOCAL_IP=$(hostname -I | awk '{print $1}')
echo -e "${GREEN}✓ Web UI disponible en: http://${LOCAL_IP}:7860${NC}"

# ── Iniciar Centinela vía API ──────────────────────────────────────────────────
echo -e "${CYAN}→ Iniciando Centinela...${NC}"
SENTINEL_RESP=$(curl -s -X POST http://localhost:7860/api/sentinel \
    -H "Content-Type: application/json" \
    -d '{"accion": "start"}' 2>/dev/null)

if echo "$SENTINEL_RESP" | grep -q '"ok": true'; then
    echo -e "${GREEN}✓ Centinela iniciado${NC}"
else
    echo -e "${YELLOW}⚠ El centinela se puede iniciar desde la Web UI (panel lateral)${NC}"
fi

# ── Resumen ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}✅ Servicios activos${NC}"
echo -e "   🌐 Web UI:     http://${LOCAL_IP}:7860"
echo -e "   📋 Server log: tail -f $LOG_FILE"
echo -e "   🤖 Agente CLI: bash ~/linux_agent/scripts/start_agent_cli.sh"
echo ""
echo -e "${YELLOW}Presioná Enter para cerrar esta ventana...${NC}"
read -r
