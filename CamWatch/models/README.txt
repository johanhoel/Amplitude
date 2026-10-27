Object detection models (Ultralytics YOLOv8, 80 COCO classes, exported to ONNX, opset 12, 640x640 input):

  yolov8s-coco.onnx   default (OBJECT_MODEL=/models/yolov8s-coco.onnx), more accurate, ~175 ms per pass on 4 CPU cores
  yolov8n-coco.onnx   faster (~65 ms), misses more partly hidden / night / edge-of-frame people

Re-create them with:  pip install ultralytics onnx onnxslim && yolo export model=yolov8s.pt format=onnx imgsz=640 opset=12
License: YOLOv8 is AGPL-3.0 (Ultralytics). Face and plate models are downloaded at image build time (see Dockerfile).
