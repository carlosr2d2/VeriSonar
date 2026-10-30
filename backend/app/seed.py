from __future__ import annotations

from app.config import settings
from app.models import UserRole


def seed_catalog() -> list[dict[str, str]]:
    """2 administradores y 8 analistas de laboratorio (idempotente al arrancar)."""
    return [
        {
            "email": settings.bootstrap_admin_email,
            "password": settings.bootstrap_admin_password,
            "full_name": settings.bootstrap_admin_name,
            "role": UserRole.ADMIN.value,
        },
        {
            "email": "carlos.herrera@verisonar.local",
            "password": "VeriSonar.Admin2",
            "full_name": "Carlos Herrera",
            "role": UserRole.ADMIN.value,
        },
        {
            "email": "ana.reyes@verisonar.local",
            "password": "Analista.Reyes1",
            "full_name": "Ana Reyes",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "luis.gomez@verisonar.local",
            "password": "Analista.Gomez1",
            "full_name": "Luis Gómez",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "maria.soto@verisonar.local",
            "password": "Analista.Soto1",
            "full_name": "María Soto",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "diego.perez@verisonar.local",
            "password": "Analista.Perez1",
            "full_name": "Diego Pérez",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "camila.rojas@verisonar.local",
            "password": "Analista.Rojas1",
            "full_name": "Camila Rojas",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "jorge.nunez@verisonar.local",
            "password": "Analista.Nunez1",
            "full_name": "Jorge Núñez",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "valentina.diaz@verisonar.local",
            "password": "Analista.Diaz1",
            "full_name": "Valentina Díaz",
            "role": UserRole.ANALYST.value,
        },
        {
            "email": "andres.castro@verisonar.local",
            "password": "Analista.Castro1",
            "full_name": "Andrés Castro",
            "role": UserRole.ANALYST.value,
        },
    ]
