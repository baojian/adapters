"""Generate the four-problem pilot while keeping native grading unchanged."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

PILOT = ("abbots_puzzle", "sudoku", "aircraft_landing", "fixed_charge")
UPSTREAM_COMMIT = "3f7e121301e0ea4565e20d8ee0660e799686c194"
HARBOR_COMMIT = "96c86af3bc6d7e92f21fc771d21273be4714c8e9"
TEMPLATE = Path(__file__).parent / "task-template"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def oracle_source(source, reference):
    tree, data, cut, output = reference.parse_source(source)
    imports = [n for n in tree.body[:cut] if isinstance(n, (ast.Import, ast.ImportFrom))]
    body = [n for n in tree.body[:cut] if n not in data and n not in imports]
    assigns = [ast.Assign(targets=[ast.Name(id=key, ctx=ast.Store())], value=ast.Subscript(
        value=ast.Name(id="instance", ctx=ast.Load()), slice=ast.Constant(key), ctx=ast.Load()))
        for key in reference.embedded_instance(source)]
    outputs = reference.OutputExpressions().visit(copy.deepcopy(output))
    ret = ast.Return(value=ast.Tuple(elts=[ast.Name(id="model", ctx=ast.Load()), outputs], ctx=ast.Load()))
    function = ast.FunctionDef(name="build", args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="instance")],
        kwonlyargs=[], kw_defaults=[], defaults=[]), body=assigns + body + [ret], decorator_list=[])
    module = ast.Module(body=imports + [function], type_ignores=[])
    result = "# Oracle derived from pinned upstream reference AST.\n" + ast.unparse(ast.fix_missing_locations(module)) + "\n"
    compile(result, "oracle.py", "exec")
    return result


class DCPBenchOpenAdapter:
    def __init__(self, output_dir: Path, *, source_dir: Path, solver_image_archive: Path,
                 solver_image_id: str, limit: int | None = None, overwrite: bool = False,
                 task_ids: list[str] | None = None, control: str = "correct",
                 controls_dir: Path | None = None, docker_binary_image: str = "docker:28.2.2-dind"):
        self.output_dir = output_dir.resolve()
        self.source_dir = source_dir.resolve()
        self.archive = solver_image_archive.resolve()
        self.image_id = solver_image_id
        self.limit, self.overwrite, self.task_ids = limit, overwrite, task_ids
        self.control, self.controls_dir = control, controls_dir
        self.docker_binary_image = docker_binary_image

    def run(self):
        if not self.archive.is_file():
            raise ValueError(f"Missing docker save archive: {self.archive}")
        if not self.image_id.startswith("sha256:") or len(self.image_id) != 71:
            raise ValueError("--solver-image-id must be the built native image's SHA-256 identity")
        ids = self.task_ids or list(PILOT)
        ids = [p.replace("-", "_").removeprefix("dcp_bench_open/") for p in ids]
        if len(set(ids)) != len(ids) or any(p not in PILOT for p in ids):
            raise ValueError(f"Pilot supports unique IDs from {PILOT}")
        if self.limit is not None:
            if self.limit < 1:
                raise ValueError("--limit must be positive")
            ids = ids[:self.limit]
        pins = json.loads((Path(__file__).parent / "source-pins.json").read_text())
        for relative, expected in pins.items():
            path = self.source_dir / relative
            if not path.is_file() or sha256(path) != expected:
                raise ValueError(f"Source differs from pinned v0.3.0: {relative}")
        # Import only the verified, trusted upstream AST loader; no submitted code.
        sys.path.insert(0, str(self.source_dir))
        from evaluation import reference
        self.output_dir.mkdir(parents=True, exist_ok=True)
        archive_hash = sha256(self.archive)
        for problem in ids:
            self._generate(problem, reference, archive_hash)

    def _generate(self, problem, reference, archive_hash):
        target = self.output_dir / problem.replace("_", "-")
        if target.exists():
            if not self.overwrite:
                raise FileExistsError(f"Refusing to overwrite {target}; pass --overwrite")
            shutil.rmtree(target)
        shutil.copytree(TEMPLATE, target)
        source_path = self.source_dir / "dataset" / problem / f"{problem}.cpmpy.py"
        source = source_path.read_text(encoding="utf-8-sig")
        tree, _, _, output = reference.parse_source(source)
        example = reference.embedded_instance(source)
        rows = json.loads(source_path.with_name(f"{problem}.json").read_text(encoding="utf-8-sig"))
        instance_ids = [i for i, _ in reference.available_instances(source, rows)]
        if self.control == "suboptimal" and problem == "aircraft_landing":
            instance_ids = ["example"]
        model = oracle_source(source, reference)
        if self.control != "correct" and self.controls_dir is None:
            raise ValueError("--controls-dir is required for negative controls")
        if self.controls_dir is not None:
            suffix = "suboptimal_example" if problem == "aircraft_landing" and self.control == "suboptimal" else self.control
            model = (self.controls_dir / f"{problem}_{suffix}.py").read_text()
        (target / "solution" / "model.py").write_text(model)
        write_json(target / "environment" / "example.json", example)
        skill = self.source_dir / "solvers" / "cpmpy_python" / "skills" / "cpmpy-python" / "SKILL.md"
        if not skill.exists():
            skill = next((self.source_dir / "solvers" / "cpmpy_python" / "skills").glob("*/SKILL.md"))
        shutil.copy2(skill, target / "environment" / "CPMPY_SKILL.md")
        brief = ast.get_docstring(tree, clean=False).strip()
        outputs = [key.value for key in output.keys]
        instruction = (TEMPLATE / "instruction.md").read_text()
        instruction = instruction.replace("{brief}", brief).replace("{outputs}", ", ".join(outputs))
        (target / "instruction.md").write_text(instruction)
        config = (TEMPLATE / "task.toml").read_text().replace("{task_id}", problem.replace("_", "-"))
        (target / "task.toml").write_text(config)
        native = target / "tests" / "native"
        shutil.copytree(self.source_dir / "evaluation", native / "evaluation", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        destination = native / "dataset" / problem
        destination.mkdir(parents=True)
        for extension in ("cpmpy.py", "json"):
            shutil.copy2(source_path.with_name(f"{problem}.{extension}"), destination)
        integration = native / "solvers" / "cpmpy_python"
        integration.mkdir(parents=True)
        shutil.copy2(self.source_dir / "solvers" / "cpmpy_python" / "metadata.yaml", integration)
        shutil.copy2(self.source_dir / "LICENSE", native / "LICENSE")
        shutil.copy2(self.source_dir / "SOURCES.md", native / "SOURCES.md")
        # Local pilot only: the native image is loaded into a verifier-private daemon.
        # Copy rather than symlink so task build context is self-contained.
        shutil.copyfile(self.archive, target / "tests" / "solver-image.tar")
        dockerfile = (TEMPLATE / "tests" / "Dockerfile").read_text().replace("{docker_binary_image}", self.docker_binary_image)
        (target / "tests" / "Dockerfile").write_text(dockerfile)
        manifest = {
            "problem": problem, "control": self.control, "instance_ids": instance_ids,
            "upstream_commit": UPSTREAM_COMMIT, "harbor_commit": HARBOR_COMMIT,
            "source_sha256": sha256(source_path), "model_sha256": hashlib.sha256(model.encode()).hexdigest(),
            "solver_image_id": self.image_id,
            "solver_archive_sha256": archive_hash, "solution_limit": 1,
            "execution_timeout": 60, "reference_timeout": 60, "memory_mb": 2048, "cpus": 1,
        }
        write_json(target / "tests" / "case.json", manifest)
        write_json(target / "pilot-manifest.json", manifest)
        print(f"Generated {target.name}: {len(instance_ids)} distinct instances, {self.control}")
