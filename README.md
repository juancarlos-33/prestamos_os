# PrestamoOS — Plataforma Web de Gestión de Préstamos para Servidor Linux

Sistema de microfinanzas y gestión de préstamos cooperativos desplegado de forma nativa en **Servidor Linux (Ubuntu 22.04/24.04 LTS o Debian 12)** para la asignatura de **Sistemas Operativos**.

## Integrantes del Equipo
1. **De la Hoz Moreno, Juan Carlos**
2. **Julio Garay, Yeffry Luis**
3. **Mogrovejo González, Luis Ángel**
4. **Rodríguez Ozahl, Yeferson Alejandro**

---

## 1. Arquitectura y Conceptos de Sistemas Operativos Implementados
- **Servidor Web Nativo en Linux:** Desarrollado con FastAPI y Uvicorn corriendo como servicio gestionado por `systemd` (`prestamo-web.service`) con reinicio automático (`Restart=always`).
- **Separación de Procesos y Demonio de Fondo:** Proceso independiente (`prestamo-daemon`) que vigila cuotas en mora y ejecuta respaldos programados.
- **IPC Real (SO-03):** Comunicación bidireccional local entre el servidor web y el demonio a través de **Sockets de Dominio UNIX (`AF_UNIX`)** en `/run/user/<UID>/` o `/run/prestamos/`.
- **Sincronización y Bloqueos de Kernel:** Bloqueo consultivo de archivos POSIX con `fcntl.flock` y transacciones ACID en SQLite (modo WAL).
- **Manejo de Señales POSIX (SO-04):**
  - `SIGTERM` / `SIGINT`: Apagado limpio (*Graceful Shutdown*), terminando transacciones y liberando sockets sin corromper la BD.
  - `SIGHUP`: Recarga en caliente de configuraciones desde `config.json` sin interrumpir el servicio.
- **Estándar XDG y Seguridad:** Datos y configuraciones en `~/.config/prestamos_os` (`0600`) y `~/.local/share/prestamos_os` (`0700`).
- **Monitoreo de Recursos (SO-09):** Medición de memoria RSS y CPU mediante lectura de `/proc/<pid>/status` y comandos POSIX (`pidstat`, `ps -eLf`, `lsof`).

---

## 2. Despliegue Rápido en Servidor Linux (Ubuntu / Debian)

### Opción A: Despliegue Automatizado en 1 Solo Paso
En la terminal del servidor Linux limpio:
```bash
git clone <URL_DEL_REPOSITORIO> prestamos_os
cd prestamos_os
chmod +x scripts/deploy_server.sh
sudo ./scripts/deploy_server.sh
```

El script instalará automáticamente las dependencias, creará el entorno virtual, sembrará más de 800 cuotas de prueba y activará el servicio `systemd`.

### Opción B: Ejecución Manual de Desarrollo
```bash
# 1. Instalar dependencias
sudo apt update && sudo apt install -y python3 python3-pip python3-venv sqlite3
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Sembrar datos masivos de prueba (800+ cuotas)
python scripts/seed_demo_data.py

# 3. Iniciar el servidor web
uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload
```

Abra el navegador en: `http://<IP-DEL-SERVIDOR>:8000`

---

## 3. Credenciales de Acceso por Defecto
- **Administrador:** `admin` / `admin123` (Acceso total, configuración y respaldos).
- **Cajero:** `cajero` / `cajero123` (Operación: clientes, préstamos y pagos).

---

## 4. Ejecución de Pruebas Unitarias
El proyecto cuenta con **15 pruebas unitarias** que verifican la precisión matemática financiera (`Decimal`), la aplicación de pagos, las validaciones de mora y los endpoints web:
```bash
python3 -m unittest discover tests -v
```

---

## 5. Comandos para la Sustentación en Vivo ante el Docente
- **Verificar estado del servicio en systemd:**
  ```bash
  sudo systemctl status prestamo-web.service
  ```
- **Monitorear logs en tiempo real (journald):**
  ```bash
  sudo journalctl -u prestamo-web.service -f
  ```
- **Demostrar recarga de configuración sin caída (SIGHUP):**
  ```bash
  PID=$(pgrep -f "src.web.app" | head -n 1)
  kill -HUP $PID
  ```
- **Demostrar apagado seguro sin corrupción (SIGTERM - Criterio 4):**
  ```bash
  kill -TERM $PID
  ```
- **Inspeccionar descriptores y sockets abiertos:**
  ```bash
  lsof -p $PID | grep -E "sock|prestamos.db"
  ```
- **Medir consumo de CPU y Memoria (SO-09):**
  ```bash
  python3 scripts/measure_resources.py $PID
  ```
