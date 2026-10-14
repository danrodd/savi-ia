"""Importa todos los modelos ORM para que queden registrados en `Base.metadata` (Alembic)."""

from app.db import Base
from app.modules.clients.infrastructure import ClientModel
from app.modules.enrollments.infrastructure import EnrollmentTokenModel
from app.modules.instances.infrastructure import InstanceModel

__all__ = ["Base", "ClientModel", "EnrollmentTokenModel", "InstanceModel"]
