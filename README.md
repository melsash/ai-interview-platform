# AI Interview Platform

> Production-style microservices backend for conducting technical interviews with AI-powered code evaluation.

[![CI](https://github.com/yourusername/ai-interview-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/ai-interview-platform/actions)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql)
![Redis](https://img.shields.io/badge/Redis-7-red?logo=redis)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.12-orange?logo=rabbitmq)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)

---

## Overview

A backend platform where interviewers create coding sessions, candidates submit solutions, and an AI worker evaluates code asynchronously — delivering real-time feedback via WebSocket.

Built to demonstrate production-grade backend engineering: clean architecture, async processing, message queues, caching, microservices, and observability.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                             │
│              Web App / Mobile / API Consumers               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│                      API Gateway                            │
│                  Rate limiting · Routing                    │
└──────┬───────────────────┬───────────────────┬─────────────┘
       │                   │                   │
┌──────▼──────┐   ┌────────▼───────┐   ┌──────▼──────────┐
│   Auth      │   │  Assessment    │   │  Notification   │
│  Service    │   │   Service      │   │    Service      │
│             │   │                │   │                 │
│ JWT · OAuth │   │ Sessions       │   │ Email · Push    │
│ FastAPI     │   │ Questions      │   │ FastAPI         │
│             │   │ WebSocket      │   │                 │
└──────┬──────┘   └───────┬────────┘   └─────────────────┘
       │                  │ publish
┌──────▼──────┐   ┌───────▼────────┐
│  Auth DB    │   │  RabbitMQ      │
│ PostgreSQL  │   │ assessment     │
└─────────────┘   │ .evaluate      │
                  │ .feedback      │
┌─────────────┐   └───────┬────────┘
│  Redis      │◄──────────┤ consume
│             │   ┌───────▼────────┐
│ Cache       │   │   AI Worker    │
│ Sessions    │   │                │
│ Pub/Sub ────┼──►│ Celery         │
│ Rate limit  │   │ OpenAI GPT-4   │
└─────────────┘   │ Code evaluation│
                  └───────┬────────┘
                  ┌───────▼────────┐
                  │  AI Results DB │
                  │  PostgreSQL    │
                  └────────────────┘
```

**Request flow for code submission:**
```
POST /sessions/{id}/questions/{qid}/submit
  → 202 Accepted (immediate)
  → RabbitMQ: assessment.evaluate queue
  → AI Worker picks up task (Celery)
  → OpenAI GPT-4o-mini evaluates code (~3-5s)
  → Result saved to PostgreSQL
  → Redis Pub/Sub notification
  → WebSocket push to candidate
```

---

## Services

| Service | Port | Tech | Responsibility |
|---------|------|------|----------------|
| **auth** | 8001 | FastAPI, PostgreSQL, Redis | JWT auth, user management |
| **assessment** | 8002 | FastAPI, PostgreSQL, RabbitMQ, WebSocket | Sessions, questions, submissions |
| **ai_worker** | — | Celery, OpenAI, Redis | Async code evaluation |
| **notification** | 8003 | FastAPI, RabbitMQ | Email & push notifications |

**Infrastructure:**

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL × 3 | 5433/5434/5435 | Isolated DB per service |
| Redis | 6379 | Cache, sessions, Pub/Sub, Celery backend |
| RabbitMQ | 5672 / 15672 | Message broker, task queue |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3000 | Dashboards |

---

## Tech Stack & Design Decisions

### Why microservices?
Each service has a **single responsibility** and can be scaled independently. The AI Worker is the bottleneck (LLM calls take 3-30s) — it can be scaled horizontally without touching Auth or Assessment.

### Why RabbitMQ for code evaluation?
HTTP request for code submission returns `202 Accepted` **immediately** — the user doesn't wait 30 seconds for AI evaluation. The task is queued in RabbitMQ, processed asynchronously, result delivered via WebSocket. This is the standard pattern for any long-running operation.

### Why separate PostgreSQL per service?
**Database-per-service** pattern: services are truly decoupled. Auth DB schema changes don't affect Assessment. In production each DB can run on different hardware, have different backup policies, different read replicas.

### Why Redis for multiple things?
- **Caching**: user sessions, rate limiting counters
- **Celery backend**: task result storage
- **Pub/Sub**: AI Worker publishes results → Assessment Service pushes via WebSocket
Using one Redis with different DB indexes (0-4) keeps infrastructure simple while maintaining logical separation.

### Clean Architecture (per service)
```
routes → services → repositories → models
```
- **Routes**: HTTP only, no business logic
- **Services**: business logic, no DB queries
- **Repositories**: DB queries only, no business logic
- **Models**: SQLAlchemy ORM definitions

This makes each layer independently testable and replaceable.

---

## Getting Started

### Prerequisites
- Docker Desktop
- Make
- Git

### Quick Start

```bash
# Clone
git clone https://github.com/yourusername/ai-interview-platform.git
cd ai-interview-platform

# Configure environment
cp .env.example .env
# Edit .env — add OPENAI_API_KEY if you have one (optional)

# Start everything
make up

# Check all services are healthy
make ps
```

### Available URLs

| URL | Description |
|-----|-------------|
| http://localhost:8001/docs | Auth Service API |
| http://localhost:8002/docs | Assessment Service API |
| http://localhost:8003/docs | Notification Service API |
| http://localhost:15672 | RabbitMQ Management (rmq_user/rmq_pass) |
| http://localhost:3000 | Grafana (admin/grafana_pass) |
| http://localhost:9090 | Prometheus |

### Make Commands

```bash
make up           # Start all services
make up-infra     # Start only infrastructure (DB, Redis, RabbitMQ)
make down         # Stop all services
make logs s=auth  # Tail logs for specific service
make ps           # Show container status
make clean        # Remove containers and volumes
```

---

## API Usage

### 1. Register & Login

```bash
# Register
curl -X POST http://localhost:8001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "interviewer@example.com", "password": "StrongPass1", "full_name": "John Doe", "role": "interviewer"}'

# Login → get tokens
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "interviewer@example.com", "password": "StrongPass1"}'
```

### 2. Create a Question

```bash
curl -X POST http://localhost:8002/api/v1/questions \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Two Sum",
    "description": "Given an array of integers nums and an integer target, return indices of the two numbers that add up to target.",
    "difficulty": "easy",
    "question_type": "coding",
    "topic": "arrays",
    "starter_code": "def two_sum(nums, target):\n    pass",
    "time_limit_minutes": 30
  }'
```

### 3. Create Session & Submit Code

```bash
# Create session
curl -X POST http://localhost:8002/api/v1/sessions \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "Backend Interview", "candidate_id": "<uuid>", "question_ids": ["<question_uuid>"]}'

# Start session
curl -X POST http://localhost:8002/api/v1/sessions/<session_id>/start \
  -H "Authorization: Bearer <token>"

# Submit code (returns 202 immediately)
curl -X POST http://localhost:8002/api/v1/sessions/<id>/questions/<sq_id>/submit \
  -H "Authorization: Bearer <token>" \
  -d '{"code": "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target-n], i]\n        seen[n] = i", "language": "python"}'
```

### 4. Real-time Results via WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8002/ws/sessions/<session_id>?token=<access_token>');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'submission.completed') {
    console.log('Score:', msg.data.score);
    console.log('Feedback:', msg.data.feedback);
    console.log('Strengths:', msg.data.strengths);
  }
};
```

---

## Project Structure

```
ai-interview-platform/
├── docker-compose.yml          # Full infrastructure
├── Makefile                    # Developer commands
├── .env.example                # Environment template
├── monitoring/
│   └── prometheus.yml          # Metrics config
├── services/
│   ├── auth/                   # Authentication microservice
│   │   ├── app/
│   │   │   ├── api/routes/     # HTTP endpoints
│   │   │   ├── core/           # Config, DB, Security
│   │   │   ├── models/         # SQLAlchemy models
│   │   │   ├── schemas/        # Pydantic schemas
│   │   │   ├── services/       # Business logic
│   │   │   └── repositories/   # DB queries
│   │   ├── tests/
│   │   └── Dockerfile
│   ├── assessment/             # Interview sessions microservice
│   │   ├── app/
│   │   │   ├── core/           # Config, DB, RabbitMQ, WebSocket
│   │   │   ├── models/         # Sessions, Questions, Submissions
│   │   │   ├── services/       # Session & submission logic
│   │   │   └── repositories/
│   │   └── Dockerfile
│   ├── ai_worker/              # Async evaluation worker
│   │   ├── app/
│   │   │   ├── tasks.py        # Celery tasks
│   │   │   ├── worker.py       # Celery app config
│   │   │   └── services/       # AI evaluator, result repo
│   │   └── Dockerfile
│   └── notification/           # Notification microservice
├── .github/
│   └── workflows/ci.yml        # GitHub Actions CI
└── docs/
    └── architecture.png
```

---

## Key Engineering Concepts Demonstrated

| Concept | Implementation |
|---------|---------------|
| **Async processing** | Code evaluation via Celery + RabbitMQ |
| **Real-time communication** | WebSocket with connection manager |
| **Message queues** | RabbitMQ with durable queues, `acks_late=True` |
| **Caching** | Redis for sessions and rate limiting |
| **Clean Architecture** | 4-layer separation per service |
| **Database per service** | 3 isolated PostgreSQL instances |
| **JWT Auth** | Access + refresh token rotation |
| **Health checks** | Docker healthchecks on all services |
| **Observability** | Prometheus metrics + Grafana dashboards |
| **CI/CD** | GitHub Actions with test + lint + build |
| **At-least-once delivery** | `acks_late=True` on Celery tasks |

---

## Environment Variables

See `.env.example` for full list. Key variables:

```env
SECRET_KEY=          # JWT signing key (min 32 chars)
OPENAI_API_KEY=      # Optional — mock evaluator used if not set
RABBITMQ_USER=       # RabbitMQ credentials
REDIS_PASSWORD=      # Redis password
```

---

## Running Tests

```bash
make test            # All services
make test s=auth     # Auth service only
```

---

## Roadmap

- [ ] Frontend (Next.js)
- [ ] Code execution sandbox (Docker-in-Docker)
- [ ] Video interview support (WebRTC)
- [ ] Kubernetes deployment manifests
- [ ] Rate limiting per user (Redis)
- [ ] Email notifications on session completion

---

## Author

Built as a portfolio project demonstrating production-grade backend engineering with Python microservices.