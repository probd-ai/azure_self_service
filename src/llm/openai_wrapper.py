"""
openai_wrapper.py — Adapts the OpenAI / Azure OpenAI SDK to BaseLLMClient.

This is the default backend used when USE_COXY=true, USE_AZURE_OPENAI=true,
or neither (plain OpenAI).

It wraps the SDK response objects and translates them into AgentResponse
so agent.py never touches the openai SDK directly.
"""
from openai import OpenAI, AzureOpenAI
from openai import RateLimitError as _OAIRateLimitError
from openai import APITimeoutError as _OAITimeoutError
from openai import APIConnectionError as _OAIConnectionError
from openai import APIStatusError as _OAIStatusError

from src.llm.base import (
    BaseLLMClient, AgentResponse, AgentChoice, AgentMessage, ToolCall, ToolFunction,
    LLMRateLimitError, LLMTimeoutError, LLMConnectionError, LLMStatusError,
)
from src.config.settings import settings


class OpenAIWrapper(BaseLLMClient):
    """
    Thin adapter around the openai SDK client.

    Works identically for:
      - Standard OpenAI  (api.openai.com)
      - Azure OpenAI     (your-resource.openai.azure.com)
      - Coxy             (localhost:3000  — OpenAI-compatible proxy)
    """

    def __init__(self):
        if settings.use_coxy:
            self._client = OpenAI(
                api_key=settings.coxy_api_key,
                base_url=settings.coxy_base_url,
            )
        elif settings.use_azure_openai:
            self._client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
            )
        else:
            self._client = OpenAI(api_key=settings.openai_api_key)

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str,
        temperature: float,
    ) -> AgentResponse:
        # Call the real SDK — this is the ONLY place in the whole project
        # that touches openai SDK objects directly
        try:
            raw = self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
            )
        except _OAIRateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except _OAITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except _OAIConnectionError as e:
            raise LLMConnectionError(str(e)) from e
        except _OAIStatusError as e:
            raise LLMStatusError(str(e), e.status_code) from e

        # Translate SDK response → AgentResponse
        choices = []
        for raw_choice in raw.choices:
            raw_msg = raw_choice.message

            tool_calls: list[ToolCall] = []
            if raw_msg.tool_calls:
                for tc in raw_msg.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        function=ToolFunction(
                            name=tc.function.name,
                            arguments=tc.function.arguments,
                        ),
                    ))

            choices.append(AgentChoice(
                finish_reason=raw_choice.finish_reason,
                message=AgentMessage(
                    role=raw_msg.role,
                    content=raw_msg.content,
                    tool_calls=tool_calls,
                ),
            ))

        return AgentResponse(choices=choices)
