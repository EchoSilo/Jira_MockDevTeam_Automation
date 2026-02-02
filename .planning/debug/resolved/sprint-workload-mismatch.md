---
status: resolved
trigger: "After /sync-reset, agent workloads in API don't match Jira Sprint 7 - API includes tickets from Sprint 6"
created: 2026-02-02T00:00:00Z
updated: 2026-02-02T00:45:00Z
---

## Current Focus

hypothesis: VERIFIED - Fix working correctly
test: Verified via Docker logs and API responses
expecting: CONFIRMED - 22 tickets assigned (23 in sprint, 1 unassigned)
next_action: Clean up debug logging and archive session

## Symptoms

expected: After /sync-reset, agent workloads should reflect only tickets in Jira's active sprint (Sprint 7, 23 tickets). Each agent's assigned_tickets should only contain tickets that are actually assigned to them in the current sprint.

actual: API /agents endpoint returns 29 tickets total - includes 21 tickets that are still in Sprint 6 (previous sprint). For example:
- Elena Rodriguez: API shows 7 tickets, Jira Sprint 7 has 6
- Ana Costa: API shows 8 tickets, Jira Sprint 7 has 6
- Tyler Brooks: API shows 6 tickets, Jira Sprint 7 has 4
- Tickets like ESCRUM-386, ESCRUM-389, ESCRUM-390 etc. are in Sprint 6 but appear in API

errors: No explicit errors. The /sync-reset endpoint returns success but doesn't properly filter tickets by active sprint when rebuilding agent workloads.

reproduction:
1. POST /sync-reset (returns success)
2. GET /agents (shows 29 tickets across agents)
3. Query Jira for Sprint 7 issues (shows 23 tickets)
4. Compare - API includes Sprint 6 tickets

started: Issue observed after sync-reset was run. The function `_rebuild_agent_workloads_from_jira` at line 1570 in src/main.py is called during sync but doesn't appear to filter by sprint.

## Eliminated

## Evidence

- timestamp: 2026-02-02T00:05:00Z
  checked: get_all_active_issues implementation in src/services/jira_client.py line 136
  found: JQL query is 'project = {project_key} AND status NOT IN ("Done", "Closed", "Resolved")' - NO sprint filter
  implication: Function returns ALL active issues across ALL sprints, not just the active sprint

- timestamp: 2026-02-02T00:06:00Z
  checked: _rebuild_agent_workloads_from_jira in src/main.py line 220-248
  found: Calls get_all_active_issues() without sprint parameter, then assigns ALL returned tickets to agents
  implication: Agent workloads get populated with tickets from all sprints (Sprint 6 + Sprint 7)

- timestamp: 2026-02-02T00:15:00Z
  checked: After fix - ran sync-reset and checked /agents endpoint
  found: Still seeing 44 tickets total across agents (Elena: 11, James: 12, Ana: 11, Tyler: 9, Rachel: 1)
  implication: Fix may not be working correctly, or there's another issue. Need to verify get_sprint_issues is being called

- timestamp: 2026-02-02T00:17:00Z
  checked: sync_state_with_jira in src/state/simulation_state.py line 227-297
  found: Function calls get_all_active_issues() at line 238, creates scenarios, then assigns tickets to agents at line 295
  implication: TWO places assign tickets - sync_state_with_jira runs FIRST and assigns all active issues, then _rebuild_agent_workloads_from_jira runs. The first one is the root problem.

- timestamp: 2026-02-02T00:42:00Z
  checked: Docker logs after implementing full fix
  found: "[REBUILD DEBUG] Retrieved 23 issues from Jira" and "[SYNC-RESET DEBUG] After rebuild: 22 tickets assigned"
  implication: Fix working correctly - queries sprint 207, retrieves 23 issues, assigns 22 (1 unassigned)

- timestamp: 2026-02-02T00:43:00Z
  checked: /agents endpoint immediately after sync-reset
  found: 22 unique tickets (down from 44 before fix)
  implication: Agent workloads now correctly reflect only active sprint tickets

## Resolution

root_cause: get_all_active_issues() queries all active issues across all sprints without filtering by active sprint. When _rebuild_agent_workloads_from_jira calls this method during /sync-reset, it assigns tickets from previous sprints (Sprint 6) to agents along with current sprint (Sprint 7) tickets.

fix: Two-part fix in src/main.py:
1. Modified _rebuild_agent_workloads_from_jira (line 220) to accept optional sprint_id parameter
2. When sprint_id provided, calls get_sprint_issues(sprint_id) instead of get_all_active_issues()
3. In sync_reset_state (line 1575), clear all agent assigned_tickets before rebuilding
4. Pass active sprint ID from jira_sprint dict to _rebuild_agent_workloads_from_jira

Root cause: sync_state_with_jira assigns ALL active tickets to agents (across all sprints), then _rebuild was also using get_all_active_issues. Now we clear assignments and rebuild from active sprint only.

verification: PASSED
- Docker logs show: "Retrieved 23 issues from Jira" and "22 tickets assigned across all agents"
- /agents endpoint returns 22 unique tickets (down from 44 pre-fix)
- Matches Jira Sprint 7: 23 issues total, 22 assigned, 1 unassigned
- Verified via multiple sync-reset cycles

files_changed:
  - c:\Users\Jamal\Documents\My Dropbox\Private\AI\Jira_MockDevTeam_Automation\src\main.py
