#!/usr/bin/env python3
"""
Mini Trust Layer (R5) + Prompt grounding/RAG (R6) -- thuc nghiem tai hien y tuong
cua bai bao Haki et al. (2025), Information Systems Journal 35:1497-1512.

Chi dung thu vien chuan cua Python.

LUU Y TRUNG THUC (xem README.md):
  * Du lieu la TONG HOP (synthetic).
  * "LLM ben ngoai" la MOT MO HINH GIA LAP (MockLLM) co tham so gia dinh, KHONG phai
    GPT/Claude that. Vi vay:
      - Cac chi so ve ro ri PII, do chinh xac cua masking/demasking, hit@1 cua retrieval,
        do tre cua pipeline la do tren CODE THAT.
      - Chi so hallucination/toxic phu thuoc vao tham so gia dinh cua MockLLM
        -> chi dung de kiem tra co che pipeline, KHONG de ket luan ve LLM thuc.
"""
import csv
import json
import math
import random
import re
import statistics
import sys
import time
from collections import Counter

# ----------------------------------------------------------------------------
# 1. DU LIEU TONG HOP
# ----------------------------------------------------------------------------
HO = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vu", "Dang", "Bui", "Do", "Ngo"]
DEM = ["Van", "Thi", "Minh", "Quoc", "Thanh", "Huu", "Ngoc", "Gia"]
TEN = ["An", "Binh", "Cuong", "Dung", "Giang", "Hanh", "Khanh", "Lan", "Mai", "Nam",
       "Phuong", "Quang", "Son", "Trang", "Tuan", "Vy"]
CITIES = ["Ha Noi", "Da Nang", "Hue", "Can Tho", "Hai Phong", "Nha Trang"]
PRODUCTS = ["ao khoac", "giay chay bo", "balo", "tai nghe", "dong ho", "binh giu nhiet"]
STATUSES = ["dang van chuyen", "da giao", "cho xac nhan", "dang dong goi", "da huy"]

# Kho tri thuc (chinh sach). Moi bai co 1 "su that" (so ngay) la dap an chuan.
KB = [
    ("doi tra", "Chinh sach doi tra: khach hang duoc doi tra san pham trong vong {n} ngay ke tu khi nhan hang."),
    ("hoan tien", "Chinh sach hoan tien: tien duoc hoan ve tai khoan trong vong {n} ngay lam viec."),
    ("bao hanh", "Chinh sach bao hanh: san pham duoc bao hanh {n} thang tinh tu ngay mua."),
    ("van chuyen", "Thoi gian van chuyen noi thanh: giao hang trong vong {n} ngay."),
    ("huy don", "Chinh sach huy don: khach co the huy don trong vong {n} gio sau khi dat."),
    ("khieu nai", "Quy trinh khieu nai: bo phan CSKH phan hoi trong vong {n} gio."),
]
POLICY_Q = {
    "doi tra": "toi muon biet bao nhieu ngay thi duoc doi tra san pham",
    "hoan tien": "hoan tien mat bao nhieu ngay lam viec",
    "bao hanh": "san pham duoc bao hanh bao nhieu thang",
    "van chuyen": "van chuyen noi thanh mat bao nhieu ngay",
    "huy don": "toi duoc huy don trong bao nhieu gio",
    "khieu nai": "khieu nai thi bao lau duoc phan hoi",
}
UNKNOWN_Q = [
    "diem thuong tich luy cua toi hien la bao nhieu",
    "cho toi biet so the ngan hang dang luu cua toi",
    "nhan vien nao da xu ly don cua toi lan truoc",
]


def make_phone(rng):
    return "09" + "".join(str(rng.randint(0, 9)) for _ in range(8))


def make_dataset(rng, n_customers=200, n_queries=300):
    kb_facts = {k: rng.randint(2, 30) for k, _ in KB}
    kb_docs = [(k, t.format(n=kb_facts[k])) for k, t in KB]
    customers = []
    for i in range(n_customers):
        name = f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"
        slug = re.sub(r"\s+", "", name.lower())
        customers.append({
            "customer_id": f"C{i:04d}",
            "name": name,
            "email": f"{slug}{rng.randint(1, 99)}@example.com",
            "phone": make_phone(rng),
            "city": rng.choice(CITIES),
            "order_id": f"DH{rng.randint(10000, 99999)}",
            "product": rng.choice(PRODUCTS),
            "status": rng.choice(STATUSES),
        })
    queries = []
    for _ in range(n_queries):
        c = rng.choice(customers)
        kind = rng.choices(["status", "policy", "unknown"], weights=[0.4, 0.4, 0.2])[0]
        # Cau hoi dang van ban tu do: co the chua PII nhung o nhieu dinh dang
        intro = rng.choice([
            f"Toi la {c['name']}, ",
            f"Em ten {c['name']}, sdt {c['phone']}, ",
            f"Lien he qua {c['email']}: ",
            "",
        ])
        # ~5% PII bi che dau (vi du email viet kieu 'at/dot') -> regex se bo sot
        if rng.random() < 0.05:
            user, dom = c["email"].split("@")
            intro = f"email cua toi la {user} at example dot com, "
        if kind == "status":
            q = intro + f"don hang {c['order_id']} cua toi dang o dau"
            gold = c["status"]
            extra = None
        elif kind == "policy":
            key = rng.choice(list(POLICY_Q))
            q = intro + POLICY_Q[key]
            gold = str(kb_facts[key])
            extra = key
        else:
            q = intro + rng.choice(UNKNOWN_Q)
            gold = "khong co thong tin"
            extra = None
        queries.append({"customer": c, "kind": kind, "question": q, "gold": gold, "key": extra})
    return customers, kb_docs, queries


# ----------------------------------------------------------------------------
# 2. MO HINH LLM GIA LAP (tham so gia dinh -- xem README)
# ----------------------------------------------------------------------------
TOXIC_PHRASES = ["dung la ngu ngoc", "thai do cua ban that te", "co nghe khong dau"]
# bo loc chi biet 2/3 cum -> mot cum "lot luoi" (de do ty le bo sot that)
TOXIC_LEXICON = {"ngu ngoc", "thai do cua ban that te"}

P_TOXIC = 0.04
P_HALLU_UNGROUNDED = 0.60   # xac suat bia dap an khi KHONG co du lieu va KHONG co chi dan grounding
P_HALLU_GROUNDED = 0.10     # khi prompt co chi dan "chi tra loi theo ngu canh"


class MockLLM:
    """Dong vai LLM ben thu ba: nhan prompt (chuoi), tra chuoi. Ghi lai prompt da nhan."""

    def __init__(self, rng):
        self.rng = rng
        self.received = []  # nhat ky prompt gui ra ngoai

    def generate(self, prompt):
        self.received.append(prompt)
        g = re.search(r"NAME=(\S.*?);EMAIL=", prompt)
        e = re.search(r"EMAIL=(\S*?);PHONE=", prompt)
        name = g.group(1) if g else "quy khach"
        email = e.group(1) if e else ""
        st = re.search(r"STATUS=(.*?);", prompt)
        order = re.search(r"ORDER=(\S*?);", prompt)
        q = re.search(r"QUESTION: (.*)$", prompt, re.S).group(1).lower()
        grounded = "CHI TRA LOI THEO NGU CANH" in prompt
        kb_ctx = re.findall(r"KB: (.*)", prompt)
        kb_text = " ".join(kb_ctx).lower()

        ans = None
        if re.search(r"don hang .* dang o dau", q) and st:
            ans = f"don hang {order.group(1)} {st.group(1)}."
            if email:
                ans += f" Chung toi se gui xac nhan toi {email}."
        else:
            # cau hoi chinh sach: tim trong KB neu co
            for key, question in POLICY_Q.items():
                if question in q:
                    m = re.search(rf"{key}.*?(\d+)", kb_text)
                    if m:
                        ans = f"theo chinh sach, ban {m.group(1)} don vi thoi gian."
                    break
        if ans is None:
            p = P_HALLU_GROUNDED if grounded else P_HALLU_UNGROUNDED
            if self.rng.random() < p:
                ans = f"theo chinh sach, ban {self.rng.randint(2, 30)} don vi thoi gian."  # bia
            else:
                ans = "toi khong co thong tin."
        out = f"Chao {name}, {ans}"
        if self.rng.random() < P_TOXIC:
            out += " " + self.rng.choice(TOXIC_PHRASES)
        return out


# ----------------------------------------------------------------------------
# 3. TRUST LAYER (R5)
# ----------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?<!\d)0\d(?:[\s.\-]?\d){8}(?!\d)")
# Heuristic ten nguoi: 2-4 tu viet hoa lien tiep (khong dung NER that -> co sai sot)
NAME_RE = re.compile(r"\b(?:[A-Z][a-z]+)(?:\s[A-Z][a-z]+){1,3}\b")


class TrustLayer:
    def __init__(self, mask=True, filter_toxic=True):
        self.mask_on = mask
        self.filter_on = filter_toxic

    def mask(self, text, vault, structured=None):
        """Thay PII bang placeholder; luu vault de demask. structured: gia tri da biet theo schema."""
        if not self.mask_on:
            return text
        def sub(regex, tag, s):
            def r(m):
                val = m.group(0)
                for k, v in vault.items():
                    if v == val:
                        return k
                key = f"<{tag}_{len(vault)}>"
                vault[key] = val
                return key
            return regex.sub(r, s)
        if structured:  # truong co schema -> che chinh xac
            for tag, val in structured.items():
                if val and val in text:
                    key = None
                    for k, v in vault.items():
                        if v == val:
                            key = k
                    if key is None:
                        key = f"<{tag}_{len(vault)}>"
                        vault[key] = val
                    text = text.replace(val, key)
        text = sub(EMAIL_RE, "EMAIL", text)
        text = sub(PHONE_RE, "PHONE", text)
        text = sub(NAME_RE, "NAME", text)
        return text

    @staticmethod
    def demask(text, vault):
        for k, v in vault.items():
            text = text.replace(k, v)
        return text

    def filter(self, text):
        if not self.filter_on:
            return text
        low = text.lower()
        if any(t in low for t in TOXIC_LEXICON):
            return "Xin loi, noi dung phan hoi da bi chan boi bo loc an toan."
        return text


# ----------------------------------------------------------------------------
# 4. RAG toi gian (TF-IDF + cosine) cho R6
# ----------------------------------------------------------------------------
def tok(s):
    return re.findall(r"[a-z0-9]+", s.lower())


class TfidfIndex:
    def __init__(self, docs):
        self.docs = docs
        toks = [tok(d[1]) for d in docs]
        df = Counter(w for t in toks for w in set(t))
        n = len(docs)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        self.vecs = [self._vec(t) for t in toks]

    def _vec(self, t):
        c = Counter(t)
        v = {w: f * self.idf.get(w, 1.0) for w, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def search(self, q, k=1):
        qv = self._vec(tok(q))
        scores = [(sum(qv.get(w, 0) * x for w, x in dv.items()), i) for i, dv in enumerate(self.vecs)]
        scores.sort(reverse=True)
        return [(self.docs[i], s) for s, i in scores[:k]]


# ----------------------------------------------------------------------------
# 5. KICH BAN K1..K4
# ----------------------------------------------------------------------------
SCENARIOS = {
    "K1": dict(mask=False, filter_toxic=False, rag=False),
    "K2": dict(mask=True, filter_toxic=False, rag=False),
    "K3": dict(mask=True, filter_toxic=True, rag=False),
    "K4": dict(mask=True, filter_toxic=True, rag=True),
}


def build_prompt(c_fields, question, kb_snips, grounded):
    p = "SYSTEM: Ban la tro ly CSKH.\n"
    if grounded:
        p += "CHI TRA LOI THEO NGU CANH. Neu khong co thong tin, noi 'toi khong co thong tin'.\n"
    p += (f"CONTEXT: NAME={c_fields['name']};EMAIL={c_fields['email']};PHONE={c_fields['phone']};"
          f"ORDER={c_fields['order_id']};PRODUCT={c_fields['product']};STATUS={c_fields['status']};"
          f"CITY={c_fields['city']};\n")
    for s in kb_snips:
        p += f"KB: {s}\n"
    p += f"QUESTION: {question}"
    return p


def contains_raw_pii(prompt, c):
    """Prompt gui ra ngoai co chua PII goc cua khach khong (ten/email/sdt, ke ca sdt khong dau cach)."""
    digits = re.sub(r"\D", "", prompt)
    return (c["name"] in prompt) or (c["email"] in prompt) or (c["phone"] in digits)


def run_scenario(name, cfg, queries, kb_index, seed):
    llm = MockLLM(random.Random(0))
    tl = TrustLayer(mask=cfg["mask"], filter_toxic=cfg["filter_toxic"])
    n = len(queries)
    pii_exposed = toxic_shown = correct = 0
    retr_hit = retr_n = 0
    t_pipe = []
    prompt_words = []
    by_kind = {k: [0, 0] for k in ("status", "policy", "unknown")}
    hallu = hallu_den = 0
    for qi, q in enumerate(queries):
        llm.rng = random.Random(f"{seed}-{qi}")  # cung 'ngau nhien' cho moi kich ban -> so sanh cap doi
        c = q["customer"]
        t0 = time.perf_counter()
        vault = {}
        structured = {"NAME": c["name"], "EMAIL": c["email"], "PHONE": c["phone"]}
        fields = {k: c[k] for k in ("order_id", "product", "status", "city")}
        fields.update({"name": c["name"], "email": c["email"], "phone": c["phone"]})
        question = q["question"]
        snips = []
        if cfg["rag"]:
            (doc, score), = kb_index.search(question, k=1)
            snips.append(doc[1])
            if q["kind"] == "policy":
                retr_n += 1
                retr_hit += int(doc[0] == q["key"])
        if cfg["mask"]:
            fields = {k: tl.mask(v, vault, structured if k in ("name", "email", "phone") else None)
                      if k in ("name", "email", "phone") else v for k, v in fields.items()}
            question = tl.mask(question, vault, structured)
        prompt = build_prompt(fields, question, snips, grounded=cfg["rag"])
        t1 = time.perf_counter()
        raw = llm.generate(prompt)
        t2 = time.perf_counter()
        out = tl.filter(raw)
        out = tl.demask(out, vault) if cfg["mask"] else out
        t3 = time.perf_counter()
        t_pipe.append(((t1 - t0) + (t3 - t2)) * 1000)  # chi phi pipeline, khong gom LLM
        prompt_words.append(len(prompt.split()))
        pii_exposed += int(contains_raw_pii(prompt, c))
        low = out.lower()
        if any(t in low for t in TOXIC_PHRASES):
            toxic_shown += 1
        ok = q["gold"] in low
        correct += int(ok)
        by_kind[q["kind"]][0] += int(ok)
        by_kind[q["kind"]][1] += 1
        if q["kind"] in ("policy", "unknown"):
            hallu_den += 1
            if not ok and "khong co thong tin" not in low:
                hallu += 1
    return {
        "scenario": name,
        "pii_exposure_rate": pii_exposed / n,
        "toxic_shown_rate": toxic_shown / n,
        "accuracy": correct / n,
        "hallucination_rate": hallu / hallu_den,
        "retrieval_hit1": (retr_hit / retr_n) if retr_n else float("nan"),
        "pipeline_ms_mean": statistics.mean(t_pipe),
        "prompt_words_mean": statistics.mean(prompt_words),
        "acc_status": by_kind["status"][0] / max(1, by_kind["status"][1]),
        "acc_policy": by_kind["policy"][0] / max(1, by_kind["policy"][1]),
        "acc_unknown": by_kind["unknown"][0] / max(1, by_kind["unknown"][1]),
    }


def masking_unit_test(seed=0):
    """Do rieng do chinh xac cua masking tren cau hoi tu do (khong qua LLM)."""
    rng = random.Random(seed)
    _, _, queries = make_dataset(rng, 200, 1000)
    tl = TrustLayer()
    n_with_pii = leaked = roundtrip_ok = 0
    for q in queries:
        c = q["customer"]
        text = q["question"]
        has = any(v in text for v in (c["name"], c["email"], c["phone"])) or " at example dot com" in text
        vault = {}
        masked = tl.mask(text, vault, {"NAME": c["name"], "EMAIL": c["email"], "PHONE": c["phone"]})
        if has:
            n_with_pii += 1
            if contains_raw_pii(masked, c) or " at example dot com" in masked:
                leaked += 1
        roundtrip_ok += int(tl.demask(masked, vault) == text)
    return {"queries": len(queries), "queries_with_pii": n_with_pii,
            "pii_residual_after_masking": leaked,
            "residual_rate": leaked / max(1, n_with_pii),
            "demask_roundtrip_exact": roundtrip_ok / len(queries)}


def main(seeds=(1, 2, 3, 4, 5), n_customers=200, n_queries=300):
    all_rows = []
    for s in seeds:
        rng = random.Random(s)
        customers, kb_docs, queries = make_dataset(rng, n_customers, n_queries)
        index = TfidfIndex(kb_docs)
        for name, cfg in SCENARIOS.items():
            r = run_scenario(name, cfg, queries, index, s)
            r["seed"] = s
            all_rows.append(r)
    metrics = ["pii_exposure_rate", "toxic_shown_rate", "accuracy", "hallucination_rate",
               "retrieval_hit1", "pipeline_ms_mean", "prompt_words_mean",
               "acc_status", "acc_policy", "acc_unknown"]
    summary = []
    for name in SCENARIOS:
        rows = [r for r in all_rows if r["scenario"] == name]
        d = {"scenario": name}
        for m in metrics:
            vals = [r[m] for r in rows if not (isinstance(r[m], float) and math.isnan(r[m]))]
            d[m + "_mean"] = statistics.mean(vals) if vals else float("nan")
            d[m + "_std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        summary.append(d)
    unit = masking_unit_test()
    with open("results_per_seed.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    with open("results_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    with open("masking_unit_test.json", "w") as f:
        json.dump(unit, f, indent=2)

    def pct(x):
        return f"{100 * x:.1f}%"
    print(f"Du lieu: {n_customers} khach, {n_queries} cau hoi/seed, seeds={list(seeds)}")
    print("Dac trung moi ban ghi khach hang: 8 (customer_id,name,email,phone,city,order_id,product,status)")
    print(f"{'KB':4} {'PIIexp':>8} {'Toxic':>8} {'Acc':>8} {'Hallu':>8} {'Hit@1':>8} {'ms/q':>8} {'words':>7}")
    for d in summary:
        h = d["retrieval_hit1_mean"]
        print(f"{d['scenario']:4} {pct(d['pii_exposure_rate_mean']):>8} {pct(d['toxic_shown_rate_mean']):>8} "
              f"{pct(d['accuracy_mean']):>8} {pct(d['hallucination_rate_mean']):>8} "
              f"{(pct(h) if not math.isnan(h) else '-'):>8} {d['pipeline_ms_mean_mean']:>8.3f} "
              f"{d['prompt_words_mean_mean']:>7.1f}")
    print("Masking unit test:", json.dumps(unit))

if __name__ == "__main__":
    main()