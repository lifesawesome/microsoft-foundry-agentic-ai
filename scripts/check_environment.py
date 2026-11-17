"""Check shared notebook configuration; --fix migrates legacy dotenv paths."""

import argparse
import ast
import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from dotenv import dotenv_values, find_dotenv, load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def parse_cell(source):
    lines = source.splitlines(keepends=True)
    masked = "".join(
        "\n" if line.lstrip().startswith(("%", "!")) else line for line in lines
    )
    return ast.parse(masked)


def dotenv_calls(tree):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_dotenv"
    ]


def environment_path_kind(argument, tree):
    discovery = ast.parse("find_dotenv(usecwd=True)", mode="eval").body
    if ast.dump(argument) == ast.dump(discovery):
        return "discovery"
    assignments = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    if isinstance(argument, ast.Name):
        value = assignments.get(argument.id)
        if value is not None and ast.dump(value) == ast.dump(discovery):
            return "discovery"
    root_path = ast.parse("repo_root / '.env'", mode="eval").body
    if ast.dump(argument) == ast.dump(root_path) and "repo_root" in assignments:
        for variable in ("p", "path"):
            resolver = ast.parse(
                f"next({variable} for {variable} in (Path.cwd(), *Path.cwd().parents) "
                f"if ({variable} / 'requirements.in').is_file())",
                mode="eval",
            ).body
            if ast.dump(assignments["repo_root"]) == ast.dump(resolver):
                return "root"
    return None


def migrate_source(source):
    tree = parse_cell(source)
    calls = [
        call for call in dotenv_calls(tree)
        if not call.args or environment_path_kind(call.args[0], tree) is None
    ]
    if not calls:
        return source
    lines = source.splitlines(keepends=True)

    def offset(line, column):
        return sum(len(part) for part in lines[: line - 1]) + len(
            lines[line - 1].encode("utf-8")[:column].decode("utf-8")
        )

    replacements = []
    for call in calls:
        if not call.args:
            raise ValueError("Notebook dotenv calls must have an explicit path.")
        argument = call.args[0]
        replacements.append(
            (
                offset(argument.lineno, argument.col_offset),
                offset(argument.end_lineno, argument.end_col_offset),
                "find_dotenv(usecwd=True)",
            )
        )
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    if "from dotenv import find_dotenv, load_dotenv" not in source:
        source = source.replace(
            "from dotenv import load_dotenv",
            "from dotenv import find_dotenv, load_dotenv",
        )
    return source


@contextmanager
def working_directory(directory):
    original = Path.cwd()
    try:
        os.chdir(directory)
        yield
    finally:
        os.chdir(original)


def check_notebooks(fix=False):
    checked = 0
    changed = 0
    for folder in (
        "agent-framework",
        "azure-ai-agents",
        "observability-and-evaluations",
    ):
        for path in sorted((ROOT / folder).rglob("*.ipynb")):
            original = path.read_text(encoding="utf-8")
            notebook = json.loads(original)
            modified = False
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] != "code":
                    continue
                source = "".join(cell["source"])
                if "load_dotenv(" not in source:
                    continue
                migrated = migrate_source(source)
                metadata = cell.get("metadata", {})
                if fix and (
                    source != migrated
                    or not metadata.get("id")
                    or metadata.get("language") != "python"
                ):
                    cell["source"] = migrated.splitlines(keepends=True)
                    cell.setdefault("metadata", {})["language"] = "python"
                    cell["metadata"].setdefault(
                        "id",
                        cell.get("id")
                        or uuid5(
                            NAMESPACE_URL, f"{path.relative_to(ROOT)}:{index}"
                        ).hex[:8],
                    )
                    modified = True
                    source = migrated
                if migrate_source(source) != source:
                    raise ValueError(
                        f"Legacy dotenv path: {path.relative_to(ROOT)} cell {index + 1}"
                    )
                tree = parse_cell(source)
                calls = dotenv_calls(tree)
                for directory in (ROOT, path.parent):
                    with (
                        working_directory(directory),
                        patch.dict(os.environ, {}, clear=True),
                    ):
                        if Path(find_dotenv(usecwd=True)) != ROOT / ".env":
                            raise ValueError(
                                f"Unexpected .env discovered from {directory}"
                            )
                        for call in calls:
                            options = {
                                keyword.arg: ast.literal_eval(keyword.value)
                                for keyword in call.keywords
                            }
                            kind = environment_path_kind(call.args[0], tree)
                            if kind == "root":
                                root = next(
                                    parent for parent in (Path.cwd(), *Path.cwd().parents)
                                    if (parent / "requirements.in").is_file()
                                )
                                env_path = root / ".env"
                            elif kind == "discovery":
                                env_path = Path(find_dotenv(usecwd=True))
                            else:
                                raise ValueError(f"Unsupported dotenv path: {path.relative_to(ROOT)}")
                            if env_path != ROOT / ".env":
                                raise ValueError(f"Unexpected dotenv path: {env_path}")
                            load_dotenv(env_path, **options)
                        if (
                            os.environ.get("AI_FOUNDRY_PROJECT_ENDPOINT")
                            != dotenv_values(ROOT / ".env")[
                                "AI_FOUNDRY_PROJECT_ENDPOINT"
                            ]
                        ):
                            raise ValueError(
                                f"Shared environment not loaded: {path.relative_to(ROOT)}"
                            )
                checked += 1
            if modified:
                path.write_text(
                    json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8",
                )
                changed += 1
    print(
        f"PASS: {checked} notebook configuration cells load the root .env from root and nested directories"
    )
    if fix:
        print(f"Migrated {changed} notebooks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Mechanically migrate old notebook dotenv paths.",
    )
    arguments = parser.parse_args()
    values = dotenv_values(ROOT / ".env")
    if not values.get("AI_FOUNDRY_PROJECT_ENDPOINT"):
        raise ValueError("Configure the root .env before running this check.")
    if values["AI_FOUNDRY_PROJECT_ENDPOINT"] != values.get("FOUNDRY_PROJECT_ENDPOINT"):
        raise ValueError("Project endpoint aliases do not match.")
    check_notebooks(fix=arguments.fix)


if __name__ == "__main__":
    main()
