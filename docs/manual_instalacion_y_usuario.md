# Manual de Instalación y Manual de Usuario

**Proyecto:** Sistema Web de Gestión de Préstamos (PrestamoOS)  
**Asignatura:** Sistemas Operativos  
**Equipo de Trabajo:**
1. De la Hoz Moreno, Juan Carlos
2. Julio Garay, Yeffry Luis
3. Mogrovejo González, Luis Ángel
4. Rodríguez Ozahl, Yeferson Alejandro  

---

# PARTE 1: MANUAL DE INSTALACIÓN EN SERVIDOR LINUX

Este manual describe el procedimiento para desplegar la aplicación web de forma nativa en un servidor limpio con **Ubuntu 22.04 / 24.04 LTS** o **Debian 12**.

## 1. Requisitos Previos del Servidor
- Servidor o Máquina Virtual con Linux (mínimo 1 vCPU, 1 GB de RAM).
- Conexión a Internet y acceso con privilegios `sudo`.
- Puertos habilitados: `8000/TCP` (Web) y `22/TCP` (SSH).

## 2. Instalación en un Solo Paso (Recomendado)
Clone el repositorio en el servidor y ejecute el script automatizado:

```bash
# 1. Clonar el repositorio
git clone <URL_DEL_REPOSITORIO_GIT> prestamos_os
cd prestamos_os

# 2. Asignar permisos de ejecución y correr el instalador
chmod +x scripts/deploy_server.sh
sudo ./scripts/deploy_server.sh
```

El script se encargará automáticamente de:
- Instalar paquetes del sistema (`python3`, `python3-pip`, `python3-venv`, `sqlite3`, `libnotify-bin`).
- Crear el entorno virtual en `/opt/prestamos_os/venv`.
- Inicializar la base de datos relacional y sembrar más de 800 cuotas de prueba.
- Instalar y habilitar el servicio del sistema `prestamo-web.service` con `systemd`.
- Abrir el puerto 8000 en el cortafuegos `ufw`.

---

## 3. Instalación Manual Paso a Paso (Alternativa)

Si prefiere realizar la configuración paso a paso:

```bash
# Paso 1: Actualizar repositorios e instalar paquetes base
sudo apt update && sudo apt install -y python3 python3-pip python3-venv sqlite3

# Paso 2: Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Paso 3: Inicializar la base de datos y datos de prueba
python scripts/seed_demo_data.py

# Paso 4: Iniciar el servidor web
uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## 4. Gestión del Servicio en Linux (systemd)

Para verificar y administrar el servicio web en el servidor:
- **Ver estado en vivo:** `sudo systemctl status prestamo-web.service`
- **Ver registros en tiempo real:** `sudo journalctl -u prestamo-web.service -f`
- **Reiniciar servicio:** `sudo systemctl restart prestamo-web.service`
- **Detener servicio:** `sudo systemctl stop prestamo-web.service`

---

# PARTE 2: MANUAL DE USUARIO

Una vez iniciado el servidor, abra su navegador web preferido (Chrome, Firefox, Edge) e ingrese a:
`http://<IP_DEL_SERVIDOR>:8000` (o `http://localhost:8000` si está local).

## 1. Inicio de Sesión y Control de Acceso (PR-01 y PR-02)
El sistema cuenta con autenticación segura protegida mediante hashes criptográficos.
- **Usuario Administrador:** `admin` / `admin123` (Acceso total al sistema y configuraciones).
- **Usuario Cajero:** `cajero` / `cajero123` (Operación diaria: clientes, préstamos y recaudos; sin acceso a configuración).

---

## 2. Padrón de Clientes (PR-03 al PR-06)
1. Ingrese a la pestaña **👥 Clientes** en la barra superior.
2. Para registrar un cliente, haga clic en **+ Registrar Nuevo Cliente**:
   - Complete tipo y número de documento (único), nombres, apellidos, teléfono, correo e ingresos.
   - El sistema valida en tiempo real expresiones regulares para email y formato telefónico numérico.
3. Use la barra de búsqueda superior para filtrar clientes por nombre o cédula.
4. La tabla incluye paginación dinámica de 10 en 10 registros.

---

## 3. Simulador y Otorgamiento de Préstamos (PR-07 al PR-13)
1. Diríjase a la pestaña **📊 Préstamos**.
2. Seleccione el cliente solicitante en el menú desplegable.
3. Ingrese el monto, plazo (cuotas), periodicidad (semanal, quincenal, mensual) y tasa de interés.
4. Elija el método de amortización:
   - **Francés:** Cuota periódica fija.
   - **Alemán:** Abono constante a capital con cuotas decrecientes.
   - **Interés Simple:** Interés lineal sobre saldo inicial.
5. Haga clic en **▶ Calcular Simulación (PR-09)**:
   - La pantalla proyectará de inmediato el resumen financiero (cuota estimada, total intereses, total a pagar) y la tabla completa cuota por cuota con sus fechas de vencimiento omitiendo fines de semana y festivos.
6. Haga clic en **✓ Aprobar y Desembolsar Préstamo**:
   - Si el cliente tiene mora superior al umbral configurado (ej. 30 días), el sistema **bloqueará el crédito automáticamente** notificando la causa (PR-11).

---

## 4. Cobros y Liquidación de Cuotas (PR-17 al PR-20)
1. Ingrese a la pestaña **💰 Pagos**.
2. Seleccione un crédito de la lista de préstamos activos o en mora.
3. El panel derecho calculará el interés moratorio diario exacto según los días de atraso.
4. Digite el valor a pagar y observe el **desglose automático de imputación legal**:
   - **1.** Cobertura de Mora $\rightarrow$ **2.** Interés Corriente $\rightarrow$ **3.** Abono a Capital.
5. Haga clic en **Confirmar Pago**:
   - El saldo se actualiza atómicamente y el navegador descargará inmediatamente el **Comprobante Oficial en PDF**.

---

## 5. Calendario Visual de Vencimientos (PR-14 y PR-15)
1. Ingrese a la pestaña **📅 Calendario**.
2. Cada día del mes cuenta con distintivos visuales de color:
   - 🔵 **Azul:** Cuota pendiente al día.
   - 🔴 **Rojo:** Cuota vencida en mora.
   - 🟢 **Verde:** Cuota pagada.
   - 🟡 **Fondo Ámbar:** Día festivo o feriado oficial.
3. Al hacer clic sobre cualquier día, el panel lateral desplegará el listado detallado de todas las cuotas de esa fecha con botón directo para proceder al cobro.

---

## 6. Reportes Oficiales y Exportación CSV (PR-21 al PR-24)
1. Ingrese a la pestaña **📑 Reportes**.
2. Podrá descargar con un solo clic:
   - **Cartera Vigente:** PDF oficial con encabezado institucional y pie de página `Página X de Y`, o archivo CSV para Excel.
   - **Cartera en Mora:** Informe con días de atraso y mora proyectada (PDF / CSV).
   - **Recaudo por Fechas:** Reporte de ingresos seleccionando fecha inicial y final (PDF / CSV).
