# Pitfalls Research

**Domain:** Real-time scheduling and external system reconciliation for Jira simulator
**Researched:** 2026-01-27
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: DST Transitions Create Duplicate or Missing Executions

**What goes wrong:**
When clocks "fall back" for DST (2:00 AM → 1:00 AM), cron jobs scheduled in the 1 AM hour run twice. When clocks "spring forward" (e.g., 2:00 AM → 3:00 AM), jobs scheduled in the 2 AM hour are skipped entirely. In some time zones (Chile, Iran), midnight DST transitions mean 00:00:00 never occurs.

**Why it happens:**
Cron has no built-in DST awareness and treats local time naively. The simulator currently uses `America/New_York` timezone (config/settings.yaml:12) with business hours 9-5, which spans DST transitions in March and November. When n8n triggers the `/trigger` endpoint based on wall-clock time, the simulator's `is_new_day()` logic (which checks `last_run` timestamps) can miscount days.

**How to avoid:**
1. **Switch to UTC for all scheduling:** Use UTC for cron expressions and n8n schedules. Convert to local time only for display/logging.
2. **Never schedule critical operations 1-3 AM:** If local time is required, avoid the DST transition window.
3. **Implement execution ID deduplication:** Use deterministic IDs (e.g., `{date}-{hour}-tick`) to detect duplicate runs within a 6-hour window.
4. **Add DST transition detection:** Before advancing `simulation_day`, check if elapsed hours include a DST boundary and adjust accordingly.

**Warning signs:**
- `simulation_day` increments by 0 or 2 instead of 1 during DST transitions
- Sprint day calculations drift from Jira's actual sprint day (`state.sprint.sprint_day != calculated_from_jira`)
- Duplicate actions logged with identical timestamps (±1 hour)
- Agent daily action counters reset mid-day or skip reset

**Phase to address:**
Phase 1: Replace virtual time with real-time clock and UTC-based scheduling

---

### Pitfall 2: Race Conditions Between Jira State Check and Execution

**What goes wrong:**
The simulator reads Jira state in `sync_state_with_jira()`, makes decisions based on that snapshot, then executes actions minutes later. In the gap, external changes (manual user edits, concurrent automations) invalidate the assumptions. Example: Analyzer detects ticket in "In Progress", plans to transition to "Code Review", but user already moved it to "Done" — action fails or creates invalid state.

**Why it happens:**
Current architecture has a 3-phase cycle (ANALYZE → PLAN → EXECUTE) with no state versioning or optimistic locking. The time gap can be 30+ seconds for LLM planning. Jira's REST API has no built-in conflict detection for status transitions.

**How to avoid:**
1. **Read-modify-write with validation:** Before executing, re-fetch the ticket's current status and verify it matches expected preconditions. Abort gracefully on mismatch.
2. **Idempotent actions only:** Design actions so re-running them is safe (e.g., "ensure ticket is in Code Review" vs. "transition to Code Review").
3. **Optimistic locking via update_time:** Store Jira's `updated` timestamp during sync, include it in state, and check it hasn't changed before execution.
4. **Graceful degradation:** When actions fail due to state mismatch, log the conflict and re-sync on next tick rather than retrying immediately (avoids thrashing).

**Warning signs:**
- Frequent "400 Bad Request" errors in Jira API calls (invalid transitions)
- State shows tickets assigned to agents, but Jira shows different assignments
- Scenarios stuck in phases where Jira status doesn't match `current_phase`
- Logs show "Failed to transition X to Y: already in Z"

**Phase to address:**
Phase 2: Implement reconciliation logic with pre-execution validation checks

---

### Pitfall 3: Execution Window Too Narrow Causes Missed Ticks

**What goes wrong:**
n8n schedules ticks every 45 minutes (config/settings.yaml:201), but if tick execution takes 50+ minutes (long LLM planning, many actions, slow Jira API), the next scheduled run is skipped. This breaks the simulation's assumption of regular intervals and causes sprint days to stall (no `is_new_day()` detection for 2+ hours).

**Why it happens:**
Cron schedulers (including n8n) are edge-triggered, not level-triggered. If the system is busy when the trigger fires, it's dropped rather than queued. Current tick processing is synchronous and unbounded — LLM calls have no timeout, and action count scales with intensity (up to 6 actions/tick in "busy" mode).

**How to avoid:**
1. **Set aggressive LLM timeouts:** Cap planning calls to 15 seconds, action generation to 10 seconds each. Fall back to templates on timeout.
2. **Track missed-run rate:** Log expected vs. actual tick times. Alert if gap exceeds 1.5x interval (67+ minutes).
3. **Limit max actions per tick:** Cap busy mode to 4 actions instead of 6. Process remaining in next tick.
4. **Async execution with queue:** Change `/trigger` to return immediately after queuing work, process in background. Ensures cron doesn't timeout.
5. **Heartbeat monitoring:** Expose `/api/last-tick-time` and have external monitor verify ticks occur within expected window.

**Warning signs:**
- Gaps in `last_run` timestamps exceeding 90 minutes during work hours
- `simulation_day` increments by 2+ when it should increment by 1
- n8n workflow logs show "execution skipped: previous run still active"
- Frontend dashboard shows stale data for extended periods

**Phase to address:**
Phase 3: Add execution time budgets and async task processing

---

### Pitfall 4: State Drift from Stale Cached Assumptions

**What goes wrong:**
The simulator maintains local state (data/state.json) that caches Jira data. If external changes happen (user closes sprint manually, reassigns tickets, completes items), the cache becomes stale. Subsequent ticks make decisions based on outdated assumptions, causing invalid actions. Example: Sprint scenario plans blocker injection on day 5, but sprint already ended externally — action targets closed sprint.

**Why it happens:**
Current sync logic (`sync_state_with_jira()`) only refreshes sprint number/day and creates scenarios for new tickets. It doesn't validate that existing scenarios' tickets still exist, are in the expected sprint, or have matching status. The `_state_cache` (5-second TTL) serves stale data to dashboard between ticks.

**How to avoid:**
1. **Full reconciliation on every tick:** Re-fetch all active sprint issues and cross-check with `state.active_scenarios`. Remove scenarios for tickets no longer in sprint.
2. **Scenario staleness detection:** Add `last_validated` timestamp to scenarios. Mark stale if not validated in 2+ ticks, remove if stale for 4+ ticks.
3. **Sprint mismatch detection:** Before executing sprint-specific actions, verify `active_sprint.id` matches the sprint referenced in action context.
4. **Tombstone tracking:** When external changes are detected (e.g., ticket moved to backlog), log a "tombstone" event explaining why the scenario was invalidated.
5. **Aggressive cache invalidation:** Reduce `_state_cache` TTL to 0 during /trigger execution to ensure dashboard sees fresh data immediately.

**Warning signs:**
- Actions referencing tickets that return "404 Not Found" from Jira
- Sprint scenario events execute against tickets not in the active sprint
- `state.active_scenarios` count grows unbounded (orphaned scenarios)
- Logs show "scenario X referenced sprint Y, but active sprint is Z"

**Phase to address:**
Phase 2: Implement reconciliation logic with tombstone tracking

---

### Pitfall 5: Over-Adaptation Creates Incoherent Scenarios

**What goes wrong:**
When reconciliation detects mismatches, the naïve fix is to immediately adapt the plan (e.g., "blocker resolved externally? inject new blocker to stay on script"). This creates thrashing where the simulator fights user actions, making behavior unpredictable and losing the intended scenario coherence (smooth/overloaded/blocker-heavy archetypes).

**Why it happens:**
Reconciliation logic often defaults to "sync to plan" rather than "adapt plan to reality." The current sprint scenario system (src/scenarios/) defines rigid scripts without adaptation strategies. When reality diverges, the analyzer keeps generating "fix" opportunities that undo external changes.

**How to avoid:**
1. **Accept reality after threshold:** If 3+ planned events are externally overridden, abandon the script and switch to reactive mode.
2. **Graceful degradation:** Define fallback behaviors for each scenario archetype (e.g., blocker-heavy → normal-flow if blockers resolve early).
3. **Human override detection:** If manual Jira changes happen during work hours (9-5), assume intentional and don't fight them. Outside work hours, assume accidental.
4. **Scenario confidence score:** Track how many events executed vs. skipped/overridden. Below 60% confidence, mark scenario as "degraded" in logs.
5. **Immutable past, flexible future:** Don't try to "undo" external changes. Only adapt future events in the script.

**Warning signs:**
- Logs show repeated cycles of "planned blocker injection → external resolution → re-injection"
- Scenario completion rates below 40% (most events get skipped)
- Tickets rapidly oscillate between statuses (In Progress → Blocked → In Progress)
- Agent assignments flip back and forth within same hour

**Phase to address:**
Phase 4: Add scenario adaptation logic with confidence tracking

---

### Pitfall 6: Timezone Conversion Bugs in Multi-System Architecture

**What goes wrong:**
The system spans three time contexts: n8n (uses server TZ), FastAPI (uses UTC in datetime.utcnow()), and Jira API (returns ISO8601 with Z suffix). When comparing timestamps across these systems, off-by-hours errors cause incorrect "is new day" detection, sprint day calculations, and expiration checks.

**Why it happens:**
Current code mixes naive datetimes (no timezone info) and aware datetimes (with UTC). Example: `state.last_run` is stored as naive datetime, `jira_sprint.end_date` is parsed as aware UTC, comparing them directly can fail or give wrong results. Python's `datetime.utcnow()` returns naive datetime despite the name.

**How to avoid:**
1. **All datetimes must be timezone-aware:** Use `datetime.now(timezone.utc)` instead of `datetime.utcnow()`. Always parse Jira timestamps with timezone.
2. **Single source of truth for "now":** Create `get_current_time()` helper that returns aware UTC datetime. Use everywhere instead of direct datetime calls.
3. **Explicit conversions only:** Never rely on implicit timezone assumptions. Convert to target TZ explicitly for display only.
4. **Validate timestamps on load:** When loading state.json, verify all timestamps can parse as ISO8601 with TZ. Reject naive timestamps.
5. **Test with multiple timezones:** Add test cases that set system TZ to America/New_York, Asia/Tokyo, etc. and verify behavior is identical.

**Warning signs:**
- `is_new_day()` triggers at 7 PM instead of midnight
- Sprint expiration check thinks sprint ended 5 hours early/late
- Dashboard shows "Last run: 3 hours ago" when it was 3 minutes ago
- Timestamps in logs.db are off by consistent offset (5 hours, 8 hours)

**Phase to address:**
Phase 1: Standardize all time handling to timezone-aware UTC

---

### Pitfall 7: Unbounded Retry Loops Without Idempotency

**What goes wrong:**
When actions fail (Jira API timeout, LLM error, invalid transition), the simulator retries on the next tick. If the failure is persistent (e.g., bug in transition logic), the same action is retried indefinitely, polluting logs and potentially creating duplicate comments/transitions if the action isn't idempotent.

**Why it happens:**
Current orchestrator (src/orchestrator/orchestrator.py) doesn't track retry counts per action. Failed actions are simply logged and state remains unchanged, so the next tick's analyzer detects the same opportunity again. CrewAI crews have default retry behavior but no cross-tick memory.

**How to avoid:**
1. **Action execution IDs:** Generate deterministic ID for each planned action (hash of action type + target ticket + sprint day). Store in state with retry count.
2. **Max 3 retries per action:** After 3 failures, mark action as "permanently failed" and remove from planning consideration.
3. **Exponential backoff:** First retry on next tick (45 min), second after 2 ticks (90 min), third after 4 ticks (3 hours).
4. **Idempotent actions only:** All Jira writes must check current state first. Comments should include unique ID in text to detect duplicates.
5. **Circuit breaker per ticket:** If a ticket causes 5+ action failures, quarantine it (mark in state as "problematic") and skip for 24 hours.

**Warning signs:**
- Same error message in logs every tick for same ticket
- Duplicate comments on Jira tickets with identical text
- Action count in logs is high but actual Jira changes are few
- Specific tickets have 10+ failed transition attempts

**Phase to address:**
Phase 3: Add retry tracking with exponential backoff and circuit breakers

---

### Pitfall 8: Business Hours Enforcement Creates Execution Gaps

**What goes wrong:**
Configuration specifies work hours 9-5, Monday-Friday (config/settings.yaml:197-200), but enforcement is inconsistent. If n8n triggers at 5:30 PM or on Saturday, should the tick execute? Current code has no business hours check, so actions happen outside intended window, making activity patterns unrealistic.

**Why it happens:**
The `/trigger` endpoint has no awareness of `settings.schedule`. n8n's cron expression is separate config. If they drift (n8n changes to run 8 AM-6 PM but settings.yaml still says 9-5), the simulator doesn't notice.

**How to avoid:**
1. **Business hours gate in /trigger:** Check current time against settings.schedule before executing. Return 200 OK but log "outside business hours, skipping."
2. **Validate n8n schedule on startup:** Have `/health` endpoint verify that if n8n schedule is detectable, it aligns with settings.yaml schedule.
3. **Accumulate intent during off-hours:** If triggered at 6 PM, queue the tick's intensity to be processed on next in-hours run instead of skipping entirely.
4. **Graceful handling of Monday 9 AM:** First tick of the week should handle "catch-up" for any weekend events that should have happened (sprint rollovers, etc.).
5. **Explicit weekend handling:** If triggered on Saturday, decide: skip entirely, or process end-of-sprint administrative tasks?

**Warning signs:**
- Actions logged with timestamps at 7 PM, 11 PM, or weekends
- Dashboard shows activity on Saturdays
- Sprint planning happens on Tuesday instead of Monday
- n8n workflow runs 24/7 but simulator expects only M-F

**Phase to address:**
Phase 1: Add business hours gate in /trigger with accumulation logic

---

### Pitfall 9: Real-Time Clock Makes Tests Non-Deterministic

**What goes wrong:**
Once the simulator switches from virtual time (`simulation_time`) to real-time (`datetime.now()`), tests become flaky. Tests that verify "sprint expires after 7 days" now depend on wall clock advancing. Tests that check DST handling must wait for actual DST dates. CI/CD pipelines fail randomly based on time of day.

**Why it happens:**
Current code is transitioning from virtual time (main.py:381: `state.simulation_time = datetime.now()`) to real-time. Tests written for virtual time assume time is controllable via state manipulation. Real-time tests require mocking `datetime.now()` everywhere, which is fragile.

**How to avoid:**
1. **Dependency injection for clock:** Create `Clock` interface with `now()` method. Inject `RealClock` in production, `FakeClock` in tests.
2. **Preserve virtual time mode for tests:** Add `USE_VIRTUAL_TIME=true` env var that keeps existing behavior. Default to `false` in production.
3. **Deterministic test fixtures:** Use `freezegun` library to freeze time during tests. Explicitly advance time with `time.sleep()` or `freezegun.tick()`.
4. **Integration tests with time mocking:** Mock `datetime` at module level, not instance level. Verify all time-dependent logic uses injected clock.
5. **Separate test suites:** Unit tests use FakeClock (fast, deterministic). Integration tests use RealClock + short durations (slow, validates real behavior).

**Warning signs:**
- Tests pass locally but fail in CI with "sprint not expired" errors
- Tests that check "is_new_day" fail at midnight UTC
- Flaky tests that pass 90% of the time
- Tests take hours to run (waiting for real-time delays)

**Phase to address:**
Phase 1: Extract time dependency into injectable Clock interface

---

### Pitfall 10: Chaos Parameter Tuning Creates Boom-Bust Cycles

**What goes wrong:**
Random event injection (blockers, scope creep, rework) is controlled by probability thresholds (config/settings.yaml:38-43: `target_distribution`). If tuned too high, every sprint devolves into chaos (nothing completes). If too low, simulation is boring (100% smooth flow). The sweet spot is narrow and hard to find without metrics.

**Why it happens:**
Current target distribution is static (50% normal, 15% blocker, etc.) and doesn't adapt to context. A sprint with 3 items behaves very differently than a sprint with 20 items under same probabilities. No feedback loop exists to detect when chaos is too high/low.

**How to avoid:**
1. **Dynamic probability scaling:** Reduce blocker probability if active blockers > 20% of sprint items. Increase if no blockers for 3+ days.
2. **Completion rate feedback:** After each sprint, calculate completion rate. If <50%, reduce chaos probabilities by 10%. If >90%, increase by 5%.
3. **Chaos budget:** Instead of probabilities, define "max chaos points per sprint" (e.g., 1 blocker = 3 points, 1 rework = 2 points). Stop injecting when budget exhausted.
4. **Archetype-specific tuning:** Smooth sprints get 0.5x chaos multiplier, overloaded get 1.0x, blocker-heavy get 2.0x. Align with sprint scenario archetype.
5. **Observability dashboard:** Add metrics panel showing chaos levels per sprint (blocker count, rework count, completion rate). Make tuning a data-driven process.

**Warning signs:**
- Sprint completion rate varies wildly (20%, 95%, 30%, 90%)
- All tickets in a sprint get blocked simultaneously
- No complications happen for entire sprints (boring)
- QA agents spend 80% of time rejecting tickets (unrealistic)

**Phase to address:**
Phase 5: Implement dynamic chaos tuning with feedback loops

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Using naive datetimes (no timezone) | Simpler code, fewer imports | DST bugs, multi-TZ failures, impossible to debug time issues | Never — always use timezone-aware |
| Skipping idempotency checks in actions | Faster action execution | Duplicate comments, corrupted state on retry, hard-to-debug race conditions | Never — idempotency is foundational |
| Storing n8n schedule separately from settings.yaml | Easy to change n8n schedule | Drift between schedule configs, violations of business hours, confusion about "intended" schedule | Only during initial setup; sync ASAP |
| Caching Jira state for >5 seconds | Reduces API calls, faster dashboard | Stale data causes invalid actions, state drift goes undetected | Acceptable for dashboard display only, NOT for decision-making |
| Synchronous tick processing (blocking /trigger) | Simpler request/response model | Missed ticks when execution exceeds interval, no parallelism | Only in MVP; migrate to async in phase 3 |
| Hardcoding "45 minutes" interval in multiple places | Easy to reference in code | Config changes don't propagate, interval drift | Never — read from single source (settings.yaml or n8n API) |
| Using LLM for routine comments instead of templates | Initially seems flexible | Costs scale with usage, adds latency, non-deterministic output | Acceptable for <10 actions/day; template at scale |
| Letting scenarios grow unbounded in state.json | No explicit cleanup logic needed | State file bloats to megabytes, load/save becomes slow | Acceptable for <100 scenarios; add cleanup at 200+ |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Jira REST API | Assuming transitions are synchronous and always succeed | Check response status, handle 400 errors (invalid transition), verify state after transition |
| Jira Sprint API | Parsing sprint name without error handling ("Sprint 7" vs. "ESCRUM Sprint 7") | Use regex with fallback: `int(re.search(r'(\d+)', name).group(1) if re.search(r'(\d+)', name) else '0')` |
| Jira timestamps | Treating "Z" suffix timestamps as naive datetime | Always use `.replace("Z", "+00:00")` before parsing with fromisoformat() |
| LiteLLM / Anthropic API | No timeout on LLM calls, blocking indefinitely | Set `request_timeout=30` for all litellm.completion() calls |
| n8n webhook triggers | Assuming /trigger is called exactly every X minutes | Add missed-run detection, log gap warnings, handle 2x interval gaps |
| CrewAI crews | Assuming crew.kickoff() always succeeds and returns valid data | Wrap in try/except, validate output structure, have fallback templates for failures |
| State persistence (state.json) | Concurrent writes from multiple processes | Use file locking (fcntl on Linux, msvcrt on Windows) or atomic write-then-rename pattern |
| Frontend dashboard polling | Polling /state every second causing API overload | Use 15-second interval minimum, implement exponential backoff on errors |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all sprint issues on every tick | Fast with 10 issues, slow with 100+ | Cache issue list, only re-fetch when sprint changes or 5+ minutes pass | >50 issues in sprint, or API rate limits exceeded |
| Storing full LLM prompts in logs.db | Works fine for days, then DB grows to GB | Truncate prompts to 1000 chars in logs, or disable `log_full_prompts` after initial testing | After 1000+ LLM calls (~3 days of operation) |
| Synchronous action execution (no parallelism) | Ticks complete in 30s with 2 actions | Use asyncio.gather() to parallelize independent actions (different tickets) | >4 actions per tick, or slow Jira API responses |
| Linear search through active_scenarios | Fast with 10 scenarios | Index scenarios by ticket_key in dict, not list | >100 active scenarios (large backlogs) |
| No pagination on Jira API calls | Works with default 50 max_results | Use `startAt` and `maxResults` params, loop until exhausted | Project has >50 issues total |
| Keeping all historical actions in state.json | Small file for first month | Archive actions older than 30 days to separate file | After 30 days (file grows to 10+ MB) |
| Dashboard re-fetches all data on every poll | Fast with small state | Implement ETag or Last-Modified caching, return 304 Not Modified | State file >1 MB or >5 agents |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging Jira API tokens in error messages | Token leaks in logs, unauthorized access to Jira | Redact tokens in exception handlers, use `token[-4:]` for debugging |
| Storing LLM API keys in state.json or logs | Keys committed to git, leaked in backups | Always use environment variables, never serialize to JSON |
| Exposing /trigger endpoint without authentication | Anyone can trigger simulation, causing resource exhaustion | Add API key header check, or restrict to n8n's IP range only |
| Using predictable scenario IDs (sequential ints) | Attackers can guess valid scenario IDs from API responses | Use UUIDs or random strings (current code does this correctly) |
| Allowing unbounded user input in chat endpoint | Prompt injection via /chat, excessive LLM costs | Truncate messages to 500 chars, sanitize for prompt injection patterns |
| Not validating Jira webhook signatures (if added) | Malicious webhooks could poison state | Verify HMAC signature if using Jira webhooks to push state changes |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No feedback when tick is skipped (outside business hours) | User triggers /trigger at 6 PM, sees 200 OK but nothing happens — confusing | Return JSON with `{executed: false, reason: "outside business hours", next_run: "2026-01-28T09:00:00Z"}` |
| Dashboard shows stale data without indication | User waits for tick, dashboard doesn't update, assumes simulator is broken | Add "Last updated: 5s ago" timestamp, visual indicator if >60s stale |
| Error messages reference internal state IDs | "Scenario abc123 failed" means nothing to user who sees Jira ticket keys | Always include ticket_key in error messages, de-emphasize internal IDs |
| Sprint scenario archetype not visible | User doesn't know why so many blockers are happening, seems random | Show current sprint scenario in dashboard: "Sprint 7: Blocker-heavy archetype (3/7 events executed)" |
| No way to see what simulator will do next | User can't preview upcoming actions, feels like black box | Add /api/next-tick-preview endpoint that runs ANALYZE and PLAN without EXECUTE |
| Logs only show errors, not successful actions | User sees silent success, assumes nothing happened | Log INFO-level summaries: "Tick 47: Completed 4 actions (2 transitions, 1 comment, 1 work log)" |
| Business hours violations are silent | User schedules n8n for 24/7, doesn't realize it's wasting resources | Add startup warning if n8n schedule is detectable and conflicts with business hours |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Real-time scheduling:** Often missing business hours enforcement in /trigger — verify by calling endpoint at 7 PM and checking it returns early
- [ ] **DST handling:** Often missing duplicate/skip detection — verify by mocking time to DST transition and checking simulation_day increments correctly
- [ ] **Jira reconciliation:** Often missing tombstone tracking for externally-changed tickets — verify by manually moving ticket in Jira and checking next tick logs "detected external change"
- [ ] **Retry logic:** Often missing max retry count — verify by forcing persistent error and checking it gives up after 3 attempts
- [ ] **Timezone handling:** Often mixing naive and aware datetimes — verify by running `assert all(dt.tzinfo is not None for dt in [state.last_run, state.simulation_time])` after load
- [ ] **Idempotency:** Often missing duplicate comment detection — verify by running same action twice and checking only one Jira comment is created
- [ ] **Execution timeouts:** Often missing LLM call timeouts — verify by mocking slow LLM and checking request fails after 30s
- [ ] **State validation:** Often missing schema migration for old state.json files — verify by loading state from 3 months ago and checking it doesn't crash
- [ ] **Performance at scale:** Often missing pagination on Jira queries — verify with project containing 500+ issues and checking API doesn't return truncated results
- [ ] **Error observability:** Often missing structured error logging — verify failed actions log ticket_key, error type, retry count, not just stack trace

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| DST duplicate run detected | LOW | De-duplicate based on execution ID, mark second run as "skipped_duplicate" in logs, don't increment simulation_day |
| Race condition caused invalid Jira transition | LOW | Log conflict, skip action, re-sync state on next tick — system self-heals within 45 minutes |
| Missed ticks due to long execution | MEDIUM | Detect gap >90 minutes, log warning, optionally run "catch-up" tick with 2x action budget to compensate |
| State drift (stale scenarios) | MEDIUM | Run full reconciliation pass: fetch all sprint issues, cross-check with active_scenarios, remove orphans, create tombstone log |
| Over-adaptation (fighting user changes) | HIGH | Manually set `sprint_scenario.confidence = 0.0` to disable script, let system run in reactive mode for rest of sprint |
| Timezone conversion bug corrupted timestamps | HIGH | Stop simulator, run migration script to parse all timestamps in state.json and re-serialize with explicit UTC, restart |
| Unbounded retries polluted Jira with duplicate comments | HIGH | Manually delete duplicate comments in Jira, add execution IDs to state retroactively, implement idempotency checks |
| Business hours drift (n8n running 24/7) | LOW | Update n8n schedule, add /trigger gate check, ignore out-of-hours ticks going forward |
| Tests broke due to real-time clock | MEDIUM | Inject FakeClock for all tests, run migration pass to replace `datetime.now()` with `clock.now()` |
| Chaos parameters caused sprint failure | LOW | Manually complete sprint, adjust target_distribution in settings.yaml, restart with lower probabilities |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| DST Transitions | Phase 1: Time handling | Run test suite with frozen time at DST boundaries, verify simulation_day increments correctly |
| Race Conditions | Phase 2: Reconciliation logic | Manually change ticket in Jira mid-tick, verify action aborts gracefully with conflict log |
| Missed Ticks | Phase 3: Execution budgets | Mock slow LLM taking 50 minutes, verify tick returns early with partial results |
| State Drift | Phase 2: Reconciliation logic | Create stale scenario, run tick, verify scenario is tombstoned and removed |
| Over-Adaptation | Phase 4: Scenario adaptation | Manually override 3+ scenario events, verify script is abandoned and system goes reactive |
| Timezone Bugs | Phase 1: Time handling | Load state.json, verify all datetimes have tzinfo, verify comparisons work across TZ changes |
| Retry Loops | Phase 3: Retry tracking | Force persistent error, verify action is retired exactly 3 times then quarantined |
| Business Hours Gaps | Phase 1: Business hours gate | Call /trigger at 7 PM, verify returns {executed: false} and logs reason |
| Test Determinism | Phase 1: Clock injection | Run test suite with FakeClock, verify 100% pass rate, repeat 10 times |
| Chaos Tuning | Phase 5: Dynamic tuning | Run 10 sprints, verify completion rate stays between 60-80%, no boom-bust cycles |

---

## Sources

**DST and Timezone Handling:**
- [Handling Timezone Issues in Cron Jobs (2025 Guide)](https://dev.to/cronmonitor/handling-timezone-issues-in-cron-jobs-2025-guide-52ii)
- [How are cron jobs affected when a Daylight Savings change occurs](https://access.redhat.com/solutions/477963)
- [When Daylight Savings Time Broke Our Cronjobs in 3 Different Ways](https://medium.com/@rudra910203/when-daylight-savings-time-broke-our-cronjobs-in-3-different-ways-ee3ce525904f)
- [Blog CronMonitor - Handling Timezone Issues in Cron Jobs](https://cronmonitor.app/blog/handling-timezone-issues-in-cron-jobs)

**Reconciliation and State Drift:**
- [Designing for Eventual Consistency and Reconciliation](https://30dayscoding.com/blog/designing-for-eventual-consistency-and-reconciliation)
- [Reconciliation Loop - Kubernetes Kubebuilder](https://deepwiki.com/kubernetes-sigs/kubebuilder/5.2-reconciliation-loop)
- [How to Avoid Race Conditions in your Microservice Application](https://blog.avenuecode.com/how-to-avoid-race-conditions-in-your-microservice-application)
- [The Art of Staying in Sync: How Distributed Systems Avoid Race Conditions](https://medium.com/@alexglushenkov/the-art-of-staying-in-sync-how-distributed-systems-avoid-race-conditions-f59b58817e02)

**Retry Logic and Idempotency:**
- [What is a Temporal Retry Policy?](https://docs.temporal.io/encyclopedia/retry-policies)
- [Developer best practices: Safe retries and idempotency](https://internetcomputer.org/docs/building-apps/best-practices/idempotency)
- [Day 20: Idempotency in Task Execution](https://javatsc.substack.com/p/day-20-idempotency-in-task-execution)
- [Error handling in distributed systems: A guide to resilience patterns](https://temporal.io/blog/error-handling-in-distributed-systems)

**Scheduled Task Monitoring:**
- [How to Monitor Scheduled Tasks](https://moss.sh/devops-monitoring/how-to-monitor-scheduled-tasks/)
- [Jobs retries and checkpoints best practices - Google Cloud](https://docs.cloud.google.com/run/docs/jobs-retries)

**Real-Time Simulation:**
- [RealTime Simulation - ns-3 Manual](https://www.nsnam.org/docs/manual/html/realtime.html)
- [Scheduling in Real Time Systems - GeeksforGeeks](https://www.geeksforgeeks.org/scheduling-in-real-time-systems/)

**Codebase Analysis:**
- Existing architecture documentation (ARCHITECTURE.md)
- Current virtual time implementation (src/state/models.py, src/main.py)
- Configuration (config/settings.yaml)
- Personas configuration (config/personas.yaml)

---

*Pitfalls research for: Real-time scheduling and external system reconciliation for Jira simulator*
*Researched: 2026-01-27*
