# IvyGPT

FastAPI chat application with LangGraph tools, long-term memory, document upload, and RAG search.

## Project Structure

```text
.
|-- app.py                  # Compatibility entrypoint: uvicorn app:app
|-- ivy_gpt/
|   |-- main.py             # App setup, CORS, lifespan, router registration
|   |-- config.py           # Shared project paths and runtime directories
|   |-- core/
|   |   `-- agent.py        # LangGraph agent setup
|   |-- db/
|   |   |-- crud.py         # Async database operations
|   |   |-- models.py       # SQLAlchemy models
|   |   `-- session.py      # Async engine, session dependency, startup init
|   |-- routes/
|   |   |-- auth.py         # OAuth, email OTP, token, and current-user endpoints
|   |   |-- chat.py         # Chat streaming endpoint
|   |   |-- conversations.py # Conversation and history endpoints
|   |   |-- home.py         # Frontend page endpoint
|   |   `-- uploads.py      # Document upload endpoint
|   |-- schemas/
|   |   `-- responses.py    # Pydantic route response schemas
|   |-- services/
|   |   |-- auth.py         # JWT, Redis OTP, and auth dependencies
|   |   |-- email_tasks.py  # Celery email tasks
|   |   |-- rag.py          # Document ingestion and vector search
|   |   `-- tools.py        # LangChain tools
|   `-- templates/
|       `-- index.html      # Frontend template
|-- pyproject.toml
`-- uv.lock
```

## Run

Create a local `.env` from the example and fill in provider keys:

```powershell
Copy-Item .env.example .env
```

Start the full stack:

```powershell
docker compose up --build
```

This starts:

- FastAPI app on `http://localhost:8080`
- PostgreSQL on port `5432`
- Redis on port `6379`
- Celery worker for OTP emails

The app container runs Alembic migrations automatically on startup.

To run the app directly on your host instead:

```powershell
docker run --name ivygpt-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ivygpt -p 5432:5432 postgres:16
docker run --name ivygpt-redis -p 6379:6379 redis:7
alembic upgrade head
uvicorn app:app --reload --host 0.0.0.0 --port 8080
```

## Settings

Configuration is loaded through `ivy_gpt.config.Settings` from environment variables and `.env`.

Supported values include:

- `DATABASE_URL`
- `GOOGLE_API_KEY` for embeddings
- `OPENROUTER_API_KEY` for chat
- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL`
- `TAVILY_API_KEY`
- `CORS_ALLOW_ORIGINS`
- `APP_BASE_URL`
- `REDIS_URL`
- `JWT_SECRET_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_FROM_NAME`
- `SMTP_USE_SSL`
- `SMTP_USE_TLS`
- `MCP_CONFIG_PATH`

Example local Postgres URL:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ivygpt
```

## Auth Setup

Authentication supports Google OAuth and email OTP.

Run the Celery worker that sends OTP emails:

```powershell
celery -A ivy_gpt.services.email_tasks.celery_app worker --loglevel=info --pool=solo
```

When using Docker Compose, this worker is already started as the `worker` service.

If SMTP settings are not configured, OTP codes are printed by the Celery worker for local development.

For Google OAuth, set the callback URL in Google Cloud to:

```text
http://localhost:8080/auth/google/callback
```

## Agent Memory

LangGraph checkpoints now use PostgreSQL through `AsyncPostgresSaver`.
The checkpoint tables are created automatically when the first agent is built.

## Agent Tools

The agent includes tools for:

- Calculator
- Uploaded document search through Chroma RAG
- Tavily current web search
- DuckDuckGo fallback web search
- Wikipedia background search
- arXiv research-paper search
- PubMed biomedical literature search
- Long-term memory save and recall
- User-configured MCP tools from `mcp_servers.json`

## MCP Tools

Add MCP servers in `mcp_servers.json`. Streamable HTTP is the primary transport. Keep stdio entries disabled unless you need them as a local backup.

From the frontend MCP dialog, adding a server connects to that MCP server immediately, discovers its tools, and saves the server plus discovered tool metadata for your account. The agent cache is cleared after add/delete, so the next chat request rebuilds the agent with all enabled MCP servers and their live tools.

Example:

```json
{
  "servers": {
    "data_fetch_mcp_http": {
      "enabled": true,
      "transport": "streamable-http",
      "url": "http://localhost:8050/mcp",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    },
    "data_fetch_mcp_stdio_backup": {
      "enabled": false,
      "transport": "stdio",
      "command": "{venv_python}",
      "args": [
        "{project_root}/CH-1_CreateMCP/1_first_mcpserver_stdio.py"
      ]
    }
  }
}
```

Supported placeholders:

- `{project_root}`: this project directory
- `{venv_python}`: the Python executable running IvyGPT

Recommended MCP transports:

- `streamable-http` as the primary transport
- `stdio` as a disabled backup option

The loader still accepts legacy aliases such as `httpstreams`, `httpstream`, and `streamable_http`, but new configs should use `streamable-http`.

When running in Docker, stdio MCP server paths must exist inside the container. HTTP MCP servers must be reachable from inside the container.
For authenticated HTTP MCP servers, add headers in the `headers` object. Headers are passed to `MultiServerMCPClient` with the server config.
