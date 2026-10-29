import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
C = []


def md(t):
    C.append(("markdown", t))


def code(t):
    C.append(("code", t))


md("# MicroMind + RAG Geode di Colab\n"
   "1. Runtime -> Change runtime type -> **T4 GPU**\n"
   "2. Colab Secrets: tambah `GITHUB_TOKEN` (scope `repo`) dan aktifkan akses notebook\n"
   "3. Ubah `API_KEY` di sel konfigurasi, lalu **Run all**\n\n"
   "Catatan: Colab gratis bukan hosting. Sesi bisa putus sewaktu-waktu dan URL tunnel berubah tiap sesi. "
   "Aturan Colab membatasi penggunaan sebagai server layanan publik, jadi pakai untuk uji pribadi.")

code("!pip install -q fastapi uvicorn httpx\n"
     "![ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp\n"
     "![ -x llama.cpp/build/bin/llama-server ] || (cd llama.cpp && cmake -B build -DGGML_CUDA=ON "
     "-DCMAKE_CUDA_ARCHITECTURES=native -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release > /dev/null "
     "&& cmake --build build --target llama-server -j 4 2>&1 | tail -n 3)")

code(r'''import os, requests, subprocess, time, re, shutil
from google.colab import userdata

API_KEY = "ganti-kunci-rahasia"   # kunci untuk endpoint publik
MODEL = "release"                  # "release" = MicroMind.gguf dari repo micromind, atau path .gguf di Drive

os.makedirs("models", exist_ok=True)
os.makedirs("data", exist_ok=True)
MODEL_PATH = "models/model.gguf"
if MODEL == "release":
    subprocess.run(["curl", "-L", "-s", "-o", MODEL_PATH,
                    "https://github.com/clovenowgaming-sudo/micromind/releases/latest/download/MicroMind.gguf"], check=True)
else:
    from google.colab import drive
    drive.mount("/content/drive")
    shutil.copy(MODEL, MODEL_PATH)
print("model: %.2f GB" % (os.path.getsize(MODEL_PATH) / 1e9))

H = {"Authorization": "Bearer " + userdata.get("GITHUB_TOKEN"), "Accept": "application/vnd.github+json"}
rel = requests.get("https://api.github.com/repos/clovenowgaming-sudo/geode-dataset/releases/latest", headers=H).json()
for a in rel["assets"]:
    r = requests.get(a["url"], headers={**H, "Accept": "application/octet-stream"})
    open("data/" + a["name"], "wb").write(r.content)
    print(a["name"], len(r.content))
''')

for fn in ("rag_core.py", "rag_server.py"):
    code("%%writefile " + fn + "\n" + open(fn, encoding="utf-8").read())

code(r'''subprocess.run("pkill -f llama-server; pkill -f uvicorn", shell=True)
os.environ["API_KEY"] = API_KEY
os.environ["DATA_DIR"] = "data"

llama = subprocess.Popen(["llama.cpp/build/bin/llama-server", "-m", MODEL_PATH, "--host", "127.0.0.1",
                          "--port", "8081", "-ngl", "99", "-c", "16384", "-np", "2"],
                         stdout=open("llama.log", "w"), stderr=subprocess.STDOUT)

def tunggu(url, n):
    for _ in range(n):
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False

if not tunggu("http://127.0.0.1:8081/health", 120):
    print(open("llama.log").read()[-2500:])
    raise RuntimeError("llama-server gagal start")
print("llama-server siap")

rag = subprocess.Popen(["python", "-m", "uvicorn", "rag_server:app", "--host", "127.0.0.1", "--port", "8080"],
                       stdout=open("rag.log", "w"), stderr=subprocess.STDOUT, env=os.environ.copy())
if not tunggu("http://127.0.0.1:8080/", 240):
    print(open("rag.log").read()[-2500:])
    raise RuntimeError("server RAG gagal start")
print("server RAG siap")
''')

code(r'''!wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /usr/local/bin/cloudflared
tun = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://127.0.0.1:8080", "--no-autoupdate"],
                       stdout=open("tunnel.log", "w"), stderr=subprocess.STDOUT)
URL = None
for _ in range(60):
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open("tunnel.log").read())
    if m:
        URL = m.group(0)
        break
    time.sleep(2)
print("URL publik:", URL)
print("base_url =", str(URL) + "/v1", "| API key =", API_KEY)
''')

code(r'''r = requests.post("http://127.0.0.1:8080/v1/chat/completions",
                  headers={"Authorization": "Bearer " + API_KEY},
                  json={"messages": [{"role": "user", "content": "Buat hook MenuLayer::init di Geode yang menulis log."}],
                        "max_tokens": 400})
print(r.json()["choices"][0]["message"]["content"])
''')

code("import time\n"
     "while True:   # biarkan sel ini berjalan agar sesi tidak idle; tekan stop untuk mematikan\n"
     "    time.sleep(300)\n"
     "    print(time.strftime('%H:%M'), 'masih jalan', flush=True)\n")

cells = []
for kind, text in C:
    cell = {"cell_type": kind, "metadata": {}, "source": text.splitlines(True)}
    if kind == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    cells.append(cell)
nb = {"cells": cells,
      "metadata": {"accelerator": "GPU", "colab": {"provenance": []},
                   "kernelspec": {"display_name": "Python 3", "name": "python3"}},
      "nbformat": 4, "nbformat_minor": 0}
json.dump(nb, open("colab_host.ipynb", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("colab_host.ipynb dibuat:", len(cells), "sel")
