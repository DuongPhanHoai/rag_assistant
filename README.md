# RAG Assistant

A small LangChain-based project that uses RAG (Retrieval-Augmented Generation) over my CV and target job descriptions to:

- Answer questions like:
  - “Why are you a good fit for this role?”
  - “List 3 relevant experiences for this JD.”
- Surface relevant experience for specific JDs
- Run simple evaluations over a fixed question set

This project is also a playground for:
- Local LLMs (via LM Studio or remote APIs)
- RAG pipelines
- Basic LLM evals
- Agentic workflows (later step)

---

## Project Structure

```text
cv_rag_assistant/
  data/
    cv.txt
    jd_ai_pm.txt
    jd_ai_engineer.txt
  eval/
    questions.json
  rag_assistant.py
  eval_run.py
  requirements.txt
  README.md
