"""
agent.py — Agentic loop
LLM ↔ tools (list_directory + read_file) until a final answer is ready.
"""
import re
import json
from typing import Generator
from openai import AzureOpenAI, OpenAI
from openai import RateLimitError, APIStatusError, APIConnectionError, APITimeoutError
from loguru import logger

from src.config.settings import settings
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.conversation import Session
from src.tools.fs_tools import list_directory, read_file, find_dependencies, generate_tfvars_template, search_templates

# ── Guard: patterns that attempt to extract the system prompt ─────────────────
_PROMPT_PROBE_RE = re.compile(
    r"system\s*prompt|your\s*(instructions?|rules?|prompt|directives?|guidelines?)|"
    r"how\s+(are\s+you\s+)?programmed|what\s+(were\s+you\s+)?told|"
    r"ignore\s+(previous|prior|above|all)\s*(instructions?|prompt)?|"
    r"(reveal|show|repeat|print|output|tell\s+me)\s+(your\s+)?(prompt|instructions?|rules?)|"
    r"jailbreak|act\s+as\s+(?!azure)|pretend\s+you\s+are|you\s+are\s+now\s+(?!an?\s+azure)",
    re.IGNORECASE,
)

_CONFIDENTIAL_REPLY = (
    "That information is confidential. I'm here to help you plan and understand "
    "Azure deployments — what would you like to deploy today?"
)

# ── Tool definitions sent to LLM ─────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List contents of a directory. Use to explore terraform/ folder structure "
                "and discover available services, template types, and files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root, e.g. 'terraform/' or 'terraform/aks/create'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full content of a file. Use to read README.md, main.tf (for data{} dependencies), "
                "variables.tf (for required inputs), and outputs.tf (for exposed values)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root, e.g. 'terraform/aks/create/main.tf'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_dependencies",
            "description": (
                "Parse a template's main.tf and extract ALL data{} blocks to return a guaranteed-correct "
                "list of which other templates must be deployed first. "
                "Use this INSTEAD of manually reading main.tf to find dependencies — it is faster and more accurate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to main.tf or its parent directory, e.g. 'terraform/aks/create/'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_tfvars_template",
            "description": (
                "Parse a template's variables.tf and generate a complete, ready-to-paste terraform.tfvars file. "
                "Use this INSTEAD of manually reading variables.tf — it gives the user a copy-pasteable file "
                "with all variables, types, descriptions, defaults and <REPLACE_ME> placeholders. "
                "Always call this when producing a deployment plan step."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to variables.tf or its parent directory, e.g. 'terraform/aks/create/'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_templates",
            "description": (
                "Full-text search across all Terraform template README files for a keyword. "
                "Use this when the user asks a vague question like 'which templates support private endpoints?' "
                "or 'what can I deploy?' — much faster than reading every README individually."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Word or phrase to search for, e.g. 'private endpoint' or 'autoscaling'"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
]

# ── Tool executor ─────────────────────────────────────────────────────────────
TOOL_MAP = {
    "list_directory":         list_directory,
    "read_file":              read_file,
    "find_dependencies":      find_dependencies,
    "generate_tfvars_template": generate_tfvars_template,
    "search_templates":       search_templates,
}


def _execute_tool(name: str, arguments: dict) -> str:
    func = TOOL_MAP.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    result = func(**arguments)
    return json.dumps(result, indent=2)


# ── LLM client factory ────────────────────────────────────────────────────────
def _get_client():
    if settings.use_coxy:
        # Coxy exposes a local OpenAI-compatible API backed by GitHub Copilot.
        # Use a dummy key '_' — Coxy uses its own token set via its admin UI.
        return OpenAI(
            api_key=settings.coxy_api_key,
            base_url=settings.coxy_base_url,
        )
    if settings.use_azure_openai:
        return AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
    return OpenAI(api_key=settings.openai_api_key)


# ── Streaming agent loop ─────────────────────────────────────────────────────
def stream_agent(
    session: Session, user_message: str, max_iterations: int = 15
) -> Generator[dict, None, None]:
    """
    Agentic loop that yields typed status events so the UI can show live progress.

    Event shapes
    ------------
    thinking  : {"type": "thinking", "text": str}
    tool_call : {"type": "tool_call", "tool": str, "args": dict}
    tool_done : {"type": "tool_done", "tool": str, "summary": str}
    done      : {"type": "done", "reply": str}
    """
    client = _get_client()

    # ── Guard: block prompt-extraction and jailbreak attempts ─────────────────
    if _PROMPT_PROBE_RE.search(user_message):
        logger.warning(f"Prompt probe attempt blocked: {user_message!r}")
        session.add("user", user_message)
        session.add("assistant", _CONFIDENTIAL_REPLY)
        yield {"type": "done", "reply": _CONFIDENTIAL_REPLY}
        return

    session.add("user", user_message)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + session.to_openai_format()

    for iteration in range(max_iterations):
        thinking_text = "Analyzing your request\u2026" if iteration == 0 else "Reviewing results\u2026"
        yield {"type": "thinking", "text": thinking_text}
        logger.debug(f"Agent iteration {iteration + 1}")

        try:
            response = client.chat.completions.create(
                model=settings.model_name,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except RateLimitError:
            msg = "The AI service is currently rate-limited. Please wait a moment and try again."
            logger.warning("LLM rate limit hit")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return
        except APITimeoutError:
            msg = "The AI service timed out. Please try again."
            logger.warning("LLM request timed out")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return
        except APIConnectionError as e:
            msg = f"Cannot reach the AI service. Is Coxy/the LLM backend running? ({e})"
            logger.error(f"LLM connection error: {e}")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return
        except APIStatusError as e:
            msg = f"The AI service returned an error (HTTP {e.status_code}). Please try again."
            logger.error(f"LLM API error {e.status_code}: {e.message}")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return

        choice = response.choices[0]

        # ── Final answer ──────────────────────────────────────────────────────
        if choice.finish_reason == "stop":
            final_text = choice.message.content
            session.add("assistant", final_text)
            logger.info(f"Agent finished after {iteration + 1} iterations")
            yield {"type": "done", "reply": final_text}
            return

        # ── Tool calls ────────────────────────────────────────────────────────
        if choice.finish_reason == "tool_calls":
            assistant_msg = choice.message
            messages.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in assistant_msg.tool_calls
                ]
            })

            for tool_call in assistant_msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                logger.debug(f"Tool call: {name}({args})")

                yield {"type": "tool_call", "tool": name, "args": args}

                result = _execute_tool(name, args)

                # Build a short human-readable summary for the status log
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, list):
                        n = len(parsed)
                        summary = f"{n} item{'s' if n != 1 else ''}"
                    elif isinstance(parsed, dict) and "content" in parsed:
                        n = len(parsed["content"].splitlines())
                        summary = f"{n} line{'s' if n != 1 else ''}"
                    elif isinstance(parsed, dict) and "error" in parsed:
                        summary = "error"
                    else:
                        summary = "ok"
                except Exception:
                    summary = "ok"

                yield {"type": "tool_done", "tool": name, "summary": summary}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            continue  # next iteration with tool results in context

        # Unexpected finish reason
        break

    # Fallback if max iterations hit
    fallback = "I wasn't able to gather enough information to complete the plan. Please try rephrasing your request."
    session.add("assistant", fallback)
    yield {"type": "done", "reply": fallback}


# ── Synchronous wrapper ───────────────────────────────────────────────────────
def run_agent(session: Session, user_message: str, max_iterations: int = 15) -> str:
    """Thin wrapper around stream_agent — drains events and returns the final reply."""
    for event in stream_agent(session, user_message, max_iterations):
        if event["type"] == "done":
            return event["reply"]
    return "I wasn't able to gather enough information to complete the plan. Please try rephrasing your request."
