"""Phoenix / OpenTelemetry tracing setup.

Initializes the OTEL tracer provider that sends spans to Arize Phoenix.
Call ``init_tracing()`` once at application startup.
"""

from __future__ import annotations

import logging

from phoenix.otel import register as phoenix_register

from zerebro.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def init_tracing() -> None:
    """Register the Phoenix OTEL tracer provider (idempotent).

    Sends traces to the Phoenix collector at ``settings.phoenix_collector_endpoint``.
    The LangChain auto-instrumentor is attached so every LLM / chain / tool
    invocation is captured automatically.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return

    tracer_provider = phoenix_register(
        project_name="zerebro",
        endpoint=settings.phoenix_collector_endpoint,
    )
    logger.info(
        "Phoenix tracing initialized -> %s (provider=%s)",
        settings.phoenix_collector_endpoint,
        type(tracer_provider).__name__,
    )

    # Auto-instrument LangChain / LangGraph
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

    _initialized = True
