import os, re, json, gzip, math, hashlib
from collections import defaultdict

DATA = os.environ.get("DATA_DIR", "data")
CHUNK = 1400
TOPK = int(os.environ.get("TOPK", "5"))
OK_LIC = {"BSL-1.0", "MIT", "Apache-2.0", "Unlicense"}

SYS = ("Kamu adalah MicroMind, asisten AI untuk membuat mod Geode (Geometry Dash, Geode SDK 5.11.2, C++). "
       "Gunakan HANYA nama kelas, fungsi, dan makro yang muncul di REFERENSI di bawah atau yang benar-benar kamu yakini ada di Geode. "
       "Jangan mengarang API. Jika tidak ada di referensi dan kamu tidak yakin, katakan tidak yakin. "
       "Tulis kode lengkap yang bisa dikompilasi, jelaskan singkat, dan jawab dengan bahasa pengguna.")

TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def toks(s):
    out = []
    for w in TOK.findall(s):
        out.append(w.lower())
        parts = [p.lower() for p in CAMEL.findall(w.replace("_", " "))]
        if len(parts) > 1:
            out.extend(parts)
    return [t for t in out if len(t) > 1]


def split_text(src, body):
    res, cur = [], ""
    for para in re.split(r"\n\s*\n", body):
        while len(para) > CHUNK * 2:
            if cur.strip():
                res.append((src, cur))
                cur = ""
            res.append((src, para[:CHUNK]))
            para = para[CHUNK:]
        if len(cur) + len(para) > CHUNK and cur.strip():
            res.append((src, cur))
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        res.append((src, cur))
    return res


class Index:
    def __init__(self):
        self.docs, self.boost, self.dl = [], [], []
        self.post = defaultdict(list)
        self.seen = set()
        self.N, self.avg = 0, 1.0

    def add(self, src, text, boost=1.0):
        h = hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()
        if h in self.seen:
            return
        self.seen.add(h)
        t = toks(src + " " + text)
        if not t:
            return
        i = len(self.docs)
        self.docs.append((src, text))
        self.boost.append(boost)
        self.dl.append(len(t))
        tf = defaultdict(int)
        for w in t:
            tf[w] += 1
        for w, c in tf.items():
            self.post[w].append((i, c))

    def finish(self):
        self.N = len(self.docs)
        self.avg = sum(self.dl) / max(1, self.N)

    def search(self, q, k=TOPK):
        sc = defaultdict(float)
        for w in set(toks(q)):
            p = self.post.get(w)
            if not p:
                continue
            idf = math.log(1 + (self.N - len(p) + 0.5) / (len(p) + 0.5))
            for i, c in p:
                sc[i] += idf * c * 2.5 / (c + 1.5 * (0.25 + 0.75 * self.dl[i] / self.avg))
        ranked = sorted(sc.items(), key=lambda x: -x[1] * self.boost[x[0]])
        out, seen = [], set()
        for i, _ in ranked[:80]:
            key = re.sub(r"\s+", " ", self.docs[i][1])[:160]
            if key in seen:
                continue
            seen.add(key)
            out.append(self.docs[i])
            if len(out) >= k:
                break
        return out


def load_index():
    idx = Index()
    p = os.path.join(DATA, "geode-docs-5.11.2.md")
    if os.path.exists(p):
        text = open(p, encoding="utf-8").read()
        for part in text.split("<!-- FILE: ")[1:]:
            name, _, body = part.partition(" -->")
            for src, ch in split_text("docs/" + name.strip(), body.strip()):
                idx.add(src, ch, 1.4)
    p = os.path.join(DATA, "geode-api-headers-5.11.2.txt")
    if os.path.exists(p):
        text = open(p, encoding="utf-8").read()
        parts = re.split(r"\n\n// ===== FILE: (.+?) =====\n", text)
        for j in range(1, len(parts) - 1, 2):
            for src, ch in split_text("api/" + parts[j], parts[j + 1]):
                idx.add(src, ch, 1.2)
    p = os.path.join(DATA, "geode-code.jsonl.gz")
    if os.path.exists(p):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                repo, path = r["repo"], r["path"]
                if path.endswith(".bro"):
                    continue
                if repo == "geode-sdk/geode" and path.startswith(("loader/include", "bindings/")):
                    continue
                sdk = repo.startswith("geode-sdk/")
                if not (sdk or r["license"] in OK_LIC):
                    continue
                for src, ch in split_text("%s/%s" % (repo, path), r["text"]):
                    idx.add(src, ch, 1.1 if sdk else 1.0)
    idx.finish()
    return idx


def augment(messages, idx):
    q, extra = "", []
    for m in messages:
        if m.get("role") == "system" and isinstance(m.get("content"), str):
            extra.append(m["content"])
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            q = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
            break
    hits = idx.search(q)
    ctx = "\n\n".join("[%d] %s\n%s" % (i + 1, s, t.strip()) for i, (s, t) in enumerate(hits))
    sys_text = SYS + ("\n\n" + "\n".join(extra) if extra else "") + "\n\nREFERENSI (potongan docs dan kode Geode SDK 5.11.2):\n" + ctx
    rest = [m for m in messages if m.get("role") != "system"]
    return [{"role": "system", "content": sys_text}] + rest
