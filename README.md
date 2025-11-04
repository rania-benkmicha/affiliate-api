# Affiliate API

A Python-based simulation of an affiliate platform API. This project allows editors to:

1. Retrieve advertiser information
2. Apply to advertisers
3. Retrieve tracked orders via webhook

Data is stored in **SQLite** (for persistence) and **Redis** (for caching and job queueing). Background jobs are handled by **RQ workers**.

---

## Table of Contents

* [Project Overview](#project-overview)
* [Features](#features)
* [Tech Stack](#tech-stack)
* [Project Structure](#project-structure)
* [Setup & Run](#setup--run)
* [API Endpoints](#api-endpoints)
* [Testing](#testing)
* [Design Notes](#design-notes)

---

## Project Overview

An editor works with affiliate platforms to track user purchases. This project simulates an affiliate platform API with:

* Advertiser retrieval
* Editor applications to advertisers
* Tracking of orders via webhooks

The project emphasizes **simplicity**, **readability**, and **scalability discussions**, while keeping the data in-memory or using lightweight persistence.

---

## Features

* Retrieve all advertisers or only eligible advertisers for a given editor
* Retrieve single advertiser details
* Apply for an advertiser as an editor (with background processing)
* Receive orders through webhook and store in Redis + SQLite
* Cached responses for performance (Redis)
* Unit tests and local integration test script

---

## Tech Stack

* Python 3.11+
* Flask (API framework)
* SQLAlchemy (ORM for SQLite)
* Redis (cache and RQ queue backend)
* RQ (Redis Queue for background jobs)
* Docker & Docker Compose

---

## Project Structure

```
.
├── app/
│   ├── app.py             # Main Flask app and routes
│   ├── models.py          # SQLAlchemy models
│   ├── redis_client.py    # Redis connection
│   ├── tasks.py           # RQ background jobs
│   └── worker.py          # RQ worker
├── tests/
│   └── unit_test.py       # Unit tests with pytest
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── local_test.sh          # Local integration test script
└── README.md
```

---

## Setup & Run

### Prerequisites

* **Python 3.11+**
* **pip** (for Python package installation)
* **Docker** 
* **Docker Compose** 
* Optional: `jq` (for pretty-printing JSON in `test_local.sh`)

---

### 1. Using Docker (Recommended)

1. Build and start containers:

```bash
docker compose up --build -d
```

2. Check running services:

```bash
docker compose ps
```

3. The API will be available at:

```text
http://localhost:5000

```

* Redis: `localhost:6379`
* Worker automatically processes background jobs

4. Stop containers:

```bash
docker compose down -v
```

---

### 2. Running Tests

**Using Docker:**

```bash
docker compose exec web pytest tests/unit_test.py
```

**Local Integration Test:**



```bash
./shell_script/local_test.sh
```
* the script is already preparing the docker containers.
* Performs health check, API requests, application submission, webhook orders, and verifies responses
* Uses Docker containers automatically

---

## API Endpoints

### Health Check

```
GET /
Response: { "status": "ok" }
```

### Get All Advertisers

```
GET /advertisers?editor_id=<id>
```

* Optional `editor_id` filters advertisers eligible for that editor
* Cached in Redis

### Get Single Advertiser

```
GET /advertisers/<advertiser_id>?editor_id=<id>
```

* Returns `403` if editor not eligible

### Apply to Advertiser

```
POST /applications
Body: { "advertiser_id": <id>, "editor_id": <id> }
```

* Returns `202` and enqueues a background job
* Job marks the application as `approved`

### Get Applications

```
GET /applications
```

* Returns list of all applications

### Webhook Orders

```
POST /webhook/orders
Headers: X-Partner-Signature: <hmac>
Body: { "order_id": "...", "advertiser_id": ..., "user_id": ..., "amount": ..., "commission": ... }
```

* Verifies HMAC signature using a secret key
* Saves order in Redis and SQLite

### Get Orders

```
GET /orders
```

* Returns orders saved in Redis

---

## Design Notes

* **SQLite**: Lightweight database for persistence, preloaded with advertisers and editors
* **Redis**:

  * Caching advertisers for fast reads
  * Storing temporary order data
  * Backend for RQ queue jobs
* **Background Jobs**: RQ workers simulate asynchronous application processing
* **Scalability Considerations**:

  * Redis caching reduces DB load
  * Separate worker processes allow horizontal scaling
  * Modular Flask app structure allows easy addition of endpoints

### Database Tables

| Table Name          | Columns / Description                                                                                                     | Relationships                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `Editor`            | `id` (PK), `name`                                                                                                         | Many-to-many with `Advertiser` via `editor_advertiser` |
| `Advertiser`        | `id` (PK), `name`, `category`                                                                                             | Many-to-many with `Editor` via `editor_advertiser`     |
| `editor_advertiser` | `editor_id` (FK → Editor.id), `advertiser_id` (FK → Advertiser.id) — link table for many-to-many                          | Links `Editor` and `Advertiser`                        |
| `Application`       | `id` (PK), `editor_id` (FK → Editor.id), `advertiser_id` (FK → Advertiser.id), `status` (`pending`/`approved`/`rejected`) | Many-to-one: `Editor` & `Advertiser`                   |
| `Order`             | `id` (PK), `order_id`, `editor_id` (FK → Editor.id), `advertiser_id` (FK → Advertiser.id), `amount`, `commission`         | Many-to-one: `Editor` & `Advertiser`                   |
