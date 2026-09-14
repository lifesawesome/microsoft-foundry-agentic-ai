import os

from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

# Load environment variables from .env file for local development
load_dotenv()


def create_agent() -> Agent:
    """Create and return an Agent using the Foundry hosting pattern."""
    assert "FOUNDRY_PROJECT_ENDPOINT" in os.environ, (
        "FOUNDRY_PROJECT_ENDPOINT environment variable must be set."
    )
    assert "AZURE_AI_MODEL_DEPLOYMENT_NAME" in os.environ, (
        "AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable must be set."
    )

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions=(
            "You are a helpful assistant that can search the web for current information. "
            "Use available tools to find up-to-date information and provide accurate, "
            "well-sourced answers. Always cite your sources when possible."
        ),
        default_options={"store": False},
    )
    return agent


if __name__ == "__main__":
    agent = create_agent()
    server = ResponsesHostServer(agent)
    server.run()
