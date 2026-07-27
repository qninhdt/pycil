"""Enforce Pycil's dependency on Lexi's explicit public boundary only."""

import ast
from pathlib import Path

import lexi_ai.contracts as contracts

_API_ROOT = Path(__file__).parents[2] / "pycil"
_WORKER_ROOT = Path(__file__).parents[3] / "worker" / "pycil_worker"


def _production_files():
    yield from _API_ROOT.rglob("*.py")
    yield from _WORKER_ROOT.rglob("*.py")


def _runtime_boundary_violations(source: str, label: str = "source") -> list[str]:
    tree = ast.parse(source, filename=label)
    importlib_aliases = {"importlib"}
    import_module_aliases = {"import_module"}
    lexicon_types = {"Lexicon"}
    lexicon_instances: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib":
                import_module_aliases.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "import_module"
                )
            if node.module == "lexi_ai":
                lexicon_types.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "Lexicon"
                )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ):
                if (
                    isinstance(argument.annotation, ast.Name)
                    and argument.annotation.id in lexicon_types
                ):
                    lexicon_instances.add(argument.arg)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            value = node.value
            if isinstance(value, ast.Call):
                func = value.func
                constructs_lexicon = (
                    isinstance(func, ast.Name) and func.id in lexicon_types
                ) or (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id in lexicon_types
                )
                if constructs_lexicon:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    lexicon_instances.update(
                        target.id for target in targets if isinstance(target, ast.Name)
                    )

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dynamic_import = (
                isinstance(node.func, ast.Name) and node.func.id in import_module_aliases
            ) or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in importlib_aliases
            )
            if dynamic_import and any(
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.startswith("lexi_ai")
                for arg in node.args
            ):
                violations.append(f"{label}:{node.lineno}: dynamic lexi import")
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
            ):
                receiver, attribute = node.args[:2]
                if (
                    isinstance(receiver, ast.Name)
                    and receiver.id in lexicon_instances
                    and isinstance(attribute, ast.Constant)
                    and isinstance(attribute.value, str)
                    and attribute.value.startswith("_")
                ):
                    violations.append(f"{label}:{node.lineno}: private Lexicon getattr")
        if (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("_")
            and isinstance(node.value, ast.Name)
            and node.value.id in lexicon_instances
        ):
            violations.append(f"{label}:{node.lineno}: private Lexicon attribute")
        elif isinstance(node, ast.Attribute) and node.attr == "_engine":
            violations.append(f"{label}:{node.lineno}: ._engine")
    return violations


def test_required_question_contract_is_installed():
    required = {
        "AnswerSubmission",
        "Evaluation",
        "PrepareDemand",
        "PresentedQuestion",
        "QuestionTypeInfo",
    }
    assert required.issubset(set(dir(contracts)))


def test_production_imports_only_public_lexi_modules():
    violations: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("lexi_ai"):
                        violations.append(f"{path}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("lexi_ai"):
                if node.module == "lexi_ai.contracts":
                    continue
                if node.module == "lexi_ai" and {alias.name for alias in node.names} == {"Lexicon"}:
                    continue
                violations.append(f"{path}:{node.lineno}: from {node.module}")
    assert violations == []


def test_production_has_no_dynamic_or_private_lexi_access():
    violations = [
        violation
        for path in _production_files()
        for violation in _runtime_boundary_violations(path.read_text(), str(path))
    ]
    assert violations == []


def test_runtime_guard_detects_aliases_and_private_access():
    source = """
import importlib as il
from importlib import import_module as dyn
from lexi_ai import Lexicon as PublicLexicon
lexicon = PublicLexicon.from_settings()
il.import_module("lexi_ai.questions.base")
dyn("lexi_ai.persistence")
lexicon._repository
getattr(lexicon, "_engine")
"""
    violations = _runtime_boundary_violations(source)
    assert len(violations) == 4



def test_installed_sense_view_satisfies_the_pycil_port():
    """Every field ``lexi_port.SenseView`` declares must exist on the real build.

    The protocol is structural, so a missing attribute is not a type error — it is
    an ``AttributeError`` at request time, or worse a silently null field. Pinning
    the manifest without syncing the venv is the exact way that happens, so this
    asserts against the INSTALLED dataclass rather than the lockfile.
    """
    from dataclasses import fields

    from lexi_ai.read_models import SenseView as InstalledSenseView

    from pycil.content.lexi_port import SenseView as PortSenseView

    declared = set(PortSenseView.__annotations__)
    installed = {field.name for field in fields(InstalledSenseView)}
    assert declared - installed == set(), (
        f"pycil expects fields Lexi does not provide: {sorted(declared - installed)}"
    )
    # Named explicitly: the headword is what makes a sense listing renderable, and
    # a build without it must fail loudly here rather than serve null words.
    assert {"word", "word_id"} <= installed


def test_installed_nested_sense_views_satisfy_the_pycil_ports():
    from dataclasses import fields

    from lexi_ai.read_models import FormView, ReferenceView, SenseRelationView

    from pycil.content.lexi_port import (
        SenseFormView,
        SenseReferenceView,
    )
    from pycil.content.lexi_port import (
        SenseRelationView as PortSenseRelationView,
    )

    for port, installed_type in (
        (SenseFormView, FormView),
        (SenseReferenceView, ReferenceView),
        (PortSenseRelationView, SenseRelationView),
    ):
        declared = set(port.__annotations__)
        installed = {field.name for field in fields(installed_type)}
        assert declared - installed == set(), (
            f"{port.__name__} expects fields {installed_type.__name__} lacks: "
            f"{sorted(declared - installed)}"
        )
