# Computer-vision evaluation data

Keep private photographs outside the repository. A dataset directory may be
mounted or passed to the evaluator and should contain a JSON Lines manifest:

```json
{"id":"shirt-001","image":"images/shirt-001.jpg","mask":"masks/shirt-001.png","category":"top"}
```

The evaluator reports mask IoU, automatic acceptance rate, and per-category
counts. It intentionally refuses to describe these results as product accuracy
when no labelled samples are present. Copy `manifest.example.jsonl` to a private
dataset directory and replace its placeholder paths.

Run:

```sh
python scripts/evaluate_cv.py /path/to/private-dataset/manifest.jsonl
```
