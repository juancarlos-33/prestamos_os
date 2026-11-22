# Informe Técnico de Conceptos de Sistemas Operativos Aplicados

**Proyecto:** Sistema Web de Gestión de Préstamos (PrestamoOS)  
**Asignatura:** Sistemas Operativos  
**Plataforma de Ejecución:** Servidor Linux (Ubuntu 22.04/24.04 LTS / Debian 12)  
**Equipo de Trabajo:**
1. De la Hoz Moreno, Juan Carlos
2. Julio Garay, Yeffry Luis
3. Mogrovejo González, Luis Ángel
4. Rodríguez Ozahl, Yeferson Alejandro  

---

## 1. Introducción y Objetivo Técnico
El propósito de este informe es documentar formalmente la aplicación de los conceptos fundamentales del curso de Sistemas Operativos dentro de la arquitectura de **PrestamoOS**. La solución se diseñó desacoplando el servidor web de un proceso demonio en segundo plano, comunicados mediante IPC nativo y gestionados por el subsistema `systemd` del kernel de Linux.

---

## 2. Matriz de Conceptos de SO Implementados

| Concepto de S.O. | ¿Qué se usó? | ¿En qué archivo está? | ¿Por qué y para qué se usó? |
| :--- | :--- | :--- | :--- |
| **Procesos y Servicios** | `systemd` Service (`multi-user.target`) y demonio independiente | `scripts/prestamo-web.service`<br/>`src/daemon/daemon_service.py` | Para garantizar alta disponibilidad en el servidor Linux, arranque automático con el sistema y reinicio ante fallos inesperados (`Restart=always`). |
| **Concurrencia e Hilos** | Modelo multihilo POSIX y workers asíncronos | `src/web/app.py`<br/>`src/daemon/daemon_service.py` | Para permitir que múltiples usuarios consulten la web y ejecuten cálculos o reportes simultáneamente sin bloquear el hilo principal. |
| **IPC (Comunicación entre Procesos)** | Sockets de Dominio UNIX (`AF_UNIX`, `SOCK_STREAM`) | `src/daemon/daemon_service.py`<br/>`src/daemon/ipc_client.py` | Permite que el servidor web envíe órdenes al demonio de fondo y consulte su estado en RAM sin sobrecarga de red TCP/IP y con seguridad de permisos Linux. |
| **Sincronización** | Bloqueo de archivos consultivo POSIX (`fcntl.flock`) y transacciones WAL | `src/database/db_manager.py` | Evita condiciones de carrera y corrupción de datos cuando el servidor web y el demonio acceden al mismo tiempo a la base de datos SQLite. |
| **Manejo de Señales POSIX** | `SIGTERM`, `SIGINT` y `SIGHUP` vía `signal.signal` | `src/web/app.py`<br/>`src/daemon/daemon_service.py` | **SIGTERM/SIGINT:** Apagado limpio (*Graceful Shutdown*), cerrando transacciones y sockets.<br/>**SIGHUP:** Recarga de configuración en caliente sin reiniciar el servicio. |
| **Sistema de Archivos y Permisos** | Estándar XDG Base Directory y llamadas `os.chmod` | `src/config.py` | Aislamiento de seguridad: permisos restrictivos `0700` para carpetas de datos y `0600` para archivos de configuración sensibles. |
| **Planificación de Tareas** | Hilos programados y timers en el demonio | `src/daemon/daemon_service.py` | Verificación periódica automática de cuotas vencidas y generación de respaldos comprimidos `.sql.gz`. |
| **Monitoreo de Recursos** | Lectura directa de `/proc/<pid>/status` y `pidstat` | `scripts/measure_resources.py`<br/>`scripts/measure_resources.sh` | Medición del consumo real de CPU, memoria residente (RSS) y conteo de hilos activos para cumplir con el requerimiento SO-09. |

---

## 3. Justificación Detallada de Decisiones de Arquitectura

### 3.1 Comunicación entre Procesos (IPC con Sockets UNIX)
A diferencia de los sockets de red tradicionales (`AF_INET`), los **Sockets de Dominio UNIX (`AF_UNIX`)** operan íntegramente en el espacio de memoria del kernel mediante buffers en `tmpfs`. Esto reduce drásticamente la latencia, elimina la sobrecarga del stack de red (TCP/IP checksums, headers) y permite aplicar los permisos estándar de archivos de Linux (`0600`), garantizando que solo los procesos autorizados del servidor puedan comunicarse con el demonio.

### 3.2 Sincronización y Bloqueo Consultivo (`fcntl.flock`)
Al compartir una base de datos SQLite entre el proceso del servidor web (`Uvicorn`) y el proceso del demonio de fondo, se implementó un administrador de contexto que adquiere un bloqueo exclusivo:
```python
fcntl.flock(fd, fcntl.LOCK_EX)  # Adquirir bloqueo exclusivo a nivel de kernel
try:
    yield conn                  # Ejecutar transacción segura
finally:
    fcntl.flock(fd, fcntl.LOCK_UN)  # Liberar descriptores
```
Esto garantiza consistencia ACID estricta incluso bajo cargas concurrentes intensas.

### 3.3 Manejo de Señales POSIX y Tolerancia a Fallos (Criterio 4)
El sistema intercepta las señales estándar del estándar POSIX:
- **`SIGTERM` (Signal 15):** Utilizada por `systemctl stop`. El servidor detiene la recepción de nuevas conexiones, espera a que las escrituras activas terminen, limpia el socket de `/run/` y finaliza con código de salida `0` sin corromper la base de datos.
- **`SIGHUP` (Signal 1):** Utilizada para recargar configuración al vuelo (`kill -HUP <PID>`). Permite modificar las tasas de usura o datos de la entidad en `config.json` sin tirar el servicio web.

---

## 4. Guía de Comandos para la Sustentación en Vivo

Durante la sustentación ante el docente, se pueden ejecutar los siguientes comandos para demostrar cada concepto en la terminal de Linux:

### 1. Demostrar el Servicio en systemd y Logs en Tiempo Real
```bash
# Ver el estado del proceso demonio y web
sudo systemctl status prestamo-web.service

# Inspeccionar los logs del journal del sistema (SO-06)
sudo journalctl -u prestamo-web.service -n 25 --no-pager
```

### 2. Demostrar el Manejo de Señales POSIX (Criterio 4)
```bash
# Obtener el PID del proceso
PID=$(pgrep -f "src.web.app" | head -n 1)

# Enviar SIGHUP para recarga en caliente sin reiniciar el proceso
kill -HUP $PID

# Enviar SIGTERM para demostrar apagado limpio sin corrupción
kill -TERM $PID
```

### 3. Demostrar Sockets y Descriptores Abiertos
```bash
# Listar los sockets UNIX y archivos de base de datos abiertos por el proceso
lsof -p $PID | grep -E "sock|prestamos.db"
```

### 4. Demostrar Hilos y Concurrencia (SO-02)
```bash
# Inspeccionar los hilos POSIX creados por el proceso
ps -eLf | grep $PID
```

### 5. Medir el Consumo de Recursos (SO-09)
```bash
# Ejecutar la herramienta técnica de medición desarrollada
python3 scripts/measure_resources.py $PID
```
