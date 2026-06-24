# Student Management Agentic RAG

A small local sample for answering Student Management questions with:

- SQLite structured data for students, courses, enrollments, attendance, assessments, and fees.
- Chroma embeddings over advising notes, policies, and course descriptions.
- An agentic workflow that plans, decomposes the request, runs read-only SQL, retrieves notes, produces a table or Vega-Lite chart spec, replans if needed, and answers.

The project uses LM Studio's OpenAI-compatible local chat API, HuggingFace embeddings, Chroma, and Python's built-in SQLite support.

---

## Project Structure

```text
student_management_agentic_rag/
  data/
    student_management/
      students.csv
      courses.csv
      enrollments.csv
      attendance.csv
      assessments.csv
      fees.csv
      docs/
        advising_notes.md
        policies.md
        course_descriptions.md
  eval/
    student_questions.json
  scripts/
    build_student_db.py
    build_student_vectors.py
  src/
    student_rag/
      __init__.py
      paths.py
      artifacts.py
      llm.py
      data/
        __init__.py
        db.py
        retrieval.py
      agents/
        __init__.py
        deterministic.py
        lmstudio.py
      mcp/
        __init__.py
        server.py
        http_server.py
  eval_student_run.py
  pyproject.toml
  requirements.txt
  README.md
```

---

## Setup

Build the local assets:

```powershell
pip install -r requirements.txt
python scripts/build_student_db.py
python scripts/build_student_vectors.py
```

Ask questions interactively:

```powershell
python -m student_rag.agents.deterministic
```

Run the LM Studio tool-calling agent:

```powershell
python -m student_rag.agents.lmstudio
```

After `pip install -r requirements.txt`, you can also use the console scripts:

```powershell
student-agent
student-lmstudio-agent
```

To chat directly inside LM Studio, configure LM Studio MCP to run:

```powershell
student-mcp-server
```

Example questions:

- `Which students are at risk this term and why?`
- `Show average grade by course and explain weak areas.`
- `Who qualifies for scholarship support based on GPA, attendance, and fee status?`
- `Create a chart of attendance trend by month for at-risk students.`

Run the student eval set:

```powershell
python eval_student_run.py
```

Generated local artifacts are ignored by git:

- `student_management.sqlite`
- `chroma_student_db/`
- `eval/student_results.jsonl`

## LM Studio Setup

Start the LM Studio local server and load a tool-capable model. For example:

```env
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen/qwen3-4b-thinking-2507
LMSTUDIO_TIMEOUT_SECONDS=30
```

Use `student_rag.agents.deterministic` for the deterministic workflow with fallback planning. Use `student_rag.agents.lmstudio` when you want LM Studio to choose and call tools directly through the OpenAI-compatible tool-calling API.

For detailed setup, tool behavior, and troubleshooting, see `docs/LMSTUDIO_CHAT_AGENT_GUIDE.md`.

For terminal commands and validation steps, see `docs/CLI_GUIDE.md`.

For Cursor Chat MCP setup, see `docs/CURSOR_CHAT_MCP_GUIDE.md`.

For testing the Python API tool loop, see `docs/API_TESTING_GUIDE.md`.

For running the MCP server from another machine, see `docs/REMOTE_MCP_SERVER_GUIDE.md`.