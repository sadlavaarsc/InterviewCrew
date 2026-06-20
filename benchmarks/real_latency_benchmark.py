"""
Real LLM latency benchmark using actual API calls.
Measures TTFT (Time To First Token) with async streaming.

Usage:
    python -m benchmarks.real_latency_benchmark          # Live API calls
    python -m benchmarks.real_latency_benchmark --offline  # Read from cache
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

from interview_crew.llm.async_client import async_llm
from interview_crew.llm.model_resolver import get_default_model, get_premium_model

CACHE_DIR = Path(".benchmark_cache")
CACHE_FILE = CACHE_DIR / "last_ttft.json"

# Test messages simulating a typical interview turn
TEST_MESSAGES = [
    {"role": "system", "content": "你是一位技术面试官。请提出一个面试问题。"},
    {"role": "user", "content": "我熟悉 Python 和 Go，有 3 年后端开发经验。"},
]


def load_cache() -> Optional[Dict]:
    """Load cached benchmark results if available."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(results: Dict) -> None:
    """Save benchmark results to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "default": results.get("default", {}),
        "premium": results.get("premium", {}),
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    print(f"\nCached results written to {CACHE_FILE}")


def check_api_key() -> bool:
    """Check if any API key is configured."""
    return bool(
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("ARK_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


async def measure_ttft(
    model: str,
    num_runs: int = 10,
) -> Dict:
    """Measure TTFT for a given model."""
    ttft_values = []
    total_times = []

    print(f"\n=== TTFT Benchmark: {model} ({num_runs} runs) ===")

    for i in range(num_runs):
        try:
            start = time.perf_counter()
            first_token_time = None
            tokens = []

            # Stream and measure
            async for token in async_llm.astream(
                TEST_MESSAGES,
                model_name=model,
                temperature=0.7,
            ):
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                tokens.append(token)

            end = time.perf_counter()

            if first_token_time:
                ttft_ms = (first_token_time - start) * 1000
                total_ms = (end - start) * 1000
                ttft_values.append(ttft_ms)
                total_times.append(total_ms)
                print(f"  Run {i+1}: TTFT={ttft_ms:.0f}ms, Total={total_ms:.0f}ms, Tokens={len(tokens)}")
            else:
                print(f"  Run {i+1}: No tokens received")

            # Small delay between runs
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"  Run {i+1}: Error - {e}")

    if not ttft_values:
        return {"error": "No successful runs"}

    import statistics
    return {
        "model": model,
        "runs": num_runs,
        "ttft_min_ms": min(ttft_values),
        "ttft_max_ms": max(ttft_values),
        "ttft_avg_ms": statistics.mean(ttft_values),
        "ttft_median_ms": statistics.median(ttft_values),
        "ttft_p95_ms": sorted(ttft_values)[int(len(ttft_values) * 0.95)] if len(ttft_values) > 1 else ttft_values[0],
        "total_avg_ms": statistics.mean(total_times),
    }


def print_results(results: Dict, label: str) -> None:
    """Print benchmark results for a model."""
    if "error" in results:
        print(f"\n{label}: ERROR - {results['error']}")
        return
    print(f"\n{label} ({results['model']}):")
    print(f"  TTFT avg:    {results['ttft_avg_ms']:.0f}ms")
    print(f"  TTFT median: {results['ttft_median_ms']:.0f}ms")
    print(f"  TTFT p95:    {results['ttft_p95_ms']:.0f}ms")
    print(f"  TTFT range:  {results['ttft_min_ms']:.0f}ms - {results['ttft_max_ms']:.0f}ms")
    print(f"  Total avg:   {results['total_avg_ms']:.0f}ms")


async def run_all(offline: bool = False) -> Dict:
    """Run all real latency benchmarks."""
    print("=" * 60)
    print("Real LLM Latency Benchmark")
    if offline:
        print("Mode: OFFLINE (reading from cache)")
    else:
        print("Mode: LIVE (calling APIs)")
    print("=" * 60)

    if offline:
        cache = load_cache()
        if cache is None:
            print(f"\nERROR: No cache file found at {CACHE_FILE}")
            print("Run without --offline first to generate cached results.")
            return {}

        print(f"\nUsing cached results from {cache.get('timestamp', 'unknown time')}")
        default_results = cache.get("default", {})
        premium_results = cache.get("premium", {})

        print_results(default_results, "Default Model")
        print_results(premium_results, "Premium Model")
        return {"default": default_results, "premium": premium_results}

    # Live mode
    if not check_api_key():
        print("\nERROR: No API key found in environment.")
        print("Please set one of: DEEPSEEK_API_KEY, ARK_API_KEY, DASHSCOPE_API_KEY, OPENAI_API_KEY")
        print("Or run with --offline to use cached results.")
        return {}

    # Test with default/economy model (cheaper)
    default_results = await measure_ttft(get_default_model(), num_runs=10)

    # Test with premium/quality model (if budget allows)
    premium_results = await measure_ttft(get_premium_model(), num_runs=5)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    print_results(default_results, "Default Model")
    print_results(premium_results, "Premium Model")

    # Cost estimate: provider-specific; update multipliers as needed
    default_cost = 10 * 0.0005   # 10 runs × default model cost per call (example)
    premium_cost = 5 * 0.003     # 5 runs × premium model cost per call (example)
    print(f"\nEstimated cost: ${default_cost + premium_cost:.3f} (update multipliers for your provider)")

    results = {"default": default_results, "premium": premium_results}
    save_cache(results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real LLM Latency Benchmark")
    parser.add_argument("--offline", action="store_true", help="Read from cache instead of calling APIs")
    args = parser.parse_args()

    results = asyncio.run(run_all(offline=args.offline))
