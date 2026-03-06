#!/usr/bin/env python3
"""
Fornax Hook for Claude Code

This hook integrates Claude Code with Fornax for tracing and observability.
It captures conversation interactions and sends them to Fornax for analysis.

Usage:
    1. Configure this hook in ~/.claude/settings.json
    2. Set environment variables in project's .claude/settings.local.json
    3. Run Claude Code as normal - traces will be sent automatically
"""

import json
import os
import sys
import glob
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Debug mode
DEBUG = os.environ.get("CC_FORNAX_DEBUG", "").lower() == "true"


def debug_log(message: str):
    """Print debug message if debug mode is enabled."""
    if DEBUG:
        print(f"[FORNAX DEBUG] {datetime.now().isoformat()} - {message}", file=sys.stderr)


def get_state_file_path(conversation_file: str) -> str:
    """Get the state file path for tracking processed messages."""
    state_dir = Path.home() / ".claude" / "fornax_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create a unique hash for the conversation file
    file_hash = hashlib.md5(conversation_file.encode()).hexdigest()[:12]
    return str(state_dir / f"state_{file_hash}.json")


def load_state(state_file: str) -> Dict[str, Any]:
    """Load the processing state from file."""
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            debug_log(f"Error loading state: {e}")
    return {"last_processed_line": 0, "session_id": None}


def save_state(state_file: str, state: Dict[str, Any]):
    """Save the processing state to file."""
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        debug_log(f"Error saving state: {e}")


def find_latest_conversation_file() -> Optional[str]:
    """Find the most recently modified conversation file."""
    claude_dir = Path.home() / ".claude" / "projects"

    if not claude_dir.exists():
        debug_log(f"Claude projects directory not found: {claude_dir}")
        return None

    # Find all .jsonl files recursively
    jsonl_files = list(claude_dir.rglob("*.jsonl"))

    if not jsonl_files:
        debug_log("No conversation files found")
        return None

    # Sort by modification time, most recent first
    jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    latest_file = str(jsonl_files[0])
    debug_log(f"Found latest conversation file: {latest_file}")
    return latest_file


def read_conversation_messages(file_path: str, start_line: int = 0) -> List[Dict[str, Any]]:
    """Read messages from conversation file starting from a specific line."""
    messages = []

    try:
        with open(file_path, 'r') as f:
            for i, line in enumerate(f):
                if i < start_line:
                    continue
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        msg['_line_number'] = i
                        messages.append(msg)
                    except json.JSONDecodeError as e:
                        debug_log(f"Error parsing line {i}: {e}")
    except Exception as e:
        debug_log(f"Error reading conversation file: {e}")

    return messages


def extract_tool_info(content: Any) -> Dict[str, Any]:
    """Extract tool information from message content."""
    tool_info = {
        "name": None,
        "input": None,
        "output": None,
        "type": None
    }

    if isinstance(content, dict):
        if content.get("type") == "tool_use":
            tool_info["name"] = content.get("name")
            tool_info["input"] = content.get("input")
            tool_info["type"] = "tool_use"
        elif content.get("type") == "tool_result":
            tool_info["output"] = content.get("content")
            tool_info["type"] = "tool_result"
            tool_info["name"] = content.get("tool_use_id")

    return tool_info


def is_tool_result_message(msg: Dict[str, Any]) -> bool:
    """Check if a message is a tool_result (not a real user input)."""
    message = msg.get("message", {})
    content = message.get("content", [])

    if isinstance(content, list) and len(content) > 0:
        # Check if all items are tool_result type
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                return True
    return False


def extract_tool_result_from_message(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool_result items from a user message."""
    results = []
    message = msg.get("message", {})
    content = message.get("content", [])

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                results.append(item)
    return results


def group_messages_into_turns(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group messages into conversation turns (user -> assistant -> tool_results).

    A turn represents a complete interaction cycle:
    - User's real input (not tool_result)
    - Assistant's responses (may include multiple tool calls)
    - Tool results (collected and associated with their tool calls)

    tool_result messages are NOT treated as new turns, they belong to the current turn.
    """
    turns = []
    current_turn = None

    for msg in messages:
        msg_type = msg.get("type")
        role = msg.get("role")
        message = msg.get("message", {})
        message_role = message.get("role", "")

        # Check if this is a user message
        is_user_msg = msg_type == "user" or role == "user" or message_role == "user"

        if is_user_msg:
            # Check if this is a tool_result message (should not start a new turn)
            if is_tool_result_message(msg):
                # Extract tool results and add to current turn
                if current_turn:
                    tool_results = extract_tool_result_from_message(msg)
                    current_turn["tool_results"].extend(tool_results)
            else:
                # This is a real user input, start a new turn
                if current_turn:
                    turns.append(current_turn)
                current_turn = {
                    "user_message": msg,
                    "assistant_messages": [],
                    "tool_calls": [],
                    "tool_results": [],
                    "start_line": msg.get("_line_number", 0)
                }
        elif msg_type == "assistant" or role == "assistant" or message_role == "assistant":
            if current_turn:
                current_turn["assistant_messages"].append(msg)
                # Extract tool calls from content (content is nested under msg["message"])
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            current_turn["tool_calls"].append(item)

    # Don't forget the last turn
    if current_turn:
        turns.append(current_turn)

    return turns


def format_message_for_trace(msg: Dict[str, Any]) -> str:
    """Format a message for trace input/output."""
    content = msg.get("content", msg.get("message", ""))

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    parts.append(f"[Tool: {item.get('name')}]")
                elif item.get("type") == "tool_result":
                    result = item.get("content", "")
                    if isinstance(result, str) and len(result) > 500:
                        result = result[:500] + "..."
                    parts.append(f"[Tool Result: {result}]")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    elif isinstance(content, str):
        return content
    else:
        return str(content)


def format_message_to_dict(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Format a message for trace, returning the message dict directly."""
    # msg already has the correct structure with role and content
    message = msg.get("message", msg)
    return message


def format_messages_to_dict(messages: List[Dict[str, Any]]) -> Any:
    """Format multiple messages into a single dict, merging content if needed."""
    from bytedance.fornax.infra.trace import Choice

    if not messages:
        return []
    if len(messages) == 1:
        return [Choice(message=format_message_to_dict(messages[0]))]

    res = []
    for msg in messages:
        res.append(Choice(message=format_message_to_dict(msg)))
    return res


    # Merge multiple messages: use the first message's role, combine content
    role = messages[0].get("role", "assistant")
    contents = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text from content list
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    contents.append(item.get("text", ""))
        elif isinstance(content, str):
            contents.append(content)
    return {"role": role, "content": "\n".join(contents)}


def send_to_fornax(turns: List[Dict[str, Any]], session_id: str):
    """Send conversation turns to Fornax for tracing."""
    try:
        from bytedance.fornax.infra import initialize, FornaxClient
        from bytedance.fornax.infra.trace import (
            QueryInput, QueryContent, QueryOutput,
            ModelInput, ModelOutput, Message, Choice, Runtime
        )
    except ImportError as e:
        debug_log(f"Fornax SDK not installed: {e}")
        print("Error: Fornax SDK not installed. Please install it with: pip install fornax-sdk", file=sys.stderr)
        return

    # Get credentials from environment
    ak = os.environ.get("FORNAX_AK", "")
    sk = os.environ.get("FORNAX_SK", "")

    if not ak or not sk:
        debug_log("FORNAX_AK or FORNAX_SK not set")
        print("Error: FORNAX_AK and FORNAX_SK environment variables must be set", file=sys.stderr)
        return

    # Initialize Fornax
    try:
        region = os.environ.get("FORNAX_REGION", "cn")
        initialize(ak, sk, fornax_custom_region=region)
        debug_log("Fornax initialized successfully")
    except Exception as e:
        debug_log(f"Error initializing Fornax: {e}")
        return

    try:
        # Create a single root span for the entire request
        root_span = FornaxClient.start_span(
            f"claude_code_request",
            "claude_code"
        )
        root_span.set_tag({
            "session_id": session_id,
            "total_turns": len(turns),
            "source": "claude_code"
        })
        root_span.set_baggage({"session_id": session_id})
        root_span.set_runtime(Runtime(library="claude-code"))

        # Process each turn as a child span under the root
        for i, turn in enumerate(turns):
            try:
                # Create turn span as child of root
                turn_span = FornaxClient.start_span(
                    f"turn_{i}",
                    "turn"
                )
                turn_span.set_tag({
                    "turn_index": i
                })
                turn_span.set_runtime(Runtime(library="claude-code"))

                # Create query span for user input
                if turn.get("user_message"):
                    query_span = FornaxClient.start_query_span("user_input")
                    query_span.set_runtime(Runtime(library="claude-code"))
                    user_content = format_message_for_trace(turn["user_message"])
                    query_span.set_input(QueryInput([
                        QueryContent(content_type="text", text=user_content)
                    ]))
                    query_span.set_tag({"role": "user"})
                    query_span.finish()

                # Create model span for assistant response
                if turn.get("assistant_messages"):
                    model_span = FornaxClient.start_model_span("assistant_response")
                    model_span.set_runtime(Runtime(library="claude-code"))
                    model_span.set_model_name("claude-code")

                    model_span.set_input(ModelInput(
                        messages=[format_message_to_dict(turn.get("user_message", {}))]
                    ))
                    model_span.set_output(ModelOutput(
                        choices=format_messages_to_dict(turn["assistant_messages"])
                    ))
                    model_span.finish()

                # Create spans for tool calls
                for tool_call in turn.get("tool_calls", []):
                    tool_span = FornaxClient.start_span(
                        f"tool_{tool_call.get('name', 'unknown')}",
                        "tool"
                    )
                    tool_span.set_tag({
                        "tool_name": tool_call.get("name"),
                        "tool_id": tool_call.get("id")
                    })
                    tool_span.set_runtime(Runtime(library="claude-code"))
                    tool_span.set_input(json.dumps(tool_call.get("input", {}), ensure_ascii=False)[:2000])

                    # Find matching tool result
                    tool_id = tool_call.get("id")
                    for result in turn.get("tool_results", []):
                        if result.get("tool_use_id") == tool_id:
                            result_content = result.get("content", "")
                            if isinstance(result_content, str) and len(result_content) > 2000:
                                result_content = result_content[:2000] + "..."
                            tool_span.set_output(str(result_content))
                            break

                    tool_span.finish()

                turn_span.finish()
                debug_log(f"Processed turn {i}")

            except Exception as e:
                debug_log(f"Error processing turn {i}: {e}")
                continue

        root_span.finish()
        debug_log(f"Sent request with {len(turns)} turns to Fornax")

    except Exception as e:
        debug_log(f"Error creating root span: {e}")

    # Flush traces
    try:
        FornaxClient.flush_trace()
        debug_log("Traces flushed successfully")
    except Exception as e:
        debug_log(f"Error flushing traces: {e}")


def main():
    """Main entry point for the Fornax hook."""
    debug_log("Fornax hook started")

    # Check if tracing is enabled
    if os.environ.get("TRACE_TO_FORNAX", "").lower() != "true":
        debug_log("TRACE_TO_FORNAX is not set to 'true', skipping")
        return

    # Find the latest conversation file
    conversation_file = find_latest_conversation_file()
    if not conversation_file:
        debug_log("No conversation file found")
        return

    # Load state
    state_file = get_state_file_path(conversation_file)
    state = load_state(state_file)

    # Read new messages
    messages = read_conversation_messages(conversation_file, state["last_processed_line"])

    # Extract session ID from messages (use sessionId field from JSONL)
    session_id = None
    for msg in messages:
        if msg.get("sessionId"):
            session_id = msg.get("sessionId")
            break

    # Fallback to state or generate new session ID if not found in messages
    if not session_id:
        if state.get("session_id"):
            session_id = state["session_id"]
        else:
            session_id = f"claude_code_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"

    state["session_id"] = session_id
    debug_log(f"Session ID: {session_id}")

    if not messages:
        debug_log("No new messages to process")
        return

    debug_log(f"Found {len(messages)} new messages")

    # Group messages into turns
    turns = group_messages_into_turns(messages)
    debug_log(f"Grouped into {len(turns)} turns")

    if turns:
        # Send to Fornax
        send_to_fornax(turns, session_id)

        # Update state
        last_line = max(msg.get("_line_number", 0) for msg in messages) + 1
        state["last_processed_line"] = last_line
        save_state(state_file, state)
        debug_log(f"State updated, last processed line: {last_line}")

    debug_log("Fornax hook completed")


if __name__ == "__main__":
    main()
