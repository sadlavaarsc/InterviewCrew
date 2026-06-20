"""
Precise token counting using tiktoken.
Replaces the heuristic len(content)//4 with model-aware encoding.
"""

from typing import List

import tiktoken

# Use cl100k_base which covers GPT-4, GPT-3.5, and most OpenAI-compatible models
ENCODING = tiktoken.get_encoding("cl100k_base")


def count_string(text: str) -> int:
    """Count tokens in a single string."""
    return len(ENCODING.encode(text))


def count_messages(messages: List[dict]) -> int:
    """
    Count tokens in a list of messages.
    Approximates OpenAI's message token counting format.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += count_string(content)
        # Add overhead per message (~4 tokens for role/name metadata)
        total += 4
    # Add initial prompt overhead
    total += 2
    return total


def estimate_tokens(messages: List[dict]) -> int:
    """
    Drop-in replacement for the old heuristic estimator.
    Returns precise token count using tiktoken.
    """
    return count_messages(messages)
