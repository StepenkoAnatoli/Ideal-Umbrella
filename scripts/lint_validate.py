"""Compare old vs new abbreviation rule on real repo text and on known invented abbreviations."""
import importlib.util, sys, io, glob, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
K = "C:/Users/PC/Desktop/gittoken/keyline"
sys.path.insert(0, K)
import keyline_lint as new
spec = importlib.util.spec_from_file_location("old", sys.argv[1]); old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
words = new.load_words()
def flags(mod, text):
    allow = getattr(mod, "BUILTIN_ALLOW", set())
    return [m.split("'")[1] for _, m in mod.lint_text(text, words, allow) if m.startswith("abbreviation")]
# corpus: README/docs markdown across the gittoken repos (real human/agent prose)
files = [f for f in glob.glob("C:/Users/PC/Desktop/gittoken/*/**/*.md", recursive=True)
         if "node_modules" not in f and "/.git/" not in f.replace("\\", "/")][:400]
text = []
for f in files:
    try: text.append(open(f, encoding="utf-8", errors="ignore").read())
    except OSError: pass
corpus = "\n".join(text)
o, n = collections.Counter(flags(old, corpus)), collections.Counter(flags(new, corpus))
print(f"corpus: {len(files)} files, {len(corpus)} chars")
print(f"old rule: {len(o)} distinct words flagged; new rule: {len(n)} distinct words flagged")
print("new rule still flags (top 40 by count):", ", ".join(f"{w}({c})" for w, c in n.most_common(40)))
print("sample of words the old rule flagged and the new rule lets through:", ", ".join(w for w, _ in (o - n).most_common(40)))
real = "worktree uncommitted unpushed branched harmlessly octopus amends rework reworks rerun asctime autocollect dryrun countersignature cp1252 sha256 utf8 x2 b07b3b6 d7c00f96a17c35e6c47c5ba1f7e3a9160c966042"
invented = "alrt rst xh k8s i18n a11y mgmt pkts srvc sref"
print("\nreal words flagged by new rule:", flags(new, real) or "none")
inv_multi = [w for w in invented.split() if w not in words]
print("invented abbreviations that are multi-token:", inv_multi)
print("of those, flagged by new rule:", flags(new, " ".join(inv_multi)))
