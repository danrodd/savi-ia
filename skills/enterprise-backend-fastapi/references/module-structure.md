# Estructura de Módulos

## Estructura global

```
app/
├── main.py
├── shared/
│   ├── middleware/          # correlation-id, logging, auth, rate-limit, metrics
│   └── exceptions/          # mapeo global excepciones → HTTP
├── modules/
│   ├── users/
│   ├── auth/
│   └── billing/
├── infrastructure/
│   ├── database/            # session, engine, base
│   ├── security/
│   ├── cache/
│   ├── logging/
│   ├── messaging/
│   ├── external/
│   └── config/              # settings.py, environments.py, constants.py
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

## Anatomía de un módulo (ej. `modules/users/`)

```
users/
├── domain/
│   ├── entities/            # User, Profile (sin SQLAlchemy/FastAPI/Pydantic)
│   ├── interfaces/          # UserRepository (ABC abstract)
│   ├── value_objects/       # Email, Password (inmutables, autovalidados)
│   └── exceptions/          # UserAlreadyExistsError, InvalidCredentialsError
│
├── application/
│   ├── dtos/                # @dataclass — transporte interno
│   ├── requests/            # Pydantic — input HTTP
│   ├── responses/           # Pydantic — output HTTP
│   ├── use_cases/           # CreateUserUseCase, AuthenticateUserUseCase
│   ├── services/            # lógica reutilizable entre use cases (NO god services)
│   ├── validators/          # PasswordValidator (validaciones complejas)
│   └── mappers/             # Entity ↔ DTO
│
├── infrastructure/
│   ├── persistence/
│   │   ├── models/          # SQLAlchemy ORM (UserModel)
│   │   ├── repositories/    # SqlAlchemyUserRepository (implementa interface)
│   │   └── mappers/         # ORM ↔ Entity
│   │
│   ├── http/
│   │   ├── controllers/     # endpoints FastAPI extremadamente delgados
│   │   ├── dependencies/    # DI específica del módulo
│   │   └── routes/          # router del módulo
│   │
│   └── integrations/        # clientes a APIs externas específicos del módulo
│
└── __init__.py
```

## Separación estricta de tipos

| Tipo | Función | Tecnología |
|------|---------|------------|
| **Request** | Entrada HTTP | Pydantic v2 |
| **DTO** | Transporte interno entre capas | `@dataclass` |
| **Response** | Salida HTTP | Pydantic v2 |
| **Entity** | Modelo de dominio | Clase Python pura |
| **ORM Model** | Persistencia | SQLAlchemy |

**Nunca** retornar un ORM Model directamente desde un controller. **Nunca** que un use case reciba o devuelva ORM Models.

## Flujo completo de una petición

```
HTTP Request
   ↓
FastAPI Controller (infrastructure/http/controllers/)
   ↓
Request (Pydantic, application/requests/)
   ↓
DTO (@dataclass, application/dtos/)
   ↓
Use Case (application/use_cases/)
   ↓
Repository Interface (domain/interfaces/)
   ↓
Repository Implementation (infrastructure/persistence/repositories/)
   ↓
ORM Model → Mapper → Entity
   ↓
PostgreSQL
```
