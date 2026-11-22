"""
Gestor de Base de Datos y Persistencia para el Sistema de Préstamos.

Cumple con:
- SO-02 / Sincronización: Control de concurrencia y bloqueos mediante `fcntl.flock` en Linux.
- PR-01 / PR-02: Creación de roles (Administrador, Cajero) y usuario inicial seguro.
- SO-10: Manejo robusto de errores de E/S y transacciones seguras (ACID) con SQLite WAL.
"""

import hashlib
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from src.config import config_app

# Soporte opcional para fcntl en Linux/Unix
try:
    import fcntl
    HAVE_FCNTL = True
except ImportError:
    HAVE_FCNTL = False


def hash_password(password: str) -> str:
    """
    Genera un hash seguro para contraseñas.
    Usa Argon2 si está instalado; de lo contrario utiliza PBKDF2-HMAC-SHA256 con sal nativa.
    """
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        return ph.hash(password)
    except ImportError:
        # Fallback seguro estándar de Python sin dependencias externas
        salt = os.urandom(16)
        kdf = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return f"pbkdf2:sha256:100000${salt.hex()}${kdf.hex()}"


def verify_password(stored_hash: str, password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con el hash almacenado."""
    if stored_hash.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError
            ph = PasswordHasher()
            try:
                return ph.verify(stored_hash, password)
            except VerifyMismatchError:
                return False
        except ImportError:
            return False

    if stored_hash.startswith("pbkdf2:sha256:"):
        parts = stored_hash.split("$")
        if len(parts) == 3:
            salt = bytes.fromhex(parts[1])
            expected_kdf = bytes.fromhex(parts[2])
            calc_kdf = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
            return calc_kdf == expected_kdf

    return False


class DatabaseManager:
    """Gestor de conexiones SQLite con soporte para WAL, transacciones y flock."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config_app.db_file
        self.lock_file_path = self.db_path.with_suffix(".lock")
        self._inicializar_base_datos()

    def get_connection(self) -> sqlite3.Connection:
        """Crea y retorna una conexión configurada con PRAGMAs óptimos."""
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=20.0,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            conn.row_factory = sqlite3.Row
            # Activar claves foráneas y modo WAL para lectura y escritura simultáneas
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            return conn
        except sqlite3.OperationalError as e:
            print(f"[ERROR SO-10 BD] No se pudo abrir la base de datos: {e}", file=sys.stderr)
            raise

    @contextmanager
    def file_lock(self, exclusive: bool = True):
        """
        Bloqueo consultivo de archivo POSIX (flock).
        Garantiza sincronización segura entre el proceso de la UI y el Demonio en Linux.
        """
        if not HAVE_FCNTL:
            # En Windows u otros sistemas sin fcntl, opera como no-op transparente
            yield
            return

        lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            with open(self.lock_file_path, "w") as lock_f:
                fcntl.flock(lock_f.fileno(), lock_mode)
                try:
                    yield
                finally:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            print(f"[ALERTA SINCRONIZACIÓN] Error en bloqueo flock: {e}", file=sys.stderr)
            yield

    @contextmanager
    def transaction(self):
        """Manejador de contexto para transacciones atómicas con control de bloqueo."""
        with self.file_lock(exclusive=True):
            conn = self.get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"[ERROR TRANSACCIÓN BD] Rollback ejecutado: {e}", file=sys.stderr)
                raise
            finally:
                conn.close()

    def _inicializar_base_datos(self):
        """Ejecuta el script schema.sql y siembra datos iniciales si es la primera ejecución."""
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            return

        with self.transaction() as conn:
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())

            # Siembra de roles por defecto
            conn.execute(
                "INSERT OR IGNORE INTO roles (id, nombre, descripcion) VALUES (1, 'ADMINISTRADOR', 'Acceso total y configuración');"
            )
            conn.execute(
                "INSERT OR IGNORE INTO roles (id, nombre, descripcion) VALUES (2, 'CAJERO', 'Clientes, préstamos y recaudos');"
            )

            # Siembra de usuario inicial admin/admin123
            cur = conn.execute("SELECT id FROM usuarios WHERE username = 'admin';")
            if not cur.fetchone():
                admin_hash = hash_password("admin123")
                conn.execute(
                    """
                    INSERT INTO usuarios (rol_id, username, password_hash, nombre_completo, activo)
                    VALUES (1, 'admin', ?, 'Administrador Principal', 1);
                    """,
                    (admin_hash,),
                )
                # También sembramos un cajero por defecto (cajero/cajero123)
                cajero_hash = hash_password("cajero123")
                conn.execute(
                    """
                    INSERT INTO usuarios (rol_id, username, password_hash, nombre_completo, activo)
                    VALUES (2, 'cajero', ?, 'Cajero de Turno', 1);
                    """,
                    (cajero_hash,),
                )


db_manager = DatabaseManager()
