# Capas en Detalle

## Domain

### entities/

Entidades de dominio puras. Sin SQLAlchemy / FastAPI / Pydantic.

```python
from uuid import UUID
from dataclasses import dataclass

@dataclass
class User:
    id: UUID
    email: str
    is_active: bool
```

### interfaces/

Contratos abstractos. La capa domain sólo conoce interfaces, nunca implementaciones.

```python
from abc import ABC, abstractmethod
from uuid import UUID
from app.modules.users.domain.entities import User

class UserRepository(ABC):
    @abstractmethod
    async def find_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def save(self, user: User) -> None: ...
```

### value_objects/

Objetos inmutables que se autovalidan.

```python
class Email:
    def __init__(self, value: str):
        if "@" not in value:
            raise ValueError("Invalid email")
        self.value = value
```

### exceptions/

Errores del dominio (luego mapeados a HTTP en `shared/exceptions/`).

```python
class UserAlreadyExistsError(Exception): ...
class InvalidCredentialsError(Exception): ...
```

---

## Application

### use_cases/

Una clase = una acción de negocio. Recibe DTO, devuelve DTO.

```python
from uuid import uuid4
from app.modules.users.application.dtos import CreateUserDTO, UserDTO
from app.modules.users.domain.interfaces import UserRepository
from app.modules.users.domain.entities import User
from app.modules.users.domain.exceptions import UserAlreadyExistsError

class CreateUserUseCase:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def execute(self, dto: CreateUserDTO) -> UserDTO:
        if await self.repository.find_by_email(dto.email):
            raise UserAlreadyExistsError()

        user = User(id=uuid4(), email=dto.email, is_active=True)
        await self.repository.save(user)
        return UserDTO.from_entity(user)
```

### requests/ (Pydantic)

```python
from pydantic import BaseModel, EmailStr, Field

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
```

### dtos/ (`@dataclass`)

```python
from dataclasses import dataclass

@dataclass
class CreateUserDTO:
    email: str
    password: str
```

DTOs son transporte interno: **no** dependen de HTTP ni de Pydantic.

### responses/ (Pydantic)

```python
from uuid import UUID
from pydantic import BaseModel

class UserResponse(BaseModel):
    id: UUID
    email: str
```

### validators/

Validaciones complejas reutilizables.

```python
class PasswordValidator:
    @staticmethod
    def validate(password: str) -> None:
        # reglas de complejidad
        ...
```

### services/

Lógica reutilizable entre use cases. **Nunca convertirlos en "god services"** — si crece, dividir.

---

## Infrastructure

### persistence/repositories/

Implementación real del contrato definido en `domain/interfaces/`.

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.users.domain.interfaces import UserRepository
from app.modules.users.domain.entities import User

class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_email(self, email: str) -> User | None:
        # query + map ORM → Entity
        ...
```

### persistence/models/

ORM SQLAlchemy. **No son entidades de dominio.**

```python
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy import String
from uuid import UUID

class Base(DeclarativeBase): ...

class UserModel(Base):
    __tablename__ = "users"
    id = mapped_column(primary_key=True)
    email = mapped_column(String, unique=True)
```

### persistence/mappers/

Transforman `ORM ↔ Entity`.

### http/controllers/

Controladores FastAPI extremadamente delgados.

```python
from fastapi import APIRouter
from app.modules.users.application.requests import CreateUserRequest
from app.modules.users.application.responses import UserResponse
from app.modules.users.application.dtos import CreateUserDTO
from app.modules.users.infrastructure.http.dependencies import CreateUserUseCaseDep

router = APIRouter(prefix="/users")

@router.post("/", response_model=UserResponse)
async def create_user(
    request: CreateUserRequest,
    use_case: CreateUserUseCaseDep,
):
    dto = CreateUserDTO(email=request.email, password=request.password)
    result = await use_case.execute(dto)
    return UserResponse.model_validate(result)
```

**Controllers NO contienen lógica.** Sólo: validan request → arman DTO → llaman use case → devuelven response.
