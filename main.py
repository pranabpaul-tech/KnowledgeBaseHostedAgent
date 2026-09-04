# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

import knowledge_source_patch

# Load environment variables from .env file
load_dotenv()

# Work around a kind-mismatch bug in AzureAISearchContextProvider's agentic mode
# for Knowledge Bases whose knowledge source is not searchIndex-kind (e.g. azureBlob).
# See knowledge_source_patch.py for details; remove once fixed upstream.
knowledge_source_patch.apply()


async def main():
    credential = DefaultAzureCredential()

    # Ground the agent in the existing Foundry IQ Knowledge Base. Agentic mode runs
    # multi-hop query planning over the indexed documents before each model
    # invocation and injects the retrieved context automatically -- this is the
    # "knowledge" integration, not a model-invoked function/hosted tool.
    search_provider = AzureAISearchContextProvider(
        source_id="foundry_knowledge_base",
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        credential=credential,
        mode="agentic",
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE_NAME"],
        knowledge_base_output_mode="extractive_data",
        retrieval_reasoning_effort="minimal",
    )

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    async with search_provider:
        agent = Agent(
            client=client,
            instructions=(
                "You are a helpful assistant. Ground every answer in the connected "
                "knowledge base and cite sources when available. If nothing relevant "
                "is found, say you don't know rather than guessing."
            ),
            context_providers=[search_provider],
            # History is managed by the hosting infrastructure, so there is no need
            # to store history via the service. Learn more at:
            # https://developers.openai.com/api/reference/resources/responses/methods/create
            default_options={"store": False},
        )
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
