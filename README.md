

# ⚖️ VerdictBridge

**AI-Powered Court Judgment Intelligence for Government Action**

Transforms Karnataka High Court judgment PDFs into verified, department-routed
action plans with full tamper-evident audit trails — in minutes, not days.

---

## Architecture

```
PDF Upload
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  INGESTION LAYER                                            │
│  PyMuPDF → native text extraction                          │
│  Tesseract OCR → fallback for scanned documents            │
│  (eng+kan — English + Kannada support)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PII MASKING (Presidio)                                     │
│  Party names, phone numbers, Aadhaar, PAN, email           │
│  replaced with tokens BEFORE any LLM call                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM EXTRACTION (Claude → Gemini → GPT-4o → Mock)          │
│  14-field structured JSON schema                           │
│  Per-field confidence scores (0.0–1.0)                     │
│  Source passage quotes for highlighting                    │
│  Auto-flag fields below 70% confidence                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  ACTION PLAN GENERATION (second LLM pass)                  │
│  comply / consider_appeal / file_appeal / no_action        │
│  Responsible department routing                            │
│  Deadline calculation (relative date parser)               │
│  Red alert if deadline ≤ 14 days                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  HUMAN REVIEW (React frontend)                             │
│  Side-by-side PDF + extracted fields                       │
│  Click field → scroll to source passage (PDF.js)          │
│  Edit, approve, or reject individual fields                │
│  Only approved records reach the dashboard                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  DASHBOARD + AUDIT TRAIL                                   │
│  Department-scoped views                                   │
│  SHA-256 chained audit log (tamper-evident)                │
│  Every edit timestamped and attributed                     │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI 0.111 |
| Database | PostgreSQL + SQLAlchemy 2.0 |
| Async tasks | Celery 5.4 + Redis |
| PDF extraction | PyMuPDF (fitz) |
| OCR | Tesseract (eng+kan) |
| PII masking | Microsoft Presidio |
| LLM primary | Claude 3.5 Sonnet (Anthropic) |
| LLM fallback | Gemini 1.5 Pro (Google) |
| LLM tertiary | GPT-4o (OpenAI) |
| Auth | JWT (python-jose) + bcrypt |
| Tests | pytest |

## Project Structure

```
verdictbridge/
├── backend/
│   ├── main.py                  # FastAPI app, lifespan, CORS
│   ├── config.py                # Pydantic settings (from .env)
│   ├── database.py              # SQLAlchemy engine + session
│   ├── models.py                # ORM: Document, ExtractedField, ActionPlan, AuditLog
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── dependencies.py          # JWT auth + department scoping
│   ├── worker.py                # Celery app configuration
│   ├── tasks.py                 # Async extraction pipeline task
│   ├── routes/
│   │   ├── auth.py              # POST /auth/register, /auth/login, /auth/me
│   │   ├── upload.py            # POST /upload/
│   │   ├── extraction.py        # GET /extraction/{id}, POST /extraction/{id}/retry
│   │   ├── review.py            # PATCH fields, approve/reject, audit trail
│   │   └── dashboard.py        # Stats, document list, file serving
│   ├── services/
│   │   ├── pdf_service.py       # PyMuPDF extraction + passage search
│   │   ├── ocr_service.py       # Tesseract OCR with image pre-processing
│   │   ├── llm_service.py       # Claude/Gemini/GPT-4o with fallback chain
│   │   ├── pii_service.py       # Presidio PII masking
│   │   ├── audit_service.py     # SHA-256 chained audit log
│   │   └── auth_service.py      # JWT + bcrypt auth
│   └── utils/
│       └── deadline_calculator.py  # Court day arithmetic + relative date parser
├── tests/
│   ├── test_llm_service.py      # LLM extraction tests (mock provider)
│   ├── test_deadline_calculator.py
│   ├── test_audit_service.py    # Chain integrity tests
│   └── test_api.py              # FastAPI integration tests
├── demo_pipeline.py             # End-to-end demo (no server needed)
├── setup.py                     # One-time setup script
├── requirements.txt
├── alembic.ini
└── .env.example
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Tesseract OCR (`apt install tesseract-ocr tesseract-ocr-kan` on Ubuntu)

### 1. Install dependencies
## Clone Repository

```bash
git clone https://github.com/your-username/VerdictBridge.git
cd VerdictBridge
```

---

# Backend Setup

## Create Virtual Environment

```bash
python -m venv venv
```

---

## Activate Virtual Environment

### Windows

```bash
venv\Scripts\activate
```

### Mac/Linux

```bash
source venv/bin/activate
```

---

## Install Backend Dependencies

```bash
pip install -r requirements.txt
```

---

## Run Backend Server

```bash
uvicorn backend.main:app --reload
```

Backend runs on:

```text
http://localhost:8000
```

---

# Frontend Setup

## Move to Frontend Folder

```bash
cd frontend
```

---

## Install Frontend Dependencies

```bash
npm install
```

---

## Run Frontend

```bash
npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

---

# Environment Variables

Create a `.env` file in the project root.

Example:

```env
SECRET_KEY=your_secret_key
DATABASE_URL=sqlite:///./verdictbridge.db

OPENAI_API_KEY=your_api_key
GOOGLE_API_KEY=your_api_key
ANTHROPIC_API_KEY=your_api_key
```

---

# Optional Features

## OCR Support

Install Tesseract OCR:

### Windows
Download from:
https://github.com/tesseract-ocr/tesseract

Then add path:

```env
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```


## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Register officer account |
| POST | `/api/v1/auth/login` | Login, get JWT token |
| GET | `/api/v1/auth/me` | Current user profile |
| POST | `/api/v1/upload/` | Upload judgment PDF |
| GET | `/api/v1/extraction/{id}` | Get extraction result + action plan |
| POST | `/api/v1/extraction/{id}/retry` | Re-queue failed extraction |
| GET | `/api/v1/tasks/{task_id}` | Poll Celery task status |
| GET | `/api/v1/review/{id}/fields` | List extracted fields |
| PATCH | `/api/v1/review/{id}/fields/{fid}` | Edit a field |
| POST | `/api/v1/review/{id}/fields/{fid}/approve` | Approve a field |
| GET | `/api/v1/review/{id}/action-plan` | Get action plan |
| PATCH | `/api/v1/review/{id}/action-plan` | Update action plan |
| POST | `/api/v1/review/{id}/approve` | Approve document (reviewer+) |
| POST | `/api/v1/review/{id}/reject` | Reject document (reviewer+) |
| GET | `/api/v1/review/{id}/audit` | Document audit trail |
| GET | `/api/v1/dashboard/stats` | Dashboard statistics |
| GET | `/api/v1/dashboard/documents` | Paginated document list |
| GET | `/api/v1/dashboard/audit-logs` | Recent audit logs |
| GET | `/api/v1/dashboard/audit-chain/verify` | Verify chain integrity (admin) |
| GET | `/api/v1/dashboard/files/{filename}` | Serve PDF for viewer |

Interactive docs: http://localhost:8000/docs

## Security Design

| Concern | Mitigation |
|---|---|
| PII on LLM calls | Presidio masks names, phone, Aadhaar, PAN before any API call |
| Audit tampering | SHA-256 chained log — each entry hashes the previous |
| Cross-department leakage | JWT claims scope queries to officer's department |
| LLM hallucination | Source highlighting lets reviewers verify every field |
| Prompt injection | Strict JSON schema output; length/type validation on all fields |
| Path traversal | File serving validates filename before disk access |

## LLM Provider Selection

The system auto-selects the best available provider:

```
ANTHROPIC_API_KEY set?  → Claude 3.5 Sonnet  (primary)
GOOGLE_API_KEY set?     → Gemini 1.5 Pro     (fallback)
OPENAI_API_KEY set?     → GPT-4o             (tertiary)
None set?               → Mock provider      (deterministic, for demos/tests)
```

Set any combination in `.env`. The system falls through the chain on failure.

## Default Credentials

After running `setup.py`:

| Field | Value |
|---|---|
| Email | admin@verdictbridge.gov.in |
| Password | Admin@1234 |
| Role | admin |

**Change the password immediately in production.**
