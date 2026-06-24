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
  student_agent.py
  eval_student_run.py
  requirements.txt
  README.md
```

---

## Setup

Build the local assets:

```powershell
python scripts/build_student_db.py
python scripts/build_student_vectors.py
```

Ask questions interactively:

```powershell
python student_agent.py
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