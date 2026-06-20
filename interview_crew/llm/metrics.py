"""
Prometheus-style metrics collection for InterviewCrew.
Exposes LLM latency, token usage, and system health metrics.
"""

import time
from typing import Optional

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# LLM call latency (seconds)
LLM_LATENCY = Histogram(
    "interview_llm_latency_seconds",
    "LLM API call latency",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
)

# Time to first token (streaming)
LLM_TTFT = Histogram(
    "interview_llm_ttft_seconds",
    "Time to first token in streaming mode",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

# Token consumption
LLM_TOKENS = Counter(
    "interview_llm_tokens_total",
    "Total tokens consumed",
    ["model", "direction"],
)

# Active sessions
ACTIVE_SESSIONS = Gauge(
    "interview_sessions_active",
    "Number of active interview sessions",
)

# Total turns processed
TOTAL_TURNS = Counter(
    "interview_turns_total",
    "Total interview turns processed",
    ["agent"],
)

# Session duration
SESSION_DURATION = Histogram(
    "interview_session_duration_seconds",
    "Interview session duration",
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600],
)


def record_llm_call(
    model: str,
    latency: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Record metrics for a single LLM call."""
    LLM_LATENCY.labels(model=model).observe(latency)
    LLM_TOKENS.labels(model=model, direction="input").inc(input_tokens)
    LLM_TOKENS.labels(model=model, direction="output").inc(output_tokens)


def record_ttft(model: str, ttft: float) -> None:
    """Record time-to-first-token for streaming."""
    LLM_TTFT.labels(model=model).observe(ttft)


def record_turn(agent: str) -> None:
    """Record a completed turn."""
    TOTAL_TURNS.labels(agent=agent).inc()


def set_active_sessions(count: int) -> None:
    """Set current active session count."""
    ACTIVE_SESSIONS.set(count)


def record_session_duration(duration_seconds: float) -> None:
    """Record session duration."""
    SESSION_DURATION.observe(duration_seconds)


def get_metrics_text() -> str:
    """Get all metrics in Prometheus exposition format."""
    return generate_latest().decode("utf-8")


def get_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
