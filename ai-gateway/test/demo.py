"""Interactive demo for the Foundry AI Gateway.

Demonstrates three AI Gateway capabilities against the deployed Azure API
Management instance:

  1. Semantic caching  - a semantically similar prompt is served from cache.
  2. Token metrics     - per-response prompt/completion/total token headers.
  3. Token limiting     - repeated calls eventually return HTTP 429.

Reads AI_GATEWAY_URL and AI_GATEWAY_KEY from ai-gateway/.env (written by
deploy.ps1) or from the environment.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CHAT_DEPLOYMENT = os.getenv("AI_GATEWAY_CHAT_DEPLOYMENT", "gpt-4o")
API_VERSION = os.getenv("AI_GATEWAY_API_VERSION", "2024-10-21")

# Fresh cache partition per run so the demo is repeatable (the gateway policy
# adds x-cache-bucket to its semantic-cache vary-by).
RUN_BUCKET = uuid.uuid4().hex[:12]

_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        pool_connections=32,
        pool_maxsize=32,
        max_retries=Retry(
            total=2,
            connect=2,
            read=0,
            backoff_factor=0.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            raise_on_status=False,
        ),
    ),
)


def load_env() -> tuple[str, str]:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    url = os.environ.get("AI_GATEWAY_URL")
    key = os.environ.get("AI_GATEWAY_KEY")
    if not url or not key:
        raise SystemExit(
            "Missing AI_GATEWAY_URL / AI_GATEWAY_KEY. Run deploy.ps1 first "
            "or set them in the environment."
        )
    return url.rstrip("/"), key


def chat(url: str, key: str, prompt: str, max_tokens: int = 120) -> requests.Response:
    endpoint = f"{url}/openai/deployments/{CHAT_DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    return _session.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "api-key": key,
            "x-cache-bucket": RUN_BUCKET,
        },
        json={
            "messages": [
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
        timeout=(10, 120),
    )


def call_and_report(url: str, key: str, prompt: str, label: str) -> None:
    t0 = time.perf_counter()
    resp = chat(url, key, prompt)
    dt = time.perf_counter() - t0
    # A cache HIT short-circuits before the token-limit policy, so the header is absent.
    is_hit = "x-tokens-remaining" not in resp.headers
    verdict = "CACHE HIT" if is_hit else "cache miss (backend call)"
    answer = resp.json()["choices"][0]["message"]["content"] if resp.ok else resp.text[:120]
    print(f"\n--- {label} ---")
    print(f"HTTP {resp.status_code} | {verdict} | latency {dt:.2f}s")
    print(f"answer: {answer[:150]}")


def demo_semantic_cache(url: str, key: str) -> None:
    print("\n========== 1. SEMANTIC CACHING ==========")
    fact = "In one sentence, what is the tallest mountain on Earth?"
    identical = fact  # exact repeat -> guaranteed cache hit
    reworded = "In a single sentence, what is the tallest mountain on Earth?"
    unrelated = "In one sentence, who painted the Mona Lisa?"

    call_and_report(url, key, fact, "First call (expect miss)")
    time.sleep(3)  # let the cache-store settle
    call_and_report(url, key, identical, "Identical prompt (expect CACHE HIT)")
    call_and_report(url, key, reworded, "Reworded, same meaning (expect CACHE HIT)")
    call_and_report(url, key, unrelated, "Unrelated prompt (expect miss)")


# Genuinely distinct topics so each call is a cache miss and burns tokens.
_TOPICS = [
    "the history of the Roman aqueducts",
    "how photosynthesis works in plants",
    "the rules of the game of cricket",
    "the origins of jazz music in New Orleans",
    "how a lithium-ion battery stores energy",
    "the migration patterns of monarch butterflies",
    "the architecture of Gothic cathedrals",
    "how sourdough bread fermentation works",
    "the discovery of penicillin",
    "the physics of how airplanes generate lift",
    "the cultural significance of the Japanese tea ceremony",
    "how coral reefs form over time",
    "the invention of the printing press",
    "the water cycle and cloud formation",
    "the strategy behind a game of chess",
]


def demo_token_limit(url: str, key: str, max_calls: int = 12) -> None:
    print("\n========== 2 & 3. TOKEN METERING + TOKEN QUOTA (403) ==========")
    print("Each call meters tokens (consumed / per-minute remaining). A hard cumulative")
    print("token quota (1500) enforces a deterministic 403 once the budget is spent.")
    for i, topic in enumerate(_TOPICS[:max_calls], start=1):
        nonce = uuid.uuid4().hex[:8]
        prompt = f"[{nonce}] Write a detailed paragraph about {topic}."
        try:
            resp = chat(url, key, prompt, max_tokens=256)
        except requests.RequestException as exc:
            print(f"call {i:>2}: request failed ({exc.__class__.__name__}); continuing")
            continue
        consumed = resp.headers.get("x-tokens-consumed", "n/a")
        tpm_left = resp.headers.get("x-tokens-remaining", "n/a")
        quota_left = resp.headers.get("x-quota-remaining", "n/a")
        print(
            f"call {i:>2}: HTTP {resp.status_code}  consumed={consumed}  "
            f"tpm_remaining={tpm_left}  quota_remaining={quota_left}"
        )
        if resp.status_code == 403:
            print("  -> Hard token quota exhausted (403). Budget resets at the top of the hour.")
            break
        time.sleep(0.3)
    else:
        print("  (quota not reached; lower token-quota in the policy or add topics)")


def main() -> None:
    url, key = load_env()
    print(f"Gateway: {url}")
    demo_semantic_cache(url, key)
    demo_token_limit(url, key)
    print("\nDone. View token metrics in APIM > Monitoring > Metrics (namespace 'ai-gateway').")


if __name__ == "__main__":
    main()
