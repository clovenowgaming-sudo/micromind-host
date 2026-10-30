import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
C = []


def md(t):
    C.append(("markdown", t))


def code(t):
    C.append(("code", t))


md("# MicroMind + RAG Geode di Colab (tanpa build)\n"
   "1. Runtime -> Change runtime type -> **T4 GPU**\n"
   "2. Colab Secrets: tambah `GITHUB_TOKEN` (scope `repo`) dan aktifkan akses notebook\n"
   "3. Ubah `API_KEY` di sel konfigurasi, lalu **Run all**\n\n"
   "Pakai wheel `llama-cpp-python` CUDA yang sudah jadi (Python 3.12 lewat `uv`, karena wheel CUDA belum ada untuk Python 3.13 bawaan Colab). "
   "Library CUDA dipasang lewat pip (`nvidia-cuda-runtime-cu12`, `nvidia-cublas-cu12`).\n\n"
   "Catatan: Colab gratis bukan hosting. Sesi bisa putus sewaktu-waktu dan URL tunnel berubah tiap sesi. "
   "Aturan Colab membatasi pemakaian sebagai server layanan publik, jadi pakai untuk uji pribadi.")

code(r'''!pip install -q uv fastapi uvicorn httpx
import os, subprocess, requests, time, re, shutil

V = "/content/venv312"

def sh(c):
    r = subprocess.run(c, shell=True, text=True, capture_output=True)
    print((r.stdout + r.stderr)[-1200:])
    if r.returncode:
        raise RuntimeError("gagal: " + c[:90])

if not os.path.exists(V + "/bin/python"):
    sh("uv venv --python 3.12 " + V)
    sh("uv pip install --python " + V + "/bin/python --index-strategy unsafe-best-match "
       "--only-binary llama-cpp-python "
       "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 "
       "'llama-cpp-python[server]' nvidia-cuda-runtime-cu12 nvidia-cublas-cu12")

LD = ":".join("%s/lib/python3.12/site-packages/nvidia/%s/lib" % (V, d) for d in ("cuda_runtime", "cublas"))
env = dict(os.environ, LD_LIBRARY_PATH=LD + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
r = subprocess.run([V + "/bin/python", "-c",
                    "import llama_cpp; print('llama-cpp-python', llama_cpp.__version__, '| GPU offload:', llama_cpp.llama_supports_gpu_offload())"],
                   env=env, capture_output=True, text=True)
print(r.stdout + r.stderr[-1500:])
''')

code(r'''from google.colab import userdata

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

code(r'''subprocess.run("pkill -f llama_cpp.server; pkill -f uvicorn", shell=True)
os.environ["API_KEY"] = API_KEY
os.environ["DATA_DIR"] = "data"

llama = subprocess.Popen([V + "/bin/python", "-m", "llama_cpp.server", "--model", MODEL_PATH,
                          "--model_alias", "micromind", "--n_gpu_layers", "-1", "--n_ctx", "16384",
                          "--chat_format", "chatml", "--host", "127.0.0.1", "--port", "8081"],
                         stdout=open("llama.log", "w"), stderr=subprocess.STDOUT, env=env)

def tunggu(url, n):
    for _ in range(n):
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False

if not tunggu("http://127.0.0.1:8081/v1/models", 120):
    print(open("llama.log").read()[-2500:])
    raise RuntimeError("server model gagal start")
print("server model siap")

rag = subprocess.Popen(["python", "-m", "uvicorn", "rag_server:app", "--host", "127.0.0.1", "--port", "8765"],
                       stdout=open("rag.log", "w"), stderr=subprocess.STDOUT, env=os.environ.copy())
if not tunggu("http://127.0.0.1:8765/", 240):
    print(open("rag.log").read()[-2500:])
    raise RuntimeError("server RAG gagal start")
print("server RAG siap")
''')

code(r'''!wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /usr/local/bin/cloudflared
tun = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://127.0.0.1:8765", "--no-autoupdate"],
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

code(r'''r = requests.post("http://127.0.0.1:8765/v1/chat/completions",
                  headers={"Authorization": "Bearer " + API_KEY},
                  json={"messages": [{"role": "user", "content": "Buat hook MenuLayer::init di Geode yang menulis log."}],
                        "max_tokens": 400})
print(r.json()["choices"][0]["message"]["content"])
''')

code("while True:   # biarkan sel ini berjalan agar sesi tidak idle; tekan stop untuk mematikan\n"
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
