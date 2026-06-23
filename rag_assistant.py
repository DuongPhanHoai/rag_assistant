# rag_assistant.py
import os
from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA

load_dotenv()  # expects OPENAI_API_KEY in .env

DATA_DIR = "data"
VECTOR_DB_DIR = "chroma_db"

def load_documents():
    docs = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".txt"):
            path = os.path.join(DATA_DIR, filename)
            loader = TextLoader(path, encoding="utf-8")
            docs.extend(loader.load())
    return docs

def build_vectorstore(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200
    )
    chunks = splitter.split_documents(docs)

    embeddings = OpenAIEmbeddings()
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=VECTOR_DB_DIR
    )
    return vectordb

def get_qa_chain():
    # If DB exists, reuse; else build
    if os.path.exists(VECTOR_DB_DIR):
        embeddings = OpenAIEmbeddings()
        vectordb = Chroma(
            embedding_function=embeddings,
            persist_directory=VECTOR_DB_DIR
        )
    else:
        docs = load_documents()
        vectordb = build_vectorstore(docs)

    retriever = vectordb.as_retriever(search_kwargs={"k": 4})
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # choose model you have

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True
    )
    return qa_chain

def answer_question(question: str) -> dict:
    qa_chain = get_qa_chain()
    result = qa_chain({"query": question})
    answer = result["result"]
    sources = [doc.metadata.get("source", "") for doc in result["source_documents"]]
    return {
        "question": question,
        "answer": answer,
        "sources": list(set(sources))
    }

if __name__ == "__main__":
    while True:
        q = input("Ask a question (or 'quit'): ").strip()
        if q.lower() in ["quit", "exit"]:
            break
        res = answer_question(q)
        print("\nAnswer:\n", res["answer"])
        print("\nSources:")
        for s in res["sources"]:
            print(" -", s)
        print("-" * 40)
