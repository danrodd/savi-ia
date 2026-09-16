"""Turnos que viven fuera de la conexión HTTP.

Hasta acá el turno **era** el stream: si el cliente se iba, el generador se
cancelaba y la generación moría con él. Medido contra el backend real, cortar
la conexión a los 9,7 s dejaba 70 caracteres guardados como `interrupted` que
nunca crecían.

Ahora el turno es una **tarea** y el stream se suscribe a ella:

    POST /chat ──▶ registro ──▶ tarea (acumula eventos y persiste al terminar)
                                   ▲
                       SSE suscripto│  si el cliente se va, la tarea no se entera

Consecuencias que hay que tener presentes:

- **El cupo global se toma y se suelta acá**, no en la conexión. Atado a la
  conexión se filtraría en cuanto alguien cierre la pestaña.
- **El registro es el candado por conversación**: si hay turno para esa
  conversación, es que ya hay una respuesta en curso.
- **Detener necesita un endpoint**: abortar el fetch ya no detiene nada.

En memoria y por proceso, como el índice de documentos. En un despliegue
multiproceso haría falta un bus compartido; ver
`docs/chat-turnos-en-segundo-plano.md`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

from app.infrastructure.config import Settings
from app.modules.chat.domain.entities import ChatEvent
from app.shared.exceptions import ConversationBusyError, RateLimitExceededError

log = logging.getLogger(__name__)

# Cuánto se conserva un turno YA terminado. Es la ventana para que quien
# vuelve enseguida vea el final en vivo; pasado eso el mensaje ya está en la
# base y el buffer no aporta nada.
_RETENTION_SECONDS = 300.0
_BUSY_RETRY_AFTER_S = 5


@dataclass
class RunningTurn:
    """Un turno en curso (o recién terminado) y todo lo que emitió."""

    conversation_id: UUID
    events: list[ChatEvent] = field(default_factory=list[ChatEvent])
    done: bool = False
    finished_at: float | None = None
    task: asyncio.Task[None] | None = None
    # Se despierta con cada evento nuevo y al terminar. Los suscriptores lo
    # esperan en lugar de consultar en bucle.
    _pulse: asyncio.Event = field(default_factory=asyncio.Event)

    def publish(self, event: ChatEvent) -> None:
        self.events.append(event)
        self._wake()

    def finish(self) -> None:
        self.done = True
        self.finished_at = time.monotonic()
        self._wake()

    def _wake(self) -> None:
        self._pulse.set()
        self._pulse.clear()

    async def subscribe(self) -> AsyncIterator[ChatEvent]:
        """Reenvía lo ya emitido y después sigue en vivo.

        Desde el evento 0 siempre: el cliente reconstruye el mensaje entero
        con la lista completa, que es idempotente. Sincronizar posiciones
        sería más frágil y el buffer de un turno son pocos KB.
        """
        entregados = 0
        while True:
            while entregados < len(self.events):
                yield self.events[entregados]
                entregados += 1
            if self.done:
                return
            # `wait()` antes de volver a mirar: si llegaron eventos mientras
            # se entregaban los anteriores, el bucle de arriba los toma en la
            # próxima vuelta sin dormirse.
            await self._pulse.wait()

    def cancel(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()


class TurnRegistry:
    """Sin candado: reservar y liberar no tienen ni un `await` en el medio.

    En asyncio un bloque sin `await` no se interrumpe, así que el contador ya
    es atómico. Y un `asyncio.Lock` acá sería peor que inútil: liberar el cupo
    pasa por el `finally` de una tarea que puede venir **cancelada**, y ahí
    cualquier `await` vuelve a lanzar `CancelledError` antes de decrementar.
    Resultado: "Detener" filtraba un cupo por uso y al tercero nadie podía
    chatear.
    """

    def __init__(self) -> None:
        self._turns: dict[UUID, RunningTurn] = {}
        self._active = 0

    async def start(
        self,
        settings: Settings,
        conversation_id: UUID,
        producer: Callable[[RunningTurn], Awaitable[None]],
    ) -> RunningTurn:
        """Crea la tarea del turno o rechaza si no hay lugar.

        `producer` recibe el turno y va publicando eventos en él. Corre en una
        tarea propia: el llamador puede irse sin afectarla.
        """
        limite = max(1, settings.max_concurrent_chat_turns)
        self._purgar()
        existente = self._turns.get(conversation_id)
        if existente is not None and not existente.done:
            raise ConversationBusyError(str(conversation_id))
        # El cupo por conversación se revisa ANTES del global: si no, insistir
        # desde una pestaña consumiría cupo de todos.
        if self._active >= limite:
            raise RateLimitExceededError(
                retry_after_seconds=_BUSY_RETRY_AFTER_S,
                detail="SAVI está atendiendo otras consultas. Probá en unos segundos.",
            )
        turno = RunningTurn(conversation_id=conversation_id)
        self._turns[conversation_id] = turno
        self._active += 1

        tarea = asyncio.create_task(
            self._run(settings, turno, producer), name=f"chat-turn-{conversation_id}"
        )
        turno.task = tarea
        # El cierre va en un callback y NO en el `finally` de `_run`: si alguien
        # aprieta "Detener" antes de que la tarea llegue a correr, la corrutina
        # no se ejecuta nunca y ese `finally` tampoco. El turno quedaba marcado
        # como en curso para siempre y el cupo, tomado. El callback corre igual.
        tarea.add_done_callback(lambda _: self._cerrar(turno))
        return turno

    async def _run(
        self,
        settings: Settings,
        turno: RunningTurn,
        producer: Callable[[RunningTurn], Awaitable[None]],
    ) -> None:
        try:
            # El reloj de pared envuelve la TAREA, no la conexión: un turno
            # que se cuelga ya no depende de que alguien lo esté mirando.
            async with asyncio.timeout(settings.chat_turn_timeout_seconds):
                await producer(turno)
        except TimeoutError:
            log.warning("chat_turn_timeout conversation_id=%s", turno.conversation_id)
        except asyncio.CancelledError:
            # Detención explícita del usuario. Lo generado hasta acá ya se
            # persiste por el mismo camino que la cancelación del cliente.
            log.info("chat_turn_cancelled conversation_id=%s", turno.conversation_id)
        except Exception:
            log.exception("chat_turn_failed conversation_id=%s", turno.conversation_id)

    def _cerrar(self, turno: RunningTurn) -> None:
        """Cierra el turno y devuelve el cupo. Exactamente una vez por tarea."""
        if turno.done:
            return
        turno.finish()
        self._active = max(0, self._active - 1)

    def get(self, conversation_id: UUID) -> RunningTurn | None:
        return self._turns.get(conversation_id)

    def running(self, conversation_id: UUID) -> bool:
        turno = self._turns.get(conversation_id)
        return turno is not None and not turno.done

    def cancel(self, conversation_id: UUID) -> bool:
        """`True` si había algo que cortar."""
        turno = self._turns.get(conversation_id)
        if turno is None or turno.done:
            return False
        turno.cancel()
        return True

    def active_count(self) -> int:
        return self._active

    def _purgar(self) -> None:
        ahora = time.monotonic()
        for cid, turno in list(self._turns.items()):
            if (
                turno.done
                and turno.finished_at is not None
                and ahora - turno.finished_at > _RETENTION_SECONDS
            ):
                del self._turns[cid]

    def reset_for_tests(self) -> None:
        for turno in self._turns.values():
            turno.cancel()
        self._turns.clear()
        self._active = 0


_registry = TurnRegistry()


def get_turn_registry() -> TurnRegistry:
    return _registry
