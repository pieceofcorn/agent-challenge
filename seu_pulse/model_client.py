"""Bounded DeepSeek adapter. This client has no tools or database access."""
from __future__ import annotations

from dataclasses import dataclass
from http.client import HTTPException
import json
import os
from pathlib import Path
import stat
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ModelError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelError("model_redirect", "模型接口重定向已拒绝")


@dataclass(frozen=True)
class Completion:
    content: str
    model: str | None
    request_id: str | None = None


class DeepSeekClient:
    endpoint = "https://api.deepseek.com/chat/completions"
    max_response_bytes = 512 * 1024

    def __init__(self, api_key=None, *, env_file=".env", timeout=60, max_tokens=4096, opener=None):
        self._api_key = api_key
        self.env_file = env_file
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.model = "deepseek-flash"
        self.provider = "deepseek"
        self.opener = opener or build_opener(NoRedirect())

    def complete(self, messages):
        key = validate_api_key(self._api_key) if self._api_key is not None else load_api_key(self.env_file)
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "thinking": {"type": "disabled"}, "max_tokens": self.max_tokens,
                   "response_format": {"type": "json_object"}}
        request = Request(self.endpoint, json.dumps(payload, ensure_ascii=False).encode(),
                          {"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                          method="POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    raise ModelError("model_response_limit", "模型响应超过大小限制")
                data = json.loads(raw)
        except HTTPError as exc:
            code = "model_auth" if exc.code in (401, 403) else (
                "model_rate_limit" if exc.code == 429 else "model_http")
            raise ModelError(code, f"模型接口 HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError, HTTPException):
            raise ModelError("model_network", "模型网络请求失败或超时") from None
        except (ValueError, UnicodeError, RecursionError):
            raise ModelError("model_response", "模型接口响应不是有效 JSON") from None
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ModelError("model_incomplete", "模型输出未正常结束")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ModelError("model_blank", "模型返回空白内容")
            model, request_id = data.get("model"), data.get("id")
            if model is not None and not isinstance(model, str):
                raise ValueError()
            if request_id is not None and not isinstance(request_id, str):
                raise ValueError()
            return Completion(content, model, request_id)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ModelError("model_response", "模型接口响应结构无效") from None
