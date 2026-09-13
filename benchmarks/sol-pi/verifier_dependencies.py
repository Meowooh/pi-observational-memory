"""Prepare pinned verifier dependencies when Docker cannot reach GitHub release assets.

The task, reference solution, and verifier are unchanged. Use this same setup for
the oracle and every model arm; archives stay outside the task's /app directory.
"""
import hashlib
import json
import os
from pathlib import Path

from harbor.agents.oracle import OracleAgent
from harbor.models.trial.paths import TrialPaths


async def prepare_verifier_dependencies(environment):
    configured = os.environ.get("OM_BENCH_VERIFIER_DEPS")
    if not configured:
        return
    root = Path(configured)
    manifest = json.loads((root / "dependencies.json").read_text())
    for name in ("uv-0.9.5-linux.tar.gz", "python-3.13-linux.tar.gz"):
        archive = root / name
        if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest[name]["sha256"]:
            raise RuntimeError(f"Verifier dependency checksum mismatch: {name}")
        await environment.upload_file(source_path=archive, target_path=f"/tmp/{name}")
    result = await environment.exec(
        command="mkdir -p /root/.local/bin /opt/benchmark-python && "
        "tar -xzf /tmp/uv-0.9.5-linux.tar.gz --strip-components=1 -C /root/.local/bin && "
        "tar -xzf /tmp/python-3.13-linux.tar.gz --strip-components=1 -C /opt/benchmark-python && "
        "ln -s /opt/benchmark-python/bin/python3.13 /root/.local/bin/python3.13 && "
        "printf '%s\\n' 'export PATH=\"/root/.local/bin:$PATH\"' > /root/.local/bin/env && "
        "/root/.local/bin/uv --version && /root/.local/bin/python3.13 --version",
        user="root",
        timeout_sec=120,
    )
    if result.return_code != 0:
        raise RuntimeError(f"Could not prepare pinned verifier dependencies: {result.stdout}; {result.stderr}")


class PreparedOracle(OracleAgent):
    def __init__(self, logs_dir, task_dir, **kwargs):
        super().__init__(logs_dir=logs_dir, task_dir=Path(task_dir),
                         trial_paths=TrialPaths(trial_dir=Path(logs_dir).parent), **kwargs)

    async def setup(self, environment):
        await prepare_verifier_dependencies(environment)
        await super().setup(environment)
