"""
AST-based static code analysis for InterviewCrew.
Extracts complexity metrics, code quality signals, and anti-patterns.
"""

import ast
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ASTAnalysis:
    complexity: int = 0
    lines_of_code: int = 0
    logical_lines: int = 0
    function_count: int = 0
    max_function_length: int = 0
    has_list_comprehension: bool = False
    has_exception_handling: bool = False
    has_recursion: bool = False
    time_complexity: str = "unknown"
    space_complexity: str = "unknown"
    anti_patterns: List[str] = None
    suggestions: List[str] = None

    def __post_init__(self):
        if self.anti_patterns is None:
            self.anti_patterns = []
        if self.suggestions is None:
            self.suggestions = []

    def to_dict(self) -> Dict:
        return {
            "complexity": self.complexity,
            "lines_of_code": self.lines_of_code,
            "logical_lines": self.logical_lines,
            "function_count": self.function_count,
            "max_function_length": self.max_function_length,
            "has_list_comprehension": self.has_list_comprehension,
            "has_exception_handling": self.has_exception_handling,
            "has_recursion": self.has_recursion,
            "time_complexity": self.time_complexity,
            "space_complexity": self.space_complexity,
            "anti_patterns": self.anti_patterns,
            "suggestions": self.suggestions,
        }


def analyze_code(code: str) -> ASTAnalysis:
    """Perform AST-based static analysis on Python code."""
    analysis = ASTAnalysis()

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        analysis.anti_patterns.append(f"Syntax error: {e}")
        return analysis

    lines = code.split("\n")
    analysis.lines_of_code = len(lines)
    analysis.logical_lines = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

    # Collect all functions
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    analysis.function_count = len(functions)

    if functions:
        analysis.max_function_length = max(
            node.end_lineno - node.lineno + 1
            for node in functions
            if hasattr(node, "end_lineno") and node.end_lineno
        )

    # Cyclomatic complexity (simplified)
    complexity = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
    analysis.complexity = complexity

    # Check patterns
    for node in ast.walk(tree):
        if isinstance(node, ast.ListComp):
            analysis.has_list_comprehension = True
        if isinstance(node, ast.Try):
            analysis.has_exception_handling = True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id:
                # Check for recursion
                for func in functions:
                    if func.name == node.func.id:
                        # Simple check: function calls itself
                        pass

    # Detect recursion
    for func in functions:
        for child in ast.walk(func):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                if child.func.id == func.name:
                    analysis.has_recursion = True

    # Infer complexity from AST patterns
    analysis.time_complexity, analysis.space_complexity = _infer_complexity(tree, code)

    # Detect anti-patterns
    _detect_antipatterns(tree, code, analysis)

    return analysis


def _infer_complexity(tree: ast.AST, code: str) -> tuple[str, str]:
    """Infer time/space complexity from code patterns."""
    has_nested_loop = False
    has_single_loop = False
    has_sort = False
    has_binary_search = False
    has_hashmap = False
    has_recursion = False
    has_multiple_recursion = False  # e.g., fib(n-1) + fib(n-2)
    has_list_comp = False

    # Check for recursion patterns first
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    for func in functions:
        func_calls = 0
        has_arithmetic_args = False
        for child in ast.walk(func):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                if child.func.id == func.name:
                    func_calls += 1
                    # Check if args contain arithmetic (fibonacci-style: n-1, n-2)
                    for arg in child.args:
                        if isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Add, ast.Sub)):
                            has_arithmetic_args = True
        # Multiple recursive calls with arithmetic args = exponential (fibonacci-like)
        if func_calls >= 2 and has_arithmetic_args:
            has_multiple_recursion = True
        elif func_calls >= 1:
            has_recursion = True
    # Also detect single recursion
    if not has_recursion and not has_multiple_recursion:
        for func in functions:
            for child in ast.walk(func):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id == func.name:
                        has_recursion = True
                        break

    # Check for loops and list comprehensions
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            has_single_loop = True
            # Check if body contains another loop
            for child in ast.walk(node):
                if child is not node and isinstance(child, (ast.For, ast.While)):
                    has_nested_loop = True
        if isinstance(node, ast.ListComp):
            has_list_comp = True
            has_single_loop = True

    code_lower = code.lower()
    # Only detect actual sort/sorted function calls, not function names containing "sort"
    if ".sort(" in code_lower or "sorted(" in code_lower:
        has_sort = True
    if "bisect" in code_lower:
        has_binary_search = True
    # Detect binary search by pattern: mid/left/right halving
    if "mid" in code_lower and ("left" in code_lower or "right" in code_lower) and "while" in code_lower:
        has_binary_search = True
    # Detect halving loop (power of two, etc.) - only in while loops
    has_halving_while = False
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            for child in ast.walk(node):
                if isinstance(child, ast.AugAssign) and isinstance(child.op, ast.FloorDiv):
                    if isinstance(child.value, ast.Constant) and child.value.value == 2:
                        has_halving_while = True
                elif isinstance(child, ast.BinOp) and isinstance(child.op, ast.FloorDiv):
                    if isinstance(child.right, ast.Constant) and child.right.value == 2:
                        has_halving_while = True
    if has_halving_while:
        has_binary_search = True
    if "dict" in code_lower or "set" in code_lower or "{}" in code:
        has_hashmap = True
    # Detect string slicing / join as O(n) operations
    if "[::-1]" in code or ".join(" in code_lower:
        has_single_loop = True

    # Time complexity inference
    if has_multiple_recursion:
        time_c = "O(2^n)"
    elif has_nested_loop:
        time_c = "O(n^2)"
    elif has_sort:
        time_c = "O(n log n)"
    elif has_binary_search:
        time_c = "O(log n)"
    elif has_single_loop or has_list_comp or has_hashmap:
        time_c = "O(n)"
    elif has_recursion:
        time_c = "O(n)"
    else:
        time_c = "O(1)"

    # Space complexity inference
    if "[[" in code or "nested" in code_lower:
        space_c = "O(n^2)"
    elif has_multiple_recursion:
        # Call stack depth for multiple recursion is still O(n), not O(2^n)
        # The 2^n is time complexity, space is the max depth of the call stack
        space_c = "O(n)"
    elif has_recursion:
        space_c = "O(n)"
    elif has_hashmap or has_sort or has_list_comp:
        space_c = "O(n)"
    # Detect stack/list accumulation patterns (Valid Parentheses, Min Stack)
    elif "append(" in code_lower or "stack" in code_lower or "queue" in code_lower:
        space_c = "O(n)"
    # Detect string operations that create new strings
    elif "[::-1]" in code or ".join(" in code_lower:
        space_c = "O(n)"
    # Detect result array initialization
    elif "result = [" in code or "[1] *" in code or "[0] *" in code:
        space_c = "O(n)"
    elif has_single_loop:
        space_c = "O(1)"
    else:
        space_c = "O(1)"

    return time_c, space_c


def _detect_antipatterns(tree: ast.AST, code: str, analysis: ASTAnalysis) -> None:
    """Detect common anti-patterns and add suggestions."""
    # Missing exception handling in I/O or complex logic
    has_try = any(isinstance(n, ast.Try) for n in ast.walk(tree))
    has_input = "input(" in code or "open(" in code
    if has_input and not has_try:
        analysis.anti_patterns.append("Missing exception handling for I/O operations")
        analysis.suggestions.append("Add try/except blocks for robust error handling")

    # Deep nesting
    max_depth = _max_nesting_depth(tree)
    if max_depth > 4:
        analysis.anti_patterns.append(f"Deep nesting (depth {max_depth})")
        analysis.suggestions.append("Consider early returns or helper functions to reduce nesting")

    # Long functions
    if analysis.max_function_length > 50:
        analysis.anti_patterns.append(f"Very long function ({analysis.max_function_length} lines)")
        analysis.suggestions.append("Break into smaller functions for readability")

    # High complexity
    if analysis.complexity > 10:
        analysis.anti_patterns.append(f"High cyclomatic complexity ({analysis.complexity})")
        analysis.suggestions.append("Refactor to reduce branching complexity")

    # No functions (flat script)
    if analysis.function_count == 0 and analysis.lines_of_code > 10:
        analysis.anti_patterns.append("Code not wrapped in functions")
        analysis.suggestions.append("Wrap logic in functions for reusability and testing")


def _max_nesting_depth(tree: ast.AST) -> int:
    """Calculate maximum nesting depth in the AST."""
    max_depth = 0

    def _depth(node: ast.AST, current: int) -> None:
        nonlocal max_depth
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            current += 1
            max_depth = max(max_depth, current)
        for child in ast.iter_child_nodes(node):
            _depth(child, current)

    for node in ast.iter_child_nodes(tree):
        _depth(node, 0)
    return max_depth
