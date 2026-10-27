import os, time, numpy as np, cv2
from PIL import Image
from fastembed import ImageEmbedding, TextEmbedding
t = time.time()
img_model = ImageEmbedding("Qdrant/clip-ViT-B-32-vision", cache_dir=os.environ.get("SEARCH_MODEL_DIR") or str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"), threads=2)
txt_model = TextEmbedding("Qdrant/clip-ViT-B-32-text", cache_dir=os.environ.get("SEARCH_MODEL_DIR") or str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"), threads=2)
print(f"models loaded in {time.time() - t:.0f}s")
def canvas(color, shape):
    img = np.full((360, 640, 3), 200, np.uint8)
    if shape == "circle": cv2.circle(img, (320, 180), 120, color, -1)
    else: cv2.rectangle(img, (160, 60), (480, 300), color, -1)
    return Image.fromarray(img[..., ::-1])
pics = {"red circle": canvas((0, 0, 220), "circle"), "blue square": canvas((220, 0, 0), "square"),
        "green square": canvas((0, 180, 0), "square"), "yellow circle": canvas((0, 220, 230), "circle")}
t = time.time(); vecs = np.array(list(img_model.embed(list(pics.values())))); print(f"4 images embedded in {(time.time()-t)*1000:.0f} ms, dim {vecs.shape[1]}")
vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
for q in ["a red circle", "a blue square", "something green", "a yellow ball"]:
    v = next(iter(txt_model.embed([f"a photo of {q}"]))); v /= np.linalg.norm(v)
    sims = vecs @ v; best = list(pics)[int(sims.argmax())]
    print(f"{'PASS' if best.split()[0] in q or (q == 'a yellow ball' and best == 'yellow circle') else 'FAIL'}  '{q}' -> {best}  scores {np.round(sims, 3)}")
