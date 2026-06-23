# rag_assistant.py
import os
from operator import itemgetter

from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

DATA_DIR = "data"
VECTOR_DB_DIR = "chroma_db"

# Read LM Studio config from .env (with sensible defaults)
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "lmstudio")  # set exact model name in .env


def load_documents():
    docs = []
    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(f"DATA_DIR '{DATA_DIR}' not found")
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".txt"):
            path = os.path.join(DATA_DIR, filename)
            loader = TextLoader(path, encoding="utf-8")
            docs.extend(loader.load())
    if not docs:
        raise ValueError(f"No .txt files found in '{DATA_DIR}'")
    return docs


def build_vectorstore(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
    )
    chunks = splitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=VECTOR_DB_DIR,
    )
    return vectordb


def get_vectorstore():
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    if os.path.exists(VECTOR_DB_DIR):
        vectordb = Chroma(
            embedding_function=embeddings,
            persist_directory=VECTOR_DB_DIR,
        )
    else:
        docs = load_documents()
        vectordb = build_vectorstore(docs)
    return vectordb


def get_rag_chain():
    vectordb = get_vectorstore()
    retriever = vectordb.as_retriever(search_kwargs={"k": 4})

    # LM Studio as OpenAI-compatible chat endpoint
    llm = ChatOpenAI(
        base_url=LMSTUDIO_BASE_URL,
        api_key="not-needed",  # LM Studio ignores this
        model=LMSTUDIO_MODEL,
        temperature=0,
    )

    prompt = ChatPromptTemplate.from_template(
        """You are helping to answer questions based on the user's CV and job descriptions.

Use the following context to answer the question. If the answer is not in the context, say you don't see it in the documents.

Context:
{context}

Question:
{question}

Answer in a concise, factual way, grounded in the context."""
    )

    chain = (
            {
                "context": itemgetter("question") | retriever,
                "question": itemgetter("question"),
            }
            | prompt
            | llm
            | StrOutputParser()
    )

    return chain


def answer_question(question: str) -> dict:
    vectordb = get_vectorstore()

    # Run the RAG chain for the answer
    rag_chain = get_rag_chain()
    answer = rag_chain.invoke({"question": question})

    # Get source docs directly from the vector store
    docs = vectordb.similarity_search(question, k=4)
    sources = list({doc.metadata.get("source", "") for doc in docs})

    return {
        "question": question,
        "answer": answer,
        "sources": sources,
    }


if __name__ == "__main__":
    while True:
        q = input("Ask a question (or 'quit'): ").strip()
        if q.lower() in ["quit", "exit"]:
            break
        try:
            res = answer_question(q)
            print("\nAnswer:\n", res["answer"])
            print("\nSources:")
            for s in res["sources"]:
                print(" -", s)
        except Exception as e:
            print("Error:", e)
        print("-" * 40)