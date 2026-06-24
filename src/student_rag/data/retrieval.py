import shutil

from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from student_rag.paths import DOCS_DIR, EMBEDDING_MODEL, VECTOR_DB_DIR


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
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(VECTOR_DB_DIR),
    )


def ensure_vectorstore() -> None:
    if not VECTOR_DB_DIR.exists():
        build_student_vectorstore()


def get_student_vectorstore() -> Chroma:
    ensure_vectorstore()
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return Chroma(
        embedding_function=embeddings,
        persist_directory=str(VECTOR_DB_DIR),
    )


def retrieve_notes(query: str, k: int = 4) -> list[dict]:
    vectordb = get_student_vectorstore()
    docs = vectordb.similarity_search(query, k=k)
    return [
        {
            "source": doc.metadata.get("source", ""),
            "content": doc.page_content,
        }
        for doc in docs
    ]
