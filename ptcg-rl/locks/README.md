# Environment Profiles

`uv.lock` is the authoritative cross-platform resolution. The exported profiles are generated from it:

- `local-cpu.txt`: local runtime only.
- `colab-cuda.txt`, `kaggle-cuda.txt`, `modal-cuda.txt`: project dependencies only; each platform's PyTorch/CUDA build remains platform-supplied until its preflight doctor freezes an image/wheel source.

This avoids silently replacing a working CUDA build before the official runtime and platform images are verified.

