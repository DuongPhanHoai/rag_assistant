from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "student_management"
DOCS_DIR = DATA_DIR / "docs"
DB_PATH = ROOT_DIR / "student_management.sqlite"
VECTOR_DB_DIR = ROOT_DIR / "chroma_student_db"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
