"""Live end-to-end smoke test.

Runs one full orchestrator turn against the configured Foundry model and knowledge base,
printing the streamed event types and the assembled answer. Requires a valid .env and
`az login`. Not part of the automated test suite.
"""

from __future__ import annotations

import asyncio

from agent_platform.config import load_settings
from agent_platform.runtime.bootstrap import build_platform


async def _run() -> int:
    settings = load_settings()
    platform = build_platform(settings)
    orchestrator = platform.orchestrator
    sessions = orchestrator._sessions  # noqa: SLF001 - shared store from bootstrap
    try:
        session = await sessions.create("smoke-user", "rest")
        text_parts: list[str] = []
        types: list[str] = []
        citations: list[str] = []
        async for event in orchestrator.run(
            text="How does the platform ground answers and cite sources?",
            session=session,
        ):
            types.append(event.type.value)
            if event.text:
                text_parts.append(event.text)
            for citation in event.citations:
                citations.append(citation.source_id)
            if event.error:
                print("ERROR:", event.error.code.value, "-", event.error.message)

        answer = "".join(text_parts).strip()
        print("event types:", types)
        print("citations:", citations)
        print("answer:", answer[:600])
        ok = "completed" in types and bool(answer)
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        platform.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
