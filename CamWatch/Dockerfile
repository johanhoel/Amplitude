FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# rclone for off-site storage (app/offsite.py): official release, checksum verified
ARG RCLONE_VERSION=v1.75.2
ARG RCLONE_SHA256=349ac8fba6ff65d6247043f1750cdcb518ec5d500ef91463a10d37c0ccdf3702
RUN curl -fsSL -o /tmp/rclone.zip https://downloads.rclone.org/${RCLONE_VERSION}/rclone-${RCLONE_VERSION}-linux-amd64.zip \
    && echo "${RCLONE_SHA256}  /tmp/rclone.zip" | sha256sum -c - \
    && python -c "import zipfile; zipfile.ZipFile('/tmp/rclone.zip').extract('rclone-${RCLONE_VERSION}-linux-amd64/rclone', '/tmp')" \
    && install -m 755 /tmp/rclone-${RCLONE_VERSION}-linux-amd64/rclone /usr/local/bin/rclone \
    && rm -rf /tmp/rclone* && rclone version | head -1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Face detection (YuNet) and recognition (SFace) models from the OpenCV model zoo
RUN mkdir -p /models \
    && curl -fsSL -o /models/face_detection_yunet_2023mar.onnx \
       https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
    && curl -fsSL -o /models/face_recognition_sface_2021dec.onnx \
       https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx \
    && test "$(stat -c%s /models/face_detection_yunet_2023mar.onnx)" -gt 100000 \
    && test "$(stat -c%s /models/face_recognition_sface_2021dec.onnx)" -gt 1000000

# Number plate detector + OCR (downloaded once at build time)
RUN python -c "from fast_alpr import ALPR; ALPR(detector_model='yolo-v9-t-640-license-plate-end2end', ocr_model='cct-s-v2-global-model', ocr_device='cpu')"

# CLIP image + text models for searching recordings by description (app/search.py), ~580 MB
ENV SEARCH_MODEL_DIR=/models/fastembed
RUN python -c "from fastembed import ImageEmbedding, TextEmbedding; ImageEmbedding('Qdrant/clip-ViT-B-32-vision', cache_dir='/models/fastembed'); TextEmbedding('Qdrant/clip-ViT-B-32-text', cache_dir='/models/fastembed')"

COPY models/ /models/
COPY app/ /app/
ENV PYTHONUNBUFFERED=1

