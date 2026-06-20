"""
Code execution sandbox for InterviewCrew.
Supports real subprocess execution with AST analysis.
"""

import time
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from interview_crew.protocol.schemas import CodingProblem, TestCase
from interview_crew.services.code_executor import execute_python, ExecutionResult
from interview_crew.services.docker_executor import DockerCodeExecutor
from interview_crew.services.ast_analyzer import analyze_code, ASTAnalysis


@dataclass
class SandboxResult:
    """Unified result from code sandbox execution."""
    success: bool
    compile_output: str
    test_results: List[Dict]
    overall_passed: bool
    execution_time_ms: float
    memory_usage_mb: float
    ast_analysis: Dict

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "compile_output": self.compile_output,
            "test_results": self.test_results,
            "overall_passed": self.overall_passed,
            "execution_time_ms": self.execution_time_ms,
            "memory_usage_mb": self.memory_usage_mb,
            "ast_analysis": self.ast_analysis,
        }


class CodeSandbox:
    """
    Production-ready code sandbox with real execution and AST analysis.
    Supports subprocess and Docker execution modes.
    """

    def __init__(self, use_real_execution: bool = True, use_docker: bool = False):
        self.use_real_execution = use_real_execution
        self.use_docker = use_docker
        self.timeout = 2
        self.memory_limit = "256m"
        self._docker_executor: Optional[DockerCodeExecutor] = None

    def _get_docker_executor(self) -> DockerCodeExecutor:
        if self._docker_executor is None:
            self._docker_executor = DockerCodeExecutor(
                timeout=self.timeout,
                memory_limit=self.memory_limit,
            )
        return self._docker_executor

    def execute(
        self,
        code: str,
        test_cases: List,
        language: str = "python"
    ) -> SandboxResult:
        """
        Execute code against test cases with full analysis.
        """
        if not self.use_real_execution or language != "python":
            return self._execute_mock(code, test_cases, language)

        # Docker execution (preferred if available)
        if self.use_docker:
            try:
                docker_result = self._get_docker_executor().execute(code, test_cases, language)
                if not docker_result.error or "Docker not available" not in docker_result.error:
                    return SandboxResult(
                        success=docker_result.success,
                        compile_output=docker_result.compile_output,
                        test_results=docker_result.test_results,
                        overall_passed=docker_result.overall_passed,
                        execution_time_ms=docker_result.execution_time_ms,
                        memory_usage_mb=docker_result.memory_usage_mb,
                        ast_analysis=analyze_code(code).to_dict(),
                    )
            except Exception:
                pass  # Fall through to subprocess

        # Subprocess execution (fallback)
        exec_result = execute_python(
            code,
            test_cases,
            timeout=self.timeout,
        )

        # AST analysis
        ast_result = analyze_code(code)

        return SandboxResult(
            success=exec_result.success,
            compile_output=exec_result.compile_output,
            test_results=[self._test_result_to_dict(tr) for tr in exec_result.test_results],
            overall_passed=exec_result.overall_passed,
            execution_time_ms=exec_result.execution_time_ms,
            memory_usage_mb=exec_result.memory_usage_mb,
            ast_analysis=ast_result.to_dict(),
        )

    def _test_result_to_dict(self, tr) -> Dict:
        """Convert TestResult dataclass or dict to dict."""
        if hasattr(tr, "to_dict"):
            return tr.to_dict()
        if hasattr(tr, "__dict__"):
            return tr.__dict__
        return dict(tr)

    def _execute_mock(
        self,
        code: str,
        test_cases: List,
        language: str
    ) -> SandboxResult:
        """Fallback mock execution."""
        start_time = time.time()
        test_results = []
        overall_passed = True

        try:
            compile(code, '<string>', 'exec')
            compile_success = True
            compile_output = "Syntax OK (mock mode)"
        except SyntaxError as e:
            compile_success = False
            compile_output = f"SyntaxError: {e}"
            overall_passed = False

        if compile_success:
            for i, tc in enumerate(test_cases):
                has_function = "def " in code or "class " in code
                has_solution_logic = len(code.strip().split('\n')) > 3

                input_data = tc.get("input", "") if isinstance(tc, dict) else getattr(tc, "input", "")
                expected = tc.get("expected", "") if isinstance(tc, dict) else getattr(tc, "expected", "")

                if has_function and has_solution_logic:
                    passed = True
                    actual = expected
                    error = ""
                else:
                    passed = False
                    actual = ""
                    error = "Code appears incomplete"
                    overall_passed = False

                test_results.append({
                    "case_id": i + 1,
                    "input_data": input_data,
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                    "error_message": error,
                })
        else:
            for i, tc in enumerate(test_cases):
                input_data = tc.get("input", "") if isinstance(tc, dict) else getattr(tc, "input", "")
                expected = tc.get("expected", "") if isinstance(tc, dict) else getattr(tc, "expected", "")
                test_results.append({
                    "case_id": i + 1,
                    "input_data": input_data,
                    "expected": expected,
                    "actual": "",
                    "passed": False,
                    "error_message": "Compilation failed",
                })

        execution_time = (time.time() - start_time) * 1000

        return SandboxResult(
            success=compile_success,
            compile_output=compile_output,
            test_results=test_results,
            overall_passed=overall_passed,
            execution_time_ms=execution_time,
            memory_usage_mb=10.0,
            ast_analysis=analyze_code(code).to_dict(),
        )

    def generate_problem(
        self,
        tech_stack: List[str],
        difficulty: str,
        resume_context: str = ""
    ) -> CodingProblem:
        """Generate a coding problem from built-in bank."""
        problems = self._get_problem_bank()

        if difficulty == "easy":
            pool = problems["easy"]
        elif difficulty == "medium":
            pool = problems["medium"]
        else:
            pool = problems["easy"] + problems["medium"]

        import random
        problem_template = random.choice(pool)

        return CodingProblem(
            title=problem_template["title"],
            description=problem_template["description"],
            difficulty=difficulty,
            starter_code=problem_template["starter_code"],
            test_cases=[TestCase(**tc) for tc in problem_template["test_cases"]],
            time_limit_sec=2,
            memory_limit_mb=256
        )

    def _get_problem_bank(self) -> Dict:
        """Built-in problem bank."""
        return {
            "easy": [
                {
                    "title": "Two Sum",
                    "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
                    "starter_code": "def two_sum(nums, target):\n    # Write your code here\n    pass\n",
                    "test_cases": [
                        {"input": "nums=[2,7,11,15], target=9", "expected": "[0,1]"},
                        {"input": "nums=[3,2,4], target=6", "expected": "[1,2]"},
                        {"input": "nums=[3,3], target=6", "expected": "[0,1]"}
                    ]
                },
                {
                    "title": "Valid Parentheses",
                    "description": "Given a string s containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.",
                    "starter_code": "def is_valid(s):\n    # Write your code here\n    pass\n",
                    "test_cases": [
                        {"input": "s='()'", "expected": "True"},
                        {"input": "s='()[]{}'", "expected": "True"},
                        {"input": "s='(]'", "expected": "False"}
                    ]
                },
                {
                    "title": "Reverse Linked List",
                    "description": "Given the head of a singly linked list, reverse the list, and return the reversed list.",
                    "starter_code": "# Definition for singly-linked list.\nclass ListNode:\n    def __init__(self, val=0, next=None):\n        self.val = val\n        self.next = next\n\ndef reverse_list(head):\n    # Write your code here\n    pass\n",
                    "test_cases": [
                        {"input": "head=[1,2,3,4,5]", "expected": "[5,4,3,2,1]"},
                        {"input": "head=[1,2]", "expected": "[2,1]"},
                        {"input": "head=[]", "expected": "[]"}
                    ]
                }
            ],
            "medium": [
                {
                    "title": "LRU Cache",
                    "description": "Design a data structure that follows the constraints of a Least Recently Used (LRU) cache.",
                    "starter_code": "class LRUCache:\n    def __init__(self, capacity):\n        # Initialize the cache\n        pass\n    \n    def get(self, key):\n        # Return the value if key exists, otherwise -1\n        pass\n    \n    def put(self, key, value):\n        # Update the value if key exists, otherwise add key-value pair\n        pass\n",
                    "test_cases": [
                        {"input": "operations=['LRUCache','put','put','get','put','get','put','get','get'], params=[[2],[1,1],[2,2],[1],[3,3],[2],[4,4],[1],[3],[4]]", "expected": "[None,None,None,1,None,-1,None,-1,3,4]"},
                        {"input": "operations=['LRUCache','put','get'], params=[[1],[2,1],[2]]", "expected": "[None,None,1]"}
                    ]
                },
                {
                    "title": "Binary Tree Level Order Traversal",
                    "description": "Given the root of a binary tree, return the level order traversal of its nodes' values.",
                    "starter_code": "# Definition for a binary tree node.\nclass TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef level_order(root):\n    # Write your code here\n    pass\n",
                    "test_cases": [
                        {"input": "root=[3,9,20,null,null,15,7]", "expected": "[[3],[9,20],[15,7]]"},
                        {"input": "root=[1]", "expected": "[[1]]"},
                        {"input": "root=[]", "expected": "[]"}
                    ]
                },
                {
                    "title": "Top K Frequent Elements",
                    "description": "Given an integer array nums and an integer k, return the k most frequent elements.",
                    "starter_code": "def top_k_frequent(nums, k):\n    # Write your code here\n    pass\n",
                    "test_cases": [
                        {"input": "nums=[1,1,1,2,2,3], k=2", "expected": "[1,2]"},
                        {"input": "nums=[1], k=1", "expected": "[1]"},
                        {"input": "nums=[4,1,-1,2,-1,2,3], k=2", "expected": "[-1,2]"}
                    ]
                }
            ]
        }


# Global singleton — auto-detect Docker availability
code_sandbox = CodeSandbox(use_real_execution=True, use_docker=True)
