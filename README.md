# AffectLearn

Adaptive e-learning platform with real-time affect detection and content adaptation.

## Tech Stack

- **Frontend:** Next.js 16.2.1, TypeScript, Tailwind CSS, shadcn/ui
- **Backend:** FastAPI 0.135.x, Python 3.12, SQLAlchemy 2.0, Alembic
- **Database:** PostgreSQL 16, Redis 7
- **Infrastructure:** Docker Compose

## Quick Start

```bash
# Clone and start all services
docker-compose up

# Frontend: http://localhost:3000
# Backend API docs: http://localhost:8000/docs
```

## Project Structure

```
affectlearn/
├── frontend/          # Next.js 16 application
├── backend/           # FastAPI + LangGraph application
├── docker-compose.yml # Service orchestration
└── .env.example       # Environment template
```

## Development

```bash
# Start all services with hot reload
docker-compose up

# Run backend migrations
docker-compose exec api alembic upgrade head

# Run backend tests
docker-compose exec api pytest
```
