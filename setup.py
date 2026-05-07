"""
VerdictBridge – Quick setup script.

Creates the database, uploads directory, and seeds the admin user.
Run once after installing requirements:
  python setup.py
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ Loaded .env")
except ImportError:
    print("⚠  python-dotenv not installed — using environment variables directly")

from backend.database import init_db, get_db
from backend.config import get_settings

settings = get_settings()


def main():
    print("\n── VerdictBridge Setup ──────────────────────────────────────────")

    # Create upload directory
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Upload directory: {upload_dir.resolve()}")

    # Initialise database
    print(f"  Connecting to: {settings.database_url[:40]}...")
    try:
        init_db()
        print("✓ Database tables created")
    except Exception as exc:
        print(f"✗ Database error: {exc}")
        print("  Make sure PostgreSQL is running and DATABASE_URL is correct.")
        sys.exit(1)

    # Seed admin user
    db = next(get_db())
    try:
        from backend.models import User
        if db.query(User).count() == 0:
            from backend.services.auth_service import create_user
            from backend.models import UserRole
            admin = create_user(
                db,
                email="admin@verdictbridge.gov.in",
                full_name="System Administrator",
                password="Admin@1234",
                department="Administration",
                role=UserRole.ADMIN,
            )
            print(f"✓ Admin user created: {admin.email}")
            print("  ⚠  Default password: Admin@1234 — change immediately!")
        else:
            print("✓ Users already exist — skipping seed")
    finally:
        db.close()

    print("\n── Setup complete ───────────────────────────────────────────────")
    print("  Start the API:    uvicorn backend.main:app --reload")
    print("  Start the worker: celery -A backend.worker worker --loglevel=info")
    print("  API docs:         http://localhost:8000/docs")
    print("  Run demo:         python demo_pipeline.py")
    print("  Run tests:        pytest tests/ -v")
    print("─────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
