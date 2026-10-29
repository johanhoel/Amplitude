"""YOLOv8 object detection (ONNX, on the CPU or a GPU, see accel.py) used to confirm motion is a person/car/etc."""
import cv2
import numpy as np

import accel

COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]
SIZE = 640


class ObjectDetector:
    def __init__(self, model_path, wanted, confidence, threads=2, part=None):
        self.model_path, self.threads, self.part = model_path, threads, part
        self._open()
        self.input = self.session.get_inputs()[0].name
        self.wanted = set(wanted)
        self.confidence = confidence

    def _open(self):
        self.session, self.providers = accel.session(self.model_path, self.threads, self.part)

    def detect(self, frame):
        """Returns [(label, confidence, (x, y, w, h))] in frame pixels, wanted labels only."""
        if accel.providers() != self.providers:      # Settings -> Image processing changed
            self._open()
        h, w = frame.shape[:2]
        scale = SIZE / max(h, w)
        nw, nh = int(w * scale), int(h * scale)
        canvas = np.full((SIZE, SIZE, 3), 114, dtype=np.uint8)
        canvas[:nh, :nw] = cv2.resize(frame, (nw, nh))
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        out = self.session.run(None, {self.input: blob})[0][0]  # [4 + classes, boxes]
        names = ["person"] if out.shape[0] == 5 else COCO     # person-only or full COCO export
        scores = out[4:]
        cls = scores.argmax(0)
        conf = scores.max(0)
        keep = conf >= self.confidence
        if not keep.any():
            return []

        cx, cy, bw, bh = (out[i, keep] / scale for i in range(4))
        cls, conf = cls[keep], conf[keep]
        rects = [[int(x - ww / 2), int(y - hh / 2), int(ww), int(hh)] for x, y, ww, hh in zip(cx, cy, bw, bh)]
        # Per-class NMS, so a person on a bicycle doesn't suppress the bicycle (or vice versa)
        idx = cv2.dnn.NMSBoxesBatched(rects, conf.tolist(), cls.tolist(), self.confidence, 0.45)
        found = []
        for i in np.array(idx).flatten():
            label = names[int(cls[i])]
            if label in self.wanted:
                found.append((label, float(conf[i]), tuple(rects[i])))
        return found
