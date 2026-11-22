#!/bin/bash
# ==============================================================================
# Script de Despliegue Automatizado en Servidor Linux (Ubuntu 22.04/24.04 / Debian 12)
# Proyecto: Sistema de Gestión de Préstamos (Aplicativo Web)
# ==============================================================================

set -e

APP_DIR="/opt/prestamos_os"
SERVICE_WEB="prestamo-web.service"
SERVICE_DAEMON="prestamo-daemon.service"

echo "=========================================================="
echo "  DESPLIEGUE DE PRESTAMOOS EN SERVIDOR LINUX"
echo "=========================================================="

# 1. Instalar dependencias del sistema operativo
echo "[1/6] Instalando dependencias de Linux (Python, SQLite, libnotify)..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv sqlite3 libnotify-bin curl ufw

# 2. Preparar directorio de la aplicación en /opt con permisos
echo "[2/6] Preparando directorio en $APP_DIR..."
sudo mkdir -p "$APP_DIR"
sudo cp -r . "$APP_DIR/"
cd "$APP_DIR"

# 3. Entorno virtual y dependencias de Python
echo "[3/6] Configurando entorno virtual Python e instalando librerías..."
sudo python3 -m venv venv
sudo "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/venv/bin/pip" install -r requirements.txt

# 4. Sembrado inicial de datos masivos (800+ registros para Criterio 5)
echo "[4/6] Inicializando base de datos SQLite y datos de prueba..."
sudo "$APP_DIR/venv/bin/python" scripts/seed_demo_data.py

# 5. Configurar servicios systemd
echo "[5/6] Instalando y activando servicios systemd..."
sudo cp scripts/prestamo-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_WEB"
sudo systemctl restart "$SERVICE_WEB"

# 6. Configurar Firewall UFW (Permitir puerto 8000)
echo "[6/6] Abriendo puerto 8000 en el Firewall de Linux..."
sudo ufw allow 8000/tcp || true

# Obtener IP del servidor
SERVER_IP=$(hostname -I | awk '{print $1}')

echo "=========================================================="
echo "  ¡DESPLIEGUE EXITOSO EN EL SERVIDOR LINUX!"
echo "=========================================================="
echo "  Aplicación Web disponible en:"
echo "  --> http://$SERVER_IP:8000"
echo "  --> http://localhost:8000 (acceso local)"
echo ""
echo "  Credenciales por defecto:"
echo "  - Administrador: admin / admin123"
echo "  - Cajero:        cajero / cajero123"
echo ""
echo "  Comandos de monitoreo para la sustentación:"
echo "  - Estado del servicio: sudo systemctl status $SERVICE_WEB"
echo "  - Logs en tiempo real: sudo journalctl -u $SERVICE_WEB -f"
echo "  - Métricas de proceso: python3 scripts/measure_resources.py"
echo "=========================================================="
