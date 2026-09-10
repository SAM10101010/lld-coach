"""Thin LLM client wrapper with timeout + strict JSON parsing.

Works with OpenAI directly and with any OpenAI-compatible endpoint
(OpenRouter). The LLM is never the source of truth for deterministic facts
(missing sections, keyword coverage). It only judges quality, trade-offs,
and explanations. Any transport/parse failure raises EvaluatorError so the
caller can mark the attempt FAILED while preserving the submission.
"""
import json
import re

from ..domain.evaluator import EvaluatorError


def _balanced_json_around(text: str, anchor: str) -> dict | None:
    """Find a balanced {...} object containing `anchor` (handles prose around JSON)."""
    i = text.find(anchor)
    if i == -1:
        return None
    start = text.rfind("{", 0, i)
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for j in range(start, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(text[start : j + 1])
                            if isinstance(data, dict):
                                return data
                        except Exception:
                            pass
                        break
        start = text.rfind("{", 0, start)
    return None


def _extract_json(content: str) -> dict:
    """Parse model output robustly: plain JSON or fenced ```json blocks.

    Some OpenRouter free models ignore response_format and wrap JSON in
    markdown fences or add prose. We extract the first {...} block.
    """
    text = (content or "").strip()
    if not text:
        raise EvaluatorError("AI returned empty response")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # strip markdown fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            data = json.loads(fenced.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # first balanced-ish {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # reasoning models often bury the answer after thinking: anchor on schema key
    anchored = _balanced_json_around(text, '"overallScore"')
    if anchored is not None:
        return anchored
    raise EvaluatorError(f"AI returned invalid JSON: {text[:300]!r}")


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    timeout_s: int,
    base_url: str | None = None,
    extra_headers: dict | None = None,
    max_tokens: int = 4000,
) -> dict:
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - import guard
        raise EvaluatorError(f"openai package unavailable: {exc}") from exc

    kwargs: dict = {"api_key": api_key, "timeout": timeout_s}
    if base_url:
        kwargs["base_url"] = base_url
        # Reasoning-style free models narrate thinking into the content
        # channel; forbid that so the JSON contract survives.
        user_prompt = (
            user_prompt
            + "\n\nIMPORTANT: Output ONLY the JSON object. Do not narrate your thinking process, "
              "do not add headings, do not wrap in markdown."
        )
    # OpenRouter recommends identifying headers; harmless for OpenAI.
    headers = dict(extra_headers or {})
    client = OpenAI(**kwargs)
    try:
        create_kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if headers:
            create_kwargs["extra_headers"] = headers
        # Prefer strict JSON mode; some OpenRouter free models reject it,
        # so retry without it on failure.
        try:
            resp = client.chat.completions.create(
                **create_kwargs, response_format={"type": "json_object"}
            )
        except Exception as first_exc:
            if base_url and "response_format" in str(first_exc).lower():
                resp = client.chat.completions.create(**create_kwargs)
            else:
                raise
    except EvaluatorError:
        raise
    except Exception as exc:
        raise EvaluatorError(f"AI request failed: {exc}") from exc

    try:
        content = resp.choices[0].message.content or ""
        return _extract_json(content)
    except EvaluatorError:
        raise
    except Exception as exc:
        raise EvaluatorError(f"AI returned invalid JSON: {exc}") from exc


def call_openai_json(system_prompt: str, user_prompt: str, model: str, api_key: str, timeout_s: int) -> dict:
    return call_llm_json(system_prompt, user_prompt, model, api_key, timeout_s)
