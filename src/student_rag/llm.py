import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()

LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "lmstudio")
LMSTUDIO_TIMEOUT_SECONDS = float(os.getenv("LMSTUDIO_TIMEOUT_SECONDS", "10"))


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LMSTUDIO_BASE_URL,
        api_key="not-needed",
        model=LMSTUDIO_MODEL,
        temperature=0,
        timeout=LMSTUDIO_TIMEOUT_SECONDS,
    )
