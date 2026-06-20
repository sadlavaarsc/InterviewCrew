"""
Real LLM latency benchmark using actual API calls.
Measures TTFT (Time To First Token) with async streaming.
"""

import asyncio
import time
from typing import List, Dict

from interview_crew.llm.async_client import async_llm
from interview_crew.llm.model_resolver import get_default_model, get_premium_model


# Test messages simulating a typical interview turn
TEST_MESSAGES = [
    {"role": "system", "content": "你是一位技术面试官。请提出一个面试问题。"},
    {"role": "user", "content": "我熟悉 Python 和 Go，有 3 年后端开发经验。"},
]


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


async def run_all():
    """Run all real latency benchmarks."""
    print("=" * 60)
    print("Real LLM Latency Benchmark (Live API Calls)")
    print("=" * 60)

    # Test with default/economy model (cheaper)
    default_results = await measure_ttft(get_default_model(), num_runs=10)

    # Test with premium/quality model (if budget allows)
    premium_results = await measure_ttft(get_premium_model(), num_runs=5)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if "error" not in default_results:
        print(f"\nDefault Model ({default_results['model']}):")
        print(f"  TTFT avg:    {default_results['ttft_avg_ms']:.0f}ms")
        print(f"  TTFT median: {default_results['ttft_median_ms']:.0f}ms")
        print(f"  TTFT p95:    {default_results['ttft_p95_ms']:.0f}ms")
        print(f"  TTFT range:  {default_results['ttft_min_ms']:.0f}ms - {default_results['ttft_max_ms']:.0f}ms")
        print(f"  Total avg:   {default_results['total_avg_ms']:.0f}ms")

    if "error" not in premium_results:
        print(f"\nPremium Model ({premium_results['model']}):")
        print(f"  TTFT avg:    {premium_results['ttft_avg_ms']:.0f}ms")
        print(f"  TTFT median: {premium_results['ttft_median_ms']:.0f}ms")
        print(f"  TTFT p95:    {premium_results['ttft_p95_ms']:.0f}ms")
        print(f"  Total avg:   {premium_results['total_avg_ms']:.0f}ms")

    # Cost estimate: provider-specific; update multipliers as needed
    default_cost = 10 * 0.0005   # 10 runs × default model cost per call (example)
    premium_cost = 5 * 0.003     # 5 runs × premium model cost per call (example)
    print(f"\nEstimated cost: ${default_cost + premium_cost:.3f} (update multipliers for your provider)")

    return {"default": default_results, "premium": premium_results}


if __name__ == "__main__":
    results = asyncio.run(run_all())
