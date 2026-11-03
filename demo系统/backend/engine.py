#!/usr/bin/env python3
"""规则引擎：向导答案 → 报价配置 JSON（与 知识库/skill/报价配置_schema.md 一致）。
纯函数、无网络、不依赖大模型。规则来自 知识库/规则/{家具模板,价格档位,问答配置}.json。
命令行： python3 engine.py 答案.json  → 打印报价配置 JSON
"""
import json, os, re, math, datetime, copy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KB = os.path.join(ROOT, "知识库")
RULES = os.path.join(KB, "规则")

def load_rules():
    def rd(n): return json.load(open(os.path.join(RULES, n), encoding="utf-8"))
    return rd("家具模板.json"), rd("价格档位.json"), rd("问答配置.json")

# ---------- 小工具 ----------
def _fmt(v):
    if isinstance(v, bool): return str(v)
    if isinstance(v, (int, float)):
        if float(v).is_integer(): return str(int(v))
        return ("%.4f" % v).rstrip("0").rstrip(".")
    return str(v)

def _ns(params):
    ns = {"math": math, "round": round, "int": int, "float": float, "min": min, "max": max, "abs": abs, "str": str, "len": len, "list": list, "sum": sum}
    ns.update(params)
    return ns

def render(tpl, params):
    """把 '{表达式}' 替换成求值结果。表达式可用参数名。"""
    def rep(m):
        try: return _fmt(eval(m.group(1), {"__builtins__": {}, **_ns(params)}))
        except Exception as e: return f"?{m.group(1)}?"
    return re.sub(r"\{([^{}]+)\}", rep, tpl)

def cond(expr, params):
    if not expr: return True
    try: return bool(eval(expr, {"__builtins__": {}, **_ns(params)}))
    except Exception: return False

def eval_qty(q):
    """把数量字符串（可能是 '=1.6*2.4'）算成数值，无法算返回 None（如 =@ 引用）。"""
    q = str(q).strip()
    if q.startswith("=@"): return None
    if q.startswith("="):
        if re.fullmatch(r"=[\d\.\+\-\*/\(\) ]+", q):
            try: return float(eval(q[1:]))
            except Exception: return None
        return None
    try: return float(q)
    except Exception: return None

def clean_formula(q):
    """'=3+0+0' → '=3'；'=1.6*2.4' 保留。"""
    if not str(q).startswith("=") or str(q).startswith("=@"): return q
    body = q[1:]
    parts = [p for p in re.split(r"(?=\+)", body) if p not in ("+0", "")]
    body = "".join(parts)
    body = re.sub(r"^\+", "", body)
    body = re.sub(r"\*1$", "", body)          # '=1.6*2.2*1' → '=1.6*2.2'
    return "=" + (body or "0")

# ---------- 取价 ----------
def price_of(key, tier, prices):
    """返回 (单价, 单位, 类别, 材质, 来源, 是否估价)；找不到返回 None。"""
    p = prices.get(key)
    if not p: return None
    t = tier if tier in ("基础", "中配", "高配") else "中配"
    mat = p.get("材质", "")
    if isinstance(mat, dict): mat = mat.get(t, "")
    return (p.get(t), p.get("单位", ""), p.get("类别", "木作"), mat, p.get("来源", ""), bool(p.get("_估价")))

# ---------- 展开一件家具 ----------
def expand_furniture(tpl_name, label, params, tier, templates, prices):
    tpl = templates[tpl_name]
    P = {}
    for a in tpl["参数"]:
        P[a["键"]] = params.get(a["键"], a.get("默认"))
    P["家具"] = label
    rows, warnings = [], []
    for part in tpl["部件"]:
        loops = [None]
        if part.get("循环"):
            loops = list(P.get(part["循环"]) or [])
        for item in loops:
            PP = dict(P); 
            if item is not None: PP["项"] = item
            if not cond(part.get("条件"), PP): continue
            key = render(part["取价"], PP)
            pr = price_of(key, tier, prices)
            name = render(part["名称"], PP)
            qty = clean_formula(render(part["数量"], PP))
            row = {"名称": name, "材质": "", "尺寸": render(part.get("尺寸", ""), PP), "数量": qty,
                   "单位": "", "单价": 0, "说明": render(part.get("说明", ""), PP), "类别": "木作",
                   "备注": part.get("备注", ""), "_取价键": key, "_来源": ""}
            if part.get("锚"): row["_锚"] = part["锚"]
            if pr:
                price, unit, cat, mat, src, est = pr
                row.update({"单价": price, "单位": unit, "类别": cat, "材质": mat, "_来源": src})
                if est: row["备注"] = row["备注"] or "估价"
                if part.get("单价公式"):
                    try:
                        v = float(eval(part["单价公式"], {"__builtins__": {}, **_ns({**PP, "价": price})}))
                        row["单价"] = int(v) if v.is_integer() else round(v, 2)
                    except Exception as e:
                        warnings.append(f"{label}/{name}: 单价公式错误 {e}")
                if part.get("单价覆盖") is not None: row["单价"] = part["单价覆盖"]
            else:
                row["备注"] = "⚠未定价"; warnings.append(f"{label}/{name}: 价格档位.json 无 '{key}'")
            if row["单价"] is None: row["单价"] = 0
            rows.append(row)
    return rows, warnings

def accessory_rows(acc_list, tier, prices, label):
    """家具级配件：目录项查价，自定义项单价留空。数量 0 的跳过。"""
    rows, customs = [], []
    for a in acc_list or []:
        try: n = float(a.get("数量", 0) or 0)
        except Exception: n = 0
        if n <= 0: continue
        name = str(a.get("名称", "")).strip()
        if not name: continue
        key = a.get("取价键") or name
        pr = price_of(key, tier, prices)
        row = {"名称": name, "材质": "", "尺寸": "", "数量": _fmt(n), "单位": a.get("单位", ""), "单价": 0,
               "说明": a.get("说明", "配件"), "类别": a.get("类别", "木作"), "备注": "", "_取价键": key, "_来源": "", "_配件": True}
        if pr and pr[0] is not None:
            price, unit, cat, mat, src, est = pr
            row.update({"单价": price, "单位": row["单位"] or unit, "类别": cat, "材质": mat, "_来源": src})
            if est: row["备注"] = "估价"
        elif a.get("单价") not in (None, "", 0):
            row["单价"] = float(a["单价"]); row["_来源"] = "本单自定义"; row["备注"] = "自定义"; row["_自定义"] = True
            customs.append({"名称": name, "单位": row["单位"], "类别": row["类别"], "单价": row["单价"]})
        else:
            row["单价"] = None; row["备注"] = "待定价"; row["_自定义"] = True
            customs.append({"名称": name, "单位": row["单位"], "类别": row["类别"], "单价": None})
        rows.append(row)
    return rows, customs

# ---------- 主入口 ----------
def build_config(answers, rules=None):
    """answers = {meta:{}, 组织方式, 档位, 折扣:{}, 价格口径, 楼层:[...], 房间:[{名称,楼层,家具:[{模板,标签,参数}]}], 不含项:[], 说明:[]}"""
    templates, prices, wiz = rules or load_rules()
    tier = answers.get("档位", "中配")
    d = wiz.get("默认", {})
    meta = dict(answers.get("meta", {}))
    meta.setdefault("客户名", "客户"); meta.setdefault("客户抬头", meta["客户名"])
    meta.setdefault("项目名", meta["客户名"] + "全屋定制家具"); meta.setdefault("项目地址", "")
    meta.setdefault("报价日期", datetime.date.today().isoformat())
    if not meta.get("订单编号"): meta["订单编号"] = d.get("订单编号前缀", "HTBJ") + meta["报价日期"].replace("-", "") + "001"
    for k in ("生产周期", "付款条件", "税", "担当"): meta.setdefault(k, d.get(k, ""))
    cfg = {"meta": meta, "组织方式": answers.get("组织方式", "按区域"), "配置档位": tier,
           "价格口径": answers.get("价格口径", "牌价"), "折扣": answers.get("折扣", {"方式": "无"}),
           "不含项": list(answers.get("不含项", [])), "说明": list(answers.get("说明", [])), "分组": []}
    warnings = []; all_customs = []
    for room in answers.get("房间", []):
        for f in room.get("家具", []):
            if f.get("模板") not in templates:
                warnings.append(f"未知家具模板 {f.get('模板')}"); continue
            label = f.get("标签") or f["模板"]
            rows, w = expand_furniture(f["模板"], label, f.get("参数", {}), tier, templates, prices)
            warnings += w
            arows, customs = accessory_rows(f.get("配件"), tier, prices, label)
            rows += arows; all_customs += customs
            if not rows: continue
            for r in rows:   # 用户在预览里改过的行（按名称覆盖单价/数量）
                for ov in f.get("覆盖", []):
                    if ov.get("名称") == r["名称"]:
                        if "单价" in ov: r["单价"] = ov["单价"]
                        if "数量" in ov: r["数量"] = str(ov["数量"])
            multi = len({r.get("楼层", "一层") for r in answers.get("房间", [])}) > 1
            gname = (f"{room.get('楼层','一层')}{room['名称']}" if multi else room['名称']) + f"-{label}"
            cfg["分组"].append({"名称": gname, "楼层": room.get("楼层", "一层"),
                                "房间": room["名称"], "家具": label, "部件": rows})
    # 统计
    total = 0; est_rows = 0; unpriced = 0; rows_n = 0
    anchors = {}
    for g in cfg["分组"]:
        for r in g["部件"]:
            rows_n += 1
            q = eval_qty(r["数量"])
            if q is None and str(r["数量"]).startswith("=@"):
                key = str(r["数量"])[2:]
                q = sum((eval_qty(o["数量"]) or 0) for o in g["部件"] if o.get("_锚") == key or (key in o["名称"] and o is not r))
            if q is not None: total += q * float(r["单价"] or 0)
            if "估价" in (r.get("备注") or ""): est_rows += 1
            if "未定价" in (r.get("备注") or "") or "待定价" in (r.get("备注") or ""): unpriced += 1
    disc = cfg["折扣"]; final = total
    if disc.get("方式") == "整单": final = total * float(disc.get("整单折扣", 1))
    elif disc.get("方式") == "谈判整数": final = float(disc.get("成交价") or total)
    elif disc.get("方式") == "按类别":
        rates = disc.get("按类别", {}); final = 0
        for g in cfg["分组"]:
            for r in g["部件"]:
                q = eval_qty(r["数量"])
                if q is None and str(r["数量"]).startswith("=@"):
                    key = str(r["数量"])[2:]
                    q = sum((eval_qty(o["数量"]) or 0) for o in g["部件"] if o.get("_锚") == key)
                final += (q or 0) * float(r["单价"] or 0) * float(rates.get(r["类别"], 1))
    cfg["_摘要"] = {"分组数": len(cfg["分组"]), "部件行数": rows_n, "牌价合计": round(total, 2),
                   "折后金额": round(final, 2), "估价行数": est_rows, "未定价行数": unpriced, "警告": warnings, "自定义项": all_customs}
    return cfg

def strip_private(cfg):
    """去掉 _ 开头的内部字段，得到可交给 build_quote.py 的干净 JSON。"""
    c = copy.deepcopy(cfg)
    c.pop("_摘要", None)
    for g in c["分组"]:
        for r in g["部件"]:
            for k in [k for k in r if k.startswith("_")]: r.pop(k)
    return c

if __name__ == "__main__":
    import sys
    ans = json.load(open(sys.argv[1], encoding="utf-8"))
    cfg = build_config(ans)
    print(json.dumps(cfg["_摘要"], ensure_ascii=False, indent=2))
    if len(sys.argv) > 2:
        json.dump(strip_private(cfg), open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("written", sys.argv[2])
