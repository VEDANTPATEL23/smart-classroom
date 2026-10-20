# Models

The pretrained YOLO weights are **not committed** — Ultralytics downloads them
automatically the first time detection runs, and they land here.

Phase 4 uses `yolov8n.pt` (nano, ~6 MB): the smallest COCO model, fast enough for
a laptop CPU. COCO includes both classes this project cares about — `person`
(class 0) and `cell phone` (class 67).

If you want to pre-download it instead of waiting on first run:

```bash
venv/Scripts/python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

No custom training is used in the first version.
