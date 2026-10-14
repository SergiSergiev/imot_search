# Brickwise — Imot.bg Agency Property Assistant

Локално single-user приложение за импорт, структуриране, търсене и обяснимо оценяване на обяви на оторизирана агенция в imot.bg.

## Какво включва MVP

- Next.js responsive интерфейс с търсене, карти, детайли, любими, бележки и сравнение.
- FastAPI backend и SQLAlchemy data model за всички основни обекти.
- PostgreSQL/pgvector-ready конфигурация и SQLite fallback за най-бърз локален старт.
- Детерминистичен match score 0–100 с hard criteria, soft criteria и подробна разбивка.
- Разбиране на български заявки чрез OpenAI Structured Outputs; rule-based fallback без API ключ.
- Ръчен JSON import и консервативен authorized URL importer с пауза и спиране при HTTP 403/429.
- Deduplication, snapshots и история на промени в цена, описание и основни полета.
- Демонстрационни обяви, които се създават автоматично при празна база.

> Използвайте автоматичния importer само за профили, за които имате изрично право. Не заобикаляйте CAPTCHA, login или технически ограничения. За production употреба поискайте писмено разрешение от imot.bg.

## Структура

```text
backend/
  app/
    main.py                 REST endpoints
    models.py               SQLAlchemy data model
    schemas.py              API contracts
    services/ai.py          OpenAI + local query parser
    services/scoring.py     explainable score v1
    services/importer.py    manual/authorized import
    services/normalizer.py  normalization and features
  tests/
frontend/
  app/                      Next.js App Router screens
  lib/api.ts                typed API client
docker-compose.yml          PostgreSQL + pgvector
```

## Най-бърз локален старт (SQLite)

Изисквания: Python 3.11+, Node.js 20+.

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

Добавете `OPENAI_API_KEY` в `.env`, ако искате LLM parsing. Без ключ приложението работи с локалния parser.

Терминал 1:

```bash
source .venv/bin/activate
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Терминал 2:

```bash
cd frontend
npm run dev
```

Отворете <http://localhost:3000>. API документацията е на <http://localhost:8000/docs>.

## PostgreSQL режим

```bash
docker compose up -d postgres
```

В `.env` задайте:

```dotenv
DATABASE_URL=postgresql+psycopg://imot:imot@localhost:5432/imot
```

След това стартирайте backend и frontend по същия начин. За MVP таблиците се създават автоматично; следващата production стъпка е Alembic migrations.

## Manual import

1. Добавете агенцията от екрана „Агенции“.
2. Изпратете JSON към `POST /api/agencies/{id}/manual-import`.

Пример:

```json
{
  "listings": [{
    "source_listing_id": "agency-12345",
    "source_url": "https://www.imot.bg/example",
    "title": "Тристаен апартамент в Лозенец",
    "description": "Обзаведен, с асансьор, близо до метро.",
    "property_type": "апартамент",
    "room_count": 3,
    "price_eur": 240000,
    "area_sqm": 96,
    "district": "Лозенец",
    "floor_number": 3,
    "total_floors": 6,
    "features": {"elevator": true, "near_metro": true},
    "images": []
  }]
}
```

Повторното изпращане на същия `source_listing_id` обновява обявата и записва променените полета.

## Проверки

```bash
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests
cd frontend
npm run typecheck
npm run build
```

## Ограничения на MVP

- URL importer-ът използва консервативни HTML heuristics. При реален agency URL селекторите трябва да се валидират спрямо разрешения формат/API.
- Background jobs са FastAPI background tasks и не оцеляват при рестарт. Production версията следва да използва Redis + Dramatiq/Celery.
- „Подценен“ означава спрямо медианата на наличните обяви, не независима пазарна оценка.
- Няма multi-user auth, роли, Alembic migrations, geocoding или автоматична метро дистанция.
- Снимките остават външни URL адреси; не се копират локално.

## Следващи production стъпки

1. Официален imot.bg API/export договор и schema-specific adapter.
2. Alembic, Redis worker, job locking, retries и observability.
3. Геокодиране и PostGIS за реална дистанция до метро.
4. Embeddings в pgvector за подобни обяви и semantic recall.
5. Пазарен benchmark от разрешен dataset и калибриране на score чрез потребителска обратна връзка.
6. Authentication, encryption на чувствителни полета, retention policy и audit log.
7. Parser fixtures, contract tests и scraper monitoring.

OpenAI интеграцията използва Responses API, Structured Outputs и `store=False`; телефоните и другите контактни данни не се включват в заявките към модела.
