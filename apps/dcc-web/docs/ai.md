# AI configuration assistant

AI assistant is separate from MCP. It prepares Docker configurations and improves existing commands; MCP exposes granted read tools to an external client. Neither grants unrestricted Docker access.

An administrator configures AI assistant → AI connection: provider, API base URL, model, optional key and enable switch.

| Provider | Base URL example | Requests |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Responses API, `store:false` |
| OpenAI-compatible | `http://127.0.0.1:1234/v1` or external HTTPS endpoint | `/chat/completions`, `/models` |
| Ollama | `http://127.0.0.1:11434` | `/api/generate` with non-streaming JSON, `/api/tags` |

Enter a model name or fetch the configured server's model list. DCC does not launch models, Ollama instances or execution workers. The model server must already be running. Inside a Web container, localhost identifies that container; use an explicit LAN address or `host.docker.internal` where supported to reach the host. Local/LAN access requires consent. Public services should use HTTPS; redirects are rejected.

The API key is encrypted using the state vault and excluded from public configuration/exports. A blank key retains the previous value only for the same provider and endpoint. Changing either clears the retained key to prevent forwarding another provider's credential. An unauthenticated local server needs no key.

## Propose, review, apply

The assistant appears in its own view, new-container/store configuration and the existing-container editor. Enter a request or existing Docker command. Optional context includes architecture, RAM and occupied Docker ports. Common secret environment fields are masked. Arbitrary free text can contain sensitive material; review what you submit externally. Each explicit generation click sends a request; external providers may charge for usage.

The backend validates a structured proposal through the normal installation planner. Apply proposal to form changes the form only. Installation/recreation still requires permissions, preview and confirmation. Model text is never executed on the host. At most two generation requests run concurrently. Image changes for existing containers remain a separate update operation.

Automatic selection resolves occupied Docker ports and shows changes in the preview. The final configuration locks chosen ports; Docker remains authoritative if another process claims one later. Editing excludes the container's own name/ports from collision checks. The existing safe Updater preserves mounts and data.

Provider adapters and key handling have mocked tests; browser QA uses a synthetic model. No paid API call or real model generation was performed in automated acceptance. Test your chosen model after entering its credentials in the panel. References: [OpenAI Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses), [Chat Completions](https://platform.openai.com/docs/api-reference/chat/create), [Ollama generate](https://docs.ollama.com/api/generate).
