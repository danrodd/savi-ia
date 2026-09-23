"""Políticas de la Fase 4: todo con IA o todo con `pypdf`.

La Fase 5 agrega una política por umbrales, calibrada con las métricas que
se guardan en `company_document_pages`. El resto de la lectura no cambia.
"""

from app.modules.company_knowledge.domain.entities.page_reading import PageMetrics
from app.modules.company_knowledge.domain.interfaces.pdf_reading import PageRoutingPolicy
from app.modules.company_knowledge.domain.value_objects.reading import PageRoute


class AllAiPolicy(PageRoutingPolicy):
    def decide(self, page: PageMetrics) -> PageRoute:
        return PageRoute.AI


class TextOnlyPolicy(PageRoutingPolicy):
    def decide(self, page: PageMetrics) -> PageRoute:
        return PageRoute.TEXT
