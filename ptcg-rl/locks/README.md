# Environment Profiles

`uv.lock` is one shared Python 3.11/3.12-compatible cross-platform resolution.
Python 3.11 is the primary runtime-matching profile; Python 3.12 remains a
secondary development compatibility target. The exported profiles are generated from it:

- `local-cpu.txt`: local runtime only.
- `colab-cuda.txt`, `kaggle-cuda.txt`, `modal-cuda.txt`: project dependencies only; each platform's PyTorch/CUDA build remains platform-supplied until its preflight doctor freezes an image/wheel source.

Dashboard dependencies live only in the separate `dashboard` dependency group
and are never installed for submissions. This avoids silently replacing a
working CUDA build before the official runtime and platform images are verified.
