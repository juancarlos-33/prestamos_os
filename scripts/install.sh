#!/bin/bash
# ==============================================================================
# Script de Instalación / Desinstalación para PrestamoOS (Ubuntu / Debian)
# Cumple con: SO-07 (.desktop e icono), SO-08 (script install/uninstall)
# ==============================================================================

set -e

ACTION="${1:-install}"
APP_NAME="prestamos_os"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
CONFIG_DIR="$HOME/.config/$APP_NAME"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"

if [ "$ACTION" = "install" ]; then
    echo "=========================================="
    echo "  Instalando PrestamoOS en Linux..."
    echo "=========================================="

    # 1. Crear directorios con permisos estrictos
    mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$SYSTEMD_USER_DIR" "$DESKTOP_DIR"
    chmod 700 "$INSTALL_DIR" "$CONFIG_DIR"

    # 2. Copiar archivos del proyecto
    echo "[1/4] Copiando código fuente a $INSTALL_DIR..."
    cp -r src "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"

    # 3. Instalar servicio systemd de usuario
    echo "[2/4] Configurando servicio systemd --user..."
    cp scripts/prestamo-daemon.service "$SYSTEMD_USER_DIR/"
    systemctl --user daemon-reload
    systemctl --user enable prestamo-daemon.service
    systemctl --user restart prestamo-daemon.service
    echo "      Servicio demonio iniciado correctamente."

    # 4. Instalar acceso directo en el escritorio (.desktop)
    echo "[3/4] Instalando lanzador de escritorio..."
    cp scripts/prestamos.desktop "$DESKTOP_DIR/"
    chmod +x "$DESKTOP_DIR/prestamos.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    echo "=========================================="
    echo "  ¡Instalación completada con éxito!"
    echo "  Para desinstalar ejecute: ./scripts/install.sh uninstall"
    echo "=========================================="

elif [ "$ACTION" = "uninstall" ]; then
    echo "=========================================="
    echo "  Desinstalando PrestamoOS..."
    echo "=========================================="

    # Detener y remover servicio systemd
    systemctl --user stop prestamo-daemon.service 2>/dev/null || true
    systemctl --user disable prestamo-daemon.service 2>/dev/null || true
    rm -f "$SYSTEMD_USER_DIR/prestamo-daemon.service"
    systemctl --user daemon-reload

    # Remover lanzador
    rm -f "$DESKTOP_DIR/prestamos.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    echo "¿Desea eliminar la base de datos y respaldos en $INSTALL_DIR? (s/N): "
    read -r RESP
    if [ "$RESP" = "s" ] || [ "$RESP" = "S" ]; then
        rm -rf "$INSTALL_DIR" "$CONFIG_DIR"
        echo "Datos y configuraciones eliminados."
    else
        echo "Datos conservados en $INSTALL_DIR."
    fi

    echo "Desinstalación finalizada."
else
    echo "Uso: $0 [install|uninstall]"
    exit 1
fi
