"""知识库文件的列出 / 读取 / 写回（写前备份到 知识库/.bak/）。只允许操作 知识库/ 目录内的 md/csv/json。"""
import os, shutil, time, json, csv, io

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KB = os.path.join(ROOT, "知识库")
ALLOWED = (".md", ".csv", ".json")
SKIP_DIRS = (".bak", "skill", "工具", "__pycache__")

def _safe(rel):
    p = os.path.abspath(os.path.join(KB, rel))
    if not p.startswith(KB + os.sep) or not p.endswith(ALLOWED): raise ValueError("非法路径")
    return p

def list_files():
    out = []
    for dp, dns, fns in os.walk(KB):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in sorted(fns):
            if f.endswith(ALLOWED) and not f.startswith("."):
                p = os.path.join(dp, f); rel = os.path.relpath(p, KB)
                out.append({"path": rel, "size": os.path.getsize(p), "mtime": os.path.getmtime(p),
                            "type": f.rsplit(".", 1)[-1]})
    out.sort(key=lambda x: x["path"])
    return out

def read_file(rel):
    p = _safe(rel)
    return {"path": rel, "content": open(p, encoding="utf-8-sig").read(), "mtime": os.path.getmtime(p)}

def write_file(rel, content, expect_mtime=None):
    p = _safe(rel)
    if expect_mtime and os.path.exists(p) and abs(os.path.getmtime(p) - float(expect_mtime)) > 1:
        return {"ok": False, "error": "文件在网页外被修改过，请先重新加载", "mtime": os.path.getmtime(p)}
    if rel.endswith(".json"):
        json.loads(content)   # 语法校验
    if os.path.exists(p):
        bak = os.path.join(KB, ".bak"); os.makedirs(bak, exist_ok=True)
        shutil.copy2(p, os.path.join(bak, time.strftime("%Y%m%d_%H%M%S_") + os.path.basename(p)))
    with open(p, "w", encoding="utf-8" + ("-sig" if rel.endswith(".csv") else "")) as f:
        f.write(content)
    return {"ok": True, "mtime": os.path.getmtime(p)}

def csv_to_rows(text):
    return list(csv.reader(io.StringIO(text)))

def rows_to_csv(rows):
    buf = io.StringIO(); csv.writer(buf, lineterminator="\n").writerows(rows); return buf.getvalue()

# ---------- v0.4：别名表追加 / 自定义配件写回 / 待定价 ----------
import json as _json, collections as _c, datetime as _dt
ALIAS_MD = os.path.join(KB, "简写名与商品名映射.md")
PRICES = os.path.join(KB, "规则", "价格档位.json")

def _backup(p):
    if os.path.exists(p):
        bak = os.path.join(KB, ".bak"); os.makedirs(bak, exist_ok=True)
        shutil.copy2(p, os.path.join(bak, time.strftime("%Y%m%d_%H%M%S_") + os.path.basename(p)))

def alias_append(section, cells):
    """往 简写名与商品名映射.md 的某个小节表格末尾追加一行。section: 房间别名/家具别名/配置词。已存在同简写则跳过。"""
    md = open(ALIAS_MD, encoding="utf-8").read() if os.path.exists(ALIAS_MD) else "# 简写名与商品名映射\n"
    lines = md.splitlines()
    try: start = next(i for i, l in enumerate(lines) if l.strip() == "## " + section)
    except StopIteration:
        lines += ["", "## " + section, "| 简写 | ... |", "|---|---|"]; start = len(lines) - 3
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    key = cells[0].strip()
    for l in lines[start:end]:
        if l.strip().startswith("|") and l.strip().strip("|").split("|")[0].strip() == key: return {"ok": True, "skipped": True}
    last_tbl = max((i for i in range(start, end) if lines[i].strip().startswith("|")), default=None)
    row = "| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |"
    if last_tbl is None: lines.insert(end, row)
    else: lines.insert(last_tbl + 1, row)
    _backup(ALIAS_MD)
    open(ALIAS_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return {"ok": True}

def register_customs(customs, source=""):
    """自定义配件写回 价格档位.json：键 自定义.<名称>，单价 null，标 _待定价。返回新增键列表。"""
    if not customs: return []
    d = _json.load(open(PRICES, encoding="utf-8"), object_pairs_hook=_c.OrderedDict)
    added = []
    for c in customs:
        key = "自定义." + c["名称"]
        if key in d or c["名称"] in d: continue
        p = c.get("单价")
        d[key] = _c.OrderedDict([("单位", c.get("单位", "")), ("基础", p), ("中配", p), ("高配", p), ("类别", c.get("类别", "木作")),
                                 ("来源", f"自定义 · {source} · {_dt.date.today().isoformat()}"), ("_配件", True), ("_待定价", p in (None, "", 0))])
        added.append(key)
    if added:
        _backup(PRICES); _json.dump(d, open(PRICES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return added

def pending_prices():
    d = _json.load(open(PRICES, encoding="utf-8"))
    return [{"键": k, **{x: v.get(x) for x in ("单位", "基础", "中配", "高配", "类别", "来源")}} for k, v in d.items() if isinstance(v, dict) and v.get("_待定价")]

def set_price(key, prices):
    """填价：prices = {基础, 中配, 高配}（可只给一个，其余沿用）。填完去掉 _待定价。"""
    d = _json.load(open(PRICES, encoding="utf-8"), object_pairs_hook=_c.OrderedDict)
    if key not in d: return {"ok": False, "error": "键不存在"}
    vals = [prices.get(t) for t in ("基础", "中配", "高配")]
    fill = next((v for v in vals if v not in (None, "")), None)
    for t, v in zip(("基础", "中配", "高配"), vals): d[key][t] = float(v) if v not in (None, "") else (float(fill) if fill is not None else None)
    d[key]["_待定价"] = d[key]["基础"] is None
    _backup(PRICES); _json.dump(d, open(PRICES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"ok": True}
