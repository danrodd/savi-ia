"""Importa todos los modelos ORM para que queden registrados en `Base.metadata` (Alembic)."""

from app.db import Base
from app.modules.alerts.infrastructure import AlertModel, AlertRuleModel
from app.modules.audit.infrastructure import AuditLogModel
from app.modules.clients.infrastructure import ClientModel
from app.modules.enrollments.infrastructure import EnrollmentTokenModel
from app.modules.ingest.infrastructure import (
    EvConversationModel,
    EvFreeQueryModel,
    EvSessionModel,
    EvTurnModel,
    IngestBatchModel,
    InstanceDatabaseModel,
)
from app.modules.instances.infrastructure import HeartbeatModel, InstanceModel
from app.modules.staff.infrastructure import StaffSessionModel, StaffUserModel

__all__ = [
    "AlertModel",
    "AlertRuleModel",
    "AuditLogModel",
    "Base",
    "ClientModel",
    "EnrollmentTokenModel",
    "EvConversationModel",
    "EvFreeQueryModel",
    "EvSessionModel",
    "EvTurnModel",
    "HeartbeatModel",
    "IngestBatchModel",
    "InstanceDatabaseModel",
    "InstanceModel",
    "StaffSessionModel",
    "StaffUserModel",
]
