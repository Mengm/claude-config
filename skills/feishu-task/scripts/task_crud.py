#!/usr/bin/env python3
"""Manage Feishu tasks (Task V2 API)."""

import argparse
import json
import os
import sys
from datetime import datetime

from feishu_auth import api_get, api_post, api_patch, api_delete


def _parse_time(s: str) -> dict:
    """Parse ISO time string to Feishu due/start object.

    Accepts: "2026-02-15" (all-day) or "2026-02-15T14:00" (precise).
    Returns: {"timestamp": "ms", "is_all_day": bool}
    """
    s = s.strip()
    if "T" in s:
        dt = datetime.fromisoformat(s)
        return {"timestamp": str(int(dt.timestamp() * 1000)), "is_all_day": False}
    else:
        dt = datetime.fromisoformat(s)
        return {"timestamp": str(int(dt.timestamp() * 1000)), "is_all_day": True}


def _user_id_type() -> str:
    """Detect user_id_type from env TASKPOOL_USER_ID format."""
    uid = os.getenv("TASKPOOL_USER_ID", "")
    if uid.startswith("ou_"):
        return "open_id"
    if uid.startswith("on_"):
        return "union_id"
    return "open_id"


def create_task(summary: str, description: str | None = None,
                due: str | None = None, start: str | None = None,
                assignee: str | None = None) -> dict:
    """Create a task.

    Always assigns the current user ($TASKPOOL_USER_ID) so the task
    appears in their Feishu task list.  An explicit --assignee is
    merged in (deduplicated).
    """
    body = {"summary": summary}
    if description:
        body["description"] = description
    if due:
        body["due"] = _parse_time(due)
    if start:
        body["start"] = _parse_time(start)

    # Always include current user as assignee
    member_ids: set[str] = set()
    user_id = os.getenv("TASKPOOL_USER_ID", "")
    if user_id:
        member_ids.add(user_id)
    if assignee:
        member_ids.add(assignee)
    if member_ids:
        body["members"] = [{"id": mid, "type": "user", "role": "assignee"} for mid in member_ids]

    params = {"user_id_type": _user_id_type()}
    resp = api_post("/task/v2/tasks", body=body, params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def complete_task(task_id: str) -> dict:
    """Mark a task as completed."""
    now_ms = str(int(datetime.now().timestamp() * 1000))
    resp = api_patch(
        f"/task/v2/tasks/{task_id}",
        body={"task": {"completed_at": now_ms}, "update_fields": ["completed_at"]},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def uncomplete_task(task_id: str) -> dict:
    """Mark a task as not completed."""
    resp = api_patch(
        f"/task/v2/tasks/{task_id}",
        body={"task": {"completed_at": "0"}, "update_fields": ["completed_at"]},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def add_members(task_id: str, member_ids: list[str], role: str = "assignee") -> dict:
    """Add members to a task."""
    members = [{"id": mid, "type": "user", "role": role} for mid in member_ids]
    params = {"user_id_type": _user_id_type()}
    resp = api_post(f"/task/v2/tasks/{task_id}/add_members", body={"members": members}, params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def get_task(task_id: str) -> dict:
    """Get task details."""
    params = {"user_id_type": _user_id_type()}
    resp = api_get(f"/task/v2/tasks/{task_id}", params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def delete_task(task_id: str) -> dict:
    """Delete a task (irreversible)."""
    resp = api_delete(f"/task/v2/tasks/{task_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def list_tasklist_tasks(tasklist_id: str, page_size: int = 50,
                        page_token: str | None = None) -> dict:
    """List tasks in a tasklist."""
    params = {"page_size": page_size, "user_id_type": _user_id_type()}
    if page_token:
        params["page_token"] = page_token
    resp = api_get(f"/task/v2/tasklists/{tasklist_id}/tasks", params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def create_tasklist(name: str) -> dict:
    """Create a tasklist and add the current user as viewer+editor."""
    params = {"user_id_type": _user_id_type()}
    body = {"name": name}
    resp = api_post("/task/v2/tasklists", body=body, params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    tasklist = resp.get("data", {}).get("tasklist", {})
    # Add current user as member so they can see it
    user_id = os.getenv("TASKPOOL_USER_ID", "")
    if user_id and tasklist.get("guid"):
        members = [{"id": user_id, "type": "user", "role": "editor"}]
        api_post(
            f"/task/v2/tasklists/{tasklist['guid']}/add_members",
            body={"members": members}, params=params,
        )
    return tasklist


def list_tasklists(page_size: int = 50, page_token: str | None = None) -> dict:
    """List all tasklists visible to the current identity."""
    params = {"page_size": page_size}
    if page_token:
        params["page_token"] = page_token
    resp = api_get("/task/v2/tasklists", params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def add_task_to_tasklist(task_id: str, tasklist_id: str) -> dict:
    """Add a task to a tasklist."""
    body = {"tasklist_guid": tasklist_id}
    resp = api_post(f"/task/v2/tasks/{task_id}/add_tasklist", body=body)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def delete_tasklist(tasklist_id: str) -> dict:
    """Delete a tasklist."""
    resp = api_delete(f"/task/v2/tasklists/{tasklist_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def create_subtask(parent_id: str, summary: str, description: str | None = None,
                   due: str | None = None, assignee: str | None = None) -> dict:
    """Create a subtask under a parent task."""
    body = {"summary": summary}
    if description:
        body["description"] = description
    if due:
        body["due"] = _parse_time(due)

    member_ids: set[str] = set()
    user_id = os.getenv("TASKPOOL_USER_ID", "")
    if user_id:
        member_ids.add(user_id)
    if assignee:
        member_ids.add(assignee)
    if member_ids:
        body["members"] = [{"id": mid, "type": "user", "role": "assignee"} for mid in member_ids]

    params = {"user_id_type": _user_id_type()}
    resp = api_post(f"/task/v2/tasks/{parent_id}/subtasks", body=body, params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("task", {})


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu tasks")
    parser.add_argument("--action", required=True,
                        choices=["create", "get", "complete", "uncomplete",
                                 "delete", "add-member", "list-tasklist",
                                 "create-subtask", "create-tasklist",
                                 "list-tasklists", "add-to-tasklist",
                                 "delete-tasklist"])
    parser.add_argument("--summary", help="Task title")
    parser.add_argument("--description", help="Task description")
    parser.add_argument("--due", help="Due date/time (ISO format: 2026-02-15 or 2026-02-15T14:00)")
    parser.add_argument("--start", help="Start date/time (ISO format)")
    parser.add_argument("--assignee", help="Assignee open_id")
    parser.add_argument("--task-id", help="Task GUID")
    parser.add_argument("--parent-id", help="Parent task GUID (for create-subtask)")
    parser.add_argument("--tasklist-id", help="Tasklist GUID")
    parser.add_argument("--name", help="Tasklist name (for create-tasklist)")
    parser.add_argument("--member-ids", help="Comma-separated member open_ids")
    parser.add_argument("--role", default="assignee", choices=["assignee", "follower"],
                        help="Member role (default: assignee)")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--page-token", help="Pagination token")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output for list-tasklist: only guid/summary/completed_at")
    args = parser.parse_args()

    if args.action == "create":
        if not args.summary:
            print("ERROR: --summary is required for create", file=sys.stderr)
            sys.exit(1)
        result = create_task(args.summary, args.description, args.due,
                             args.start, args.assignee)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "get":
        if not args.task_id:
            print("ERROR: --task-id is required for get", file=sys.stderr)
            sys.exit(1)
        result = get_task(args.task_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "complete":
        if not args.task_id:
            print("ERROR: --task-id is required for complete", file=sys.stderr)
            sys.exit(1)
        result = complete_task(args.task_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "uncomplete":
        if not args.task_id:
            print("ERROR: --task-id is required for uncomplete", file=sys.stderr)
            sys.exit(1)
        result = uncomplete_task(args.task_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "delete":
        if not args.task_id:
            print("ERROR: --task-id is required for delete", file=sys.stderr)
            sys.exit(1)
        result = delete_task(args.task_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "add-member":
        if not args.task_id or not args.member_ids:
            print("ERROR: --task-id and --member-ids are required for add-member", file=sys.stderr)
            sys.exit(1)
        ids = [x.strip() for x in args.member_ids.split(",")]
        result = add_members(args.task_id, ids, args.role)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "list-tasklist":
        if not args.tasklist_id:
            print("ERROR: --tasklist-id is required for list-tasklist", file=sys.stderr)
            sys.exit(1)
        result = list_tasklist_tasks(args.tasklist_id, args.page_size, args.page_token)
        if args.brief:
            items = result.get("items", [])
            brief = [{"guid": t.get("guid"), "summary": t.get("summary"),
                       "completed_at": t.get("completed_at")} for t in items]
            out = {"items": brief}
            if result.get("has_more"):
                out["has_more"] = True
                out["page_token"] = result.get("page_token")
            result = out
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "create-subtask":
        if not args.parent_id or not args.summary:
            print("ERROR: --parent-id and --summary are required for create-subtask", file=sys.stderr)
            sys.exit(1)
        result = create_subtask(args.parent_id, args.summary, args.description,
                                args.due, args.assignee)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "create-tasklist":
        if not args.name:
            print("ERROR: --name is required for create-tasklist", file=sys.stderr)
            sys.exit(1)
        result = create_tasklist(args.name)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "list-tasklists":
        result = list_tasklists(args.page_size, args.page_token)
        if args.brief:
            items = result.get("items", [])
            brief = [{"guid": t.get("guid"), "name": t.get("name")} for t in items]
            out = {"items": brief}
            if result.get("has_more"):
                out["has_more"] = True
                out["page_token"] = result.get("page_token")
            result = out
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "add-to-tasklist":
        if not args.task_id or not args.tasklist_id:
            print("ERROR: --task-id and --tasklist-id are required for add-to-tasklist", file=sys.stderr)
            sys.exit(1)
        result = add_task_to_tasklist(args.task_id, args.tasklist_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "delete-tasklist":
        if not args.tasklist_id:
            print("ERROR: --tasklist-id is required for delete-tasklist", file=sys.stderr)
            sys.exit(1)
        result = delete_tasklist(args.tasklist_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
