"""AI Responder module for Daraei Academy Telegram bot.

This file exposes a single singleton instance `responder` that can be
imported anywhere in the project and used like:

    from ai.model import responder
    reply_text = responder.answer_ticket(subject, body)

The old standalone script functions are refactored into the `AIResponder`
class without changing their internal logic/prompts.  All heavy loading
(documents, embeddings, FAISS index) happens once on the first import so
that handlers stay fast.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

import numpy as np
import faiss  # type: ignore
import openai  # type: ignore
import google.generativeai as genai  # type: ignore
from docx import Document  # type: ignore
import tiktoken  # type: ignore
import nltk  # type: ignore
from nltk.tokenize import sent_tokenize  # type: ignore

from database.queries import DatabaseQueries
nltk.download('punkt_tab')
# ---------------------------------------------------------------------------
# Environment & constants
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPEN_AI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not OPENAI_API_KEY or not GEMINI_API_KEY:
    raise RuntimeError("OPEN_AI and GEMINI_API_KEY must be set in .env")

openai.api_key = OPENAI_API_KEY
genai.configure(api_key=GEMINI_API_KEY)

# Module logger
logger = logging.getLogger(__name__)

# Document paths (relative to repo root)
DOCS_DIR = Path(__file__).resolve().parents[1] / "database" / "data" / "documents"
GENERAL_DOC_NO_SIGNAL = DOCS_DIR / "Q&A_no_signal.docx"
GENERAL_DOC = DOCS_DIR / "Q&A.docx"
EXPERT_DOC = DOCS_DIR / "scripts.docx"

HISTORY_DIR = Path(__file__).parent / "user_histories"
HISTORY_DIR.mkdir(exist_ok=True)

# Ensure NLTK punkt is available at runtime (one-time download)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:  # pragma: no cover – runs only once in prod
    nltk.download("punkt", quiet=True)

# ---------------------------------------------------------------------------
# Helper functions (ported unchanged except minor typographical fixes)
# ---------------------------------------------------------------------------

def read_docx(file_path: Path) -> str:
    if not file_path.exists():
        logger.warning(f"[AIResponder] Document not found at {file_path}. Using empty content.")
        return ""
    try:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        logger.error(f"[AIResponder] Failed reading {file_path}: {e}. Using empty content.")
        return ""


def chunk_text(text: str, max_tokens: int = 300, overlap: int = 50) -> List[str]:
    tokenizer = tiktoken.get_encoding("cl100k_base")
    sentences = sent_tokenize(text)
    chunks, current_chunk, current_tokens = [], [], 0

    for sentence in sentences:
        token_count = len(tokenizer.encode(sentence))
        if current_tokens + token_count <= max_tokens:
            current_chunk.append(sentence)
            current_tokens += token_count
        else:
            chunks.append(" ".join(current_chunk))
            while current_tokens > overlap and current_chunk:
                current_tokens -= len(tokenizer.encode(current_chunk.pop(0)))
            current_chunk.append(sentence)
            current_tokens = sum(len(tokenizer.encode(s)) for s in current_chunk)
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks


def get_embedding(text: str, model: str = "text-embedding-3-small") -> np.ndarray:
    resp = openai.embeddings.create(input=text, model=model)
    return np.array(resp.data[0].embedding, dtype="float32")


def build_faiss(chunks: List[str]) -> Tuple[faiss.IndexFlatL2, List[str]]:
    with ThreadPoolExecutor(max_workers=4) as ex:
        embeddings = list(ex.map(get_embedding, chunks))
    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings, dtype="float32"))
    return index, chunks


def translate_to_english(persian_text: str) -> str:
    few_shot = (
        "Persian: حداقل پولی که میتونم باهاش سرمایه گذاری کنم چقدره؟\n"
        "English: What is the minimum capital required to start investing?\n\n"
        "Persian: تو این شرایط بازار چه نوع استراتژی پیشنهاد میدی؟\n"
        "English: What kind of strategy do you recommend in this market condition?"
    )
    prompt = f"{few_shot}\nPersian: {persian_text}\nEnglish:"
    model = genai.GenerativeModel("gemini-2.5-flash")
    return model.generate_content(prompt).text.strip()


def retrieve(query: str, index: faiss.IndexFlatL2 | None, chunks: List[str], k: int = 3) -> List[str]:
    if not chunks or index is None or index.ntotal == 0:
        return []
    q_vec = get_embedding(query)
    distances, indices = index.search(np.array([q_vec], dtype="float32"), k)
    return [chunks[i] for i in indices[0]]


def save_history(history: list, user_id: int | str):
    """Save conversation history for a specific user."""
    history_path = HISTORY_DIR / f"{user_id}.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_history(user_id: int | str):
    """Load conversation history for a specific user."""
    history_path = HISTORY_DIR / f"{user_id}.json"
    if history_path.exists():
        with open(history_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []  # Return empty list if file is corrupted or empty
    return []


def summarize_history(history):
    if not history:
        return ""
    convo = "\n".join([f"User: {h['user']}\nAssistant: {h['response']}" for h in history[-10:]])
    prompt = (
        "Summarize this user-assistant conversation history for future context (finance-specific):\n\n"
        f"{convo}"
    )
    model = genai.GenerativeModel("gemini-2.5-flash")
    return model.generate_content(prompt).text.strip()


def summarize_response(response: str) -> str:
    prompt = (
        "Rewrite the following assistant reply in Persian, keeping it short (3–5 sentences), FRIENDLY, and based only on the original answer. "
        "Do not add any new content.\n\nOriginal answer:\n" + response
    )
    model = genai.GenerativeModel("gemini-2.5-flash")
    return model.generate_content(prompt).text.strip()


def generate_agentic_answer(
    persian_question: str,
    translated_question: str,
    summary: str,
    general_chunks: str,
    expert_chunks: str,
    history: list,
    user_id: int | str,
) -> str:
    prompt = f"""Answer in PERSIAN only — both written and spoken. DO NOT use English letters (no Fingilish). Absolutely NO ENGLISH in the response.
Do NOT mention that you are an AI or that you are reading from a source. Keep answers SHORT, CLEAR, and ACCURATE. You are acting as a sales support in آکادمی دارایی. Use ONLY the provided internal context as your main source.
Only if the context is clearly insufficient, use general financial knowledge — and clearly state that you’re doing so.

### GENERAL KNOWLEDGE CONTEXT:
{general_chunks}

### EXPERT STRATEGY CONTEXT:
{expert_chunks}

###CONVERSATION SUMMARY:
{summary}

### PERSIAN QUESTION:
{persian_question}

### ENGLISH TRANSLATION:
{translated_question}

### FINAL ANSWER:"""

    response = openai.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
    )
    raw_answer = response.choices[0].message.content.strip()
    history.append({"user": persian_question, "response": raw_answer})
    save_history(history, user_id)
    return raw_answer

# ---------------------------------------------------------------------------
# Main class wrapper
# ---------------------------------------------------------------------------

class AIResponder:
    """Singleton-style responder encapsulating all heavy lifting."""

    _instance: "AIResponder | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        # Load documents & build indexes once.
        self._load_documents()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def answer_ticket(self, subject: str, message: str, user_id: int | str) -> str:
        """Generate an answer given ticket subject & body, for a specific user."""
        persian_question = f"موضوع: {subject}\nمتن: {message}"
        translated = translate_to_english(persian_question)
        history = load_history(user_id)
        summary = summarize_history(history)

        # Check user's subscription status to select the correct knowledge base
        has_subscription = DatabaseQueries.has_active_subscription(user_id)
        
        if has_subscription:
            logger.info(f"User {user_id} has active subscription. Using general KB.")
            general_index = self._general_index
            general_chunks = self._general_chunks
        else:
            logger.info(f"User {user_id} has no active subscription. Using no-signal KB.")
            general_index = self._general_no_signal_index
            general_chunks = self._general_no_signal_chunks

        general_ctx = retrieve(translated, general_index, general_chunks)
        expert_ctx = retrieve(translated, self._expert_index, self._expert_chunks)

        answer = generate_agentic_answer(
            persian_question,
            translated,
            summary,
            "\n\n".join(general_ctx),
            "\n\n".join(expert_ctx),
            history,
            user_id,
        )
        return answer

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_documents(self):
        # Load both versions of the general knowledge base
        general_text = read_docx(GENERAL_DOC)
        general_no_signal_text = read_docx(GENERAL_DOC_NO_SIGNAL)
        expert_text = read_docx(EXPERT_DOC)

        self._general_chunks = chunk_text(general_text) if general_text else []
        self._general_no_signal_chunks = chunk_text(general_no_signal_text) if general_no_signal_text else []
        self._expert_chunks = chunk_text(expert_text) if expert_text else []

        self._general_index = None
        self._general_no_signal_index = None
        self._expert_index = None

        if self._general_chunks:
            self._general_index, _ = build_faiss(self._general_chunks)
        if self._general_no_signal_chunks:
            self._general_no_signal_index, _ = build_faiss(self._general_no_signal_chunks)
        if self._expert_chunks:
            self._expert_index, _ = build_faiss(self._expert_chunks)


# Singleton instance ready for import
responder = AIResponder()

# ---------------------------------------------------------------------------
# Optional CLI for manual testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("AIResponder interactive demo. Type 'exit' to quit.\n")
    # Use a dummy user ID for testing history and subscription logic
    try:
        test_user_id = int(input("Enter a test user ID (e.g., 12345): "))
    except ValueError:
        print("Invalid ID. Using default 0.")
        test_user_id = 0

    while True:
        subj = input("موضوع تیکت: ")
        if subj.lower() == "exit":
            break
        body = input("متن تیکت: ")
        resp = responder.answer_ticket(subj, body, test_user_id)
        print("\nپاسخ پیشنهادی:\n", resp)
