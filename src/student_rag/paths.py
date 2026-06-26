import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "student_management"
DOCS_DIR = DATA_DIR / "docs"
DB_PATH = ROOT_DIR / "student_management.sqlite"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
DEFAULT_TERM = os.getenv("STUDENT_TERM", "2026-Spring")
