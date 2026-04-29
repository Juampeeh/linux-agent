#!/bin/bash
# =============================================================================
# setup_autostart.sh — Instala autostart y shortcuts del Linux Agent en la VM
#
# Crea:
#   1. Servicio systemd: linux-agent.service (autostart al boot)
#   2. Acceso directo desktop: "Iniciar Agente" (Web + Sentinel)
#   3. Acceso directo desktop: "Agente CLI" (terminal con main.py)
#
# Requiere sudo para instalar el servicio systemd.
# Uso: bash ~/linux_agent/scripts/setup_autostart.sh
# =============================================================================

set -e

AGENT_DIR="$HOME/linux_agent"
SCRIPTS_DIR="$AGENT_DIR/scripts"
DESKTOP_DIR="$HOME/Desktop"
SERVICE_NAME="linux-agent"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
info() { echo -e "${CYAN}  → $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo ""
echo -e "${BOLD}${CYAN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║  Linux AI Agent — Setup Autostart         ║${NC}"
echo -e "${BOLD}${CYAN}╚═══════════════════════════════════════════╝${NC}"
echo ""

# ── Verificar directorio del agente ───────────────────────────────────────────
[ -d "$AGENT_DIR" ] || fail "No se encontró $AGENT_DIR. Instalá el agente primero."
[ -f "$AGENT_DIR/venv/bin/python" ] || fail "Entorno virtual no encontrado. Ejecutá python3 setup.py"

# ── Permisos de ejecución en los scripts ──────────────────────────────────────
info "Configurando permisos de scripts..."
chmod +x "$SCRIPTS_DIR/start_services.sh"
chmod +x "$SCRIPTS_DIR/start_agent_cli.sh"
ok "Permisos configurados"

# ── Crear directorio Desktop ───────────────────────────────────────────────────
mkdir -p "$DESKTOP_DIR"

# ── Shortcut 1: Iniciar Agente (Web + Sentinel) ────────────────────────────────
info "Creando acceso directo 'Iniciar Agente'..."
cat > "$DESKTOP_DIR/Iniciar Agente.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Iniciar Agente
GenericName=Linux AI Agent Services
Comment=Inicia Web UI (puerto 7860) y Centinela del Linux Agent
Exec=bash -c "bash $SCRIPTS_DIR/start_services.sh"
Icon=utilities-terminal
Terminal=true
Categories=Utility;System;
StartupNotify=false
EOF
chmod +x "$DESKTOP_DIR/Iniciar Agente.desktop"
# En Ubuntu con Nautilus: marcar como trusted
if command -v gio &>/dev/null; then
    gio set "$DESKTOP_DIR/Iniciar Agente.desktop" "metadata::trusted" true 2>/dev/null || true
fi
ok "Shortcut 'Iniciar Agente' creado en el Desktop"

# ── Shortcut 2: Agente CLI ─────────────────────────────────────────────────────
info "Creando acceso directo 'Agente CLI'..."
cat > "$DESKTOP_DIR/Agente CLI.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Agente CLI
GenericName=Linux AI Agent CLI
Comment=Inicia el agente Linux en modo terminal interactivo (python main.py)
Exec=bash -c "bash $SCRIPTS_DIR/start_agent_cli.sh"
Icon=utilities-terminal
Terminal=true
Categories=Utility;System;
StartupNotify=false
EOF
chmod +x "$DESKTOP_DIR/Agente CLI.desktop"
if command -v gio &>/dev/null; then
    gio set "$DESKTOP_DIR/Agente CLI.desktop" "metadata::trusted" true 2>/dev/null || true
fi
ok "Shortcut 'Agente CLI' creado en el Desktop"

# ── Alias para la terminal SSH ─────────────────────────────────────────────────
info "Configurando alias de terminal en ~/.bashrc..."
BASHRC="$HOME/.bashrc"
BLOCK_START="# >>> Linux Agent Aliases >>>"
BLOCK_END="# <<< Linux Agent Aliases <<<"

if grep -q "$BLOCK_START" "$BASHRC"; then
    # Remover el bloque viejo
    sed -i "/$BLOCK_START/,/$BLOCK_END/d" "$BASHRC"
fi

cat >> "$BASHRC" << 'EOF'
# >>> Linux Agent Aliases >>>
alias agente='bash ~/linux_agent/scripts/start_agent_cli.sh'
alias iniciar_agente='bash ~/linux_agent/scripts/start_services.sh'
iniciar() {
    if [ "$1" = "agente" ]; then
        bash ~/linux_agent/scripts/start_services.sh
    else
        echo "Comando no reconocido: iniciar $1"
    fi
}
# <<< Linux Agent Aliases <<<
EOF
ok "Alias configurados (agente, iniciar_agente, iniciar agente)"

# ── Instalar servicio systemd ──────────────────────────────────────────────────
info "Instalando servicio systemd '$SERVICE_NAME'..."

# Detener si ya está corriendo
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    warn "Servicio ya activo, deteniéndolo para actualizar..."
    sudo systemctl stop "$SERVICE_NAME" || true
fi

# Copiar el archivo de servicio
sudo cp "$SCRIPTS_DIR/linux-agent.service" "$SERVICE_FILE"
ok "Archivo de servicio instalado en $SERVICE_FILE"

# Recargar systemd y habilitar
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
ok "Servicio habilitado para autostart al boot"

# Iniciar el servicio ahora
info "Iniciando el servicio ahora..."
sudo systemctl start "$SERVICE_NAME"
sleep 5

if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "Servicio '$SERVICE_NAME' corriendo correctamente"
else
    warn "El servicio tardó en iniciar. Verificá con: sudo systemctl status $SERVICE_NAME"
fi

# ── Resumen final ──────────────────────────────────────────────────────────────
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║  ✅  Setup completado                          ║${NC}"
echo -e "${BOLD}${GREEN}╠═══════════════════════════════════════════════╣${NC}"
echo -e "${BOLD}${GREEN}║${NC}  🌐 Web UI: http://${LOCAL_IP}:7860            ${BOLD}${GREEN}║${NC}"
echo -e "${BOLD}${GREEN}║${NC}  📌 Shortcuts creados en ~/Desktop             ${BOLD}${GREEN}║${NC}"
echo -e "${BOLD}${GREEN}║${NC}  🔄 Autostart: habilitado en systemd           ${BOLD}${GREEN}║${NC}"
echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Comandos útiles:"
echo -e "  ${CYAN}sudo systemctl status $SERVICE_NAME${NC}  → ver estado"
echo -e "  ${CYAN}sudo systemctl stop $SERVICE_NAME${NC}    → detener"
echo -e "  ${CYAN}sudo systemctl restart $SERVICE_NAME${NC} → reiniciar"
echo -e "  ${CYAN}journalctl -u $SERVICE_NAME -f${NC}       → ver logs en vivo"
echo ""
