"""
多模型调度层：按调用角色固定分流，主失败即切备用一次。
"""

import logging
import os
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)


class MultiLLMDispatcher:
    """统一管理 Kimi / DeepSeek 调用与主备切换。"""

    PROVIDER_CONFIG = {
        "kimi": {
            "key_env": "MOONSHOT_API_KEY",
            "base_url_env": "MOONSHOT_BASE_URL",
            "default_base_url": "https://api.moonshot.cn/v1",
        },
        "deepseek": {
            "key_env": "DEEPSEEK_API_KEY",
            "base_url_env": "DEEPSEEK_BASE_URL",
            "default_base_url": "https://api.deepseek.com",
        },
    }

    def __init__(self, config):
        self.config = config
        self.clients: Dict[str, OpenAI] = {}
        self._init_clients()

    def _init_clients(self):
        for provider in self.PROVIDER_CONFIG:
            client = self._build_client(provider)
            if client is not None:
                self.clients[provider] = client
        if not self.clients:
            raise ValueError("未检测到可用LLM Key，请至少配置 MOONSHOT_API_KEY 或 DEEPSEEK_API_KEY")
        logger.info("LLM调度层初始化完成，可用通道: %s", ",".join(sorted(self.clients.keys())))

    def _build_client(self, provider: str) -> Optional[OpenAI]:
        conf = self.PROVIDER_CONFIG.get(provider)
        if not conf:
            return None
        api_key = os.getenv(conf["key_env"])
        if not api_key:
            return None
        base_url = os.getenv(conf["base_url_env"], conf["default_base_url"])
        return OpenAI(api_key=api_key, base_url=base_url)

    def _role_config(self, role: str) -> Tuple[str, str, str, str]:
        if role == "assist":
            return (
                getattr(self.config, "llm_assist_primary_provider", "deepseek"),
                getattr(self.config, "llm_assist_primary_model", "deepseek-chat"),
                getattr(self.config, "llm_assist_backup_provider", "kimi"),
                getattr(self.config, "llm_assist_backup_model", getattr(self.config, "llm_model", "")),
            )
        return (
            getattr(self.config, "llm_generation_primary_provider", "kimi"),
            getattr(self.config, "llm_generation_primary_model", getattr(self.config, "llm_model", "")),
            getattr(self.config, "llm_generation_backup_provider", "deepseek"),
            getattr(self.config, "llm_generation_backup_model", "deepseek-chat"),
        )

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        status = getattr(error, "status_code", None)
        if status in {429, 500, 502, 503, 504}:
            return True
        text = str(error).lower()
        patterns = [
            "429",
            "too many requests",
            "overload",
            "overloaded",
            "timeout",
            "timed out",
            "connection",
            "rate limit",
            "server error",
        ]
        return any(p in text for p in patterns)

    def _create(
        self,
        provider: str,
        model: str,
        messages: Any,
        temperature: float,
        max_tokens: int,
        stream: bool,
        timeout: Optional[int],
    ):
        client = self.clients.get(provider)
        if client is None:
            raise RuntimeError(f"LLM通道不可用: {provider}")
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        return client.chat.completions.create(**kwargs)

    def create_chat_completion(
        self,
        role: str,
        messages: Any,
        temperature: float = 0.1,
        max_tokens: int = 512,
        stream: bool = False,
        timeout: Optional[int] = None,
    ):
        primary_provider, primary_model, backup_provider, backup_model = self._role_config(role)
        timeout = timeout or getattr(self.config, "llm_request_timeout_seconds", 60)
        backup_available = backup_provider != primary_provider and backup_provider in self.clients

        # 主通道未配置或不可用时，直接切备，避免单点失败穿透。
        if primary_provider not in self.clients:
            if backup_available:
                logger.warning(
                    "LLM主通道不可用，直接切换备用通道: role=%s primary=%s backup=%s",
                    role,
                    primary_provider,
                    backup_provider,
                )
                response = self._create(
                    provider=backup_provider,
                    model=backup_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    timeout=timeout,
                )
                return response, backup_provider, backup_model
            raise RuntimeError(f"LLM主通道不可用且无备用通道: {primary_provider}")

        try:
            response = self._create(
                provider=primary_provider,
                model=primary_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                timeout=timeout,
            )
            return response, primary_provider, primary_model
        except Exception as primary_error:
            if (
                not backup_available
                or (
                    not self._is_retryable_error(primary_error)
                    and "llm通道不可用" not in str(primary_error).lower()
                )
            ):
                raise
            logger.warning(
                "LLM主通道失败，切换备用通道: role=%s primary=%s backup=%s err=%s",
                role,
                primary_provider,
                backup_provider,
                primary_error,
            )
            response = self._create(
                provider=backup_provider,
                model=backup_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                timeout=timeout,
            )
            return response, backup_provider, backup_model
