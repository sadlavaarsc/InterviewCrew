"""
Docker-based code execution sandbox for InterviewCrew.
Provides secure, isolated, resource-limited code execution.
"""

import json
import tempfile
import os
import time
import uuid
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class DockerResult:
    success: bool
    compile_output: str
    test_results: List[Dict]
    overall_passed: bool
    execution_time_ms: float
    memory_usage_mb: float
    container_id: str = ""
    error: str = ""


class DockerCodeExecutor:
    """
    Docker-based code execution with full isolation.
    Requires Docker daemon to be running.
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 2,
        memory_limit: str = "256m",
        cpu_limit: float = 1.0,
        network_disabled: bool = True,
    ):
        self.image = image
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.network_disabled = network_disabled
        self._client = None

    def _get_client(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    def execute(
        self,
        code: str,
        test_cases: List[Dict],
        language: str = "python",
    ) -> DockerResult:
        """
        Execute code in a Docker container.

        Args:
            code: User's Python code
            test_cases: List of test cases
            language: Programming language (currently only python supported)

        Returns:
            DockerResult with execution results
        """
        start_time = time.time()
        container_id = str(uuid.uuid4())[:8]

        try:
            client = self._get_client()
        except Exception as e:
            return DockerResult(
                success=False,
                compile_output="",
                test_results=[],
                overall_passed=False,
                execution_time_ms=0,
                memory_usage_mb=0,
                error=f"Docker not available: {str(e)}",
            )

        # Create temporary directory for code
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write user code
            code_file = os.path.join(tmpdir, "solution.py")
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)

            # Write test runner
            runner_code = self._build_test_runner(code, test_cases)
            runner_file = os.path.join(tmpdir, "runner.py")
            with open(runner_file, "w", encoding="utf-8") as f:
                f.write(runner_code)

            try:
                container = client.containers.run(
                    image=self.image,
                    command=["python", "/tmp/runner.py"],
                    volumes={
                        tmpdir: {"bind": "/tmp", "mode": "ro"}
                    },
                    mem_limit=self.memory_limit,
                    cpu_quota=int(self.cpu_limit * 100000),
                    cpu_period=100000,
                    network_disabled=self.network_disabled,
                    detach=True,
                    auto_remove=False,
                )

                # Wait for completion with timeout
                try:
                    result = container.wait(timeout=self.timeout + 2)
                    exit_code = result.get("StatusCode", -1)
                except Exception:
                    # Timeout - force kill and remove
                    try:
                        container.kill()
                    except Exception:
                        pass
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass
                    return DockerResult(
                        success=False,
                        compile_output="Execution timeout (exceeded {}s)".format(self.timeout),
                        test_results=[],
                        overall_passed=False,
                        execution_time_ms=(time.time() - start_time) * 1000,
                        memory_usage_mb=0,
                        container_id=container_id,
                    )

                # Get logs before removing
                try:
                    logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                except Exception:
                    logs = ""
                finally:
                    # Clean up container
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass

                execution_time = (time.time() - start_time) * 1000

                # Parse results from logs
                return self._parse_results(
                    logs, exit_code, test_cases, execution_time, container_id
                )

            except Exception as e:
                return DockerResult(
                    success=False,
                    compile_output="",
                    test_results=[],
                    overall_passed=False,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    memory_usage_mb=0,
                    container_id=container_id,
                    error=str(e),
                )

    def _build_test_runner(self, code: str, test_cases: List[Dict]) -> str:
        """Build a test runner script that executes in the container."""
        test_cases_json = json.dumps(test_cases, ensure_ascii=False)

        runner = f'''import json
import sys
import traceback

# Load test cases
test_cases = json.loads({repr(test_cases_json)})

# Execute user's code in isolated namespace
user_namespace = {{}}
exec(open("/tmp/solution.py").read(), user_namespace)

results = []
overall_passed = True

for i, tc in enumerate(test_cases):
    input_data = tc.get("input", "")
    expected = tc.get("expected", "")

    try:
        # Try to evaluate expected for comparison
        try:
            expected_val = eval(expected)
        except Exception:
            expected_val = expected

        # Try common function patterns
        result_val = None
        found = False

        for name in ["two_sum", "is_valid", "reverse_list", "level_order", "top_k_frequent", "LRUCache"]:
            if name in user_namespace:
                if name == "LRUCache":
                    result_val = "[class instance]"
                    found = True
                    break
                elif name == "two_sum":
                    import re
                    nums_match = re.search(r"nums=(\[.*?\])", input_data)
                    target_match = re.search(r"target=(\\d+)", input_data)
                    if nums_match and target_match:
                        nums = eval(nums_match.group(1))
                        target = int(target_match.group(1))
                        result_val = user_namespace[name](nums, target)
                        found = True
                        break
                elif name == "is_valid":
                    import re
                    s_match = re.search(r"s='([^']+)'", input_data)
                    if s_match:
                        s = s_match.group(1)
                        result_val = user_namespace[name](s)
                        found = True
                        break
                elif name == "reverse_list":
                    result_val = "[linked list]"
                    found = True
                    break
                else:
                    result_val = user_namespace[name]()
                    found = True
                    break

        if not found:
            # Try to find any function
            for name, obj in user_namespace.items():
                if callable(obj) and not name.startswith("_"):
                    result_val = obj()
                    found = True
                    break

        # Compare results
        if found:
            passed = result_val == expected_val or str(result_val) == str(expected_val)
        else:
            passed = False
            result_val = "Could not find callable function"

        if not passed:
            overall_passed = False

        results.append({{
            "case_id": i + 1,
            "input_data": input_data,
            "expected": expected,
            "actual": str(result_val),
            "passed": passed,
            "error_message": "",
        }})

    except Exception as e:
        overall_passed = False
        results.append({{
            "case_id": i + 1,
            "input_data": input_data,
            "expected": expected,
            "actual": "",
            "passed": False,
            "error_message": str(e),
        }})

# Output results as JSON
print("---RESULTS_START---")
print(json.dumps({{
    "success": overall_passed,
    "overall_passed": overall_passed,
    "test_results": results,
}}))
print("---RESULTS_END---")
'''
        return runner

    def _parse_results(
        self,
        logs: str,
        exit_code: int,
        test_cases: List[Dict],
        execution_time_ms: float,
        container_id: str,
    ) -> DockerResult:
        """Parse test results from container logs."""
        # Try to find JSON results in logs
        import re
        match = re.search(r"---RESULTS_START---\n(.*?)\n---RESULTS_END---", logs, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group(1))
                return DockerResult(
                    success=data.get("success", False),
                    compile_output=logs[:500] if exit_code != 0 else "OK",
                    test_results=data.get("test_results", []),
                    overall_passed=data.get("overall_passed", False),
                    execution_time_ms=execution_time_ms,
                    memory_usage_mb=0,  # Docker stats not collected in this version
                    container_id=container_id,
                )
            except json.JSONDecodeError:
                pass

        # Fallback: compilation/execution error
        return DockerResult(
            success=False,
            compile_output=logs[:1000] if logs else "Execution failed",
            test_results=[],
            overall_passed=False,
            execution_time_ms=execution_time_ms,
            memory_usage_mb=0,
            container_id=container_id,
            error=f"Exit code: {exit_code}",
        )
