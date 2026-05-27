# Principios Arquitectónicos

## Filosofía

Combinación pragmática de:

- Clean Architecture
- Hexagonal Architecture (Ports & Adapters)
- Feature-based modularity
- DDD táctico ligero
- Tipado fuerte + async-first + bajo acoplamiento

**Objetivo**: lógica de negocio independiente del framework, infraestructura desacoplada, testing simple, mantenibilidad a largo plazo — sin sobreingeniería empresarial.

## Dependencias hacia adentro

```
Infrastructure → Application → Domain
```

Las capas externas dependen de las internas. **NUNCA al revés.**

## El dominio no conoce nada externo

La capa `domain`:

- NO importa FastAPI.
- NO importa SQLAlchemy.
- NO conoce HTTP, PostgreSQL, Redis.

Contiene únicamente: entities, contratos (interfaces), value objects, exceptions, reglas de negocio puras.

## Infrastructure contiene TODO lo externo

Todo acceso a base de datos, Redis, APIs externas, archivos, JWT, WebSockets, email, cloud services vive **exclusivamente** en `infrastructure/`.

## Application contiene la lógica

La capa `application`:

- Orquesta casos de uso.
- Valida reglas de negocio.
- Coordina repositorios (vía interfaces).
- Transforma DTOs.
- Controla transacciones.
- Ejecuta workflows.

## Infrastructure es reemplazable

Idealmente podrías cambiar PostgreSQL → MySQL, Redis → Memcached, FastAPI → Litestar, sin tocar `domain/`.

## Resumen final

```
Domain         → puro
Application    → lógica
Infrastructure → externo
HTTP           → extremadamente delgado
```
