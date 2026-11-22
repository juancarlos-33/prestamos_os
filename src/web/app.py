"""
Servidor Web de PrestamoOS (FastAPI + Jinja2 Templates).
Plataforma: Linux Server (Ubuntu 22.04/24.04 LTS / Debian 12)

Cumple con:
- SO-01: Ejecución nativa en Linux Server sin emuladores ni servicios externos.
- SO-02: Manejo de concurrencia mediante trabajadores asíncronos y multihilo.
- SO-03: Comunicación IPC con el demonio vía sockets de dominio UNIX (AF_UNIX).
- SO-04: Captura de señales POSIX (SIGTERM para apagado ordenado, SIGHUP para recarga).
- PR-01 / PR-02: Autenticación web con roles (Administrador y Cajero) y sesiones seguras.
- PR-03 a PR-26: Vistas completas para clientes, simulador, pagos, calendario y reportes.
"""

import os
import signal
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Form, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.config import config_app
from src.database.db_manager import db_manager, verify_password
from src.core.loan_engine import (
    LoanEngine, SistemaAmortizacion, TipoTasa, Periodicidad, TipoSeguro, round_money
)
from src.core.pdf_service import PDFService
from src.core.csv_exporter import CSVExporter
from src.daemon.ipc_client import DaemonIPCClient


app = FastAPI(title="PrestamoOS - Linux Server Web Application")

# Configuración de Plantillas Jinja2
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
ipc_client = DaemonIPCClient()

# Sesiones en memoria simple para el servidor web (o basadas en cookies firmadas)
SESSIONS: Dict[str, Dict[str, Any]] = {}


# ==============================================================================
# Manejo de Señales POSIX en el Servidor Web (SO-04)
# ==============================================================================
def manejador_senales_web(signum, frame):
    signame = "SIGTERM" if signum == signal.SIGTERM else ("SIGINT" if signum == signal.SIGINT else "SIGHUP")
    print(f"\n[WEB SERVER] Señal POSIX recibida: {signame}", file=sys.stdout)
    if signum == signal.SIGHUP:
        print("[WEB SERVER] Recargando configuración...", file=sys.stdout)
        config_app.config_data = config_app.cargar_configuracion()
    else:
        print("[WEB SERVER] Cierre ordenado de conexiones...", file=sys.stdout)
        sys.exit(0)

try:
    signal.signal(signal.SIGTERM, manejador_senales_web)
    signal.signal(signal.SIGINT, manejador_senales_web)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, manejador_senales_web)
except (ValueError, AttributeError):
    pass


# ==============================================================================
# Helpers de Autenticación y Sesión (PR-01 y PR-02)
# ==============================================================================
def obtener_usuario_actual(request: Request) -> Optional[Dict[str, Any]]:
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in SESSIONS:
        return None
    return SESSIONS[session_id]


def requerir_autenticacion(request: Request) -> Dict[str, Any]:
    user = obtener_usuario_actual(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def requerir_admin(request: Request) -> Dict[str, Any]:
    user = requerir_autenticacion(request)
    if user["rol"] != "ADMINISTRADOR":
        raise HTTPException(status_code=403, detail="Acceso denegado: Se requiere rol de Administrador.")
    return user


# ==============================================================================
# Rutas de Autenticación (Login / Logout)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = obtener_usuario_actual(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(request=request, name="login.html", context={
        "request": request,
        "error": error,
        "user": None
    })


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = db_manager.get_connection()
    cur = conn.execute(
        """
        SELECT u.id, u.username, u.password_hash, u.nombre_completo, u.activo, r.nombre AS rol
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id
        WHERE u.username = ?
        """,
        (username.strip(),)
    )
    row = cur.fetchone()
    conn.close()

    if not row or not verify_password(row["password_hash"], password.strip()):
        return templates.TemplateResponse(request=request, name="login.html", context={
            "request": request,
            "error": "Usuario o contraseña incorrectos.",
            "user": None
        })

    if not row["activo"]:
        return templates.TemplateResponse(request=request, name="login.html", context={
            "request": request,
            "error": "Usuario inactivo en el sistema.",
            "user": None
        })

    # Crear sesión
    session_token = f"sess_{row['id']}_{datetime.now().timestamp()}"
    SESSIONS[session_token] = {
        "id": row["id"],
        "username": row["username"],
        "nombre_completo": row["nombre_completo"],
        "rol": row["rol"],
    }

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="session_id", value=session_token, httponly=True)
    return response


@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_id")
    return response


# ==============================================================================
# Dashboard Principal
# ==============================================================================
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = requerir_autenticacion(request)

    conn = db_manager.get_connection()
    
    # 1. Estadísticas
    cur = conn.execute("SELECT COUNT(*) FROM clientes WHERE activo = 1")
    total_clientes = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*), COALESCE(SUM(saldo_capital_actual), 0) FROM prestamos WHERE estado = 'ACTIVO'")
    r_act = cur.fetchone()
    prestamos_activos = r_act[0]
    total_cartera = Decimal(str(r_act[1]))

    cur = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(saldo_pendiente_cuota), 0)
        FROM cuotas_amortizacion
        WHERE estado IN ('PENDIENTE', 'EN_MORA') AND fecha_vencimiento < ?
        """,
        (date.today().isoformat(),)
    )
    r_mora = cur.fetchone()
    cuotas_en_mora = r_mora[0]
    total_mora_capital = Decimal(str(r_mora[1]))

    # Recaudo mes actual
    mes_actual_str = date.today().strftime("%Y-%m")
    cur = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(monto_recibido), 0) FROM pagos WHERE strftime('%Y-%m', fecha_pago) = ?",
        (mes_actual_str,)
    )
    r_pag = cur.fetchone()
    pagos_mes_conteo = r_pag[0]
    recaudo_mes = Decimal(str(r_pag[1]))

    # Préstamos recientes
    cur = conn.execute(
        """
        SELECT p.id, cl.nombres, cl.apellidos, p.monto_solicitado, p.saldo_capital_actual,
               p.sistema_amortizacion, p.estado
        FROM prestamos p
        JOIN clientes cl ON p.cliente_id = cl.id
        ORDER BY p.id DESC LIMIT 5
        """
    )
    prestamos_recientes = [dict(r) for r in cur.fetchall()]

    # Alertas de mora crítica
    hoy = date.today()
    tasa_mora = Decimal(str(config_app.config_data.get("parametros_prestamo", {}).get("tasa_mora_anual_defecto", 28.0)))
    cur = conn.execute(
        """
        SELECT p.id as prestamo_id, cl.nombres, cl.apellidos, c.numero_cuota,
               c.fecha_vencimiento, c.saldo_pendiente_cuota
        FROM cuotas_amortizacion c
        JOIN prestamos p ON c.prestamo_id = p.id
        JOIN clientes cl ON p.cliente_id = cl.id
        WHERE c.estado IN ('PENDIENTE', 'EN_MORA') AND c.fecha_vencimiento < ?
        ORDER BY c.fecha_vencimiento ASC LIMIT 4
        """,
        (hoy.isoformat(),)
    )
    alertas_mora = []
    for r in cur.fetchall():
        y, m, d = map(int, str(r["fecha_vencimiento"]).split("-"))
        dias = (hoy - date(y, m, d)).days
        mora_est = LoanEngine.calcular_interes_moratorio_diario(Decimal(str(r["saldo_pendiente_cuota"])), tasa_mora, dias)
        alertas_mora.append({
            "prestamo_id": r["prestamo_id"],
            "nombres": r["nombres"],
            "apellidos": r["apellidos"],
            "numero_cuota": r["numero_cuota"],
            "saldo_pendiente_cuota": Decimal(str(r["saldo_pendiente_cuota"])),
            "dias_mora": dias,
            "mora_estimada": mora_est
        })

    conn.close()

    # Estado Demonio IPC
    ipc_resp = ipc_client.obtener_estado()
    daemon_online = (ipc_resp.get("status") == "OK")
    daemon_pid = ipc_resp.get("data", {}).get("daemon_pid") if daemon_online else None

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "request": request,
        "user": user,
        "active_page": "dashboard",
        "stats": {
            "total_clientes": total_clientes,
            "prestamos_activos": prestamos_activos,
            "total_cartera": total_cartera,
            "cuotas_en_mora": cuotas_en_mora,
            "total_mora_capital": total_mora_capital,
            "pagos_mes_conteo": pagos_mes_conteo,
            "recaudo_mes": recaudo_mes,
        },
        "prestamos_recientes": prestamos_recientes,
        "alertas_mora": alertas_mora,
        "daemon_online": daemon_online,
        "daemon_pid": daemon_pid,
    })


# ==============================================================================
# Gestión de Clientes (PR-03 al PR-06)
# ==============================================================================
@app.get("/clientes", response_class=HTMLResponse)
async def clientes_list(request: Request, p: int = 1, q: Optional[str] = None):
    user = requerir_autenticacion(request)
    tamanio = 10
    offset = (p - 1) * tamanio
    termino = f"%{q.strip()}%" if q else "%"

    conn = db_manager.get_connection()
    c_cur = conn.execute(
        "SELECT COUNT(*) FROM clientes WHERE numero_documento LIKE ? OR (nombres || ' ' || apellidos) LIKE ?",
        (termino, termino)
    )
    total_registros = c_cur.fetchone()[0]
    total_paginas = max(1, (total_registros + tamanio - 1) // tamanio)

    cur = conn.execute(
        """
        SELECT * FROM clientes
        WHERE numero_documento LIKE ? OR (nombres || ' ' || apellidos) LIKE ?
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,
        (termino, termino, tamanio, offset)
    )
    clientes = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="clientes.html", context={
        "request": request,
        "user": user,
        "active_page": "clientes",
        "clientes": clientes,
        "pagina": p,
        "total_paginas": total_paginas,
        "total_registros": total_registros,
        "query": q
    })


@app.post("/clientes/guardar")
async def cliente_guardar(
    request: Request,
    cliente_id: Optional[str] = Form(None),
    tipo_documento: str = Form(...),
    numero_documento: str = Form(...),
    nombres: str = Form(...),
    apellidos: str = Form(...),
    fecha_nacimiento: str = Form(...),
    telefono: str = Form(...),
    correo: str = Form(...),
    ingresos_mensuales: float = Form(...),
    direccion: str = Form(...),
    ocupacion: Optional[str] = Form(""),
    activo: Optional[int] = Form(1)
):
    requerir_autenticacion(request)

    with db_manager.transaction() as conn:
        if cliente_id and cliente_id.strip():
            conn.execute(
                """
                UPDATE clientes
                SET tipo_documento = ?, nombres = ?, apellidos = ?, fecha_nacimiento = ?,
                    telefono = ?, correo = ?, direccion = ?, ocupacion = ?, ingresos_mensuales = ?, activo = ?
                WHERE id = ?
                """,
                (tipo_documento, nombres, apellidos, fecha_nacimiento, telefono, correo, direccion, ocupacion, str(ingresos_mensuales), activo, int(cliente_id))
            )
        else:
            conn.execute(
                """
                INSERT INTO clientes (tipo_documento, numero_documento, nombres, apellidos,
                                     fecha_nacimiento, telefono, correo, direccion, ocupacion, ingresos_mensuales, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (tipo_documento, numero_documento.strip(), nombres, apellidos, fecha_nacimiento, telefono, correo, direccion, ocupacion, str(ingresos_mensuales))
            )

    return RedirectResponse(url="/clientes", status_code=303)


# ==============================================================================
# Préstamos y Simulador (PR-07 al PR-13)
# ==============================================================================
class SimularRequest(BaseModel):
    monto: float
    tasa_interes: float
    tipo_tasa: str
    num_cuotas: int
    periodicidad: str
    sistema: str
    seguro_comision: float = 0.0
    tipo_seguro: str = "FIJO"
    fecha_desembolso: str


@app.get("/prestamos", response_class=HTMLResponse)
async def prestamos_page(request: Request):
    user = requerir_autenticacion(request)
    conn = db_manager.get_connection()
    cur = conn.execute("SELECT id, tipo_documento, numero_documento, nombres, apellidos FROM clientes WHERE activo = 1 ORDER BY nombres ASC")
    clientes = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="prestamos.html", context={
        "request": request,
        "user": user,
        "active_page": "prestamos",
        "clientes": clientes,
        "hoy": date.today().isoformat()
    })


@app.post("/api/simular")
async def api_simular(req: SimularRequest):
    try:
        y, m, d = map(int, req.fecha_desembolso.split("-"))
        f_desemb = date(y, m, d)

        # Feriados desde BD
        feriados = set()
        conn = db_manager.get_connection()
        for r in conn.execute("SELECT fecha FROM feriados").fetchall():
            fy, fm, fd = map(int, str(r[0]).split("-"))
            feriados.add(date(fy, fm, fd))
        conn.close()

        resumen = LoanEngine.generar_tabla_amortizacion(
            monto=Decimal(str(req.monto)),
            tasa_interes=Decimal(str(req.tasa_interes)),
            tipo_tasa=TipoTasa(req.tipo_tasa),
            num_cuotas=req.num_cuotas,
            periodicidad=Periodicidad(req.periodicidad),
            sistema=SistemaAmortizacion(req.sistema),
            fecha_desembolso=f_desemb,
            seguro_comision=Decimal(str(req.seguro_comision)),
            tipo_seguro=TipoSeguro(req.tipo_seguro),
            feriados=feriados,
        )

        cuotas_data = []
        for c in resumen.cuotas:
            cuotas_data.append({
                "numero_cuota": c.numero_cuota,
                "fecha_vencimiento": c.fecha_vencimiento.isoformat(),
                "abono_capital": float(c.abono_capital),
                "interes_corriente": float(c.interes_corriente),
                "cargo_adicional": float(c.cargo_adicional),
                "cuota_total": float(c.cuota_total),
                "saldo_restante": float(c.saldo_restante)
            })

        return {
            "status": "OK",
            "data": {
                "total_capital": float(resumen.total_capital),
                "total_intereses": float(resumen.total_intereses),
                "total_cargos": float(resumen.total_cargos),
                "total_a_pagar": float(resumen.total_a_pagar),
                "cuota_fija_referencial": float(resumen.cuota_fija_referencial) if resumen.cuota_fija_referencial else None,
                "cuotas": cuotas_data
            }
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


@app.post("/prestamos/desembolsar")
async def prestamos_desembolsar(
    request: Request,
    cliente_id: int = Form(...),
    monto: float = Form(...),
    tasa_interes: float = Form(...),
    tipo_tasa: str = Form(...),
    num_cuotas: int = Form(...),
    periodicidad: str = Form(...),
    sistema: str = Form(...),
    seguro_comision: float = Form(0.0),
    tipo_seguro: str = Form("FIJO"),
    fecha_desembolso: str = Form(...)
):
    user = requerir_autenticacion(request)

    # 1. Verificar umbral de mora (PR-11)
    umbral_dias = config_app.config_data.get("parametros_prestamo", {}).get("umbral_dias_mora_bloqueo", 30)
    hoy = date.today()

    conn = db_manager.get_connection()
    cur = conn.execute(
        """
        SELECT c.fecha_vencimiento
        FROM cuotas_amortizacion c
        JOIN prestamos p ON c.prestamo_id = p.id
        WHERE p.cliente_id = ? AND c.estado IN ('PENDIENTE', 'EN_MORA') AND c.fecha_vencimiento < ?
        ORDER BY c.fecha_vencimiento ASC LIMIT 1
        """,
        (cliente_id, hoy.isoformat())
    )
    mora_row = cur.fetchone()
    conn.close()

    if mora_row:
        my, mm, md = map(int, str(mora_row[0]).split("-"))
        dias = (hoy - date(my, mm, md)).days
        if dias > umbral_dias:
            return RedirectResponse(url=f"/prestamos?error=Cliente_con_mora_superior_al_umbral_{dias}_dias", status_code=303)

    # 2. Generar tabla de amortización
    y, m, d = map(int, fecha_desembolso.split("-"))
    f_desemb = date(y, m, d)
    monto_dec = Decimal(str(monto))

    resumen = LoanEngine.generar_tabla_amortizacion(
        monto=monto_dec,
        tasa_interes=Decimal(str(tasa_interes)),
        tipo_tasa=TipoTasa(tipo_tasa),
        num_cuotas=num_cuotas,
        periodicidad=Periodicidad(periodicidad),
        sistema=SistemaAmortizacion(sistema),
        fecha_desembolso=f_desemb,
        seguro_comision=Decimal(str(seguro_comision)),
        tipo_seguro=TipoSeguro(tipo_seguro)
    )

    # 3. Guardar en BD con transacción atómica (SO-10)
    with db_manager.transaction() as tx:
        cur_p = tx.execute(
            """
            INSERT INTO prestamos (
                cliente_id, usuario_id, monto_solicitado, tasa_interes, tipo_tasa,
                plazo_cuotas, periodicidad, sistema_amortizacion, seguro_comision,
                tipo_seguro, fecha_desembolso, estado, saldo_capital_actual
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?)
            """,
            (
                cliente_id, user["id"], str(monto_dec), str(tasa_interes), tipo_tasa,
                num_cuotas, periodicidad, sistema, str(seguro_comision), tipo_seguro,
                fecha_desembolso, str(monto_dec)
            )
        )
        prestamo_id = cur_p.lastrowid

        for c in resumen.cuotas:
            tx.execute(
                """
                INSERT INTO cuotas_amortizacion (
                    prestamo_id, numero_cuota, fecha_vencimiento, abono_capital,
                    interes_corriente, cargo_adicional, cuota_total, saldo_restante,
                    estado, saldo_pendiente_cuota
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
                """,
                (
                    prestamo_id, c.numero_cuota, c.fecha_vencimiento.isoformat(),
                    str(c.abono_capital), str(c.interes_corriente), str(c.cargo_adicional),
                    str(c.cuota_total), str(c.saldo_restante), str(c.cuota_total)
                )
            )

    return RedirectResponse(url="/dashboard", status_code=303)


# ==============================================================================
# Pagos y Recaudos (PR-17 al PR-20)
# ==============================================================================
@app.get("/pagos", response_class=HTMLResponse)
async def pagos_page(request: Request, prestamo_id: Optional[int] = None):
    user = requerir_autenticacion(request)

    conn = db_manager.get_connection()
    cur = conn.execute(
        """
        SELECT p.id, p.monto_solicitado, p.saldo_capital_actual, p.estado,
               cl.tipo_documento, cl.numero_documento, cl.nombres, cl.apellidos
        FROM prestamos p
        JOIN clientes cl ON p.cliente_id = cl.id
        WHERE p.estado IN ('ACTIVO', 'EN_MORA')
        ORDER BY p.id DESC
        """
    )
    prestamos = [dict(r) for r in cur.fetchall()]

    prestamo_seleccionado = None
    cuota_actual = None
    mora_calculada = Decimal("0.00")
    dias_atraso = 0
    cuota_sugerida = 0.0

    if prestamo_id:
        p_row = conn.execute(
            """
            SELECT p.*, cl.tipo_documento, cl.numero_documento, cl.nombres, cl.apellidos
            FROM prestamos p
            JOIN clientes cl ON p.cliente_id = cl.id
            WHERE p.id = ?
            """,
            (prestamo_id,)
        ).fetchone()

        if p_row:
            prestamo_seleccionado = dict(p_row)
            c_row = conn.execute(
                """
                SELECT * FROM cuotas_amortizacion
                WHERE prestamo_id = ? AND estado IN ('PENDIENTE', 'EN_MORA')
                ORDER BY fecha_vencimiento ASC LIMIT 1
                """,
                (prestamo_id,)
            ).fetchone()

            if c_row:
                cuota_actual = dict(c_row)
                y, m, d = map(int, str(cuota_actual["fecha_vencimiento"]).split("-"))
                f_venc = date(y, m, d)
                hoy = date.today()
                if hoy > f_venc:
                    dias_atraso = (hoy - f_venc).days
                    tasa_mora = Decimal(str(config_app.config_data.get("parametros_prestamo", {}).get("tasa_mora_anual_defecto", 28.0)))
                    mora_calculada = LoanEngine.calcular_interes_moratorio_diario(
                        Decimal(str(cuota_actual["saldo_pendiente_cuota"])), tasa_mora, dias_atraso
                    )
                cuota_sugerida = float(Decimal(str(cuota_actual["saldo_pendiente_cuota"])) + mora_calculada)
            else:
                cuota_sugerida = float(p_row["saldo_capital_actual"])

    conn.close()

    return templates.TemplateResponse(request=request, name="pagos.html", context={
        "request": request,
        "user": user,
        "active_page": "pagos",
        "prestamos": prestamos,
        "prestamo_seleccionado": prestamo_seleccionado,
        "cuota_actual": cuota_actual,
        "mora_calculada": float(mora_calculada),
        "dias_atraso": dias_atraso,
        "cuota_sugerida": cuota_sugerida,
    })


@app.post("/pagos/procesar")
async def pagos_procesar(
    request: Request,
    prestamo_id: int = Form(...),
    monto_pago: float = Form(...),
    metodo_pago: str = Form(...),
    mora_actual: float = Form(0.0),
    interes_actual: float = Form(0.0),
    saldo_capital: float = Form(...)
):
    user = requerir_autenticacion(request)

    monto_dec = round_money(Decimal(str(monto_pago)))
    desglose = LoanEngine.aplicar_pago(
        monto_pago=monto_dec,
        mora_pendiente=Decimal(str(mora_actual)),
        interes_pendiente=Decimal(str(interes_actual)),
        saldo_capital=Decimal(str(saldo_capital)),
    )

    recibo_num = f"REC-{prestamo_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    fecha_ahora = datetime.now()

    conn = db_manager.get_connection()
    p_info = conn.execute(
        """
        SELECT p.*, cl.nombres, cl.apellidos, cl.tipo_documento, cl.numero_documento
        FROM prestamos p JOIN clientes cl ON p.cliente_id = cl.id WHERE p.id = ?
        """,
        (prestamo_id,)
    ).fetchone()
    conn.close()

    # Transacción segura de pago
    with db_manager.transaction() as tx:
        cur_p = tx.execute(
            """
            INSERT INTO pagos (
                prestamo_id, usuario_id, fecha_pago, monto_recibido, metodo_pago,
                numero_recibo, aplicado_mora, aplicado_interes, aplicado_capital
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prestamo_id, user["id"], fecha_ahora.strftime("%Y-%m-%d %H:%M:%S"),
                str(monto_dec), metodo_pago, recibo_num, str(desglose.mora_cubierta),
                str(desglose.interes_cubierto), str(desglose.capital_cubierto)
            )
        )
        pago_id = cur_p.lastrowid

        # Imputar cuota si aplica
        c_row = tx.execute(
            "SELECT id FROM cuotas_amortizacion WHERE prestamo_id = ? AND estado IN ('PENDIENTE', 'EN_MORA') ORDER BY fecha_vencimiento ASC LIMIT 1",
            (prestamo_id,)
        ).fetchone()
        if c_row:
            tx.execute("INSERT INTO detalle_pago_cuota (pago_id, cuota_id, monto_aplicado) VALUES (?, ?, ?)", (pago_id, c_row[0], str(monto_dec)))
            tx.execute("UPDATE cuotas_amortizacion SET estado = 'PAGADA', saldo_pendiente_cuota = 0 WHERE id = ? AND saldo_pendiente_cuota <= ?", (c_row[0], str(monto_dec)))

        nuevo_estado = "CANCELADO" if desglose.nuevo_saldo_capital <= Decimal("0.00") else "ACTIVO"
        tx.execute("UPDATE prestamos SET saldo_capital_actual = ?, estado = ? WHERE id = ?", (str(desglose.nuevo_saldo_capital), nuevo_estado, prestamo_id))

    # Generar Comprobante PDF (PR-20)
    pdf_path = PDFService.generar_comprobante_pago(
        recibo_num=recibo_num,
        fecha_pago=fecha_ahora,
        cliente_nombre=f"{p_info['nombres']} {p_info['apellidos']}",
        cliente_doc=f"{p_info['tipo_documento']} {p_info['numero_documento']}",
        prestamo_id=prestamo_id,
        monto_recibido=monto_dec,
        desglose_mora=desglose.mora_cubierta,
        desglose_interes=desglose.interes_cubierto,
        desglose_capital=desglose.capital_cubierto,
        nuevo_saldo=desglose.nuevo_saldo_capital,
        metodo_pago=metodo_pago,
        usuario_cajero=user["nombre_completo"],
    )

    with db_manager.transaction() as tx:
        tx.execute("UPDATE pagos SET ruta_pdf_comprobante = ? WHERE id = ?", (str(pdf_path), pago_id))

    return RedirectResponse(url=f"/descargar/recibo/{recibo_num}", status_code=303)


@app.get("/descargar/recibo/{recibo_num}")
async def descargar_recibo(recibo_num: str):
    conn = db_manager.get_connection()
    row = conn.execute("SELECT ruta_pdf_comprobante FROM pagos WHERE numero_recibo = ?", (recibo_num,)).fetchone()
    conn.close()

    if not row or not row[0] or not Path(row[0]).exists():
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")

    return FileResponse(row[0], media_type="application/pdf", filename=f"comprobante_{recibo_num}.pdf")


# ==============================================================================
# Calendario Visual (PR-14 y PR-15)
# ==============================================================================
@app.get("/calendario", response_class=HTMLResponse)
async def calendario_page(request: Request, anio: Optional[int] = None, mes: Optional[int] = None):
    user = requerir_autenticacion(request)

    hoy = date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month

    # Navegación
    mes_ant = 12 if mes == 1 else mes - 1
    anio_ant = anio - 1 if mes == 1 else anio
    mes_sig = 1 if mes == 12 else mes + 1
    anio_sig = anio + 1 if mes == 12 else anio

    meses_nombres = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    nombre_mes = meses_nombres[mes]

    conn = db_manager.get_connection()
    # Feriados
    feriados = {str(r[0]): r[1] for r in conn.execute("SELECT fecha, descripcion FROM feriados").fetchall()}

    # Cuotas del mes
    cur = conn.execute(
        """
        SELECT c.numero_cuota, c.fecha_vencimiento, c.cuota_total, c.estado,
               p.id as prestamo_id, cl.nombres, cl.apellidos, cl.telefono
        FROM cuotas_amortizacion c
        JOIN prestamos p ON c.prestamo_id = p.id
        JOIN clientes cl ON p.cliente_id = cl.id
        WHERE strftime('%Y-%m', c.fecha_vencimiento) = ?
        """,
        (f"{anio:04d}-{mes:02d}",)
    )
    cuotas_por_fecha = {}
    for r in cur.fetchall():
        f = str(r["fecha_vencimiento"])
        if f not in cuotas_por_fecha:
            cuotas_por_fecha[f] = []
        cuotas_por_fecha[f].append({
            "prestamo_id": r["prestamo_id"],
            "nombres": r["nombres"],
            "apellidos": r["apellidos"],
            "telefono": r["telefono"],
            "numero_cuota": r["numero_cuota"],
            "cuota_total": float(r["cuota_total"]),
            "estado": r["estado"]
        })
    conn.close()

    # Construir matriz de semanas
    import calendar
    cal = calendar.Calendar(firstweekday=0) # 0 = Lunes
    dias_mes = cal.monthdayscalendar(anio, mes)

    semanas = []
    for sem in dias_mes:
        fila = []
        for dia in sem:
            if dia == 0:
                fila.append({"dia": 0})
            else:
                f_iso = f"{anio:04d}-{mes:02d}-{dia:02d}"
                d_obj = date(anio, mes, dia)
                c_dia = cuotas_por_fecha.get(f_iso, [])
                es_fer = f_iso in feriados
                tiene_mora = any(c["estado"] == "EN_MORA" or (c["estado"] == "PENDIENTE" and d_obj < hoy) for c in c_dia)
                tiene_pend = any(c["estado"] == "PENDIENTE" and d_obj >= hoy for c in c_dia)
                tiene_pag = any(c["estado"] == "PAGADA" for c in c_dia)

                fila.append({
                    "dia": dia,
                    "fecha_iso": f_iso,
                    "es_fin_semana": d_obj.weekday() >= 5,
                    "es_feriado": es_fer,
                    "feriado_desc": feriados.get(f_iso, ""),
                    "tiene_mora": tiene_mora,
                    "tiene_pendiente": tiene_pend,
                    "tiene_pagada": tiene_pag,
                })
        semanas.append(fila)

    import json
    return templates.TemplateResponse(request=request, name="calendario.html", context={
        "request": request,
        "user": user,
        "active_page": "calendario",
        "anio": anio,
        "mes": mes,
        "nombre_mes": nombre_mes,
        "mes_ant": mes_ant,
        "anio_ant": anio_ant,
        "mes_sig": mes_sig,
        "anio_sig": anio_sig,
        "semanas": semanas,
        "cuotas_json": json.dumps(cuotas_por_fecha)
    })


# ==============================================================================
# Reportes y Exportaciones (PR-21 al PR-24)
# ==============================================================================
@app.get("/reportes", response_class=HTMLResponse)
async def reportes_page(request: Request):
    user = requerir_autenticacion(request)
    hoy = date.today().isoformat()
    hace_un_mes = (date.today() - timedelta(days=30)).isoformat()
    return templates.TemplateResponse(request=request, name="reportes.html", context={
        "request": request,
        "user": user,
        "active_page": "reportes",
        "hoy": hoy,
        "hace_un_mes": hace_un_mes
    })


@app.get("/reportes/descargar")
async def reportes_descargar(
    request: Request,
    tipo: str,
    formato: str = "PDF",
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None
):
    user = requerir_autenticacion(request)
    emisor = user["nombre_completo"]

    archivo_generado: Optional[Path] = None

    if formato.upper() == "PDF":
        if tipo == "CARTERA_VIGENTE":
            archivo_generado = PDFService.generar_reporte_cartera_vigente(emisor)
        elif tipo == "CARTERA_MORA":
            archivo_generado = PDFService.generar_reporte_cartera_en_mora(emisor)
        elif tipo == "RECAUDO_FECHAS":
            y1, m1, d1 = map(int, fecha_inicio.split("-"))
            y2, m2, d2 = map(int, fecha_fin.split("-"))
            archivo_generado = PDFService.generar_reporte_recaudo_rango(date(y1, m1, d1), date(y2, m2, d2), emisor)
        return FileResponse(archivo_generado, media_type="application/pdf", filename=archivo_generado.name)

    elif formato.upper() == "CSV":
        if tipo == "CARTERA_VIGENTE":
            archivo_generado = CSVExporter.exportar_cartera_vigente()
        elif tipo == "CARTERA_MORA":
            archivo_generado = CSVExporter.exportar_cartera_en_mora()
        elif tipo == "RECAUDO_FECHAS":
            y1, m1, d1 = map(int, fecha_inicio.split("-"))
            y2, m2, d2 = map(int, fecha_fin.split("-"))
            archivo_generado = CSVExporter.exportar_recaudo_rango(date(y1, m1, d1), date(y2, m2, d2))
        return FileResponse(archivo_generado, media_type="text/csv", filename=archivo_generado.name)

    raise HTTPException(status_code=400, detail="Tipo o formato no reconocido.")


# ==============================================================================
# Configuración y Monitor IPC (PR-25, PR-26, SO-03, SO-04) — Solo Admin
# ==============================================================================
@app.get("/configuracion", response_class=HTMLResponse)
async def configuracion_page(request: Request):
    user = requerir_admin(request)

    ipc_resp = ipc_client.obtener_estado()
    daemon_online = (ipc_resp.get("status") == "OK")
    daemon_pid = ipc_resp.get("data", {}).get("daemon_pid") if daemon_online else None

    # Lista de respaldos
    b_dir = config_app.backup_dir
    backups = []
    if b_dir.exists():
        for f in sorted(list(b_dir.glob("*.sql.gz")), key=lambda p: p.stat().st_mtime, reverse=True):
            backups.append({
                "nombre": f.name,
                "tamanio_kb": f"{f.stat().st_size / 1024:.1f}",
                "fecha": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    return templates.TemplateResponse(request=request, name="configuracion.html", context={
        "request": request,
        "user": user,
        "active_page": "configuracion",
        "config": config_app.config_data,
        "daemon_online": daemon_online,
        "daemon_pid": daemon_pid,
        "socket_path": str(config_app.socket_path),
        "backups": backups
    })


@app.post("/configuracion/guardar")
async def configuracion_guardar(
    request: Request,
    nombre_entidad: str = Form(...),
    nit: str = Form(...),
    telefono: str = Form(...),
    direccion: str = Form(...),
    tasa_maxima_anual: float = Form(...),
    tasa_mora_anual_defecto: float = Form(...),
    umbral_dias_mora_bloqueo: int = Form(...),
    alerta_cuotas_dias_anticipacion: int = Form(...)
):
    requerir_admin(request)

    nueva = config_app.config_data.copy()
    nueva["entidad"]["nombre"] = nombre_entidad.strip()
    nueva["entidad"]["nit"] = nit.strip()
    nueva["entidad"]["telefono"] = telefono.strip()
    nueva["entidad"]["direccion"] = direccion.strip()
    nueva["parametros_prestamo"]["tasa_maxima_anual"] = tasa_maxima_anual
    nueva["parametros_prestamo"]["tasa_mora_anual_defecto"] = tasa_mora_anual_defecto
    nueva["parametros_prestamo"]["umbral_dias_mora_bloqueo"] = umbral_dias_mora_bloqueo
    nueva["parametros_prestamo"]["alerta_cuotas_dias_anticipacion"] = alerta_cuotas_dias_anticipacion

    config_app.guardar_configuracion(nueva)
    # Notificar al demonio de fondo
    ipc_client.recargar_configuracion()

    return RedirectResponse(url="/configuracion", status_code=303)


@app.post("/configuracion/respaldo_ipc")
async def configuracion_respaldo_ipc(request: Request):
    requerir_admin(request)
    ipc_client.forzar_respaldo()
    return RedirectResponse(url="/configuracion", status_code=303)


@app.post("/configuracion/recargar_sighup")
async def configuracion_recargar_sighup(request: Request):
    requerir_admin(request)
    ipc_client.recargar_configuracion()
    return RedirectResponse(url="/configuracion", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.app:app", host="0.0.0.0", port=8000, reload=True)
