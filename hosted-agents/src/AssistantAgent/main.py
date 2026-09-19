# Copyright (c) Microsoft. All rights reserved.
"""Contoso Assistant — a hosted Microsoft Foundry agent that demonstrates tool calling.

The model decides when to call the local Python functions below, grounding its
answers in live/deterministic data instead of guessing. Everything here is
self-contained: no Bing, no external APIs, no extra Azure connections — so it
runs and demos identically on a laptop and in Foundry.
"""

import os
from datetime import datetime
from random import Random
from zoneinfo import ZoneInfo

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import Field
from typing_extensions import Annotated

# Load FOUNDRY_PROJECT_ENDPOINT / AZURE_AI_MODEL_DEPLOYMENT_NAME from .env when running locally.
load_dotenv()

# Small in-memory catalog so the agent can ground answers in "company data".
_PRODUCT_CATALOG = {
    "contoso laptop 14": {"price_usd": 1299, "in_stock": 42},
    "contoso laptop 16": {"price_usd": 1699, "in_stock": 12},
    "contoso mouse": {"price_usd": 39, "in_stock": 350},
    "contoso keyboard": {"price_usd": 89, "in_stock": 120},
    "contoso monitor 27": {"price_usd": 429, "in_stock": 0},
}


@tool(approval_mode="never_require", description="Get the current weather for a city.")
def get_weather(
    location: Annotated[str, Field(description="City name, e.g. 'Seattle'.")],
) -> str:
    """Return a short weather report for the location (demo data)."""
    # Seed by location so the same city always reports the same weather during a demo.
    rng = Random(location.lower())
    condition = rng.choice(["sunny", "cloudy", "rainy", "windy"])
    return f"The weather in {location} is {condition} with a high of {rng.randint(8, 32)}°C."


@tool(approval_mode="never_require", description="Get the current date and time in an IANA timezone.")
def get_current_time(
    timezone: Annotated[
        str, Field(description="IANA timezone, e.g. 'America/Los_Angeles' or 'UTC'.")
    ] = "UTC",
) -> str:
    """Return the current date and time for the given IANA timezone."""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return f"Unknown timezone '{timezone}'. Try an IANA name like 'UTC' or 'Europe/London'."
    return datetime.now(tz).strftime("%A, %d %B %Y %H:%M ") + timezone


@tool(approval_mode="never_require", description="Look up a Contoso product's price and stock.")
def search_product_catalog(
    query: Annotated[str, Field(description="Product name to search for, e.g. 'laptop'.")],
) -> str:
    """Search the demo product catalog and return matching items with price and stock."""
    q = query.lower().strip()
    matches = {name: info for name, info in _PRODUCT_CATALOG.items() if q in name}
    if not matches:
        return f"No products matched '{query}'. Try 'laptop', 'mouse', 'keyboard', or 'monitor'."
    lines = []
    for name, info in matches.items():
        stock = f"{info['in_stock']} in stock" if info["in_stock"] else "out of stock"
        lines.append(f"- {name.title()}: ${info['price_usd']} ({stock})")
    return "\n".join(lines)


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions=(
            "You are Contoso Assistant, a concise and friendly helper. "
            "Use the tools to answer with real data instead of guessing: call "
            "get_weather for weather, get_current_time for the current time, and "
            "search_product_catalog for Contoso product price and stock. "
            "Base your answer on the tool result and mention the key figures."
        ),
        tools=[get_weather, get_current_time, search_product_catalog],
        # The hosting runtime manages conversation history, so don't store it server-side.
        default_options={"store": False},
    )

    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()
