from app.modules.cloud_link.domain.entities import CloudLinkState
from app.modules.cloud_link.domain.interfaces import CloudLinkRepository


class UnlinkInstanceUseCase:
    """Desvincula **localmente**: borra secreto e `instance_id` y detiene la
    sincronización. Conserva `pseudonym_key` e `install_id` para que los mismos
    usuarios mantengan su seudónimo si se vuelve a vincular. La instancia sigue
    existiendo en Cloud hasta que la revoquen desde la consola."""

    def __init__(self, repository: CloudLinkRepository) -> None:
        self._repository = repository

    async def execute(self) -> CloudLinkState:
        state = await self._repository.update(lambda s: s.clear_link())
        await self._repository.delete_watermarks()
        return state
