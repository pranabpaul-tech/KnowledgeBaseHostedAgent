# Copyright (c) Microsoft. All rights reserved.
"""Workaround for a kind-mismatch bug in AzureAISearchContextProvider's agentic mode.

`agent_framework_azure_ai_search._context_provider.AzureAISearchContextProvider._agentic_search`
always builds `SearchIndexKnowledgeSourceParams` for every knowledge source in the
Knowledge Base, regardless of that source's actual `kind`. Azure AI Search rejects the
retrieval request when a knowledge source is backed by anything other than a search
index (e.g. `azureBlob`), with:

    (InvalidRequestParameter) Knowledge source params kind 'searchIndex' does not
    match the kind '<actual kind>' of knowledge source '<name>'.

This patches the provider to resolve each knowledge source's real `kind` via
`SearchIndexClient.get_knowledge_source()`, then builds the matching
`KnowledgeSourceParams` subclass using the SDK's own discriminator registry
(`KnowledgeSourceParams.__mapping__`, populated automatically for every subclass
declared with `discriminator=` in `azure.search.documents.knowledgebases.models`)
instead of hardcoding the search-index variant.

Remove this once upstream fixes the kind mismatch (feedback filed against
agent-framework-azure-ai-search).
"""

from __future__ import annotations

import agent_framework_azure_ai_search._context_provider as _provider_module
from azure.search.documents.knowledgebases.models import (
    KnowledgeSourceParams,
    SearchIndexKnowledgeSourceParams,
)

_kind_by_source_name: dict[str, str] = {}

_original_ensure_knowledge_base = _provider_module.AzureAISearchContextProvider._ensure_knowledge_base


async def _ensure_knowledge_base_with_kind_resolution(self) -> None:
    await _original_ensure_knowledge_base(self)
    if self._index_client is None or not self._knowledge_source_names:
        return
    for name in self._knowledge_source_names:
        if name in _kind_by_source_name:
            continue
        source = await self._index_client.get_knowledge_source(name)
        _kind_by_source_name[name] = source.kind


def _kind_aware_knowledge_source_params(
    *, knowledge_source_name: str, include_reference_source_data: bool = True, **kwargs
):
    kind = _kind_by_source_name.get(knowledge_source_name)
    params_cls = KnowledgeSourceParams.__mapping__.get(kind, SearchIndexKnowledgeSourceParams)
    return params_cls(
        knowledge_source_name=knowledge_source_name,
        include_reference_source_data=include_reference_source_data,
        **kwargs,
    )


def apply() -> None:
    """Idempotently patch AzureAISearchContextProvider's agentic-mode kind handling."""
    provider_cls = _provider_module.AzureAISearchContextProvider
    if getattr(provider_cls, "_kb_kind_patch_applied", False):
        return
    provider_cls._ensure_knowledge_base = _ensure_knowledge_base_with_kind_resolution
    _provider_module.SearchIndexKnowledgeSourceParams = _kind_aware_knowledge_source_params
    provider_cls._kb_kind_patch_applied = True
