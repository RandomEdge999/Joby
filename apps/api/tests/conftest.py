import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use an in-memory sqlite for tests
os.environ["DATABASE_URL"] = "sqlite:///./data/joby_test.db"

# Clean DB before each session
db_path = ROOT / "data" / "joby_test.db"
if db_path.exists():
    db_path.unlink()

# Create tables up front so TestClient (which does not fire startup by default)
# has schema available.
from app.db import Base, engine  # noqa: E402
from app import models  # noqa: E402,F401

Base.metadata.create_all(bind=engine)
