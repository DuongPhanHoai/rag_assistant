# DESIGN

This document describes the design of the **CV RAG Assistant**:

- What problem it solves
- Architecture and main components
- Data flow and control flow
- How LangChain is used (RAG pipeline and eval)
- Planned extensions

---

## 1. Problem & Goals

**Problem:**  
Given a set of personal documents (CV, job descriptions), we want a small local LLM application that can:

- Answer questions about **fit for specific roles** (AI PM, AI Engineer/SDET, etc.)
- Use **RAG (Retrieval-Augmented Generation)** so answers are grounded in the documents.
- Provide a simple **evaluation pipeline** to inspect answer quality over a fixed question set.

**Constraints / Choices:**

- Use **local LLMs** via **LM Studio** (OpenAI-compatible HTTP API).
- Use **LangChain** for RAG composition.
- Use **local embeddings** (HuggingFace) + **Chroma** as vector store.
- Keep the design simple and extensible (future agents, better evals).

---

## 2. High-Level Architecture

Main pieces:

- `data/` – Source documents (CV + JDs) in plain text.
- `rag_assistant.py` – Core RAG pipeline:
    - Document loading & chunking
    - Embedding + vector store
    - Retrieval + LLM answering
- `eval_run.py` – Simple evaluation runner:
    - Loads a small set of questions
    - Runs them through the RAG assistant
    - Stores outputs to JSONL for manual / later model-graded evals
- `LM Studio` – Local LLM server providing an **OpenAI-compatible** chat endpoint.

---

## 3. Components

### 3.1 Documents & Data

- **Input documents**:
    - `data/cv.txt`
    - `data/jd_ai_pm.txt`
    - `data/jd_ai_engineer.txt`
    - (any other `.txt` files added to `data/`)

- **Eval questions**:
    - `eval/questions.json` – list of objects with:
        - `id`: short identifier
        - `question`: natural language question
        - optional `notes`: guidance for human review

- **Eval results**:
    - `eval/results.jsonl` – each line is a JSON record with:
        - `run_id` (timestamp)
        - `id` (question id)
        - `question`
        - `answer`
        - `sources` (files used as context)

---

### 3.2 RAG Assistant (`rag_assistant.py`)

Key functions:

- `load_documents()`
    - Scans `data/` for `.txt` files.
    - Loads them as LangChain `Document` objects with `source` metadata (file path).

- `build_vectorstore(docs)`
    - Splits documents into overlapping chunks using  
      `RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)`.
    - Uses `HuggingFaceEmbeddings` (`sentence-transformers/all-MiniLM-L6-v2`) to embed chunks.
    - Stores them in a local **Chroma** DB with persistent directory `chroma_db`.

- `get_vectorstore()`
    - If `chroma_db` exists, reopens it with the same embedding function.
    - Otherwise, calls `load_documents()` and `build_vectorstore(docs)`.

- `get_rag_chain()`
    - Creates a **retriever** from the vector store (`k=4` top matches).
    - Creates a **Chat LLM** using `ChatOpenAI` pointing to LM Studio:
        - `base_url` from `LMSTUDIO_BASE_URL` (e.g. `http://localhost:1234/v1`)
        - `model` from `LMSTUDIO_MODEL` (e.g. `google/gemma-4-e4b`)
        - `api_key` = dummy string (`"not-needed"`)
    - Builds a **prompt** with explicit context + question slots.
    - Composes an LCEL pipeline (LangChain Expression Language):

      ```text
      {"context": retriever(question), "question": question}
        → prompt
        → llm
        → StrOutputParser (string answer)
      ```

- `answer_question(question: str) -> dict`
    - Ensures vector store exists (`get_vectorstore()`).
    - Invokes `get_rag_chain()` to get the answer.
    - Uses `vectordb.similarity_search(question, k=4)` to fetch top chunks and extract **source file paths**.
    - Returns:

      ```python
      {
        "question": question,
        "answer": <string>,
        "sources": [list of file paths]
      }
      ```

- `__main__` block
    - Simple CLI loop:
        - Reads user question.
        - Calls `answer_question`.
        - Prints answer + sources.

---

### 3.3 Evaluation Runner (`eval_run.py`)

- Ensures the current directory is on `sys.path`, then imports `answer_question` from `rag_assistant`.
- Loads questions from `eval/questions.json`.
- Generates a `run_id` (UTC timestamp).
- For each question:
    - Calls `answer_question(question)`.
    - Writes one JSON record per line into `eval/results.jsonl`:

      ```json
      {
        "run_id": "...",
        "id": "fit_ai_pm",
        "question": "Why am I a good fit for an AI & Automation Project Manager role?",
        "answer": "...",
        "sources": ["data/cv.txt", "data/jd_ai_pm.txt"]
      }
      ```

This provides a **dataset** of Q&A pairs grounded in the current CV + JDs, which can be:

- Manually reviewed and scored.
- Later fed into a **model-graded eval** pipeline.

---

## 4. LangChain Application Flow

### 4.1 RAG Answering Flow

Text flow:

```text
+-----------------------+
|  User question (CLI)  |
+-----------+-----------+
            |
            v
+----------------------+      +-------------------------+
|  answer_question(q)  |----->|  get_vectorstore()      |
+-----------+----------+      +-------------------------+
            |
            v
+---------------------------+
|  get_rag_chain()         |
|  - retriever (Chroma)    |
|  - Chat LLM (LM Studio)  |
|  - prompt template       |
+-----------+---------------+
            |
            v
   LangChain RAG Chain (LCEL):
   ---------------------------------------------
   {"context": retriever(q), "question": q}
         → ChatPromptTemplate
         → ChatOpenAI (LM Studio)
         → StrOutputParser
   ---------------------------------------------
            |
            v
+---------------------------+
|   Answer (string)         |
+---------------------------+
            |
            v
+---------------------------+
| similarity_search(q, k=4) |
|  (for source documents)   |
+---------------------------+
            |
            v
+---------------------------+
| return {question, answer, |
|         sources[]}        |
+---------------------------+
4.2 Eval Flow
text

Collapse


 Copy

python eval_run.py
       |
       v
+---------------------------+
|  Load eval/questions.json |
+---------------------------+
       |
       v
  For each question:
       |
       v
+---------------------------+
|  answer_question(q)       |
+---------------------------+
       |
       v
+---------------------------+
|  Append record to         |
|  eval/results.jsonl       |
+---------------------------+