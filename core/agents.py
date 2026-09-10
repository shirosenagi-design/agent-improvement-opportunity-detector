import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from strands import Agent

from core.cases import CUSTOMER_CONTEXT, EvaluationCase


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model_id: str | None


def resolve_model_selection() -> ModelSelection:
    provider = (os.getenv("MODEL_PROVIDER") or "bedrock").strip().lower()
    if provider == "bedrock":
        return ModelSelection(provider=provider, model_id=os.getenv("BEDROCK_MODEL_ID") or None)
    if provider == "openai":
        model_id = os.getenv("OPENAI_MODEL_ID")
        if not model_id:
            raise ValueError("OPENAI_MODEL_ID is required when MODEL_PROVIDER=openai")
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is required when MODEL_PROVIDER=openai")
        return ModelSelection(provider=provider, model_id=model_id)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


@asynccontextmanager
async def openai_client_scope() -> AsyncIterator[Any]:
    import ssl

    import truststore
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient

    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    http_client = DefaultAsyncHttpxClient(verify=ssl_context)
    client = None
    try:
        client = AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            http_client=http_client,
            max_retries=0,
        )
        yield client
    finally:
        if client is None:
            await http_client.aclose()
        else:
            await client.close()


def build_agent(
    system_prompt: str,
    selection: ModelSelection,
    *,
    context: str | None = CUSTOMER_CONTEXT,
    tools: list[Any] | None = None,
    openai_model_params: Mapping[str, Any] | None = None,
    openai_client: Any | None = None,
) -> Agent:
    prompt = f"{system_prompt}\n\n{context}" if context else system_prompt
    kwargs: dict[str, Any] = {"system_prompt": prompt, "callback_handler": None}
    if tools:
        kwargs["tools"] = tools
    if selection.provider == "openai":
        from strands.models.openai import OpenAIModel

        openai_model_config: dict[str, Any] = {"model_id": selection.model_id}
        if openai_model_params is not None:
            openai_model_config["params"] = dict(openai_model_params)
        if openai_client is not None:
            kwargs["model"] = OpenAIModel(
                client=openai_client,
                **openai_model_config,
            )
        else:
            import ssl

            import truststore
            from openai import DefaultAsyncHttpxClient

            ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            kwargs["model"] = OpenAIModel(
                client_args={
                    "api_key": os.environ["OPENAI_API_KEY"],
                    "http_client": DefaultAsyncHttpxClient(verify=ssl_context),
                    "max_retries": 0,
                },
                **openai_model_config,
            )
    elif selection.model_id:
        kwargs["model"] = selection.model_id
    return Agent(**kwargs)


def run_agent_suite(
    case: EvaluationCase,
    system_prompt: str,
    selection: ModelSelection,
    on_probe: Callable[[str], None] | None = None,
) -> dict[str, str]:
    responses: dict[str, str] = {}
    for probe in case.probes:
        if on_probe:
            on_probe(probe.id)
        agent = build_agent(system_prompt, selection)
        responses[probe.id] = str(agent(probe.prompt))
    return responses
