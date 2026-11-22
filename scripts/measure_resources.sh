#!/bin/bash
# ==============================================================================
# Script de Automatización de Medición de Recursos en Linux (SO-09)
# Utiliza pidstat, ps, /proc y free para documentar el consumo del sistema.
# ==============================================================================

TARGET_NAME="${1:-python3}"
LOG_DIR="$HOME/.local/share/prestamos_os/logs"
mkdir -p "$LOG_DIR"
OUT_FILE="$LOG_DIR/medicion_recursos_$(date +%Y%m%d_%H%M%S).txt"

echo "==========================================================" | tee -a "$OUT_FILE"
echo "  MEDICIÓN DE RECURSOS DEL SISTEMA - SISTEMAS OPERATIVOS  " | tee -a "$OUT_FILE"
echo "  Fecha: $(date)" | tee -a "$OUT_FILE"
echo "  Kernel: $(uname -r)" | tee -a "$OUT_FILE"
echo "  Distribución: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2)" | tee -a "$OUT_FILE"
echo "==========================================================" | tee -a "$OUT_FILE"

# 1. Buscar PIDs de PrestamoOS
PID_UI=$(pgrep -f "src.ui.main_window" | head -n 1 || true)
PID_DAEMON=$(pgrep -f "src.daemon.daemon_service" | head -n 1 || true)

echo "" | tee -a "$OUT_FILE"
echo "1. PROCESOS EN EJECUCIÓN (ps -eo pid,ppid,cmd,%mem,%cpu):" | tee -a "$OUT_FILE"
echo "----------------------------------------------------------" | tee -a "$OUT_FILE"
ps -eo pid,ppid,user,%cpu,%mem,rss,cmd | grep -E "prestamo|src.ui|src.daemon" | grep -v grep | tee -a "$OUT_FILE" || true

echo "" | tee -a "$OUT_FILE"
echo "2. HILOS Y CONCURRENCIA (ps -eLf):" | tee -a "$OUT_FILE"
echo "----------------------------------------------------------" | tee -a "$OUT_FILE"
if [ -n "$PID_UI" ]; then
    echo "Hilos del proceso GUI (PID $PID_UI):" | tee -a "$OUT_FILE"
    ps -eLf | grep "$PID_UI" | grep -v grep | head -n 10 | tee -a "$OUT_FILE"
fi

echo "" | tee -a "$OUT_FILE"
echo "3. DESCRIPTORES DE ARCHIVO Y SOCKETS ABIERTOS (lsof):" | tee -a "$OUT_FILE"
echo "----------------------------------------------------------" | tee -a "$OUT_FILE"
if [ -n "$PID_DAEMON" ]; then
    echo "Sockets y archivos abiertos por el demonio (PID $PID_DAEMON):" | tee -a "$OUT_FILE"
    lsof -p "$PID_DAEMON" 2>/dev/null | grep -E "sock|prestamos.db" | tee -a "$OUT_FILE" || true
fi

echo "" | tee -a "$OUT_FILE"
echo "4. MEDICIÓN CONTINUA CON PIDSTAT (10 Muestras):" | tee -a "$OUT_FILE"
echo "----------------------------------------------------------" | tee -a "$OUT_FILE"
if command -v pidstat >/dev/null 2>&1; then
    if [ -n "$PID_UI" ]; then
        pidstat -u -r -p "$PID_UI" 1 5 | tee -a "$OUT_FILE"
    else
        echo "GUI no detectada en ejecución. Monitoreando sistema general:" | tee -a "$OUT_FILE"
        pidstat -u -r 1 3 | tee -a "$OUT_FILE"
    fi
else
    echo "Nota: pidstat no está instalado (instalar con sudo apt install sysstat)." | tee -a "$OUT_FILE"
fi

echo "" | tee -a "$OUT_FILE"
echo "Informe guardado en: $OUT_FILE"
