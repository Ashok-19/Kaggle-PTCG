from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sys
from datetime import UTC, datetime


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> None:
    import torch

    payload = {
        "schema_version": 1,
        "run_id": "g2-kaggle-environment-probe-v163",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "packages": {
            "torch": torch.__version__,
            "numpy": package_version("numpy"),
            "pydantic": package_version("pydantic"),
        },
        "torch": {
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "cudnn_version": torch.backends.cudnn.version(),
            "mps_available": bool(
                hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            ),
            "num_threads": torch.get_num_threads(),
            "num_interop_threads": torch.get_num_interop_threads(),
            "default_dtype": str(torch.get_default_dtype()),
        },
        "environment": {
            "kaggle_kernel_run_type": os.environ.get("KAGGLE_KERNEL_RUN_TYPE"),
            "internet_disabled_expected": True,
            "gpu_disabled_expected": True,
        },
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    print("PTCG_G2_ENVIRONMENT_PROBE_BEGIN")
    print(encoded)
    print("PTCG_G2_ENVIRONMENT_PROBE_END")
    with open("g2_environment_probe.json", "w", encoding="utf-8") as handle:
        handle.write(encoded + "\n")


if __name__ == "__main__":
    main()
