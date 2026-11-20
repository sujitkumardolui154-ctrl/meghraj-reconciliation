"""Build a tightly allowlisted, deterministic, logic-only review archive.

No private source, financial database, workbook, uploaded evidence or CI secret
is read. The result is a staging *candidate*, not a complete allocator.
"""
import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

REPO = Path(__file__).resolve().parents[2]
OUT_DEFAULT = Path("/tmp/sbi-d024-logic-only-candidate.tar.gz")

ALLOWLIST = (
    "backend_source/invoice_import_contract.json",
    "backend_source/invoice_source_schema.py",
    "backend_source/payment_report_rules.py",
    "backend_source/credit_note_53_adapter.py",
    "staging/mxp-gst/matcher.py",
    "staging/mxp-gst/gst_preview.py",
    "staging/mxp-gst/gst_batch_preview.py",
    "staging/mxp-gst/config/approved_alias_rules_v2_7.json",
    "staging/combined-financial-engine/offline_review.py",
    "staging/combined-financial-engine/reference_financial_math.py",
    "staging/combined-financial-engine/readiness_gate.py",
    "staging/combined-financial-engine/logic_only_deploy_gate.py",
    "staging/combined-financial-engine/synthetic_only_probe.py",
    "staging/combined-financial-engine/OWNER_LOGIC_ONLY_DEPLOYMENT_RULE.md",
)
ALLOWED_IMPORT_ROOTS = frozenset((
    "__future__", "ast", "collections", "decimal", "json", "pathlib", "re",
    "sys", "typing", "invoice_source_schema", "payment_report_rules",
    "credit_note_53_adapter", "gst_batch_preview", "gst_preview",
    "matcher", "offline_review", "reference_financial_math",
    "logic_only_deploy_gate",
))
DISALLOWED_FUNCTIONS = frozenset((
    "eval", "exec", "compile", "__import__", "input",
))


class UnsafeStagingSource(ValueError):
    pass


def _code_preflight(name, data):
    if not name.endswith(".py"):
        return
    tree = ast.parse(data, filename=name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                if node.level:
                    raise UnsafeStagingSource("RELATIVE_IMPORT_FORBIDDEN:" + name)
                names = [node.module or ""]
            for module in names:
                if module.split(".")[0] not in ALLOWED_IMPORT_ROOTS:
                    raise UnsafeStagingSource("UNAPPROVED_IMPORT:" + module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DISALLOWED_FUNCTIONS:
                raise UnsafeStagingSource("DYNAMIC_EXECUTION_FORBIDDEN")
    # Explicitly deny known classes of side effects, not merely a file extension.
    # Note: static scan is defense-in-depth, not a proof of no runtime IO.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {
                "connect", "execute", "executemany", "commit", "delete",
                "unlink", "rename", "replace", "rmtree", "write_bytes",
                "write_text", "mkdir", "makedirs", "getenv", "environ"}:
            raise UnsafeStagingSource("FORBIDDEN_SIDE_EFFECT_SYMBOL:" + node.attr)


def _approved_source(repo_root):
    root = Path(repo_root).resolve(strict=True)
    source = []
    for name in ALLOWLIST:
        candidate = root / name
        if candidate.is_symlink() or not candidate.is_file():
            raise UnsafeStagingSource("MISSING_OR_LINKED_ALLOWED_SOURCE:" + name)
        actual = candidate.resolve(strict=True)
        if not actual.is_relative_to(root):
            raise UnsafeStagingSource("OUTSIDE_REPO_PATH")
        data = candidate.read_bytes()
        if not data or len(data) > 400_000:
            raise UnsafeStagingSource("SOURCE_FILE_INVALID_SIZE:" + name)
        _code_preflight(name, data)
        source.append((name, data))
    return source


def build_candidate(repo_root, output_path):
    """Only explicit vetted code files enter the archive, no walk or glob."""
    from importlib.util import spec_from_file_location, module_from_spec

    root = Path(repo_root).resolve(strict=True)
    gate_file = root / "staging/combined-financial-engine/logic_only_deploy_gate.py"
    _code_preflight("logic_only_deploy_gate.py", gate_file.read_bytes())
    spec = spec_from_file_location("d024_logic_only_gate", gate_file)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    policy = dict(module.REQUIRED)
    policy.update({
        "existing_finance_data_paths": [],
        "historical_backfill_jobs": [],
        "financial_database_endpoints": [],
    })
    module.check_logic_only_manifest(policy)
    source = _approved_source(root)

    entries = []
    for name, data in source:
        entries.append({
            "path": name, "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })
    manifest = {
        "schema": "SBI_D024_LOGIC_ONLY_CANDIDATE_V1",
        "status": "SYNTHETIC_ONLY_STAGING_PACKAGE",
        "source_files": entries,
        "source_count": len(entries),
        "historical_data_included": False,
        "private_master_included": False,
        "payments_included": False,
        "production_deployed": False,
        "canonical_allocator_certified": False,
        "financial_write_permission": False,
        "source_policy": "LOGIC_ONLY",
        "test_source": "SYNTHETIC_ONLY",
        "production_cutover": "BLOCKED",
    }
    manifest_data = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit archive members; no unknown project file may leak into output.
    mem = io.BytesIO()
    with tarfile.open(fileobj=mem, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, data in source + [("release_manifest.json", manifest_data)]:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            item.mtime = 0
            item.mode = 0o444
            item.uid = item.gid = 0
            item.uname = item.gname = ""
            tar.addfile(item, io.BytesIO(data))
    with output_path.open("wb") as f:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as z:
            z.write(mem.getvalue())
    return {
        "status": "LOGIC_ONLY_PACKAGE_CREATED",
        "source_files": len(source),
        "archive_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "production_deployed": False,
        "historical_data_used": False,
        "financial_write_performed": False,
        "canonical_allocator_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args(argv)
    print(json.dumps(build_candidate(args.repo, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
