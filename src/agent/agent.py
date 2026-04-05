"""
agent.py — Agentic loop
LLM ↔ tools (list_directory + read_file) until a final answer is ready.
"""
import re
import json
from typing import Generator
from loguru import logger
from src.llm.base import BaseLLMClient, LLMRateLimitError, LLMTimeoutError, LLMConnectionError, LLMStatusError
from src.llm.openai_wrapper import OpenAIWrapper

from src.config.settings import settings
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.conversation import Session
from src.tools.fs_tools import list_directory, read_file, read_files, generate_tfvars_template, search_templates
from src.tools.index_builder import get_template_index, rebuild_index
from src.tools.bundle_tools import bundle_deployment_plan

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
            "name": "get_template_index",
            "description": (
                "Returns the terraform template navigation map. "
                "Call this FIRST at the start of every conversation to discover all available "
                "services, their template types (create / create_common_resource), and the "
                "exact list of files in each template (mandate_read_files). "
                "WARNING: This is a navigation MAP only — not source of truth. "
                "You MUST read every file listed in mandate_read_files AND every file in "
                "config_module.mandate_read_files for each template in your plan before "
                "presenting anything to the customer. Never plan from this index alone."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rebuild_index",
            "description": (
                "Force a full re-scan of all terraform templates and rebuild the navigation index. "
                "Use this if get_template_index returns unexpected results, or if you have reason "
                "to believe templates have been added or changed since startup."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
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
            "name": "read_files",
            "description": (
                "Read multiple files in a single call. "
                "ALWAYS prefer this over calling read_file() one file at a time. "
                "Use this to read all mandate_read_files for one or more templates at once, "
                "and all config_module.mandate_read_files in the same call. "
                "Pass the full list of paths you need upfront."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of relative file paths from project root. "
                            "E.g. ['terraform/config/main.tf', 'terraform/logic_app/create/main.tf', "
                            "'terraform/logic_app/create/variables.tf']"
                        )
                    }
                },
                "required": ["paths"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full content of a single file. "
                "Use read_files (plural) when reading more than one file — it is faster. "
                "Use this only when you need exactly one file."
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
    {
        "type": "function",
        "function": {
            "name": "bundle_deployment_plan",
            "description": (
                "Package the deployment plan into a downloadable zip bundle and return a download URL. "
                "Call this as the LAST step of every deployment plan, after you have: "
                "(1) identified all templates and their order, "
                "(2) called generate_tfvars_template() for each step. "
                "Pass the ordered steps list with template_path and tfvars_content per step. "
                "Return the download_url to the customer so they can download and run the bundle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": "Ordered list of deployment steps.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number":    {"type": "integer", "description": "1-based step order"},
                                "label":          {"type": "string",  "description": "Human-readable step name, e.g. 'Resource Group'"},
                                "template_path":  {"type": "string",  "description": "Path to template dir, e.g. 'terraform/resource_group/create/'"},
                                "tfvars_content": {"type": "string",  "description": "Full terraform.tfvars content from generate_tfvars_template()"}
                            },
                            "required": ["step_number", "label", "template_path", "tfvars_content"]
                        }
                    }
                },
                "required": ["steps"]
            }
        }
    },
]

# ── Tool executor ─────────────────────────────────────────────────────────────
TOOL_MAP = {
    "list_directory":           list_directory,
    "read_file":                read_file,
    "read_files":               read_files,
    "generate_tfvars_template": generate_tfvars_template,
    "search_templates":         search_templates,
    "get_template_index":       get_template_index,
    "rebuild_index":            rebuild_index,
    "bundle_deployment_plan":   bundle_deployment_plan,
}


def _execute_tool(name: str, arguments: dict) -> str:
    func = TOOL_MAP.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    result = func(**arguments)
    return json.dumps(result, indent=2)


# ── LLM client factory ────────────────────────────────────────────────────────
def _get_client() -> BaseLLMClient:
    """
    Returns a BaseLLMClient implementation selected by env vars:
      USE_CUSTOM_LLM=true  → src/llm/custom_client.py :: CustomLLMClient
      USE_COXY=true        → OpenAIWrapper (Coxy proxy)
      USE_AZURE_OPENAI=true→ OpenAIWrapper (Azure backend)
      (default)            → OpenAIWrapper (standard OpenAI)
    """
    if settings.use_custom_llm:
        from src.llm.custom_client import CustomLLMClient      # lazy import — only when needed
        return CustomLLMClient()
    if settings.use_anthropic:
        from src.llm.anthropic_wrapper import AnthropicWrapper  # lazy import — only when needed
        return AnthropicWrapper()
    return OpenAIWrapper()


# ── Streaming agent loop ─────────────────────────────────────────────────────
def stream_agent(
    session: Session, user_message: str, max_iterations: int = 20
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
            response = client.complete(
                model=settings.model_name,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except LLMRateLimitError:
            msg = "The AI service is currently rate-limited. Please wait a moment and try again."
            logger.warning("LLM rate limit hit")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return
        except LLMTimeoutError:
            msg = "The AI service timed out. Please try again."
            logger.warning("LLM request timed out")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return
        except LLMConnectionError as e:
            msg = f"Cannot reach the AI service. Is the LLM backend running? ({e})"
            logger.error(f"LLM connection error: {e}")
            session.add("assistant", msg)
            yield {"type": "done", "reply": msg}
            return
        except LLMStatusError as e:
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
                        "type": tc.type,
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
def run_agent(session: Session, user_message: str, max_iterations: int = 20) -> str:
    """Thin wrapper around stream_agent — drains events and returns the final reply."""
    for event in stream_agent(session, user_message, max_iterations):
        if event["type"] == "done":
            return event["reply"]
    return "I wasn't able to gather enough information to complete the plan. Please try rephrasing your request."
