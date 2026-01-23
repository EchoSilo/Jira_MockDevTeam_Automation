"""
FastAPI endpoints for log viewer UI.

Provides REST API for querying logs and a simple HTML viewer.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from .query import LogQueryService

router = APIRouter(prefix="/logs", tags=["Logging"])


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """List simulation sessions/ticks with summary stats."""
    try:
        query = LogQueryService()

        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        sessions = query.get_sessions(limit, offset, start_dt, end_dt)
        total = query.get_session_count(start_dt, end_dt)

        return {
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"Failed to list log sessions: {e}")
        return {
            "sessions": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get detailed session info with all logs."""
    query = LogQueryService()
    return {
        "session": query.get_session(session_id),
        "timeline": query.get_session_timeline(session_id),
    }


@router.get("/sessions/{session_id}/conversation")
async def get_session_conversation(session_id: str):
    """Get session as conversation view (LLM prompts/responses in sequence)."""
    query = LogQueryService()
    return {"conversation": query.get_conversation_view(session_id)}


@router.get("/sessions/{session_id}/errors")
async def get_session_errors(session_id: str):
    """Get all errors for a session from all log tables."""
    query = LogQueryService()
    return {"errors": query.get_session_errors(session_id)}


@router.get("/llm-calls")
async def list_llm_calls(
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    ticket_key: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """Query LLM calls with filters."""
    query = LogQueryService()
    calls = query.get_llm_calls(
        session_id=session_id,
        agent_id=agent_id,
        ticket_key=ticket_key,
        model=model,
        limit=limit,
        offset=offset,
    )
    return {"llm_calls": calls, "count": len(calls)}


@router.get("/jira-calls")
async def list_jira_calls(
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    ticket_key: Optional[str] = None,
    method: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """Query Jira API calls with filters."""
    query = LogQueryService()
    calls = query.get_jira_calls(
        session_id=session_id,
        agent_id=agent_id,
        ticket_key=ticket_key,
        method=method,
        limit=limit,
        offset=offset,
    )
    return {"jira_calls": calls, "count": len(calls)}


@router.get("/stats")
async def get_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get usage statistics (token counts, call counts, etc.)."""
    try:
        query = LogQueryService()

        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        return query.get_token_usage_stats(start_dt, end_dt)
    except Exception as e:
        logger.error(f"Failed to get token usage stats: {e}")
        return {
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "avg_duration_ms": 0,
            "complex_calls": 0,
            "routine_calls": 0,
        }


@router.get("/viewer", response_class=HTMLResponse)
async def log_viewer_ui():
    """Simple HTML viewer for logs."""
    return HTML_VIEWER


# Clean, minimal HTML viewer
HTML_VIEWER = """
<!DOCTYPE html>
<html>
<head>
    <title>Jira Simulator - Log Viewer</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        h1 { margin: 0 0 20px 0; font-size: 24px; }
        h2 { margin: 20px 0 10px 0; font-size: 18px; }

        .container { max-width: 1400px; margin: 0 auto; }

        .stats-bar {
            background: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            gap: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .stat { text-align: center; }
        .stat-value { font-size: 24px; font-weight: bold; color: #2563eb; }
        .stat-label { font-size: 12px; color: #666; }

        .panel {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .sessions-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .session-item {
            padding: 12px 15px;
            background: #f8f9fa;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        .session-item:hover { background: #e9ecef; }
        .session-item.active { background: #dbeafe; border-left: 3px solid #2563eb; }

        .session-time { font-weight: 500; }
        .session-meta { font-size: 13px; color: #666; }
        .session-stats { display: flex; gap: 15px; font-size: 13px; }

        .badge {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        }
        .badge-light { background: #e0f2fe; color: #0369a1; }
        .badge-normal { background: #dcfce7; color: #166534; }
        .badge-busy { background: #fef3c7; color: #92400e; }
        .badge-error { background: #fee2e2; color: #991b1b; }

        .conversation {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .message {
            border-radius: 8px;
            padding: 15px;
            max-width: 100%;
        }
        .message-prompt {
            background: #eff6ff;
            border-left: 3px solid #2563eb;
        }
        .message-response {
            background: #f0fdf4;
            border-left: 3px solid #16a34a;
        }

        .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            font-size: 12px;
            color: #666;
        }
        .message-meta {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .message-content {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
        }

        .token-count {
            background: #e5e7eb;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
        }

        .tabs {
            display: flex;
            gap: 5px;
            margin-bottom: 15px;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 10px;
        }
        .tab {
            padding: 8px 16px;
            border: none;
            background: none;
            cursor: pointer;
            font-size: 14px;
            border-radius: 6px;
            color: #666;
        }
        .tab:hover { background: #f3f4f6; }
        .tab.active { background: #2563eb; color: white; }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: #666;
        }

        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }

        .timeline-item {
            padding: 10px 15px;
            border-left: 3px solid #e5e7eb;
            margin-left: 10px;
        }
        .timeline-item.llm_call { border-color: #2563eb; }
        .timeline-item.jira_call { border-color: #16a34a; }
        .timeline-item.orchestrator { border-color: #9333ea; }
        .timeline-item.agent_decision { border-color: #ea580c; }

        .timeline-time { font-size: 11px; color: #666; }
        .timeline-type { font-weight: 500; margin: 5px 0; }
        .timeline-details { font-size: 13px; color: #444; }

        .expandable {
            cursor: pointer;
        }
        .expandable:hover {
            background: rgba(0,0,0,0.02);
        }
        .expand-content {
            display: none;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e5e7eb;
        }
        .expanded .expand-content {
            display: block;
        }

        .filters {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .filter-input {
            padding: 8px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
        }

        .error-item {
            padding: 15px;
            background: #fef2f2;
            border-left: 3px solid #dc2626;
            border-radius: 6px;
            margin-bottom: 10px;
        }
        .error-source {
            font-size: 11px;
            color: #991b1b;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 5px;
        }
        .error-message {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
            font-size: 13px;
            color: #7f1d1d;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .error-context {
            font-size: 12px;
            color: #666;
            margin-top: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h1 style="margin: 0;">Jira Team Simulator - Log Viewer</h1>
            <div style="display: flex; gap: 10px;">
                <button id="plan-sprint-btn" onclick="planSprint()" style="
                    padding: 10px 20px;
                    background: #7c3aed;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                ">
                    <span id="plan-icon">&#128197;</span>
                    <span id="plan-text">Plan Sprint</span>
                </button>
                <button id="trigger-btn" onclick="triggerSimulation()" style="
                    padding: 10px 20px;
                    background: #2563eb;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                ">
                    <span id="trigger-icon">&#9654;</span>
                    <span id="trigger-text">Trigger Simulation</span>
                </button>
            </div>
        </div>

        <div class="stats-bar" id="stats">
            <div class="stat">
                <div class="stat-value" id="stat-calls">-</div>
                <div class="stat-label">Total LLM Calls</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="stat-tokens">-</div>
                <div class="stat-label">Total Tokens</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="stat-complex">-</div>
                <div class="stat-label">Complex Calls</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="stat-routine">-</div>
                <div class="stat-label">Routine Calls</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="stat-avg-time">-</div>
                <div class="stat-label">Avg Duration</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="stat-cost">-</div>
                <div class="stat-label">Total Cost</div>
            </div>
        </div>

        <div style="display: flex; gap: 20px;">
            <div class="panel" style="width: 350px; flex-shrink: 0;">
                <h2>Sessions</h2>
                <div class="sessions-list" id="sessions-list">
                    <div class="loading">Loading sessions...</div>
                </div>
            </div>

            <div class="panel" style="flex: 1;">
                <div class="tabs">
                    <button class="tab active" data-tab="conversation">Conversation</button>
                    <button class="tab" data-tab="timeline">Timeline</button>
                    <button class="tab" data-tab="errors" id="errors-tab" style="display: none;">Errors</button>
                </div>

                <div id="conversation-view">
                    <div class="empty-state">Select a session to view its conversation</div>
                </div>

                <div id="timeline-view" style="display: none;">
                    <div class="empty-state">Select a session to view its timeline</div>
                </div>

                <div id="errors-view" style="display: none;">
                    <div class="empty-state">Select a session to view its errors</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentSession = null;
        let currentTab = 'conversation';

        // Cost calculation helpers
        // Pricing: DeepSeek V3.2 via OpenRouter ~$0.14/$0.28 per MTok (input/output)
        // Using same rate for routine/complex since both use DeepSeek
        function calculateCost(isComplex, inputTokens, outputTokens) {
            const inputRate = 0.14;
            const outputRate = 0.28;
            return (inputTokens * inputRate + outputTokens * outputRate) / 1000000;
        }

        function formatCost(cost) {
            if (cost === 0) return '$0.00';
            return cost < 0.01 ? '<$0.01' : '$' + cost.toFixed(2);
        }

        // Load stats
        async function loadStats() {
            try {
                const resp = await fetch('/logs/stats');
                const stats = await resp.json();

                document.getElementById('stat-calls').textContent =
                    stats.total_calls.toLocaleString();
                document.getElementById('stat-tokens').textContent =
                    stats.total_tokens.toLocaleString();
                document.getElementById('stat-complex').textContent =
                    stats.complex_calls.toLocaleString();
                document.getElementById('stat-routine').textContent =
                    stats.routine_calls.toLocaleString();
                document.getElementById('stat-avg-time').textContent =
                    stats.avg_duration_ms.toFixed(0) + 'ms';

                // Calculate and display total cost
                const totalCost = calculateCost(true, stats.complex_input_tokens || 0, stats.complex_output_tokens || 0)
                                + calculateCost(false, stats.routine_input_tokens || 0, stats.routine_output_tokens || 0);
                document.getElementById('stat-cost').textContent = formatCost(totalCost);
            } catch (e) {
                console.error('Failed to load stats:', e);
            }
        }

        // Load sessions
        async function loadSessions() {
            try {
                const resp = await fetch('/logs/sessions?limit=50');
                const data = await resp.json();

                const container = document.getElementById('sessions-list');

                if (data.sessions.length === 0) {
                    container.innerHTML = '<div class="empty-state">No sessions yet</div>';
                    return;
                }

                container.innerHTML = data.sessions.map(s => {
                    const time = new Date(s.started_at).toLocaleString();
                    const badgeClass = s.intensity === 'light' ? 'badge-light' :
                                      s.intensity === 'busy' ? 'badge-busy' : 'badge-normal';
                    const errorBadge = s.errors > 0 ?
                        `<span class="badge badge-error">${s.errors} errors</span>` : '';
                    const sessionCost = calculateCost(true, s.complex_input_tokens || 0, s.complex_output_tokens || 0)
                                      + calculateCost(false, s.routine_input_tokens || 0, s.routine_output_tokens || 0);

                    return `
                        <div class="session-item" data-session="${s.session_id}">
                            <div>
                                <div class="session-time">${time}</div>
                                <div class="session-meta">
                                    Day ${s.simulation_day} | Sprint Day ${s.sprint_day}
                                </div>
                            </div>
                            <div class="session-stats">
                                <span class="badge ${badgeClass}">${s.intensity}</span>
                                ${errorBadge}
                                <span class="token-count">${s.total_input_tokens + s.total_output_tokens} tok | ${formatCost(sessionCost)}</span>
                            </div>
                        </div>
                    `;
                }).join('');

                // Add click handlers
                container.querySelectorAll('.session-item').forEach(item => {
                    item.addEventListener('click', () => {
                        document.querySelectorAll('.session-item').forEach(i =>
                            i.classList.remove('active'));
                        item.classList.add('active');
                        loadSession(item.dataset.session);
                    });
                });

            } catch (e) {
                console.error('Failed to load sessions:', e);
                document.getElementById('sessions-list').innerHTML =
                    '<div class="empty-state">Failed to load sessions</div>';
            }
        }

        // Load session detail
        async function loadSession(sessionId) {
            currentSession = sessionId;

            // Load conversation view
            loadConversation(sessionId);

            // Load timeline view
            loadTimeline(sessionId);

            // Load errors view
            loadErrors(sessionId);
        }

        // Load conversation
        async function loadConversation(sessionId) {
            const container = document.getElementById('conversation-view');
            container.innerHTML = '<div class="loading">Loading conversation...</div>';

            try {
                const resp = await fetch(`/logs/sessions/${sessionId}/conversation`);
                const data = await resp.json();

                if (data.conversation.length === 0) {
                    container.innerHTML = '<div class="empty-state">No LLM calls in this session</div>';
                    return;
                }

                container.innerHTML = '<div class="conversation">' +
                    data.conversation.map(c => {
                        const time = new Date(c.timestamp).toLocaleTimeString();
                        const modelBadge = c.is_complex ?
                            '<span class="badge badge-busy">Complex</span>' :
                            '<span class="badge badge-light">Routine</span>';
                        const configInfo = [
                            `max_tokens: ${c.max_tokens || 'N/A'}`,
                            c.stop_reason ? `stop: ${c.stop_reason}` : null
                        ].filter(Boolean).join(' | ');
                        const inputCost = calculateCost(c.is_complex, c.input_tokens, 0);
                        const outputCost = calculateCost(c.is_complex, 0, c.output_tokens);

                        return `
                            <div class="message message-prompt expandable" onclick="this.classList.toggle('expanded')">
                                <div class="message-header">
                                    <div class="message-meta">
                                        <strong>PROMPT</strong>
                                        ${modelBadge}
                                        <span style="font-family: monospace; font-size: 11px; color: #666;">${c.model}</span>
                                        <span>${c.action_type}</span>
                                        ${c.agent_name ? `<span>Agent: ${c.agent_name}</span>` : ''}
                                        ${c.ticket_key ? `<span>Ticket: ${c.ticket_key}</span>` : ''}
                                    </div>
                                    <div class="message-meta">
                                        <span class="token-count">${c.input_tokens} tok (${formatCost(inputCost)})</span>
                                        <span>${time}</span>
                                    </div>
                                </div>
                                <div class="message-content">${escapeHtml(c.prompt.substring(0, 300))}${c.prompt.length > 300 ? '...' : ''}</div>
                                <div class="expand-content">
                                    <div class="message-content">${escapeHtml(c.prompt)}</div>
                                </div>
                            </div>
                            <div class="message message-response">
                                <div class="message-header">
                                    <div class="message-meta">
                                        <strong>RESPONSE</strong>
                                        <span>${c.duration_ms}ms</span>
                                        <span style="font-size: 11px; color: #666;">${configInfo}</span>
                                    </div>
                                    <div class="message-meta">
                                        <span class="token-count">${c.output_tokens} tok (${formatCost(outputCost)})</span>
                                    </div>
                                </div>
                                <div class="message-content">${escapeHtml(c.response)}</div>
                            </div>
                        `;
                    }).join('') + '</div>';

            } catch (e) {
                console.error('Failed to load conversation:', e);
                container.innerHTML = '<div class="empty-state">Failed to load conversation</div>';
            }
        }

        // Load timeline
        async function loadTimeline(sessionId) {
            const container = document.getElementById('timeline-view');
            container.innerHTML = '<div class="loading">Loading timeline...</div>';

            try {
                const resp = await fetch(`/logs/sessions/${sessionId}`);
                const data = await resp.json();

                if (data.timeline.length === 0) {
                    container.innerHTML = '<div class="empty-state">No events in this session</div>';
                    return;
                }

                container.innerHTML = data.timeline.map(t => {
                    const time = new Date(t.timestamp).toLocaleTimeString();
                    let typeLabel = t.entry_type;
                    let details = '';

                    if (t.entry_type === 'llm_call') {
                        typeLabel = `LLM: ${t.action_type}`;
                        details = `Model: ${t.model} | Tokens: ${t.total_tokens}`;
                    } else if (t.entry_type === 'jira_call') {
                        typeLabel = `Jira: ${t.method}`;
                        details = t.ticket_key ? `Ticket: ${t.ticket_key}` : '';
                        if (t.response_summary) details += ` | ${t.response_summary}`;
                    } else if (t.entry_type === 'orchestrator') {
                        typeLabel = `Orchestrator: ${t.phase}`;
                        if (t.planning_reasoning) {
                            details = t.planning_reasoning.substring(0, 100);
                        }
                    } else if (t.entry_type === 'agent_decision') {
                        typeLabel = `Agent: ${t.agent_name}`;
                        details = `Decision: ${t.decision_type}`;
                        if (t.action_selected) details += ` | Action: ${t.action_selected}`;
                    }

                    return `
                        <div class="timeline-item ${t.entry_type}">
                            <div class="timeline-time">${time}</div>
                            <div class="timeline-type">${typeLabel}</div>
                            <div class="timeline-details">${escapeHtml(details)}</div>
                        </div>
                    `;
                }).join('');

            } catch (e) {
                console.error('Failed to load timeline:', e);
                container.innerHTML = '<div class="empty-state">Failed to load timeline</div>';
            }
        }

        // Load errors
        async function loadErrors(sessionId) {
            const container = document.getElementById('errors-view');
            container.innerHTML = '<div class="loading">Loading errors...</div>';

            try {
                const resp = await fetch(`/logs/sessions/${sessionId}/errors`);
                const data = await resp.json();

                // Show/hide errors tab based on whether there are errors
                const errorsTab = document.getElementById('errors-tab');
                if (data.errors.length > 0) {
                    errorsTab.style.display = 'block';
                    errorsTab.textContent = `Errors (${data.errors.length})`;
                } else {
                    errorsTab.style.display = 'none';
                }

                if (data.errors.length === 0) {
                    container.innerHTML = '<div class="empty-state">No errors in this session</div>';
                    return;
                }

                container.innerHTML = data.errors.map(e => {
                    const time = e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '';
                    const context = [];
                    if (e.action_type) context.push(`Action: ${e.action_type}`);
                    if (e.method) context.push(`Method: ${e.method}`);
                    if (e.phase) context.push(`Phase: ${e.phase}`);
                    if (e.ticket_key) context.push(`Ticket: ${e.ticket_key}`);
                    if (e.agent_name) context.push(`Agent: ${e.agent_name}`);

                    return `
                        <div class="error-item">
                            <div class="error-source">${e.source} ${time ? '@ ' + time : ''}</div>
                            <div class="error-message">${escapeHtml(e.error)}</div>
                            ${context.length > 0 ? `<div class="error-context">${context.join(' | ')}</div>` : ''}
                        </div>
                    `;
                }).join('');

            } catch (e) {
                console.error('Failed to load errors:', e);
                container.innerHTML = '<div class="empty-state">Failed to load errors</div>';
            }
        }

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                currentTab = tab.dataset.tab;

                document.getElementById('conversation-view').style.display =
                    currentTab === 'conversation' ? 'block' : 'none';
                document.getElementById('timeline-view').style.display =
                    currentTab === 'timeline' ? 'block' : 'none';
                document.getElementById('errors-view').style.display =
                    currentTab === 'errors' ? 'block' : 'none';
            });
        });

        // Escape HTML
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Trigger simulation
        async function triggerSimulation() {
            const btn = document.getElementById('trigger-btn');
            const icon = document.getElementById('trigger-icon');
            const text = document.getElementById('trigger-text');

            // Disable button and show loading state
            btn.disabled = true;
            btn.style.background = '#6b7280';
            btn.style.cursor = 'wait';
            icon.innerHTML = '&#8987;';  // Hourglass
            text.textContent = 'Running...';

            try {
                const resp = await fetch('/trigger', { method: 'POST' });
                const data = await resp.json();

                // Show result briefly
                if (data.success) {
                    icon.innerHTML = '&#10003;';  // Checkmark
                    text.textContent = `Done! ${data.actions_taken} actions`;
                    btn.style.background = '#16a34a';
                } else {
                    icon.innerHTML = '&#10007;';  // X mark
                    text.textContent = `Error: ${data.errors?.length || 0} errors`;
                    btn.style.background = '#dc2626';
                }

                // Refresh the sessions list
                loadStats();
                loadSessions();

                // Reset button after 3 seconds
                setTimeout(() => {
                    btn.disabled = false;
                    btn.style.background = '#2563eb';
                    btn.style.cursor = 'pointer';
                    icon.innerHTML = '&#9654;';
                    text.textContent = 'Trigger Simulation';
                }, 3000);

            } catch (e) {
                console.error('Trigger failed:', e);
                icon.innerHTML = '&#10007;';
                text.textContent = 'Failed!';
                btn.style.background = '#dc2626';

                setTimeout(() => {
                    btn.disabled = false;
                    btn.style.background = '#2563eb';
                    btn.style.cursor = 'pointer';
                    icon.innerHTML = '&#9654;';
                    text.textContent = 'Trigger Simulation';
                }, 3000);
            }
        }

        // Plan sprint
        async function planSprint() {
            const btn = document.getElementById('plan-sprint-btn');
            const icon = document.getElementById('plan-icon');
            const text = document.getElementById('plan-text');

            // Disable button and show loading state
            btn.disabled = true;
            btn.style.background = '#6b7280';
            btn.style.cursor = 'wait';
            icon.innerHTML = '&#8987;';  // Hourglass
            text.textContent = 'Planning...';

            try {
                const resp = await fetch('/plan-sprint', { method: 'POST' });
                const data = await resp.json();

                // Show result briefly
                if (data.success) {
                    icon.innerHTML = '&#10003;';  // Checkmark
                    const msg = data.result?.items_added
                        ? `Added ${data.result.items_added} items`
                        : (data.message || 'Done!');
                    text.textContent = msg;
                    btn.style.background = '#16a34a';
                } else {
                    icon.innerHTML = '&#10007;';  // X mark
                    text.textContent = data.error || 'Failed';
                    btn.style.background = '#dc2626';
                }

                // Refresh the sessions list
                loadStats();
                loadSessions();

                // Reset button after 3 seconds
                setTimeout(() => {
                    btn.disabled = false;
                    btn.style.background = '#7c3aed';
                    btn.style.cursor = 'pointer';
                    icon.innerHTML = '&#128197;';
                    text.textContent = 'Plan Sprint';
                }, 3000);

            } catch (e) {
                console.error('Plan sprint failed:', e);
                icon.innerHTML = '&#10007;';
                text.textContent = 'Failed!';
                btn.style.background = '#dc2626';

                setTimeout(() => {
                    btn.disabled = false;
                    btn.style.background = '#7c3aed';
                    btn.style.cursor = 'pointer';
                    icon.innerHTML = '&#128197;';
                    text.textContent = 'Plan Sprint';
                }, 3000);
            }
        }

        // Initialize
        loadStats();
        loadSessions();

        // Auto-refresh every 10 seconds for faster feedback
        setInterval(() => {
            loadStats();
            loadSessions();
        }, 10000);
    </script>
</body>
</html>
"""
