import warnings

from langchain_core.language_models import BaseChatModel

from app import config

# Newer Gemini models use fixed sampling and ignore temperature. Runs aren't fully
# deterministic either way, which is why evals report pass^3 (3 runs per task).
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults.*")


def make_llm() -> BaseChatModel:
    if not config.GEMINI_API_KEY:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
            "and put it in .env (see .env.example)."
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0,
        # Free tier: busy models answer 503 or 429. Retry a little, but fail within about
        # a minute instead of hanging for minutes.
        max_retries=2,
        timeout=20,
    )
