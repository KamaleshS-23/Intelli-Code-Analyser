import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .config import get_ai_settings


def _format_provider_error(provider: str, exc: Exception) -> str:
    status = getattr(exc, "code", None)
    message = str(exc)
    body_detail = ""
    if hasattr(exc, "read"):
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
                body_detail = f": {data['error']['message']}"
            elif "error" in data and isinstance(data["error"], str):
                body_detail = f": {data['error']}"
        except Exception:
            pass

    if status == 404:
        return (
            f"{provider} returned 404 Not Found{body_detail}. Check that AI_MODEL is valid for your provider "
            "and that the API URL/key matches the account you are using."
        )
    if status == 401:
        return f"{provider} rejected the API key or token{body_detail}. Verify the key is valid and not expired."
    if status == 429:
        return f"{provider} rate limit exceeded{body_detail}. Please wait a moment before retrying."
    if status == 403:
        return f"{provider} request was forbidden (HTTP 403){body_detail}."
    if status is not None:
        return f"{provider} request failed with HTTP {status}: {message}{body_detail}"
    return f"{provider} request failed: {message}"


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, context: dict | None = None) -> str:
        raise NotImplementedError


class FallbackProvider(AIProvider):
    def __init__(self, providers: list[AIProvider] | None = None):
        self.providers = providers or []

    def generate(self, prompt: str, context: dict | None = None) -> str:
        if not self.providers:
            raise RuntimeError("No AI providers are configured.")

        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.generate(prompt, context)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        raise RuntimeError("All configured AI providers failed: " + "; ".join(errors))


def _get_gemini_key_pairs(settings, override_model: str | None = None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    configured_keys = getattr(settings, "gemini_keys", ())
    if configured_keys:
        for key, model in configured_keys:
            if key:
                pairs.append((key, override_model or model))

    if not pairs:
        key_1 = getattr(settings, "gemini_api_key_1", "") or getattr(settings, "gemini_api_key", "")
        model_1 = override_model or getattr(settings, "gemini_model_1", "") or getattr(settings, "gemini_model", "gemini-3.1-flash-lite")
        if key_1:
            pairs.append((key_1, model_1))

        key_2 = getattr(settings, "gemini_api_key_2", "")
        model_2 = override_model or getattr(settings, "gemini_model_2", "") or model_1
        if key_2 and key_2 != key_1:
            pairs.append((key_2, model_2))

    if not pairs and getattr(settings, "gemini_api_key", ""):
        pairs.append((settings.gemini_api_key, override_model or getattr(settings, "gemini_model", "gemini-3.1-flash-lite")))

    return pairs


def _has_gemini_configured(settings) -> bool:
    return bool(
        getattr(settings, "gemini_api_key", "")
        or getattr(settings, "gemini_api_key_1", "")
        or getattr(settings, "gemini_api_key_2", "")
        or getattr(settings, "gemini_keys", ())
    )


_EXHAUSTED_KEY_COOLDOWNS: dict[str, float] = {}


class GeminiProvider(AIProvider):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        settings = get_ai_settings()
        self.explicit_model = model
        self.explicit_api_key = api_key
        self.timeout = getattr(settings, "timeout", 30)
        if api_key:
            self.key_pairs = [(api_key, model or getattr(settings, "gemini_model", "gemini-3.1-flash-lite"))]
        else:
            self.key_pairs = _get_gemini_key_pairs(settings, override_model=model)

        self.model = model or getattr(settings, "gemini_model", None) or getattr(settings, "model", "gemini-3.1-flash-lite")
        self.api_key = api_key or getattr(settings, "gemini_api_key", "")

    def _call_model(self, model: str, api_key: str, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

        candidates = body.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no content.")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("Gemini response did not include text parts.")

        return "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()

    def generate(self, prompt: str, context: dict | None = None) -> str:
        if not self.key_pairs and not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        pairs_to_try = self.key_pairs or ([(self.api_key, self.model)] if self.api_key else [])
        now = time.time()
        # Sort so healthy (non-cooldown) keys are attempted first
        healthy_pairs = [p for p in pairs_to_try if _EXHAUSTED_KEY_COOLDOWNS.get(p[0], 0) < now]
        cooldown_pairs = [p for p in pairs_to_try if _EXHAUSTED_KEY_COOLDOWNS.get(p[0], 0) >= now]
        ordered_pairs = healthy_pairs + cooldown_pairs

        last_error = None

        for api_key, primary_model in ordered_pairs:
            # Fast, lightweight candidate models to prevent timeouts
            models_to_try = [primary_model]
            for fallback in ("gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-3.5-flash"):
                if fallback not in models_to_try:
                    models_to_try.append(fallback)

            key_exhausted = False
            for candidate_model in models_to_try:
                try:
                    result = self._call_model(candidate_model, api_key, prompt)
                    # Clear cooldown on success
                    _EXHAUSTED_KEY_COOLDOWNS.pop(api_key, None)
                    return result
                except urllib.error.HTTPError as exc:
                    last_error = RuntimeError(_format_provider_error("Gemini", exc))
                    # HTTP 429: rate limit / quota reached for this key -> advance to next key
                    if exc.code == 429:
                        _EXHAUSTED_KEY_COOLDOWNS[api_key] = time.time() + 600
                        key_exhausted = True
                        break
                    # HTTP 401/403: invalid or forbidden key -> advance to next key
                    if exc.code in (401, 403):
                        _EXHAUSTED_KEY_COOLDOWNS[api_key] = time.time() + 600
                        key_exhausted = True
                        break
                    # HTTP 404, 500, 502, 503, 504: model/service transient issue -> try fallback model
                    if exc.code not in (404, 500, 502, 503, 504):
                        raise last_error from exc
                except (urllib.error.URLError, TimeoutError) as exc:
                    last_error = RuntimeError(_format_provider_error("Gemini", exc))
                    # Read timeout or connection drop -> mark key cooldown and try next key
                    _EXHAUSTED_KEY_COOLDOWNS[api_key] = time.time() + 300
                    key_exhausted = True
                    break
                except Exception as exc:
                    last_error = exc
                    break

            if key_exhausted:
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("Gemini provider failed to generate content.")


class OpenAICompatibleProvider(AIProvider):
    def __init__(self):
        settings = get_ai_settings()
        self.api_key = settings.openai_api_key or settings.gemini_api_key
        self.model = settings.model
        self.base_url = settings.openai_base_url
        self.timeout = settings.timeout

    def generate(self, prompt: str, context: dict | None = None) -> str:
        if not self.api_key:
            raise RuntimeError("OpenAI API key is not configured.")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an AI technical debt assistant for a Java project analyzer. Use only the facts provided in the project context and stay grounded in actual data."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        request = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_format_provider_error("OpenAI-compatible API", exc)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(_format_provider_error("OpenAI-compatible API", exc)) from exc

        choices = body.get("choices") or []
        if not choices:
            raise ValueError("OpenAI-compatible provider returned no content.")

        message = choices[0].get("message", {}).get("content", "")
        if isinstance(message, list):
            return "".join(part.get("text", "") for part in message if isinstance(part, dict)).strip()
        return str(message).strip()


def _build_provider_candidates() -> list[AIProvider]:
    settings = get_ai_settings()
    preferred = (settings.provider or "groq").lower()

    candidates: list[AIProvider] = []
    has_openai = bool(settings.openai_api_key or settings.openai_base_url)
    has_gemini = _has_gemini_configured(settings)

    if preferred in {"groq", "openai", "openai_compatible", "auto"} and has_openai:
        candidates.append(OpenAICompatibleProvider())
    if preferred in {"gemini"} and has_gemini:
        candidates.append(GeminiProvider())

    if preferred == "auto":
        if has_gemini and not any(isinstance(c, GeminiProvider) for c in candidates):
            candidates.append(GeminiProvider())
        if has_openai and not any(isinstance(c, OpenAICompatibleProvider) for c in candidates):
            candidates.append(OpenAICompatibleProvider())

    if not candidates and has_gemini:
        candidates.append(GeminiProvider())
    if not candidates and has_openai:
        candidates.append(OpenAICompatibleProvider())

    # Fallback to secondary provider if available
    if has_gemini and not any(isinstance(c, GeminiProvider) for c in candidates):
        candidates.append(GeminiProvider())
    if has_openai and not any(isinstance(c, OpenAICompatibleProvider) for c in candidates):
        candidates.append(OpenAICompatibleProvider())

    return candidates


def get_provider() -> AIProvider:
    candidates = _build_provider_candidates()
    if not candidates:
        return GeminiProvider()
    if len(candidates) == 1:
        return candidates[0]
    return FallbackProvider(candidates)


def get_code_generation_provider() -> AIProvider:
    """Return the dedicated code-generation provider when configured."""
    settings = get_ai_settings()
    provider = settings.code_generation_provider

    if provider in {"", "default"}:
        return get_provider()
    if provider == "gemini":
        if not _has_gemini_configured(settings):
            raise RuntimeError(
                "Set GEMINI_API_KEY in the project .env file to enable "
                "Gemini code generation."
            )
        gemini_provider = GeminiProvider(model=settings.gemini_model)
        has_openai = bool(
            getattr(settings, "openai_api_key", "")
            or (getattr(settings, "openai_base_url", "") and getattr(settings, "provider", "") in {"groq", "openai", "openai_compatible"})
        )
        if has_openai:
            return FallbackProvider([gemini_provider, OpenAICompatibleProvider()])
        return gemini_provider
    if provider in {"groq", "openai", "openai_compatible"}:
        if provider == settings.provider:
            return get_provider()
        raise RuntimeError(
            f"CODE_GENERATION_PROVIDER is '{provider}', but the configured "
            f"AI_PROVIDER is '{settings.provider}'. Set matching provider "
            "settings or use CODE_GENERATION_PROVIDER=gemini."
        )
    raise ValueError(
        "CODE_GENERATION_PROVIDER must be 'default', 'gemini', 'groq', "
        "'openai', or 'openai_compatible'."
    )
