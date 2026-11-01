"""Pydantic AI + DeepSeek adapter with explicit validation and bounded requests."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib.metadata import version
import os
from pathlib import Path
import stat

import httpx2
import openai
from pydantic import ValidationError
from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import TextPart, ToolCallPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.usage import RunUsage, UsageLimits

from .analysis_models import AnalysisOutput, AnalysisValidationError, strict_json, validate_analysis


class ModelError(Exception):
    def __init__(self, code, message, *, requests=None, model=None, request_id=None):
        super().__init__(message)
        self.code, self.message, self.requests = code, message, requests
        self.model, self.request_id = model, request_id


def validate_api_key(key):
    if not isinstance(key, str) or not key.strip():
        raise ModelError("model_unavailable", "未配置 DEEPSEEK_API_KEY")
    if any(c.isspace() for c in key) or any(ord(c) > 127 for c in key):
        raise ModelError("credential_config", "DEEPSEEK_API_KEY 格式无效")
    return key


def load_api_key(env_file=".env"):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key is None and env_file is not None:
        path = Path(env_file)
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise ModelError("credential_config", "密钥文件须为仅当前用户可读的常规文件")
            entries = [line.split("=", 1)[1].strip() for line in path.read_text(
                encoding="utf-8-sig").splitlines() if line.startswith("DEEPSEEK_API_KEY=")]
            if len(entries) != 1:
                raise ModelError("credential_config", "密钥文件需包含一个 DEEPSEEK_API_KEY 项")
            key = entries[0]
            if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
                key = key[1:-1]
        except FileNotFoundError:
            key = None
        except (OSError, UnicodeError):
            raise ModelError("credential_config", "无法读取密钥文件") from None
    return validate_api_key(key)


@dataclass(frozen=True)
class Completion:
    content: str
    model: str | None
    request_id: str | None = None
    requests: int = 1


class BoundedStream(httpx2.AsyncByteStream):
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > self.limit:
                raise ModelError("model_response_limit", "模型响应超过大小限制")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class ResponseCapture(WrapperModel):
    def __init__(self, wrapped, tool_run=None):
        super().__init__(wrapped)
        self.responses = []
        self.tool_run = tool_run

    async def request(self, messages, model_settings, model_request_parameters):
        if self.tool_run is not None:
            self.tool_run.before_request(messages)
        response = await super().request(messages, model_settings, model_request_parameters)
        self.responses.append(response)
        if self.tool_run is not None:
            self.tool_run.after_response(response)
        return response


class DeepSeekClient:
    endpoint = "https://api.deepseek.com/chat/completions"
    max_response_bytes = 512 * 1024
    manages_retries = True
    framework = "pydantic-ai"
    output_tool_name = "notice_analysis"

    def __init__(self, api_key=None, *, env_file=".env", timeout=60, max_tokens=4096,
                 agent_model=None, http_transport=None):
        self._api_key = api_key
        self.env_file, self.timeout, self.max_tokens = env_file, timeout, max_tokens
        self.model, self.provider = "deepseek-flash", "deepseek"
        self.framework_version = version("pydantic-ai-slim")
        self.agent_model, self.http_transport = agent_model, http_transport
        self.last_outputs = []
        # Keep the command's JSON output free of the framework's optional promotional banner.
        os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

    async def _guard_response(self, response):
        if 300 <= response.status_code < 400:
            raise ModelError("model_redirect", "模型接口重定向已拒绝")
        if response.is_stream_consumed:
            if len(response.content) > self.max_response_bytes:
                raise ModelError("model_response_limit", "模型响应超过大小限制")
        else:
            response.stream = BoundedStream(response.stream, self.max_response_bytes)

    def _output_content(self, response):
        for part in response.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == self.output_tool_name:
                return part.args_as_json_str()
        return "".join(p.content for p in response.parts if isinstance(p, TextPart))

    async def _run_agent(self, model, messages, context, usage, tool_run=None):
        instructions = "\n".join(m["content"] for m in messages if m["role"] == "system")
        prompt = "\n".join(m["content"] for m in messages if m["role"] == "user")
        captured = ResponseCapture(model, tool_run)
        agent = Agent(
            captured, output_type=ToolOutput(AnalysisOutput, name=self.output_tool_name,
                                            strict=False, max_retries=1), deps_type=dict,
            system_prompt=instructions, name="seu-pulse-information",
            retries={"output": 1, "tools": 0},
            tools=tool_run.tools() if tool_run is not None else (),
            model_settings={"max_tokens": self.max_tokens,
                            "timeout": tool_run.limits.request_timeout if tool_run else self.timeout, "max_retries": 0,
                            "extra_body": {"thinking": {"type": "disabled"}}},
        )

        @agent.output_validator
        async def validate(ctx: RunContext[dict], output: AnalysisOutput) -> AnalysisOutput:
            if not captured.responses:
                raise ModelRetry("缺少模型原始响应")
            response = captured.responses[-1]
            raw = self._output_content(response)
            try:
                if tool_run is not None:
                    tool_run.validate_final()
                elif any(isinstance(p, ToolCallPart) and p.tool_name != self.output_tool_name
                       for p in response.parts):
                    raise AnalysisValidationError("不允许请求业务或任意工具")
                if response.finish_reason not in (None, "stop", "tool_call", "tool_calls"):
                    raise AnalysisValidationError("模型输出未正常结束")
                parsed = strict_json(raw)
                if context is not None:
                    validate_analysis(parsed, ctx.deps)
                else:
                    AnalysisOutput.model_validate(parsed, strict=True)
            except (AnalysisValidationError, ValidationError) as exc:
                message = str(exc) if isinstance(exc, AnalysisValidationError) else "结构字段校验失败"
                raise ModelRetry(message + "。只修正无依据的字段，不重写或拼接原文；"
                                 "未知组成部分用 null。同一报名目标只保留有完整原文依据的一条截止，"
                                 "不要重复抄录报名区间推导另一个截止。") from None
            return output

        try:
            result = await agent.run(prompt, deps=context or {}, usage=usage,
                                     usage_limits=UsageLimits(request_limit=(tool_run.limits.max_requests
                                                                           if tool_run else 2)), infer_name=False)
            response = result.response
            raw = self._output_content(response)
            return Completion(raw, response.model_name, response.provider_response_id, usage.requests)
        finally:
            self.last_outputs = [
                {"model": m.model_name, "request_id": m.provider_response_id,
                 "finish_reason": m.finish_reason,
                 "content": self._output_content(m)}
                for m in captured.responses
            ]

    async def _run(self, messages, context, usage, tool_run=None):
        if self.agent_model is not None:
            return await self._run_agent(self.agent_model, messages, context, usage, tool_run)
        key = validate_api_key(self._api_key) if self._api_key is not None else load_api_key(self.env_file)
        async with httpx2.AsyncClient(
            timeout=tool_run.limits.request_timeout if tool_run else self.timeout,
            follow_redirects=False, transport=self.http_transport,
            event_hooks={"response": [self._guard_response]},
        ) as http:
            async with openai.AsyncOpenAI(
                api_key=key, base_url="https://api.deepseek.com",
                timeout=tool_run.limits.request_timeout if tool_run else self.timeout,
                max_retries=0, http_client=http, organization="", project="",
            ) as sdk:
                model = OpenAIChatModel(
                    self.model, provider=DeepSeekProvider(openai_client=sdk),
                    profile=OpenAIModelProfile(openai_chat_supports_max_completion_tokens=False))
                return await self._run_agent(model, messages, context, usage, tool_run)

    def complete(self, messages, *, context=None, tool_run=None):
        self.last_outputs = []
        usage = RunUsage()
        try:
            return asyncio.run(asyncio.wait_for(
                self._run(messages, context, usage, tool_run),
                timeout=tool_run.limits.run_timeout if tool_run else self.timeout * 2 + 5))
        except Exception as exc:
            root = exc
            chain = []
            for _ in range(8):
                chain.append(root)
                if isinstance(root, ModelError) or root.__cause__ is None:
                    break
                root = root.__cause__
            http_error = next((e for e in chain if isinstance(
                e, (ModelHTTPError, openai.APIStatusError))), None)
            if isinstance(root, ModelError):
                code, message = root.code, root.message
            elif isinstance(exc, (TimeoutError, asyncio.TimeoutError)) and tool_run is not None:
                code, message = "agent_timeout", "Agent 运行达到总时限"
            elif http_error is not None:
                status = http_error.status_code
                code = "model_auth" if status in (401, 403) else (
                    "model_rate_limit" if status == 429 else "model_http")
                message = f"模型接口 HTTP {status}"
            elif any(isinstance(e, (openai.APIConnectionError, openai.APITimeoutError,
                                    httpx2.RequestError, OSError, TimeoutError, asyncio.TimeoutError))
                     for e in chain):
                code, message = "model_network", "模型网络请求失败或超时"
            elif isinstance(exc, UsageLimitExceeded):
                code, message = "model_request_limit", "模型调用达到请求次数上限"
            elif isinstance(exc, UnexpectedModelBehavior):
                last = self.last_outputs[-1] if self.last_outputs else None
                code = ("invalid_output" if last and last["finish_reason"] in {"tool_call", "tool_calls"} else
                        "model_blank" if last and not last["content"].strip() else
                        "model_incomplete" if last and last["finish_reason"] == "length" else "invalid_output")
                message = "Pydantic AI 输出校验失败，未生成有效分析"
            else:
                code, message = "model_framework", "模型框架执行失败: " + type(exc).__name__
            last = self.last_outputs[-1] if self.last_outputs else {}
            raise ModelError(code, message, requests=usage.requests, model=last.get("model"),
                             request_id=last.get("request_id")) from None
