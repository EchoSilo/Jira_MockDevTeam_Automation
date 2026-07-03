# Jira GraphQL Explorer

Small prototype for poking at Jira's (largely undocumented) GraphQL endpoints
with the credentials already configured in this repo's `.env`.

## What it does

- **Probes multiple candidate endpoints** and tells you which actually respond:
  - `{JIRA_URL}/gateway/api/graphql` (Cloud internal gateway — primary target)
  - `{JIRA_URL}/gateway/api/jira/graphql`
  - `{JIRA_URL}/jsw/graphql` (Jira Software)
  - `{JIRA_URL}/rest/graphql/1/` (legacy Server/DC)
  - `https://api.atlassian.com/graphql` (public, OAuth-only — included for contrast)
- **Serves a GraphiQL playground** with schema introspection, autocomplete, docs panel.
- **Proxies queries** through the backend so your `JIRA_API_TOKEN` never reaches the browser.

## Run

```bash
pip install -r graphql_explorer/requirements.txt
python -m uvicorn graphql_explorer.app:app --reload --port 8765
```

Open <http://localhost:8765/>.

## Exploration flow

1. Click **Probe all endpoints** — note which return `graphql-working`.
2. Select that endpoint from the dropdown.
3. Run the default introspection query (`{ __schema { queryType { name } types { name kind } } }`).
4. From there, drill into specific types (e.g. `Jira`, `JiraIssue`, `JiraProject`) — Cloud's
   gateway exposes a federated schema spanning Jira, Confluence, and Compass.

## Notes / caveats

- The `/gateway/api/graphql` endpoint is **internal and unsupported**. Atlassian can change or
  remove it without warning. Treat anything you learn here as a research finding, not a stable contract.
- Some queries on the gateway require additional headers (`X-ExperimentalApi: opt-in` is sent by default).
- The public `api.atlassian.com/graphql` endpoint will reject Basic auth — it needs OAuth 2.0
  3LO with the right scopes. Listed here only so you can see the auth boundary.
- Rate limits apply. Don't loop introspection.
