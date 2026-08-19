"""
LLM 工厂模块
支持多种 LLM 提供商，通过配置文件切换
"""
import os
import yaml
from pathlib import Path
from typing import Optional, Any
from langchain_core.language_models import BaseChatModel


class LLMFactory:
    """LLM 工厂类，根据配置创建对应的 LLM 实例"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "llm_config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def _resolve_env_var(self, value: str) -> str:
        """解析环境变量引用 ${VAR_NAME}"""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1]
            return os.environ.get(env_name, value)
        return value

    def _get_provider_config(self, provider_name: str = None) -> dict:
        """获取指定提供商的配置"""
        if provider_name is None:
            provider_name = self.config.get("active_provider", "openai")
        providers = self.config.get("providers", {})
        if provider_name not in providers:
            raise ValueError(
                f"LLM 提供商 '{provider_name}' 未在配置文件中找到。"
                f"可用的提供商: {list(providers.keys())}"
            )
        return providers[provider_name]

    def create_llm(self, provider_name: str = None) -> BaseChatModel:
        """
        根据配置创建 LLM 实例
        
        支持的 provider 类型:
        - openai: OpenAI 或 OpenAI 兼容接口 (包括 Ollama)
        - deepseek: DeepSeek
        - zhipu: 智谱 AI
        - qwen: 通义千问
        """
        cfg = self._get_provider_config(provider_name)
        provider_type = cfg.get("provider", "openai")
        api_key = self._resolve_env_var(cfg.get("api_key", ""))
        base_url = cfg.get("base_url")
        model = cfg.get("model", "gpt-4o")
        temperature = cfg.get("temperature", 0.3)
        max_tokens = cfg.get("max_tokens", 4096)
        timeout = cfg.get("timeout", 60)

        if provider_type == "openai":
            return self._create_openai_llm(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "deepseek":
            return self._create_openai_llm(
                api_key=api_key,
                base_url=base_url or "https://api.deepseek.com",
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "zhipu":
            return self._create_openai_llm(
                api_key=api_key,
                base_url=base_url or "https://open.bigmodel.cn/api/paas/v4",
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        elif provider_type == "qwen":
            return self._create_openai_llm(
                api_key=api_key,
                base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商类型: {provider_type}")

    def _create_openai_llm(
        self,
        api_key: str,
        base_url: Optional[str],
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> BaseChatModel:
        """创建 OpenAI 兼容的 LLM 实例"""
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    def list_providers(self) -> list:
        """列出所有可用的提供商"""
        return list(self.config.get("providers", {}).keys())

    def get_active_provider(self) -> str:
        """获取当前活跃的提供商"""
        return self.config.get("active_provider", "openai")
