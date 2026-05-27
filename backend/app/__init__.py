"""Backend application package.

Sub-modules (owned by various tracks):
  - app.config    - settings (this track)
  - app.db        - engine, session factory, Base (this track)
  - app.security  - password hashing + JWT helpers (this track)
  - app.models    - SQLAlchemy ORM models (this track)
  - app.main      - FastAPI app (this track)
  - app.routes.*  - HTTP routers (this track)
"""

__version__ = "0.1.0"
