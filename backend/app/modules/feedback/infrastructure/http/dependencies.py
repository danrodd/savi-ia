from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database.session import AgentSessionDep
from app.modules.feedback.application.use_cases import (
    ClearMessageFeedbackUseCase,
    ExportFeedbackUseCase,
    GetFeedbackSummaryUseCase,
    ListFeedbackForMessagesUseCase,
    ListFeedbackUseCase,
    SetMessageFeedbackUseCase,
)
from app.modules.feedback.domain.interfaces import FeedbackReportRepository, FeedbackRepository
from app.modules.feedback.infrastructure.persistence.repositories import (
    SqlAlchemyFeedbackReportRepository,
    SqlAlchemyFeedbackRepository,
)


def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_feedback_repository(session: AgentSessionDep) -> FeedbackRepository:
    return SqlAlchemyFeedbackRepository(session)


FeedbackRepositoryDep = Annotated[FeedbackRepository, Depends(get_feedback_repository)]


def get_feedback_report_repository(
    session: AgentSessionDep, settings: SettingsDep
) -> FeedbackReportRepository:
    return SqlAlchemyFeedbackReportRepository(
        session, reporting_timezone=settings.reporting_timezone
    )


FeedbackReportRepositoryDep = Annotated[
    FeedbackReportRepository, Depends(get_feedback_report_repository)
]


def get_set_feedback_use_case(repository: FeedbackRepositoryDep) -> SetMessageFeedbackUseCase:
    return SetMessageFeedbackUseCase(repository)


def get_clear_feedback_use_case(repository: FeedbackRepositoryDep) -> ClearMessageFeedbackUseCase:
    return ClearMessageFeedbackUseCase(repository)


def get_list_feedback_for_messages_use_case(
    repository: FeedbackRepositoryDep,
) -> ListFeedbackForMessagesUseCase:
    return ListFeedbackForMessagesUseCase(repository)


def get_list_feedback_use_case(repository: FeedbackReportRepositoryDep) -> ListFeedbackUseCase:
    return ListFeedbackUseCase(repository)


def get_feedback_summary_use_case(
    repository: FeedbackReportRepositoryDep,
) -> GetFeedbackSummaryUseCase:
    return GetFeedbackSummaryUseCase(repository)


def get_export_feedback_use_case(repository: FeedbackReportRepositoryDep) -> ExportFeedbackUseCase:
    return ExportFeedbackUseCase(repository)


SetMessageFeedbackUseCaseDep = Annotated[
    SetMessageFeedbackUseCase, Depends(get_set_feedback_use_case)
]
ClearMessageFeedbackUseCaseDep = Annotated[
    ClearMessageFeedbackUseCase, Depends(get_clear_feedback_use_case)
]
ListFeedbackForMessagesUseCaseDep = Annotated[
    ListFeedbackForMessagesUseCase, Depends(get_list_feedback_for_messages_use_case)
]
ListFeedbackUseCaseDep = Annotated[ListFeedbackUseCase, Depends(get_list_feedback_use_case)]
GetFeedbackSummaryUseCaseDep = Annotated[
    GetFeedbackSummaryUseCase, Depends(get_feedback_summary_use_case)
]
ExportFeedbackUseCaseDep = Annotated[ExportFeedbackUseCase, Depends(get_export_feedback_use_case)]
