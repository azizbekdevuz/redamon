"""LLM initialization and project settings helpers."""

import logging

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from project_settings import load_project_settings

logger = logging.getLogger(__name__)


def parse_model_provider(model_name: str) -> tuple[str, str]:
    """
    Parse provider and API model name from the stored model identifier.

    Prefix convention:
      - "custom/<configId>"   → ("custom", "<configId>")
      - "openrouter/<model>"  → ("openrouter", "<model>")
      - "bedrock/<model>"     → ("bedrock", "<model>")
      - "claude-*"            → ("anthropic", "claude-*")
      - anything else         → ("openai", "<model>")

    Legacy (still supported for backward compat):
      - "openai_compat/<model>" → ("openai_compat", "<model>")
    """
    if model_name.startswith("custom/"):
        return ("custom", model_name[len("custom/"):])
    elif model_name.startswith("openai_compat/"):
        return ("openai_compat", model_name[len("openai_compat/"):])
    elif model_name.startswith("openrouter/"):
        return ("openrouter", model_name[len("openrouter/"):])
    elif model_name.startswith("bedrock/"):
        return ("bedrock", model_name[len("bedrock/"):])
    elif model_name.startswith("claude-code/"):
        return ("claude_code", model_name)
    elif model_name.startswith("claude-"):
        return ("anthropic", model_name)
    else:
        return ("openai", model_name)


def setup_llm(
    model_name: str,
    *,
    openai_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    openrouter_api_key: str | None = None,
    openai_compat_api_key: str | None = None,
    openai_compat_base_url: str | None = None,
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    aws_region: str = "us-east-1",
    custom_llm_config: dict | None = None,
) -> BaseChatModel:
    """Initialize and return the LLM based on model name (detect provider from prefix).

    For custom/ models, custom_llm_config must contain the UserLlmProvider fields.
    For built-in providers, the relevant API key must be supplied.
    """
    logger.info(f"Setting up LLM: {model_name}")

    provider, api_model = parse_model_provider(model_name)

    if provider == "custom":
        if not custom_llm_config:
            raise ValueError(
                f"Custom LLM config is required for model '{model_name}'. "
                "Configure the provider in Global Settings."
            )
        ptype = custom_llm_config.get("providerType", "openai_compatible")

        if ptype == "anthropic":
            llm = ChatAnthropic(
                model=custom_llm_config.get("modelIdentifier", api_model),
                api_key=custom_llm_config.get("apiKey", ""),
                base_url=custom_llm_config.get("baseUrl") or None,
                default_headers=custom_llm_config.get("defaultHeaders") or {},
                timeout=float(custom_llm_config.get("timeout", 120)),
                temperature=custom_llm_config.get("temperature", 0),
                max_tokens=custom_llm_config.get("maxTokens", 16384),
            )
        elif ptype == "bedrock":
            from langchain_aws import ChatBedrockConverse
            llm = ChatBedrockConverse(
                model=custom_llm_config.get("modelIdentifier", api_model),
                region_name=custom_llm_config.get("awsRegion", "us-east-1"),
                aws_access_key_id=custom_llm_config.get("awsAccessKeyId") or None,
                aws_secret_access_key=custom_llm_config.get("awsSecretKey") or None,
                temperature=custom_llm_config.get("temperature", 0),
                max_tokens=custom_llm_config.get("maxTokens", 16384),
            )
        else:
            # openai_compatible (default) — also handles openai/openrouter custom entries
            kwargs = dict(
                model=custom_llm_config.get("modelIdentifier", api_model),
                api_key=custom_llm_config.get("apiKey") or "ollama",
                temperature=custom_llm_config.get("temperature", 0),
                max_tokens=custom_llm_config.get("maxTokens", 16384),
            )
            base_url = custom_llm_config.get("baseUrl")
            if base_url:
                kwargs["base_url"] = base_url
            headers = custom_llm_config.get("defaultHeaders")
            if headers:
                kwargs["default_headers"] = headers
            timeout = custom_llm_config.get("timeout")
            if timeout:
                kwargs["timeout"] = float(timeout)
            ssl_verify = custom_llm_config.get("sslVerify", True)
            if not ssl_verify:
                import httpx
                kwargs["http_client"] = httpx.Client(verify=False)
                kwargs["http_async_client"] = httpx.AsyncClient(verify=False)
            llm = ChatOpenAI(**kwargs)

    elif provider == "claude_code":
        # Route through the Claude Code host proxy (OpenAI-compatible)
        proxy_base = None
        if custom_llm_config:
            base = custom_llm_config.get("baseUrl", "")
            if base:
                # Strip trailing /v1 if user saved full URL; we append /v1 below
                proxy_base = base.rstrip("/")
                if not proxy_base.endswith("/v1"):
                    proxy_base = proxy_base + "/v1"
        if not proxy_base:
            proxy_base = "http://host.docker.internal:8099/v1"

        llm = ChatOpenAI(
            model=api_model,  # full "claude-code/<model>" ID expected by proxy
            api_key="claude-code",  # proxy ignores key; placeholder required by SDK
            base_url=proxy_base,
            temperature=0,
            max_tokens=16384,
        )

    elif provider == "openai_compat":
        # Legacy: openai_compat/ prefix (env-var based)
        if not openai_compat_base_url:
            raise ValueError(
                f"OPENAI_COMPAT_BASE_URL is required for model '{model_name}'. "
                "Consider migrating to Global Settings."
            )
        llm = ChatOpenAI(
            model=api_model,
            api_key=openai_compat_api_key or "ollama",
            base_url=openai_compat_base_url,
            temperature=0,
        )

    elif provider == "openrouter":
        if not openrouter_api_key:
            raise ValueError(
                f"OpenRouter API key is required for model '{model_name}'"
            )
        llm = ChatOpenAI(
            model=api_model,
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
            default_headers={
                "HTTP-Referer": "https://redamon.dev",
                "X-Title": "RedAmon Agent",
            },
        )

    elif provider == "bedrock":
        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError(
                f"AWS credentials are required for model '{model_name}'"
            )
        from langchain_aws import ChatBedrockConverse
        llm = ChatBedrockConverse(
            model=api_model,
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            temperature=0,
        )

    elif provider == "anthropic":
        if not anthropic_api_key:
            raise ValueError(
                f"Anthropic API key is required for model '{model_name}'"
            )
        llm = ChatAnthropic(
            model=api_model,
            api_key=anthropic_api_key,
            temperature=0,
            max_tokens=16384,
        )

    else:  # openai
        if not openai_api_key:
            raise ValueError(
                f"OpenAI API key is required for model '{model_name}'"
            )
        llm = ChatOpenAI(
            model=api_model,
            api_key=openai_api_key,
            temperature=0,
        )

    logger.info(f"LLM provider: {provider}, model: {api_model}")
    return llm


def _resolve_provider_key(
    providers: list[dict],
    provider_type: str,
) -> dict | None:
    """Find the first provider entry matching the given type."""
    for p in providers:
        if p.get("providerType") == provider_type:
            return p
    return None


def apply_project_settings(orchestrator, project_id: str) -> None:
    """Load project settings from webapp API and reconfigure LLM if model changed."""
    settings = load_project_settings(project_id)
    new_model = settings.get('OPENAI_MODEL', 'claude-opus-4-6')

    # Re-run LLM setup if model changed OR if LLM is None (previous setup failed)
    model_changed = new_model != orchestrator.model_name
    need_setup = model_changed or orchestrator.llm is None
    if need_setup:
        if model_changed:
            logger.info(f"Model changed: {orchestrator.model_name} -> {new_model}")
        else:
            logger.info(f"Retrying LLM setup for {new_model} (previous attempt failed)")
        orchestrator.model_name = new_model

        # Resolve keys from user's LLM providers (DB-driven)
        user_providers = settings.get('USER_LLM_PROVIDERS', [])
        custom_config = settings.get('CUSTOM_LLM_CONFIG')

        # Build kwargs from DB providers (no env-var fallback)
        openai_p = _resolve_provider_key(user_providers, "openai")
        anthropic_p = _resolve_provider_key(user_providers, "anthropic")
        openrouter_p = _resolve_provider_key(user_providers, "openrouter")
        bedrock_p = _resolve_provider_key(user_providers, "bedrock")

        try:
            orchestrator.llm = setup_llm(
                new_model,
                openai_api_key=(openai_p or {}).get("apiKey"),
                anthropic_api_key=(anthropic_p or {}).get("apiKey"),
                openrouter_api_key=(openrouter_p or {}).get("apiKey"),
                aws_access_key_id=(bedrock_p or {}).get("awsAccessKeyId"),
                aws_secret_access_key=(bedrock_p or {}).get("awsSecretKey"),
                aws_region=(bedrock_p or {}).get("awsRegion") or "us-east-1",
                custom_llm_config=custom_config,
            )
        except (ValueError, Exception) as e:
            # LLM setup failed — try to fall back to Claude Code proxy before giving up.
            # This covers the common case where the model is e.g. "claude-opus-4-6" but
            # no Anthropic API key is set, yet the Claude Code proxy IS running.
            fallback_used = False
            if "API key is required" in str(e) or "api_key" in str(e).lower():
                # Map plain model name to its claude-code/ equivalent
                _plain_to_proxy = {
                    "claude-opus-4-6":           "claude-code/claude-opus-4-6",
                    "claude-sonnet-4-6":          "claude-code/claude-sonnet-4-6",
                    "claude-haiku-4-5-20251001":  "claude-code/claude-haiku-4-5-20251001",
                    "claude-sonnet-4-5-20251001": "claude-code/claude-sonnet-4-5-20251001",
                    "claude-opus-4-5-20251101":   "claude-code/claude-opus-4-5-20251101",
                }
                # Find the Claude Code provider config (for custom proxy URL if set)
                claude_code_p = _resolve_provider_key(user_providers, "claude_code")
                proxy_model = _plain_to_proxy.get(new_model)
                if proxy_model:
                    try:
                        fallback_llm = setup_llm(
                            proxy_model,
                            custom_llm_config=claude_code_p,
                        )
                        orchestrator.llm = fallback_llm
                        orchestrator.model_name = proxy_model
                        logger.warning(
                            f"No API key for '{new_model}' — auto-falling back to "
                            f"Claude Code proxy ({proxy_model})"
                        )
                        fallback_used = True
                    except Exception as fe:
                        logger.error(f"Claude Code proxy fallback also failed: {fe}")

            if not fallback_used:
                logger.error(f"LLM setup failed for {new_model}: {e}")
                orchestrator.llm = None
                return

        # Update Neo4j tool's LLM for text-to-Cypher queries
        if orchestrator.neo4j_manager:
            orchestrator.neo4j_manager.llm = orchestrator.llm
            logger.info("Updated Neo4j tool LLM")

    # Store user settings on orchestrator for other components (Tavily key)
    user_settings = settings.get('USER_SETTINGS', {})
    if user_settings:
        orchestrator._user_settings = user_settings
