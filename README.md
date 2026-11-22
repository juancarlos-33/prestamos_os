# PrestamoOS — Sistema de Gestión de Préstamos para Linux

Sistema de gestión de préstamos cooperativos desarrollado como proyecto final para la asignatura de **Sistemas Operativos**.

## Integrantes del Equipo
1. **De la Hoz Moreno, Juan Carlos**
2. **Julio Garay, Yeffry Luis**
3. **Mogrovejo González, Luis Ángel**
4. **Rodríguez Ozahl, Yeferson Alejandro**

---

## 1. Características de Sistemas Operativos Implementadas
- **Arquitectura de Procesos Desacoplada:** Interfaz de usuario (`prestamo-ui`) y Demonio de fondo (`prestamo-daemon`).
- **Concurrencia:** Hilos secundarios (`Worker Threads`) para tareas intensivas de I/O (PDFs, respaldos, consultas) manteniendo la UI a 60 FPS sin congelamientos.
- **IPC Real:** Comunicación entre la UI y el Demonio mediante Sockets de dominio UNIX (`AF_UNIX`) con protocolo JSON por líneas.
- **Sincronización:** Bloqueo consultivo de archivo POSIX (`fcntl.flock`) y transacciones ACID en SQLite (modo WAL).
- **Manejo de Señales POSIX:** Cierre seguro y liberación de descriptores ante `SIGTERM`/`SIGINT`, y recarga en caliente de configuraciones ante `SIGHUP`.
- **Estándar XDG y Seguridad:** Datos en `~/.local/share/prestamos_os` y configuración en `~/.config/prestamos_os` con permisos restrictivos `0700` y `0600`.
- **Servicio del Sistema:** Demonio gestionado por `systemd --user` con política `Restart=on-failure`.
- **Notificaciones de Escritorio:** Integración con D-Bus / `libnotify` (`notify-send`).

---

## 2. Requisitos Previos e Instalación en Linux

### Plataforma Requerida
- Ubuntu 22.04 / 24.04 LTS o Debian 12
- Python 3.10 o superior

### Dependencias del Sistema
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-pyqt6 libnotify-bin
pip install -r requirements.txt
```

### Ejecución de Pruebas Unitarias
```bash
python3 -m unittest tests/test_loan_engine.py -v
```

### Instalación como Servicio y Lanzador de Escritorio
```bash
chmod +x scripts/install.sh
./scripts/install.sh install
```

Para verificar el estado del servicio demonio con systemd:
```bash
systemctl --user status prestamo-daemon.service
journalctl --user -u prestamo-daemon.service -f
```

---

## 3. Comandos Útiles para la Sustentación
- **Monitorear procesos e hilos:** `htop`, `ps -eLf | grep prestamo`
- **Monitorear descriptores abiertos:** `lsof -p <PID>`
- **Monitorear llamadas al sistema:** `strace -p <PID> -e trace=file,desc,signal,socket`
- **Probar envío de señales:**
  - Recarga dinámica: `kill -HUP <PID_DEMONIO>`
  - Cierre ordenado: `kill -TERM <PID_DEMONIO>`
