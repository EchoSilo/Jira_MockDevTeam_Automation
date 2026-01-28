# Codebase Concerns

**Analysis Date:** 2026-01-27

## Tech Debt

**Deprecated Scenario System (Legacy Per-Ticket Scenarios):**
- Issue: Old `ActiveScenario` system mixed with new sprint-level scenario architecture creating dual maintenance burden
- Files: `src/state/models.py` (lines 856-928), `src/main.py` (lines 1095-1134), `src/orchestrator/orchestrator.py`
- Impact: Code complexity, potential for state desynchronization between old and new systems, harder to maintain
- Fix approach: Complete migration to sprint-level scenarios in `src/scenarios/sprint_scenario.py`, deprecate all legacy scenario methods in SimulationState

**Unimplemented TODO Conditions in Scenario Planner:**
- Issue: Two TODO items in scenario condition evaluation always return `False` instead of actual logic
- Files: `src/scenarios/scenario_planner.py` (lines 228, 233)
  - `"cross_team_dependencies": lambda a: False,  # TODO: Implement when we have dependency data`
  - `"new_feature_area": lambda a: False,  # TODO: Implement with epic analysis`
- Impact: Sprint scenarios never detect these conditions, limiting scenario variety and realism
- Fix approach: Implement dependency tracking in analyzer and epic/feature detection logic

**Hardcoded BOARD_ID in Multiple Locations:**
- Issue: Sprint board ID hardcoded as `4` in multiple places instead of centralized config
- Files: `src/services/jira_client.py` (line 16), `src/main.py` (line 592)
- Impact: Configuration changes require code edits; won't work if board ID changes
- Fix approach: Move BOARD_ID to `config/settings.yaml`, inject via dependency injection

## Known Bugs

**Sprint Scenario State Desynchronization Risk:**
- Symptoms: Sprint scenario can become out of sync with actual Jira sprint state, especially after sprint transitions
- Files: `src/main.py` (lines 190-203), `src/orchestrator/orchestrator.py` (handle sprint scenario lifecycle)
- Trigger: When sprint rolls over, state must clear and re-inject sprint data; race conditions possible if timing is off
- Workaround: `/reset` endpoint clears all state; sprint scenarios are re-generated on next `/trigger` call

**Incomplete Error Handling in Large File Reads:**
- Symptoms: Frontend may receive partial or truncated Jira data if API calls timeout mid-pagination
- Files: `src/main.py` (lines 591-608 velocity data collection), `src/services/jira_client.py`
- Trigger: When fetching historical velocity from closed sprints, if network is slow or Jira is overloaded
- Workaround: Frontend treats missing data gracefully; dashboard shows partial velocity data

**Release Notes Generation Silent Failures:**
- Symptoms: Release notes may generate with empty or incomplete sections without error
- Files: `src/main.py` (lines 1954-1971), `src/services/llm_service.py`
- Trigger: If LLM returns malformed JSON or empty responses, JSON parsing succeeds but notes are incomplete
- Workaround: User can regenerate with `regenerate: true` flag to force fresh generation

## Security Considerations

**API Key Exposure in Logging:**
- Risk: Jira API tokens and Anthropic keys could be exposed in logs if not carefully filtered
- Files: `src/main.py` (config loading), `src/logging/logged_jira_client.py`, `src/logging/logged_llm_service.py`
- Current mitigation: Logging captures endpoints and parameters but not auth headers; keys stored in `.env` not logged
- Recommendations: Add explicit secret filtering in log queries; audit log endpoints for sensitive data leakage

**CORS Configuration Too Permissive:**
- Risk: Frontend CORS allows multiple localhost ports (5173-5177) but same allow_credentials=True for all
- Files: `src/main.py` (lines 277-294)
- Current mitigation: Only affects localhost development, not production
- Recommendations: In production, restrict to single origin; consider environment-based CORS config

**Missing Input Validation on Chat Endpoint:**
- Risk: PM ID validation exists but user message length unbounded; could cause token overflow in LLM
- Files: `src/main.py` (lines 1374-1477)
- Current mitigation: LLM has max_tokens=300 but no request message length limit
- Recommendations: Add max length validation on ChatRequest.message (e.g., 5000 chars); rate limit chat endpoint

**Environment Variable Dependency Without Defaults:**
- Risk: Missing env vars cause immediate crashes without helpful error messages
- Files: `src/services/jira_client.py` (lines 28-31) - JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN required but no fallback
- Current mitigation: `.env` is required in Docker setup
- Recommendations: Add startup validation with clear error messages for missing required env vars

## Performance Bottlenecks

**Synchronous Jira API Calls in /trigger Endpoint:**
- Problem: Multiple sequential Jira API calls happen in `/trigger` (sprint data, issue fetching, velocity data) blocking other operations
- Files: `src/main.py` (lines 376-456), multiple crew execution calls
- Cause: Sequential crew execution and Jira API polling for state consistency
- Improvement path: Implement async Jira calls; consider caching sprint/issue data with longer TTL; batch API calls

**Full State JSON Serialization on Every GET /state:**
- Problem: `state.model_dump(mode="json")` serializes entire SimulationState including all active scenarios and agent history on every dashboard poll
- Files: `src/main.py` (lines 496-523)
- Cause: No delta updates; same data re-serialized repeatedly
- Improvement path: Implement incremental state snapshots; compress historical data; implement WebSocket for real-time updates instead of 15s polling

**Status Cache TTL Too Long (1 hour):**
- Problem: Workflow status changes in Jira not reflected for up to 1 hour
- Files: `src/services/jira_client.py` (lines 40-41: `_cache_ttl = timedelta(hours=1)`)
- Cause: Cache reuse across many operations
- Improvement path: Reduce to 15-30 minutes; invalidate on agent transitions; consider event-based cache invalidation

**Log Query Performance Not Indexed:**
- Problem: Unbounded queries on logs table without pagination can scan entire database
- Files: `src/logging/query.py` (database queries), `src/logging/api.py` (endpoint handlers)
- Cause: SQLite doesn't auto-index; no query pagination implemented
- Improvement path: Add indexes on (session_id, timestamp, agent_id); implement cursor-based pagination in log queries

## Fragile Areas

**SimulationState Sprint Injection Logic:**
- Files: `src/state/simulation_state.py`, `src/state/models.py`
- Why fragile: Sprint data comes from multiple sources (local cache vs live Jira); reconciliation happens on every tick; edge case if Jira sprint changes mid-tick
- Safe modification: Always call `inject_jira_sprint()` before any sprint-dependent logic; test sprint transition scenarios explicitly
- Test coverage: No dedicated sprint injection tests; state transitions tested only in integration with orchestrator

**Scenario Lifecycle Phase Transitions:**
- Files: `src/state/models.py` (ActiveScenario class), `src/orchestrator/orchestrator.py` (phase advancement logic)
- Why fragile: Phase transitions have minimum/maximum hour requirements; if advancement checks skip phases, cycle time targets break
- Safe modification: Before adding new phases, map all transition paths; validate cycle time totals; test rework/blocker paths explicitly
- Test coverage: Phase transitions covered in unit tests but edge cases (rework loops) only in integration tests

**Release Notes Generation with LLM Parsing:**
- Files: `src/main.py` (lines 1950-1970), `src/services/llm_service.py`
- Why fragile: LLM response parsing expects exact structure; malformed JSON crashes silently with partial results
- Safe modification: Add response validation before parsing; implement fallback templates if parsing fails
- Test coverage: No tests for malformed LLM responses; caching masks generation failures

**Log Writer Background Thread:**
- Files: `src/logging/writer.py`, `src/main.py` (AsyncLogWriter usage)
- Why fragile: Queue-based async logging means logs may not be flushed on errors; database connection in thread not protected
- Safe modification: Add explicit flush on error paths; use connection pooling; test thread shutdown
- Test coverage: Thread safety not tested; only functional testing of logging

**Multi-Agent State Synchronization:**
- Files: `src/state/simulation_state.py` (sync_agent_workloads), agent state tracking throughout
- Why fragile: Agent workloads synced from scenarios but can drift if scenario updates don't update agent state
- Safe modification: Add invariant checks after scenario updates; always update both simultaneously
- Test coverage: No specific tests for agent/scenario state consistency

## Scaling Limits

**In-Memory State for Simulation:**
- Current capacity: Can handle ~200 active scenarios before state serialization becomes slow (20ms+ JSON dumps)
- Limit: JSON serialization scales linearly with active_scenarios count; dashboard polls every 15s
- Scaling path: Implement state pagination; move to database-backed state; implement incremental updates via WebSocket

**SQLite Log Database Growth:**
- Current capacity: 30-day retention at 10 sessions/day = ~9000 log entries; cleanup works but queries slow at 100k+ entries
- Limit: SQLite has no automatic pruning; queries without indexes scan full table; typical dev machine runs 1-2 months before slowdown
- Scaling path: Migrate to PostgreSQL for production; add indexes; implement partitioning by date; implement archival process

**Jira API Rate Limits Not Enforced:**
- Current capacity: No rate limiting in JiraClient; could hit Atlassian's 1000 requests/hour limit if intensity increases
- Limit: Each `/trigger` call can make 15+ Jira API requests; running every 45 min = ~32 calls/hour, safe. But if frequency increases, will hit limits
- Scaling path: Add exponential backoff; implement request queuing; add rate limit detection and pause mechanism

**LLM Token Budgets Not Tracked:**
- Current capacity: Using Haiku (fast) and Sonnet (complex) models; no per-hour or per-day token budget tracking
- Limit: If intensity_ratio increases or more agents act per tick, token usage grows linearly; no alerting when approaching limits
- Scaling path: Add token usage tracking in LogDatabase; implement per-tier budgets; add warning/pause when approaching limits

## Dependencies at Risk

**CrewAI Dependency on LangChain Evolution:**
- Risk: CrewAI framework depends on LangChain; both are in active development with breaking changes common
- Impact: Crew definitions in `src/crews/` may break with LangChain version updates; agent prompts are tightly coupled to LangChain patterns
- Migration plan: Monitor CrewAI releases; pin dependencies to known-good versions in requirements.txt; consider using stable older versions

**Jira Python Library Compatibility:**
- Risk: `jira` package (PyJira) is community-maintained; Atlassian recommends REST API client library
- Impact: If PyJira drops support for Jira Cloud, connection breaks; Atlassian's `atlassian-python-api` is alternative
- Migration plan: Evaluate `atlassian-python-api` as replacement; feature-parity check for `get_sprint_issues`, status caching, etc.

**Anthropic API Dependencies:**
- Risk: Using both litellm (for multi-provider routing) and direct anthropic client (for Skills API)
- Impact: If Anthropic API changes, two places need updates; Skills API is beta and may change/be deprecated
- Migration plan: Monitor Anthropic release notes; implement Skills API feature toggle; have fallback for document generation

## Missing Critical Features

**No Retry Logic for Transient Jira Failures:**
- Problem: If Jira API returns 503 (Service Unavailable), operation fails immediately instead of retrying
- Files: `src/services/jira_client.py` (all API methods), `src/logging/logged_jira_client.py`
- Blocks: Simulation reliability; test environments with flaky Jira instances are frustrating
- Fix approach: Add exponential backoff with max 3 retries for 5xx errors; log retry attempts

**No Incident Alerting for Simulation Failures:**
- Problem: If `/trigger` fails, error is logged but no alert sent; users discover failures on next manual check
- Files: `src/main.py` (error handling), `src/logging/api.py` (no alerting integration)
- Blocks: Unattended simulation monitoring; production deployment needs incident notifications
- Fix approach: Add webhook/Slack/email alerting on consecutive failures; track failure rates per hour

**No Simulation Time Visualization in Frontend:**
- Problem: Dashboard shows "Simulation Day 42" but users can't see actual clock time or day-of-week
- Files: `frontend/src/components/dashboard/` (no time display component)
- Blocks: Hard to correlate with schedule config (M-F 9-5); looks like simulation is running on wrong days
- Fix approach: Add calendar view showing simulation day to real calendar mapping; show schedule context

**No Automated Scenario Failure Recovery:**
- Problem: If scenario hits deadlock (e.g., blocked item never unblocked), scenario stays stuck forever
- Files: `src/orchestrator/orchestrator.py`, scenario advancement logic
- Blocks: Long-running simulations accumulate stuck scenarios; state becomes unrealistic
- Fix approach: Add timeout-based scenario ejection; implement "force resolve" for stuck blockers after N days

## Test Coverage Gaps

**Sprint Transition Edge Cases:**
- What's not tested: Sprint rollover while scenarios are in progress; scenarios with items from old sprint; state cleanup correctness
- Files: `src/main.py` (check_and_handle_expired_sprint function), `src/state/simulation_state.py` (sprint injection)
- Risk: Sprint transitions happen weekly; any edge case affects production weekly
- Priority: **High** - Add integration tests for: (1) scenario completion during rollover, (2) issue carryover state consistency, (3) sprint_number/sprint_day recalculation

**LLM Response Validation:**
- What's not tested: Malformed JSON responses, missing fields, unexpected data types from LLM
- Files: `src/orchestrator/planner.py` (lines 200-240 JSON parsing), `src/main.py` (release notes generation)
- Risk: LLM failures cascade to state corruption if responses aren't validated
- Priority: **High** - Add unit tests for: (1) malformed action lists, (2) missing action fields, (3) empty/null responses, (4) fallback behavior

**Agent Workload Synchronization:**
- What's not tested: Agent workloads drift when scenarios don't update agent state; inconsistency after migrations
- Files: `src/state/simulation_state.py` (sync_agent_workloads), agent state tracking throughout
- Risk: Agent workload metrics become unreliable; affects intensity decisions and scenario planning
- Priority: **Medium** - Add invariant checks: (1) assigned_tickets matches active scenarios, (2) workload count consistency, (3) automated correction detection

**Error Handling Path Coverage:**
- What's not tested: Jira connection failures during orchestrator.run_tick(), database write errors during logging, partial crew failures
- Files: `src/main.py` (try/except blocks), `src/logging/writer.py` (background thread errors)
- Risk: Edge cases silently fail; logs suggest success but state is corrupt
- Priority: **Medium** - Add chaos engineering tests: (1) mock Jira unavailability, (2) simulate log database failures, (3) crew timeouts

**Frontend State Sync Reliability:**
- What's not tested: Frontend dashboard handles 5+ second backend delays gracefully; stale data display; reconnection after network interruption
- Files: `frontend/src/hooks/useApi.ts` (API polling), `frontend/src/store/` (state management)
- Risk: Users see inconsistent data or "hung" dashboard on slow networks
- Priority: **Medium** - Add E2E tests for: (1) delayed responses, (2) connection loss/reconnect, (3) concurrent state updates

---

*Concerns audit: 2026-01-27*
