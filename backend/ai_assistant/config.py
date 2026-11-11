import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(override: bool = False) -> None:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in candidates:
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]

            if override or key not in os.environ:
                os.environ[key] = value


_load_env_file(override=True)


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    code_generation_provider: str
    gemini_model: str
    gemini_api_key: str
    openai_api_key: str
    openai_base_url: str
    timeout: int
    gemini_api_key_1: str = ""
    gemini_model_1: str = "gemini-3.1-flash-lite"
    gemini_api_key_2: str = ""
    gemini_model_2: str = "gemini-3.1-flash-lite"
    gemini_keys: tuple[tuple[str, str], ...] = ()

    @property
    def is_enabled(self) -> bool:
        provider = (self.provider or "auto").lower()
        has_gemini = bool(
            self.gemini_api_key
            or self.gemini_api_key_1
            or self.gemini_api_key_2
            or self.gemini_keys
        )
        has_openai = bool(self.openai_api_key or self.openai_base_url)
        if provider == "auto":
            return bool(has_gemini or has_openai)
        if provider == "gemini":
            return has_gemini
        if provider in {"openai", "openai_compatible", "groq"}:
            return has_openai
        return False


def get_ai_settings() -> AISettings:
    _load_env_file(override=True)
    provider = (os.getenv("AI_PROVIDER", "groq") or "groq").lower()
    model = os.getenv("AI_MODEL", "openai/gpt-oss-120b")
    if provider == "groq" and model == "llama-3.3-70b-versatile":
        model = "openai/gpt-oss-120b"

    gemini_api_key_1 = os.getenv("GEMINI_API_KEY_1") or os.getenv("GEMINI_API_KEY", "")
    gemini_model_1 = os.getenv("GEMINI_MODEL_1") or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    gemini_api_key_2 = os.getenv("GEMINI_API_KEY_2", "")
    gemini_model_2 = os.getenv("GEMINI_MODEL_2", "gemini-3.1-flash-lite")

    keys: list[tuple[str, str]] = []
    if gemini_api_key_1:
        keys.append((gemini_api_key_1, gemini_model_1))
    if gemini_api_key_2 and gemini_api_key_2 != gemini_api_key_1:
        keys.append((gemini_api_key_2, gemini_model_2))

    primary_key = gemini_api_key_1 or gemini_api_key_2
    primary_model = gemini_model_1 if gemini_api_key_1 else gemini_model_2

    return AISettings(
        provider=provider,
        model=model,
        code_generation_provider=(
            os.getenv("CODE_GENERATION_PROVIDER", "default") or "default"
        ).lower(),
        gemini_model=primary_model,
        gemini_api_key=primary_key,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        timeout=int(os.getenv("AI_TIMEOUT", "60")),
        gemini_api_key_1=gemini_api_key_1,
        gemini_model_1=gemini_model_1,
        gemini_api_key_2=gemini_api_key_2,
        gemini_model_2=gemini_model_2,
        gemini_keys=tuple(keys),
    )
