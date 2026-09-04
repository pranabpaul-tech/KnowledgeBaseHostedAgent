# Knowledge Base Hosted Agent

An [Agent Framework](https://github.com/microsoft/agent-framework) agent grounded in an
existing **Foundry IQ Knowledge Base** backed by Azure AI Search, deployed as a
**Microsoft Foundry Hosted Agent** using the **Responses protocol**.

Unlike a hosted *tool* (which the model must decide to call), this agent uses
`AzureAISearchContextProvider` in **agentic mode** as a context provider: it runs
multi-hop retrieval over the Knowledge Base automatically before every model
invocation and injects the results into context, then the model answers and cites
sources.

- Knowledge Base: `<KNOWLEDGE_BASE_NAME>` on the `<AZURE_SEARCH_SERVICE_NAME>` Azure AI
  Search service (its knowledge source is `azureBlob`-backed, not a plain index — see
  [Known issue / patch](#known-issue--patch) below)
- Foundry project: `<FOUNDRY_PROJECT_NAME>` (on `<FOUNDRY_ACCOUNT_NAME>`), model deployment `gpt-4.1`
- Auth: keyless, via `DefaultAzureCredential` everywhere (no API keys in this project)

See [main.py](main.py) for the implementation.

> **Identifiers masked in this repo**: the Foundry tenant ID, Foundry project name, and
> Knowledge Base/knowledge-source names in this README and in `azure.yaml` are replaced
> with `<PLACEHOLDER>` tokens. Real values live only in the local, gitignored `.env` /
> `.azure/` files — never committed. To actually run or deploy this project, fill those
> placeholders (and `.env`, from `.env.example`) with your own tenant/project/Knowledge
> Base identifiers.

## Status: deployed and working

- **Live endpoint**: `https://<FOUNDRY_ACCOUNT_NAME>.services.ai.azure.com/api/projects/<FOUNDRY_PROJECT_NAME>/agents/agent-framework-agent-knowledge-base-responses/endpoint/protocols/openai/responses?api-version=v1`
- **Playground**: `https://ai.azure.com/nextgen/r/8m2XfUpORbO0qGjSaMRIUg,<AZURE_RESOURCE_GROUP>,,<FOUNDRY_ACCOUNT_NAME>,<FOUNDRY_PROJECT_NAME>/build/agents/agent-framework-agent-knowledge-base-responses/build`
- Deployed via `azd deploy` as agent version 2, verified end-to-end with a live query
  returning `"status":"completed"` and a grounded, cited answer.

## Known issue / patch

`agent_framework_azure_ai_search`'s `AzureAISearchContextProvider` (agentic mode)
hardcodes `SearchIndexKnowledgeSourceParams` for every knowledge source in a Knowledge
Base, regardless of that source's actual `kind`. This Knowledge Base's source is
`azureBlob`-kind, so the unpatched library fails with:

```
(InvalidRequestParameter) Knowledge source params kind 'searchIndex' does not match
the kind 'azureBlob' of knowledge source '<KNOWLEDGE_SOURCE_NAME>'.
```

[`knowledge_source_patch.py`](knowledge_source_patch.py) works around this: it resolves
each knowledge source's real `kind` via `SearchIndexClient.get_knowledge_source()`, then
builds the matching `KnowledgeSourceParams` subclass using the SDK's own discriminator
registry (`KnowledgeSourceParams.__mapping__`) instead of the hardcoded search-index
variant. `main.py` applies it (`knowledge_source_patch.apply()`) before constructing the
provider. Remove this once the upstream library fixes the kind mismatch — feedback has
been filed against `agent-framework-azure-ai-search`.

## Prerequisites

- Azure CLI, logged in: `az login`
- Azure Developer CLI (`azd`) 1.33.0+ and the `azure.ai.agents` extension (`1.0.0-beta.13`+):
  ```bash
  winget upgrade Microsoft.Azd
  azd extension upgrade azure.ai.agents
  azd auth login --tenant-id <AZURE_TENANT_ID>
  ```
  `azd auth login` is a **separate** login from `az login` and can end up on a different
  account/tenant — if `azd ai agent` commands fail with a subscription/tenant lookup
  error, re-run `azd auth login --tenant-id <tenant>` explicitly.
- **RBAC**: both your user account and the deployed agent's Managed Identity need, on
  `<AZURE_SEARCH_SERVICE_NAME>`:
  - `Search Index Data Reader` (document-level query access)
  - `Search Service Contributor` (needed to read the Knowledge Base/knowledge-source
    *definitions* — there's no narrower built-in role for that read in Azure AI Search's
    RBAC model; this matches the role set already granted to the Foundry project's own
    identity)
- If you're behind a corporate network that blocks direct `pip`/`uv` access to
  `files.pythonhosted.org` (TLS handshake failures), route through your internal package
  feed proxy — this project's [Dockerfile](Dockerfile) already does this via
  `--index-url https://packagefeedproxy.microsoft.io/pypi/simple/`. Adjust or remove that
  flag if you're not on this network.
- Git Bash on Windows: prefix `azd` commands that take a `/subscriptions/...` resource ID
  with `MSYS_NO_PATHCONV=1` — otherwise Git Bash silently rewrites the leading `/` into a
  Windows path (e.g. `C:/Program Files/Git/subscriptions/...`) and `azd` rejects it.

## Running locally (plain Python, fastest to verify)

```bash
uv venv .venv
uv pip install --pre --index-url https://packagefeedproxy.microsoft.io/pypi/simple/ -r requirements.txt
.venv\Scripts\python main.py
```

The agent host starts on `http://localhost:8088`. In another terminal:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d "{\"input\": \"Can customer get refund if the delivery is returned due to wrong address?\"}"
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Can customer get refund if the delivery is returned due to wrong address?"}').Content
```

## Project layout

This is a real `azd` project (`azd ai agent init` was run against it, targeting the
existing Foundry project via `--project-id`) — `azure.yaml` and `infra/` are
azd-generated, not hand-authored:

- `main.py` — the agent
- `knowledge_source_patch.py` — the workaround described above
- `requirements.txt`, `Dockerfile`, `.dockerignore`
- `azure.yaml` — azd project/service definition (services: the Foundry project
  connection `foundry-project` (Foundry project name masked — see `azure.yaml`), and the
  hosted agent `agent-framework-agent-knowledge-base-responses`)
- `infra/` — generated Bicep (`azd ai agent init --infra`): container registry + Foundry
  project wiring
- `.env` / `.env.example` — local-run configuration

## Running locally via `azd`

```bash
azd ai agent run
azd ai agent invoke --local "Can customer get refund if the delivery is returned due to wrong address?"
```

## Deploying to Foundry

```bash
azd provision   # only needed once, to create the ACR (already done for this project)
azd deploy
```

This builds the container, pushes it to the project's Azure Container Registry
(`<AZURE_CONTAINER_REGISTRY_NAME>` was already present in `<AZURE_RESOURCE_GROUP>`, but `azd ai agent init --infra`
provisions its own dedicated one rather than reusing an existing registry), and deploys
a new agent version. The platform injects `FOUNDRY_PROJECT_ENDPOINT`,
`AZURE_AI_MODEL_DEPLOYMENT_NAME`, and `APPLICATIONINSIGHTS_CONNECTION_STRING`
automatically; `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` are set
directly in `azure.yaml`'s `env:` block for this service.

After deploying, check status and logs:

```bash
azd ai agent show agent-framework-agent-knowledge-base-responses
azd ai agent monitor
```

The deployed agent's Managed Identity needs the RBAC roles listed under
[Prerequisites](#prerequisites) on `<AZURE_SEARCH_SERVICE_NAME>` — grant them once per new
agent version's identity if `azd ai agent show` reports a new `Instance Identity
Principal ID`.
