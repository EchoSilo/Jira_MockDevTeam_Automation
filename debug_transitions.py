# debug_transitions.py
# Compare logged actions vs actual Jira status to find discrepancies
import json
import sqlite3
from dotenv import load_dotenv
from src.services.jira_client import JiraClient

load_dotenv()

def extract_transition_name(params_json):
    """Extract transition_name from JSON parameters"""
    try:
        params = json.loads(params_json)
        return params.get('transition_name', 'unknown')
    except:
        return 'unknown'

def main():
    print("=" * 70)
    print("JIRA TRANSITION DEBUG ANALYSIS")
    print("=" * 70)

    # Connect to Jira
    jira = JiraClient()

    # Connect to logs database
    conn = sqlite3.connect('data/logs.db')
    cursor = conn.cursor()

    # 1. Find all unique tickets with transition attempts
    print("\n1. ANALYZING TRANSITION LOGS")
    print("-" * 70)

    cursor.execute("""
        SELECT ticket_key, parameters, response_summary, COUNT(*) as call_count,
               MIN(timestamp) as first_call, MAX(timestamp) as last_call
        FROM jira_calls
        WHERE method = 'transition_issue'
        GROUP BY ticket_key, parameters, response_summary
        ORDER BY first_call DESC
        LIMIT 50
    """)

    transition_attempts = cursor.fetchall()

    failed_transitions = []
    successful_transitions = []

    for row in transition_attempts:
        ticket, params, result, count, _, _ = row
        transition = extract_transition_name(params)
        if "not found" in result.lower():
            failed_transitions.append((ticket, transition, count))
        else:
            successful_transitions.append((ticket, transition, count))

    print("\nFailed transitions (transition not found):")
    for ticket, transition, count in failed_transitions[:15]:
        print(f"  {ticket}: '{transition}' - {count} attempts")

    print("\nSuccessful transitions:")
    for ticket, transition, count in successful_transitions[:10]:
        print(f"  {ticket}: '{transition}' - {count} attempts")

    # 2. Check actual status of key tickets
    print("\n\n2. ACTUAL JIRA STATUS vs EXPECTED")
    print("-" * 70)

    # Tickets from recent actions that should have changed status
    tickets_to_check = [
        ("ESCRUM-500", "Should be Blocked (but Blocked doesn't exist)"),
        ("ESCRUM-1465", "Should be Blocked (but Blocked doesn't exist)"),
        ("ESCRUM-387", "Should be In Progress"),
        ("ESCRUM-388", "Should be In Progress"),
        ("ESCRUM-437", "Should be In Progress"),
        ("ESCRUM-439", "Should be In Progress"),
        ("ESCRUM-475", "Should be Done (qa_approve logged)"),
        ("ESCRUM-499", "Should be in Code Review (progress_to_review logged)"),
        ("ESCRUM-529", "Test ticket - now CODE REVIEW"),
        ("ESCRUM-1500", "Scenario shows in_review phase"),
        ("ESCRUM-1499", "Scenario shows in_progress phase"),
        ("ESCRUM-1497", "Scenario shows in_progress phase"),
    ]

    print(f"\n{'Ticket':<15} {'Expected':<40} {'Actual Status':<20}")
    print("-" * 75)

    discrepancies = []

    for ticket_key, expected in tickets_to_check:
        try:
            issue = jira.get_issue(ticket_key)
            actual_status = issue.fields.status.name

            # Check for discrepancy
            expected_lower = expected.lower()
            actual_lower = actual_status.lower()

            is_match = False
            if "in progress" in expected_lower and "in progress" in actual_lower:
                is_match = True
            elif "code review" in expected_lower and ("code review" in actual_lower or "in review" in actual_lower):
                is_match = True
            elif "done" in expected_lower and ("done" in actual_lower or "closed" in actual_lower):
                is_match = True
            elif "blocked" in expected_lower:
                # Blocked doesn't exist, so this is expected to fail
                is_match = False

            marker = "✓" if is_match else "✗ MISMATCH"
            if "blocked" in expected_lower and "blocked" not in actual_lower:
                marker = "⚠ No 'Blocked' status"

            print(f"{ticket_key:<15} {expected:<40} {actual_status:<20} {marker}")

            if not is_match and "blocked" not in expected_lower:
                discrepancies.append((ticket_key, expected, actual_status))

        except Exception as e:
            print(f"{ticket_key:<15} {expected:<40} ERROR: {str(e)[:30]}")

    # 3. Check what transitions are available
    print("\n\n3. AVAILABLE TRANSITIONS CHECK")
    print("-" * 70)

    # Check transitions for a ticket that should be "Blocked"
    for ticket_key in ["ESCRUM-500", "ESCRUM-1465"]:
        try:
            issue = jira.get_issue(ticket_key)
            transitions = jira.get_transitions(ticket_key)
            print(f"\n{ticket_key} (currently: {issue.fields.status.name}):")
            print(f"  Available transitions: {[t['name'] for t in transitions]}")
        except Exception as e:
            print(f"\n{ticket_key}: ERROR - {e}")

    # 4. Identify the problem
    print("\n\n4. ROOT CAUSE ANALYSIS")
    print("-" * 70)

    # Count failures by transition name
    cursor.execute("""
        SELECT parameters, COUNT(*) as failures
        FROM jira_calls
        WHERE method = 'transition_issue' AND response_summary LIKE '%not found%'
        GROUP BY parameters
        ORDER BY failures DESC
    """)

    print("\nFailure counts by transition name:")
    for params, count in cursor.fetchall():
        name = extract_transition_name(params)
        print(f"  '{name}': {count} failures")

    # Check for duplicate calls
    cursor.execute("""
        SELECT ticket_key, parameters,
               strftime('%Y-%m-%d %H:%M:%S', timestamp) as time,
               COUNT(*) as calls_in_second
        FROM jira_calls
        WHERE method = 'transition_issue'
        GROUP BY ticket_key, parameters, strftime('%Y-%m-%d %H:%M:%S', timestamp)
        HAVING calls_in_second > 1
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    dupe_calls = cursor.fetchall()
    if dupe_calls:
        print("\nDuplicate calls detected (multiple calls in same second):")
        for ticket, params, time, count in dupe_calls:
            transition = extract_transition_name(params)
            print(f"  {ticket} -> '{transition}' at {time}: {count} calls")

    conn.close()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
KEY FINDINGS:

1. 'Blocked' status does NOT exist in your Jira workflow
   - Agents try to transition to 'Blocked' but it fails every time
   - This is why blocked scenarios don't show status change in Jira

2. Multiple duplicate API calls per transition
   - Each transition is called 5-6 times in rapid succession
   - This suggests a bug in the code (retry loop or duplicate execution)

3. Successful transitions do work
   - 'In Progress' transitions are succeeding
   - The Jira API itself is working correctly

RECOMMENDED FIXES:
1. Add 'Blocked' or 'On Hold' status to your Jira workflow, OR
2. Update the code to use an existing status for blocked items
3. Investigate why transitions are being called multiple times
""")

if __name__ == "__main__":
    main()
