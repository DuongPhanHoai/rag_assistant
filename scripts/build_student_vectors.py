# scripts/build_student_vectors.py
import os
import shutil
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter


ROOT_DIR = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT_DIR / "data" / "student_management" / "docs"
VECTOR_DB_DIR = ROOT_DIR / "chroma_student_db"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_student_documents():
    if not DOCS_DIR.is_dir():
        raise FileNotFoundError(f"Student docs directory not found: {DOCS_DIR}")

    docs = []
    for path in sorted(DOCS_DIR.rglob("*")):
        if path.suffix.lower() in {".md", ".txt"}:
            loader = TextLoader(str(path), encoding="utf-8")
            docs.extend(loader.load())

    if not docs:
        raise ValueError(f"No .md or .txt files found in '{DOCS_DIR}'")

    return docs


def build_student_vectorstore(reset: bool = True) -> Chroma:
    docs = load_student_documents()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=120,
    )
    chunks = splitter.split_documents(docs)

    if reset and VECTOR_DB_DIR.exists():
        shutil.rmtree(VECTOR_DB_DIR)

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(VECTOR_DB_DIR),
    )
    return vectordb


if __name__ == "__main__":
    vectorstore = build_student_vectorstore()
    print(
        "Built student vector store:"
        f" {os.path.relpath(VECTOR_DB_DIR, ROOT_DIR)}"
        f" ({vectorstore._collection.count()} chunks)"
    )
