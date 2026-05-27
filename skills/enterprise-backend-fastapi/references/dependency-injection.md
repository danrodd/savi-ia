# Dependency Injection

FastAPI funciona bien con DI explícita vía `Depends`. Usá `Annotated` para tipos reutilizables.

## Session de base de datos

```python
# app/infrastructure/database/session.py
from typing import Annotated, AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.infrastructure.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

AsyncSessionDep = Annotated[AsyncSession, Depends(get_session)]
```

## Repositorio inyectado

```python
# app/modules/users/infrastructure/http/dependencies.py
from typing import Annotated
from fastapi import Depends
from app.infrastructure.database.session import AsyncSessionDep
from app.modules.users.domain.interfaces import UserRepository
from app.modules.users.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from app.modules.users.application.use_cases import CreateUserUseCase

def get_user_repository(session: AsyncSessionDep) -> UserRepository:
    return SqlAlchemyUserRepository(session)

UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]

def get_create_user_use_case(repo: UserRepositoryDep) -> CreateUserUseCase:
    return CreateUserUseCase(repository=repo)

CreateUserUseCaseDep = Annotated[CreateUserUseCase, Depends(get_create_user_use_case)]
```

## Regla

- Las dependencies SIEMPRE devuelven el **tipo de interface** (`UserRepository`), nunca la implementación concreta.
- Esto te permite swap de implementación (ej. `InMemoryUserRepository` para tests) sin tocar use cases ni controllers.
