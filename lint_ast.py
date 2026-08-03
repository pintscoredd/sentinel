#!/usr/bin/env python3
"""SENTINEL — Advanced Static Analysis (AST-based Linter)

Features:
  1. Undefined variable detection
  2. Unused variable detection
  3. Builtin shadowing detection
  4. Type annotation checking
  5. CLI with glob support

Usage:
  python lint_ast.py                           # Lint default project files
  python lint_ast.py src/                      # Lint all .py files in src/
  python lint_ast.py src/ --glob "*.py"        # Custom glob pattern
  python lint_ast.py file.py --no-unused       # Disable unused-var checks
  python lint_ast.py file.py --no-shadow       # Disable builtin-shadow checks
  python lint_ast.py file.py --no-annotations  # Disable type annotation checks
"""

import ast
import builtins
import sys
import os
import argparse
import glob as _glob_module

_DANGEROUS_BUILTINS = frozenset({
    "list", "dict", "set", "tuple", "frozenset",
    "str", "int", "float", "bool", "bytes", "bytearray",
    "type", "id", "input", "print", "len", "range", "map", "filter",
    "zip", "enumerate", "sorted", "reversed", "min", "max", "sum",
    "abs", "round", "hash", "hex", "oct", "bin", "ord", "chr",
    "any", "all", "next", "iter", "open", "format", "repr",
    "object", "property", "staticmethod", "classmethod",
    "super", "isinstance", "issubclass", "callable", "hasattr",
    "getattr", "setattr", "delattr", "vars", "dir",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration", "OSError",
    "IOError", "FileNotFoundError", "ImportError", "NameError",
    "NotImplementedError", "ZeroDivisionError", "OverflowError",
})

_UNUSED_EXCEPTIONS = frozenset({
    "_", "__all__", "__version__", "__author__", "__doc__",
})


def check(file_path, *, enable_unused=True, enable_shadow=True, enable_annotations=True):
    """Run all enabled lint checks on a single Python file.

    Args:
        file_path: Path to the .py file to analyze.
        enable_unused: If True, report variables that are assigned but never read.
        enable_shadow: If True, report assignments that shadow Python builtins.
        enable_annotations: If True, report unresolvable names in type annotations.

    Returns:
        dict with keys: 'undefined', 'unused', 'shadow', 'annotations'
        Each value is a list of (line, name, detail) tuples.
    """
    results = {"undefined": [], "unused": [], "shadow": [], "annotations": []}

    try:
        with open(file_path) as f:
            code = f.read()
        tree = ast.parse(code, filename=file_path)
    except SyntaxError as e:
        print(f"{file_path}: SyntaxError: {e}")
        return results

    class Checker(ast.NodeVisitor):
        def __init__(self):
            self.defined = set(dir(builtins))
            self.defined.update({
                "__file__", "__name__", "__doc__", "__spec__",
                "__loader__", "__package__", "__builtins__",
                "__all__", "__cached__", "__path__",
            })
            self.used = set()
            self.errors = []
            self.scopes = [self.defined]

            self.assignments = []
            self.usages = set()
            self._in_class_depth = 0

            self.shadow_warnings = []

            self.annotation_errors = []
            self._in_annotation = False

        def _record_def(self, name, lineno, is_import=False, is_method=False):
            """Register a variable definition in the current scope."""
            self.scopes[-1].add(name)
            scope_depth = len(self.scopes) - 1
            self.assignments.append((name, lineno, scope_depth, is_import, is_method))

            if enable_shadow and name in _DANGEROUS_BUILTINS:
                self.shadow_warnings.append((lineno, name))

        def visit_Import(self, node):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                self._record_def(name, node.lineno, is_import=True)

        def visit_ImportFrom(self, node):
            for alias in node.names:
                name = alias.asname or alias.name
                self._record_def(name, node.lineno, is_import=True)

        def visit_Assign(self, node):
            self.visit(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._record_def(target.id, node.lineno)
                self.visit(target)

        def visit_AugAssign(self, node):
            """Handle augmented assignments (+=, -=, etc.)."""
            self.visit(node.value)
            if isinstance(node.target, ast.Name):
                self._record_def(node.target.id, node.lineno)
            self.visit(node.target)

        def visit_AnnAssign(self, node):
            """Handle annotated assignments (x: int = 5)."""
            if node.value:
                self.visit(node.value)
            if isinstance(node.target, ast.Name):
                self._record_def(node.target.id, node.lineno)
            if node.annotation:
                self._visit_annotation(node.annotation)

        def visit_For(self, node):
            """Handle for-loop targets (for x in ...)."""
            if isinstance(node.target, ast.Name):
                self._record_def(node.target.id, node.lineno)
            elif isinstance(node.target, ast.Tuple):
                for elt in node.target.elts:
                    if isinstance(elt, ast.Name):
                        self._record_def(elt.id, node.lineno)
            self.generic_visit(node)

        def visit_AsyncFor(self, node):
            """Handle async for-loop targets."""
            self.visit_For(node)

        def visit_With(self, node):
            """Handle with-statement targets (with expr as x)."""
            for item in node.items:
                self.visit(item.context_expr)
                if item.optional_vars:
                    if isinstance(item.optional_vars, ast.Name):
                        self._record_def(item.optional_vars.id, node.lineno)
                    elif isinstance(item.optional_vars, ast.Tuple):
                        for elt in item.optional_vars.elts:
                            if isinstance(elt, ast.Name):
                                self._record_def(elt.id, node.lineno)
            self.generic_visit(node)

        def visit_AsyncWith(self, node):
            """Handle async with-statement targets."""
            self.visit_With(node)

        def visit_ExceptHandler(self, node):
            """Handle except clauses (except Exception as e)."""
            if node.name:
                self._record_def(node.name, node.lineno)
            self.generic_visit(node)

        def visit_Global(self, node):
            """Handle global declarations.
            
            L14 fix: `global x` declares that `x` refers to the MODULE scope,
            not the current (function) scope. Must add to scopes[0] (module),
            not scopes[-1] (current). Otherwise inner functions using `global`
            create a false-positive 'undefined variable' for the global name.
            """
            for name in node.names:
                self.scopes[0].add(name)

        def visit_Nonlocal(self, node):
            """Handle nonlocal declarations."""
            for name in node.names:
                self.scopes[-1].add(name)

        def visit_Lambda(self, node):
            """Handle lambda expressions with their own scope."""
            self.scopes.append(set())
            for arg in node.args.args:
                self.scopes[-1].add(arg.arg)
            if node.args.vararg:
                self.scopes[-1].add(node.args.vararg.arg)
            if node.args.kwarg:
                self.scopes[-1].add(node.args.kwarg.arg)
            for arg in node.args.kwonlyargs:
                self.scopes[-1].add(arg.arg)
            self.generic_visit(node)
            self.scopes.pop()

        def visit_ListComp(self, node):
            """Handle list comprehensions with their own scope."""
            self.scopes.append(set())
            for gen in node.generators:
                if isinstance(gen.target, ast.Name):
                    self.scopes[-1].add(gen.target.id)
                elif isinstance(gen.target, ast.Tuple):
                    for elt in gen.target.elts:
                        if isinstance(elt, ast.Name):
                            self.scopes[-1].add(elt.id)
            self.generic_visit(node)
            self.scopes.pop()

        def visit_SetComp(self, node):
            """Handle set comprehensions."""
            self.visit_ListComp(node)

        def visit_GeneratorExp(self, node):
            """Handle generator expressions."""
            self.visit_ListComp(node)

        def visit_DictComp(self, node):
            """Handle dict comprehensions."""
            self.scopes.append(set())
            for gen in node.generators:
                if isinstance(gen.target, ast.Name):
                    self.scopes[-1].add(gen.target.id)
                elif isinstance(gen.target, ast.Tuple):
                    for elt in gen.target.elts:
                        if isinstance(elt, ast.Name):
                            self.scopes[-1].add(elt.id)
            self.generic_visit(node)
            self.scopes.pop()

        def visit_AsyncFunctionDef(self, node):
            """Handle async function definitions (same scoping as regular functions)."""
            self.visit_FunctionDef(node)

        def visit_NamedExpr(self, node):
            """Handle walrus operator (:=)."""
            self.visit(node.value)
            if isinstance(node.target, ast.Name):
                self._record_def(node.target.id, node.lineno)

        def visit_FunctionDef(self, node):
            is_method = self._in_class_depth > 0
            self._record_def(node.name, node.lineno, is_method=is_method)
            self.scopes.append(set())
            for arg in node.args.args:
                self.scopes[-1].add(arg.arg)
            if node.args.vararg: self.scopes[-1].add(node.args.vararg.arg)
            if node.args.kwarg: self.scopes[-1].add(node.args.kwarg.arg)
            for arg in node.args.kwonlyargs:
                self.scopes[-1].add(arg.arg)
            for arg in node.args.posonlyargs:
                self.scopes[-1].add(arg.arg)
            for dec in node.decorator_list:
                self.visit(dec)

            if enable_annotations:
                if node.returns:
                    self._visit_annotation(node.returns)
                for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                    if arg.annotation:
                        self._visit_annotation(arg.annotation)
                if node.args.vararg and node.args.vararg.annotation:
                    self._visit_annotation(node.args.vararg.annotation)
                if node.args.kwarg and node.args.kwarg.annotation:
                    self._visit_annotation(node.args.kwarg.annotation)

            self.generic_visit(node)
            self.scopes.pop()

        def visit_Match(self, node):
            """Handle match/case statements (Python 3.10+ PEP 634)."""
            self.visit(node.subject)
            for case in node.cases:
                self._visit_match_pattern(case.pattern)
                if case.guard:
                    self.visit(case.guard)
                for stmt in case.body:
                    self.visit(stmt)

        def _visit_match_pattern(self, pattern):
            """Walk match patterns and register any captured names."""
            if pattern is None:
                return
            if hasattr(ast, 'MatchAs') and isinstance(pattern, ast.MatchAs):
                if pattern.pattern:
                    self._visit_match_pattern(pattern.pattern)
                if pattern.name:
                    self._record_def(pattern.name, pattern.lineno)
            elif hasattr(ast, 'MatchStar') and isinstance(pattern, ast.MatchStar):
                if pattern.name:
                    self._record_def(pattern.name, pattern.lineno)
            elif hasattr(ast, 'MatchMapping') and isinstance(pattern, ast.MatchMapping):
                for key in pattern.keys:
                    self.visit(key)
                for pat in pattern.patterns:
                    self._visit_match_pattern(pat)
                if pattern.rest:
                    self._record_def(pattern.rest, pattern.lineno)
            elif hasattr(ast, 'MatchClass') and isinstance(pattern, ast.MatchClass):
                self.visit(pattern.cls)
                for pat in pattern.patterns:
                    self._visit_match_pattern(pat)
                for pat in pattern.kwd_patterns:
                    self._visit_match_pattern(pat)
            elif hasattr(ast, 'MatchOr') and isinstance(pattern, ast.MatchOr):
                for pat in pattern.patterns:
                    self._visit_match_pattern(pat)
            elif hasattr(ast, 'MatchSequence') and isinstance(pattern, ast.MatchSequence):
                for pat in pattern.patterns:
                    self._visit_match_pattern(pat)
            elif hasattr(ast, 'MatchValue') and isinstance(pattern, ast.MatchValue):
                self.visit(pattern.value)

        def visit_ClassDef(self, node):
            self._record_def(node.name, node.lineno)
            for dec in node.decorator_list:
                self.visit(dec)
            for base in node.bases:
                self.visit(base)
            self.scopes.append(set())
            self._in_class_depth += 1
            self.generic_visit(node)
            self._in_class_depth -= 1
            self.scopes.pop()

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self.usages.add(node.id)
                found = False
                for scope in reversed(self.scopes):
                    if node.id in scope:
                        found = True
                        break
                if not found:
                    self.errors.append((node.lineno, node.id))
            elif isinstance(node.ctx, ast.Store):
                self.scopes[-1].add(node.id)
            elif isinstance(node.ctx, ast.Del):
                pass

        def _visit_annotation(self, node):
            """Walk a type annotation subtree, checking that all Name references resolve."""
            if isinstance(node, ast.Name):
                found = False
                for scope in reversed(self.scopes):
                    if node.id in scope:
                        found = True
                        break
                if not found:
                    self.annotation_errors.append((node.lineno, node.id))
            elif isinstance(node, ast.Attribute):
                self._visit_annotation(node.value)
            elif isinstance(node, ast.Subscript):
                self._visit_annotation(node.value)
                self._visit_annotation(node.slice)
            elif isinstance(node, ast.Tuple):
                for elt in node.elts:
                    self._visit_annotation(elt)
            elif isinstance(node, ast.List):
                for elt in node.elts:
                    self._visit_annotation(elt)
            elif isinstance(node, ast.BinOp):
                self._visit_annotation(node.left)
                self._visit_annotation(node.right)
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, str):
                    try:
                        inner = ast.parse(node.value, mode='eval').body
                        self._visit_annotation(inner)
                    except SyntaxError:
                        pass

    checker = Checker()
    checker.visit(tree)

    if checker.errors:
        for line, name in sorted(set(checker.errors)):
            results["undefined"].append((line, name, "possibly undefined"))

    if enable_unused:
        used_names = checker.usages
        for name, lineno, scope_depth, is_import, is_method in checker.assignments:
            if name in _UNUSED_EXCEPTIONS:
                continue
            if name.startswith("__") and name.endswith("__"):
                continue
            if name.startswith("_") and scope_depth == 0:
                continue
            if scope_depth == 0 and not is_import:
                continue
            if is_method:
                continue
            if name not in used_names:
                results["unused"].append((lineno, name, "assigned but never used"))

    if enable_shadow and checker.shadow_warnings:
        for line, name in sorted(set(checker.shadow_warnings)):
            results["shadow"].append((line, name, f"shadows builtin '{name}'"))

    if enable_annotations and checker.annotation_errors:
        for line, name in sorted(set(checker.annotation_errors)):
            if not any(e[0] == line and e[1] == name for e in results["undefined"]):
                results["annotations"].append((line, name, "unresolved type annotation"))

    return results


def _print_results(file_path, results):
    """Pretty-print lint results for a single file."""
    has_output = False

    if results["undefined"]:
        has_output = True
        print(f"\n{'─'*60}")
        print(f"  ⛔ UNDEFINED VARIABLES — {file_path}")
        print(f"{'─'*60}")
        for line, name, detail in sorted(results["undefined"]):
            print(f"  Line {line:>4}: {name:<30} [{detail}]")

    if results["unused"]:
        has_output = True
        print(f"\n{'─'*60}")
        print(f"  ⚠️  UNUSED VARIABLES — {file_path}")
        print(f"{'─'*60}")
        for line, name, detail in sorted(results["unused"]):
            print(f"  Line {line:>4}: {name:<30} [{detail}]")

    if results["shadow"]:
        has_output = True
        print(f"\n{'─'*60}")
        print(f"  🔶 BUILTIN SHADOWING — {file_path}")
        print(f"{'─'*60}")
        for line, name, detail in sorted(results["shadow"]):
            print(f"  Line {line:>4}: {name:<30} [{detail}]")

    if results["annotations"]:
        has_output = True
        print(f"\n{'─'*60}")
        print(f"  📝 TYPE ANNOTATION ISSUES — {file_path}")
        print(f"{'─'*60}")
        for line, name, detail in sorted(results["annotations"]):
            print(f"  Line {line:>4}: {name:<30} [{detail}]")

    if not has_output:
        print(f"  ✅ {file_path} — no issues found")

    return has_output


def _count_issues(results):
    """Return total number of issues across all categories."""
    return sum(len(v) for v in results.values())


def main():
    parser = argparse.ArgumentParser(
        description="SENTINEL AST Linter — Static analysis for Python projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python lint_ast.py                                 # Lint default project files
  python lint_ast.py src/                            # Lint all .py files in src/
  python lint_ast.py src/ --glob "**/*.py"           # Recursive glob
  python lint_ast.py file.py --no-unused             # Skip unused variable checks
  python lint_ast.py file.py --no-shadow             # Skip builtin shadow checks
  python lint_ast.py . --glob "*.py" --strict        # Non-zero exit on any issue (CI mode)
        """,
    )
    parser.add_argument(
        "targets", nargs="*", default=None,
        help="Files or directories to lint. Defaults to project files if omitted.",
    )
    parser.add_argument(
        "--glob", "-g", default="*.py",
        help="Glob pattern for file matching within directories (default: '*.py'). "
             "Use '**/*.py' for recursive.",
    )
    parser.add_argument(
        "--no-unused", action="store_true",
        help="Disable unused variable detection.",
    )
    parser.add_argument(
        "--no-shadow", action="store_true",
        help="Disable builtin shadowing detection.",
    )
    parser.add_argument(
        "--no-annotations", action="store_true",
        help="Disable type annotation checking.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit with code 1 if any issues are found (useful for CI/CD).",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print a summary table at the end.",
    )

    args = parser.parse_args()

    files_to_lint = []

    if args.targets is None or len(args.targets) == 0:
        default_files = ["data_fetchers.py", "sentinel_app.py", "ui_components.py"]
        files_to_lint = [f for f in default_files if os.path.isfile(f)]
        if not files_to_lint:
            print("No default project files found. Specify files or directories.")
            sys.exit(1)
    else:
        for target in args.targets:
            if os.path.isfile(target):
                files_to_lint.append(target)
            elif os.path.isdir(target):
                pattern = os.path.join(target, args.glob)
                matched = sorted(_glob_module.glob(pattern, recursive=True))
                if not matched:
                    print(f"Warning: no files matched pattern '{pattern}'")
                files_to_lint.extend(matched)
            else:
                matched = sorted(_glob_module.glob(target, recursive=True))
                if matched:
                    files_to_lint.extend(matched)
                else:
                    print(f"Warning: '{target}' not found")

    if not files_to_lint:
        print("No files to lint.")
        sys.exit(1)

    seen = set()
    unique_files = []
    for f in files_to_lint:
        f_abs = os.path.abspath(f)
        if f_abs not in seen:
            seen.add(f_abs)
            unique_files.append(f)
    files_to_lint = unique_files

    print(f"\n{'═'*60}")
    print(f"  ⚡ SENTINEL AST LINTER")
    print(f"  Scanning {len(files_to_lint)} file(s)")
    print(f"{'═'*60}")

    total_issues = 0
    file_summaries = []

    for f in files_to_lint:
        results = check(
            f,
            enable_unused=not args.no_unused,
            enable_shadow=not args.no_shadow,
            enable_annotations=not args.no_annotations,
        )
        _print_results(f, results)
        count = _count_issues(results)
        total_issues += count
        file_summaries.append((f, results))

    if args.summary or len(files_to_lint) > 1:
        print(f"\n{'═'*60}")
        print(f"  SUMMARY")
        print(f"{'═'*60}")
        print(f"  {'FILE':<35} {'UNDEF':>6} {'UNUSED':>7} {'SHADOW':>7} {'ANNOT':>6} {'TOTAL':>6}")
        print(f"  {'─'*35} {'─'*6} {'─'*7} {'─'*7} {'─'*6} {'─'*6}")
        for f, results in file_summaries:
            fname = os.path.basename(f)
            u = len(results["undefined"])
            n = len(results["unused"])
            s = len(results["shadow"])
            a = len(results["annotations"])
            t = u + n + s + a
            print(f"  {fname:<35} {u:>6} {n:>7} {s:>7} {a:>6} {t:>6}")
        print(f"  {'─'*35} {'─'*6} {'─'*7} {'─'*7} {'─'*6} {'─'*6}")
        print(f"  {'TOTAL':<35} {sum(len(r['undefined']) for _,r in file_summaries):>6} "
              f"{sum(len(r['unused']) for _,r in file_summaries):>7} "
              f"{sum(len(r['shadow']) for _,r in file_summaries):>7} "
              f"{sum(len(r['annotations']) for _,r in file_summaries):>6} "
              f"{total_issues:>6}")

    print(f"\n  {'🔴' if total_issues else '✅'} {total_issues} issue(s) found.\n")

    if args.strict and total_issues > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
