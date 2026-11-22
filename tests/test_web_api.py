"""
Pruebas automatizadas para los endpoints del Servidor Web FastAPI.
Valida autenticación, cálculo por API y protección de rutas.
"""

import unittest
from decimal import Decimal
from fastapi.testclient import TestClient
from src.web.app import app


class TestWebAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_01_redireccion_login_sin_sesion(self):
        """Verifica que un usuario no autenticado sea redirigido a /login."""
        response = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_02_api_simular_prestamo_frances(self):
        """Verifica que el endpoint /api/simular calcule correctamente una amortización."""
        payload = {
            "monto": 10000000.0,
            "tasa_interes": 18.0,
            "tipo_tasa": "ANUAL",
            "num_cuotas": 12,
            "periodicidad": "MENSUAL",
            "sistema": "FRANCES",
            "seguro_comision": 0.0,
            "tipo_seguro": "FIJO",
            "fecha_desembolso": "2026-01-15"
        }
        response = self.client.post("/api/simular", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(len(data["data"]["cuotas"]), 12)
        self.assertEqual(data["data"]["total_capital"], 10000000.0)

    def test_03_login_invalido_devuelve_error(self):
        """Verifica que credenciales erróneas impidan el acceso."""
        response = self.client.post(
            "/login",
            data={"username": "invalido", "password": "password_incorrecta"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Usuario o contraseña incorrectos", response.text)


if __name__ == "__main__":
    unittest.main()
