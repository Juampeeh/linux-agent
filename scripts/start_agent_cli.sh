#!/bin/bash
# =============================================================================
# start_agent_cli.sh — Inicia el agente Linux en modo CLI interactivo
#
# Abre el agente en la terminal actual (como siempre: python main.py).
# Requiere que el entorno virtual esté configurado.
#
# Uso:  bash ~/linux_agent/scripts/start_agent_cli.sh
# =============================================================================

AGENT_DIR="$HOME/linux_agent"
PYTHON="$AGENT_DIR/venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "❌ Entorno virtual no encontrado en $AGENT_DIR/venv"
    echo "   Ejecutá: cd $AGENT_DIR && python3 setup.py"
    read -r -p "Presioná Enter para cerrar..."
    exit 1
fi

cd "$AGENT_DIR"
source venv/bin/activate

# exec reemplaza el proceso del shell con python,
# así el Ctrl+C cierra el agente limpiamente sin dejar el shell
exec python main.py
