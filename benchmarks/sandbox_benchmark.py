"""
Code sandbox benchmark suite for InterviewCrew.
Measures: execution correctness, AST analysis accuracy, security.
"""

import time
from interview_crew.services.code_executor import execute_python
from interview_crew.services.ast_analyzer import analyze_code


# Standard LeetCode problems for correctness testing
TEST_PROBLEMS = [
    {
        "name": "Two Sum (brute force)",
        "code": """def two_sum(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
    return []
""",
        "test_cases": [
            {"input": "nums=[2,7,11,15], target=9", "expected": "[0,1]"},
            {"input": "nums=[3,2,4], target=6", "expected": "[1,2]"},
        ],
        "expected_time": "O(n^2)",
        "expected_space": "O(1)",
    },
    {
        "name": "Valid Parentheses",
        "code": """def is_valid(s):
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    for c in s:
        if c in pairs:
            stack.append(c)
        elif not stack or pairs[stack.pop()] != c:
            return False
    return len(stack) == 0
""",
        "test_cases": [
            {"input": "s='()'", "expected": "True"},
            {"input": "s='(]'", "expected": "False"},
            {"input": "s='()[]{}'", "expected": "True"},
        ],
        "expected_time": "O(n)",
        "expected_space": "O(n)",
    },
    {
        "name": "LRU Cache",
        "code": """class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = {}
        self.order = []

    def get(self, key):
        if key in self.cache:
            self.order.remove(key)
            self.order.append(key)
            return self.cache[key]
        return -1

    def put(self, key, value):
        if key in self.cache:
            self.order.remove(key)
        elif len(self.cache) >= self.capacity:
            oldest = self.order.pop(0)
            del self.cache[oldest]
        self.cache[key] = value
        self.order.append(key)
""",
        "test_cases": [
            {"input": "ops=['LRUCache','put','put','get'], params=[[2],[1,1],[2,2],[1]]", "expected": "NO_RESULT"},
        ],
        "expected_time": "O(n)",
        "expected_space": "O(n)",
    },
]

# Malicious code samples for security testing
MALICIOUS_CODE = [
    ("os.system", "import os\nos.system('ls')"),
    ("subprocess", "import subprocess\nsubprocess.run(['ls'])"),
    ("file read", "with open('/etc/passwd') as f:\n    print(f.read())"),
    ("eval", "eval('1 + 1')"),
    ("exec", "exec('print(1)')"),
    ("__import__", "__import__('os').system('ls')"),
]


def benchmark_execution_correctness():
    """Test code execution on standard problems."""
    print("\n=== Code Execution Correctness Benchmark ===")

    passed = 0
    total = 0
    times = []

    for prob in TEST_PROBLEMS:
        start = time.time()
        result = execute_python(prob["code"], prob["test_cases"])
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)

        prob_passed = result.overall_passed
        passed += int(prob_passed)
        total += 1

        status = "✅ PASS" if prob_passed else "❌ FAIL"
        print(f"{status} {prob['name']:<25} ({elapsed:.0f}ms)")

    avg_time = sum(times) / len(times)
    pass_rate = passed / total * 100

    print(f"\nPass rate: {passed}/{total} ({pass_rate:.0f}%)")
    print(f"Avg execution time: {avg_time:.0f}ms")
    return {"pass_rate": pass_rate, "avg_time_ms": avg_time}


def benchmark_ast_analysis():
    """Test AST complexity inference accuracy."""
    print("\n=== AST Analysis Accuracy Benchmark ===")

    correct_time = 0
    correct_space = 0
    total = 0

    for prob in TEST_PROBLEMS:
        analysis = analyze_code(prob["code"])
        time_ok = analysis.time_complexity == prob["expected_time"]
        space_ok = analysis.space_complexity == prob["expected_space"]
        correct_time += int(time_ok)
        correct_space += int(space_ok)
        total += 1

        status_time = "✅" if time_ok else "❌"
        status_space = "✅" if space_ok else "❌"
        print(f"{prob['name']:<25} Time: {status_time} {analysis.time_complexity:<8} (expected {prob['expected_time']}) | "
              f"Space: {status_space} {analysis.space_complexity:<8} (expected {prob['expected_space']})")

    time_acc = correct_time / total * 100
    space_acc = correct_space / total * 100

    print(f"\nTime complexity accuracy: {time_acc:.0f}%")
    print(f"Space complexity accuracy: {space_acc:.0f}%")
    return {"time_accuracy": time_acc, "space_accuracy": space_acc}


def benchmark_security():
    """Test security filtering."""
    print("\n=== Security Filter Benchmark ===")

    blocked = 0
    for name, code in MALICIOUS_CODE:
        result = execute_python(code, [])
        was_blocked = not result.success and "Security" in result.compile_output
        blocked += int(was_blocked)
        status = "✅ BLOCKED" if was_blocked else "❌ PASSED THROUGH"
        print(f"{status} {name}")

    block_rate = blocked / len(MALICIOUS_CODE) * 100
    print(f"\nBlock rate: {blocked}/{len(MALICIOUS_CODE)} ({block_rate:.0f}%)")
    return {"block_rate": block_rate}


def benchmark_anti_patterns():
    """Test anti-pattern detection."""
    print("\n=== Anti-Pattern Detection Benchmark ===")

    bad_code = """
def foo(a, b, c, d, e, f):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        if f:
                            return 1
    return 0
"""
    analysis = analyze_code(bad_code)
    print(f"Deep nesting detected: {'✅' if any('Deep nesting' in a for a in analysis.anti_patterns) else '❌'}")
    print(f"Anti-patterns found: {len(analysis.anti_patterns)}")
    for ap in analysis.anti_patterns:
        print(f"  - {ap}")
    return {"anti_patterns_found": len(analysis.anti_patterns)}


def run_all():
    """Run all sandbox benchmarks."""
    print("=" * 60)
    print("InterviewCrew Sandbox Benchmark Suite")
    print("=" * 60)

    results = {
        "execution": benchmark_execution_correctness(),
        "ast_analysis": benchmark_ast_analysis(),
        "security": benchmark_security(),
        "anti_patterns": benchmark_anti_patterns(),
    }

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Execution pass rate:         {results['execution']['pass_rate']:.0f}%")
    print(f"AST time complexity accuracy: {results['ast_analysis']['time_accuracy']:.0f}%")
    print(f"Security block rate:         {results['security']['block_rate']:.0f}%")
    print(f"Anti-patterns detected:      {results['anti_patterns']['anti_patterns_found']}")

    return results


if __name__ == "__main__":
    run_all()
