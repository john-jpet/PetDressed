from __future__ import annotations

import os

from huggingface_hub import snapshot_download


def main() -> None:
    cache_dir = os.getenv("MODEL_CACHE_DIR", os.getenv("HF_HOME", "/models/huggingface"))
    models = {
        os.getenv("EMBEDDING_MODEL_NAME", "patrickjohncyh/fashion-clip"),
        os.getenv("SEGMENTATION_MODEL_CONFIG", "facebook/sam2.1-hiera-tiny"),
    }
    for model_name in sorted(models):
        print(f"Ensuring model is cached: {model_name}", flush=True)
        snapshot_download(repo_id=model_name, cache_dir=cache_dir)
    print("CV model cache is ready", flush=True)


if __name__ == "__main__":
    main()
