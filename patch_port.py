import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_notebook.py")
s = open(p, encoding="utf-8").read()
n = s.count("8080")
assert n >= 4, n
open(p, "w", encoding="utf-8").write(s.replace("8080", "8765"))
print("port 8080 -> 8765 di", n, "tempat")
