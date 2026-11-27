"""Local web page: upload or paste a manuscript, get the three estimates.

    python code/dating/app.py            # then open http://localhost:8000
    python code/dating/app.py --port 8080

Uses the models trained by train_evaluate.py (models/*.joblib); nothing is
retrained. Only the Python standard library is needed on top of the
requirements. The page accepts:
  - pasted text,
  - one or more .txt files (pages, sorted like clean_data.py), or
  - a whole manuscript folder with iiif/ and/or microfilm/ page files.
Uploaded pages get the same cleaning as clean_data.py (deleted text and tags
removed; for a folder, the source with the most pages is used).
"""
import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from clean_data import page_order, remove_deleted, remove_tags  # noqa: E402
from data import model_input  # noqa: E402
from models import MODELS  # noqa: E402
from predict import best_model, load_model  # noqa: E402
from train_evaluate import RESULTS  # noqa: E402

PAGE = os.path.join(HERE, "static", "index.html")
MAX_BODY = 200 * 1024 * 1024   # 200 MB of text is far more than any manuscript

DESCRIPTIONS = {
    "tfidf_ridge": "Word TF-IDF + ridge regression (content)",
    "style_gbm": "Function words, punctuation, sentence length + gradient boosting (style)",
    "hybrid_gbm": "Style features + 100 TF-IDF topics + gradient boosting (both)",
}


def clean_page(text):
    return remove_tags(remove_deleted(text)).strip()


def text_from_pages(pages):
    """pages: list of {"path": "MS-x/iiif/seq1.txt" or "seq1.txt", "text": ...}."""
    by_source = {"iiif": [], "microfilm": [], "other": []}
    for p in pages:
        parts = p["path"].replace("\\", "/").split("/")
        source = next((s for s in ("iiif", "microfilm") if s in parts[:-1]), "other")
        by_source[source].append((parts[-1], p["text"]))

    def joined(items):
        items = sorted(items, key=lambda it: page_order(it[0]))
        cleaned = [clean_page(t) for _, t in items]
        return [c for c in cleaned if c]

    iiif, microfilm = joined(by_source["iiif"]), joined(by_source["microfilm"])
    if iiif or microfilm:
        # Same rule as clean_data.py: most non-empty pages, iiif when equal.
        source, used = ("iiif", iiif) if len(iiif) >= len(microfilm) and iiif else ("microfilm", microfilm)
    else:
        source, used = "uploaded files", joined(by_source["other"])
    return " ".join(" ".join(used).split()), source, len(used)


def cv_table():
    path = os.path.join(RESULTS, "cv_metrics.csv")
    if not os.path.exists(path):
        return {}
    t = pd.read_csv(path, index_col="model")
    return {m: {k: round(float(v), 3) for k, v in t.loc[m].items() if pd.notna(v)}
            for m in t.index}


class App:
    def __init__(self):
        t0 = time.time()
        self.models = {name: load_model(name) for name in MODELS}
        self.best = best_model()
        self.cv = cv_table()
        print(f"Loaded {len(self.models)} models in {time.time() - t0:.0f}s")

    def predict(self, payload):
        if payload.get("pages"):
            text, source, n_pages = text_from_pages(payload["pages"])
        else:
            text = " ".join(clean_page(payload.get("text", "")).split())
            source, n_pages = "pasted text", None
        n_words = len(text.split())
        if n_words == 0:
            return {"error": "No text found after cleaning."}
        X = model_input(pd.DataFrame({"text": [text]}))
        results = {}
        for name, cp in self.models.items():
            point, iv = cp.predict_interval(X)
            r = {"pred": float(np.clip(point[0], 1850, 1914))}
            for j, level in enumerate((80, 95)):
                r[f"lo{level}"] = float(np.clip(iv[0, 0, j], 1850, 1914))
                r[f"hi{level}"] = float(np.clip(iv[0, 1, j], 1850, 1914))
            r["description"] = DESCRIPTIONS[name]
            r["cv"] = self.cv.get(name, {})
            results[name] = r
        warnings = []
        if n_words < 300:
            warnings.append("Short text (under 300 words): in cross-validation the 80% range "
                            "covered the true date only 54-73% of the time for texts this short.")
        mid = np.mean([r["pred"] for r in results.values()])
        if mid < 1885:
            warnings.append("Estimate before 1885: the models pull early manuscripts towards the "
                            "1890s, so the real date may be earlier and outside the range.")
        return {"n_words": n_words, "source": source, "n_pages": n_pages,
                "best": self.best, "models": results, "warnings": warnings,
                "baseline": self.cv.get("baseline_median", {})}


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                with open(PAGE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, b"Not found", "text/plain")

        def do_POST(self):
            if self.path != "/api/predict":
                return self._send(404, b"Not found", "text/plain")
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                return self._send(413, b'{"error": "Upload too large."}', "application/json")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = app.predict(payload)
            except Exception as e:  # report to the page instead of a dead request
                result = {"error": f"{type(e).__name__}: {e}"}
            self._send(200, json.dumps(result).encode("utf-8"), "application/json")

        def log_message(self, fmt, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = App()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Open http://localhost:{args.port} in your browser (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
