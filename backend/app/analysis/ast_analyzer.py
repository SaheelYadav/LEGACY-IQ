"""Safe static Python AST parser foundation (zero dynamic execution)."""

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class PythonSymbolDescriptor:
    """Static descriptor for a parsed Python function or class."""

    name: str
    kind: str  # "function" | "async_function" | "class"
    lineno: int
    end_lineno: int | None


def parse_python_symbols_safely(source_code: str) -> list[PythonSymbolDescriptor]:
    """
    Parse Python source text using the standard library `ast.parse` without
    executing any code.
    """
    tree = ast.parse(source_code)
    symbols: list[PythonSymbolDescriptor] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append(
                PythonSymbolDescriptor(
                    name=node.name,
                    kind="function",
                    lineno=node.lineno,
                    end_lineno=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(
                PythonSymbolDescriptor(
                    name=node.name,
                    kind="async_function",
                    lineno=node.lineno,
                    end_lineno=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                PythonSymbolDescriptor(
                    name=node.name,
                    kind="class",
                    lineno=node.lineno,
                    end_lineno=getattr(node, "end_lineno", None),
                )
            )
    return symbols

