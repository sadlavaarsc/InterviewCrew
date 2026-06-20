"""
DeepSeek API benchmark: TTFT + concurrent throughput.
Models: deepseek-v4-pro (500 concurrency) / deepseek-v4-flash (2500 concurrency)
"""
import asyncio
import time
import statistics
from typing import List, Dict
from openai import AsyncOpenAI

API_KEY = "sk-66605c9aae5242cdaf680711bdfba354"
BASE_URL = "https://api.deepseek.com"

TEST_MESSAGES = [
    {"role": "system", "content": "你是一位技术面试官。请提出一个面试问题。"},
    {"role": "user", "content": "我熟悉 Python 和 Go，有 3 年后端开发经验。"},
]


async def measure_ttft(client: AsyncOpenAI, model: str, num_runs: int = 10) -> Dict:
    """Measure TTFT for a given model."""
    ttft_values = []
    total_times = []
    tokens_counts = []

    print(f"\n=== TTFT Benchmark: {model} ({num_runs} runs) ===")

    for i in range(num_runs):
        try:
            start = time.perf_counter()
            first_token_time = None
            token_count = 0

            async for chunk in await client.chat.completions.create(
                model=model,
                messages=TEST_MESSAGES,
                stream=True,
                temperature=0.7,
            ):
                if chunk.choices[0].delta.content:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    token_count += 1

            end = time.perf_counter()

            if first_token_time:
                ttft_ms = (first_token_time - start) * 1000
                total_ms = (end - start) * 1000
                ttft_values.append(ttft_ms)
                total_times.append(total_ms)
                tokens_counts.append(token_count)
                print(f"  Run {i+1}: TTFT={ttft_ms:.0f}ms, Total={total_ms:.0f}ms, Tokens={token_count}")
            else:
                print(f"  Run {i+1}: No tokens received")

            await asyncio.sleep(0.3)

        except Exception as e:
            print(f"  Run {i+1}: Error - {e}")

    if not ttft_values:
        return {"error": "No successful runs"}

    return {
        "model": model,
        "runs": len(ttft_values),
        "ttft_min_ms": min(ttft_values),
        "ttft_max_ms": max(ttft_values),
        "ttft_avg_ms": statistics.mean(ttft_values),
        "ttft_median_ms": statistics.median(ttft_values),
        "ttft_p95_ms": sorted(ttft_values)[int(len(ttft_values) * 0.95)],
        "ttft_p99_ms": sorted(ttft_values)[int(len(ttft_values) * 0.99)],
        "total_avg_ms": statistics.mean(total_times),
        "total_median_ms": statistics.median(total_times),
        "tokens_avg": statistics.mean(tokens_counts),
    }


async def measure_concurrency(
    client: AsyncOpenAI,
    model: str,
    concurrency_levels: List[int] = [1, 5, 10, 20, 50],
) -> List[Dict]:
    """Measure throughput at different concurrency levels."""
    results = []

    print(f"\n=== Concurrency Benchmark: {model} ===")

    for level in concurrency_levels:
        print(f"\n  Testing {level} concurrent requests...")
        latencies = []
        errors = 0

        async def single_request():
            try:
                start = time.perf_counter()
                resp = await client.chat.completions.create(
                    model=model,
                    messages=TEST_MESSAGES,
                    temperature=0.7,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                return elapsed_ms, len(resp.choices[0].message.content or "")
            except Exception as e:
                return None, str(e)

        start_all = time.perf_counter()
        tasks = [single_request() for _ in range(level)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        total_elapsed_ms = (time.perf_counter() - start_all) * 1000

        for r in responses:
            if isinstance(r, Exception):
                errors += 1
            elif r[0] is not None:
                latencies.append(r[0])
            else:
                errors += 1

        if latencies:
            result = {
                "concurrency": level,
                "successful": len(latencies),
                "errors": errors,
                "total_time_ms": total_elapsed_ms,
                "latency_min_ms": min(latencies),
                "latency_max_ms": max(latencies),
                "latency_avg_ms": statistics.mean(latencies),
                "latency_p95_ms": sorted(latencies)[int(len(latencies) * 0.95)],
                "throughput_rps": len(latencies) / (total_elapsed_ms / 1000),
            }
        else:
            result = {
                "concurrency": level,
                "successful": 0,
                "errors": errors,
                "total_time_ms": total_elapsed_ms,
            }

        print(f"    Success: {result['successful']}/{level}, Errors: {errors}")
        if latencies:
            print(f"    Avg latency: {result['latency_avg_ms']:.0f}ms, P95: {result['latency_p95_ms']:.0f}ms")
            print(f"    Throughput: {result['throughput_rps']:.1f} req/s")

        results.append(result)

        # Cooldown between levels
        await asyncio.sleep(2)

    return results


async def run_all():
    print("=" * 60)
    print("DeepSeek API Benchmark (Real Calls)")
    print(f"API: {BASE_URL}")
    print("=" * 60)

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

    # Test Flash (cheap, fast)
    flash_ttft = await measure_ttft(client, "deepseek-v4-flash", num_runs=20)
    flash_concurrency = await measure_concurrency(
        client, "deepseek-v4-flash", concurrency_levels=[1, 10, 30, 50, 100]
    )

    # Test Pro (stronger, but more expensive)
    pro_ttft = await measure_ttft(client, "deepseek-v4-pro", num_runs=10)
    pro_concurrency = await measure_concurrency(
        client, "deepseek-v4-pro", concurrency_levels=[1, 10, 30, 50]
    )

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for name, ttft, conc in [("Flash", flash_ttft, flash_concurrency), ("Pro", pro_ttft, pro_concurrency)]:
        if "error" not in ttft:
            print(f"\n{name} Model ({ttft['model']}):")
            print(f"  TTFT avg:    {ttft['ttft_avg_ms']:.0f}ms")
            print(f"  TTFT median: {ttft['ttft_median_ms']:.0f}ms")
            print(f"  TTFT P95:    {ttft['ttft_p95_ms']:.0f}ms")
            print(f"  TTFT P99:    {ttft['ttft_p99_ms']:.0f}ms")
            print(f"  Total avg:   {ttft['total_avg_ms']:.0f}ms")
            print(f"  Tokens avg:  {ttft['tokens_avg']:.0f}")

        if conc:
            print(f"  Concurrency results:")
            for r in conc:
                if r.get("latency_avg_ms"):
                    print(f"    {r['concurrency']:>3} req: success={r['successful']}/{r['concurrency']+r['errors']}, "
                          f"avg={r['latency_avg_ms']:.0f}ms, p95={r['latency_p95_ms']:.0f}ms, "
                          f"rps={r['throughput_rps']:.1f}")
                else:
                    print(f"    {r['concurrency']:>3} req: FAILED ({r['errors']} errors)")

    return {"flash_ttft": flash_ttft, "flash_conc": flash_concurrency,
            "pro_ttft": pro_ttft, "pro_conc": pro_concurrency}


if __name__ == "__main__":
    results = asyncio.run(run_all())
