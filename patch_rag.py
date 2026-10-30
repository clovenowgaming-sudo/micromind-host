import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_core.py")
s = open(p, encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:50]
    s = s.replace(old, new, 1)


rep("from collections import defaultdict\n", "from collections import defaultdict\nfrom functools import lru_cache\n")

rep('''def toks(s):
    out = []
    for w in TOK.findall(s):
        out.append(w.lower())
        parts = [p.lower() for p in CAMEL.findall(w.replace("_", " "))]
        if len(parts) > 1:
            out.extend(parts)
    return [t for t in out if len(t) > 1]
''', '''@lru_cache(maxsize=300000)
def _word(w):
    parts = tuple(p.lower() for p in CAMEL.findall(w.replace("_", " ")))
    return (w.lower(),) + parts if len(parts) > 1 else (w.lower(),)


def toks(s):
    out = []
    for w in TOK.findall(s):
        out.extend(_word(w))
    return [t for t in out if len(t) > 1]
''')

rep('''        i = len(self.docs)
        self.docs.append((src, text))''', '''        i = len(self.docs)
        if i and i % 10000 == 0:
            print("indeks: %d potongan" % i, flush=True)
        self.docs.append((src, text))''')

rep('''                for src, ch in split_text("%s/%s" % (repo, path), r["text"]):
                    idx.add(src, ch, 1.1 if sdk else 1.0)''', '''                chs = split_text("%s/%s" % (repo, path), r["text"])
                if not sdk:
                    chs = chs[:6]
                for src, ch in chs:
                    idx.add(src, ch, 1.1 if sdk else 1.0)''')

open(p, "w", encoding="utf-8").write(s)
print("rag_core dipatch")
