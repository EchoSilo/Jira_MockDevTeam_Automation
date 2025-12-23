# test_transition.py
# Simple test to debug Jira status transitions
import os
from dotenv import load_dotenv
from src.services.jira_client import JiraClient

load_dotenv()

def main():
    print("=" * 50)
    print("JIRA STATUS TRANSITION TEST")
    print("=" * 50)

    # 1. Connect to Jira
    print("\n1. Connecting to Jira...")
    jira = JiraClient()
    print(f"   Connected to: {jira.url}")
    print(f"   Project: {jira.project_key}")

    # 2. Get current status
    issue_key = "ESCRUM-529"
    print(f"\n2. Fetching issue {issue_key}...")
    issue = jira.get_issue(issue_key)
    current_status = issue.fields.status.name
    print(f"   Current status: {current_status}")
    print(f"   Summary: {issue.fields.summary}")

    # 3. List available transitions
    print(f"\n3. Getting available transitions...")
    transitions = jira.get_transitions(issue_key)
    print(f"   Available transitions:")
    for t in transitions:
        print(f"     - ID: {t['id']}, Name: '{t['name']}'")

    # 4. Attempt transition
    target_status = "Code Review"
    print(f"\n4. Attempting transition to '{target_status}'...")
    success = jira.transition_issue(issue_key, target_status)
    if success:
        print(f"   SUCCESS - transition_issue() returned True")
    else:
        print(f"   FAILED - transition_issue() returned False")
        print(f"   (The target status '{target_status}' may not be in available transitions)")

    # 5. Verify new status
    print(f"\n5. Re-fetching issue to verify...")
    issue = jira.get_issue(issue_key)
    new_status = issue.fields.status.name
    print(f"   New status: {new_status}")

    # 6. Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"   Before: {current_status}")
    print(f"   After:  {new_status}")
    if current_status != new_status:
        print(f"   Result: STATUS CHANGED!")
    else:
        print(f"   Result: STATUS DID NOT CHANGE")
    print("=" * 50)

if __name__ == "__main__":
    main()
