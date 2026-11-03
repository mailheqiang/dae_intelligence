#!/usr/bin/env python3
"""现场记录解析器：把测量时的口头简写（一行一件）解析成向导答案里的 房间/家具/参数/配件。
纯规则 + 别名表（知识库/简写名与商品名映射.md），不依赖大模型。
命令行：python3 parse_notes.py 记录.txt
"""
import os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
KB = os.path.join(ROOT, "知识库")
ALIAS_MD = os.path.join(KB, "简写名与商品名映射.md")

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
# 每种模板：尺寸 a*b / N延米 落到哪些参数
DIM_MAP = {"通用柜": ["W", "H"], "衣柜": ["W", "H"], "墙板": ["W", "H"], "书桌": ["L", "D"], "电视柜": ["L", "H"],
           "浴室柜": ["W", "H"], "榻榻米": ["L", "W"], "洗衣间柜": ["地柜"], "室内门": ["W", "H"], "橱柜": ["L1"],
           "层板架": ["金属层板"], "棚柱式衣帽间": [], "配件": []}
LM_MAP = {"橱柜": "L1", "橱柜.吊柜": "吊柜长度", "橱柜.中岛": "中岛", "浴室柜": "W", "洗衣间柜": "地柜", "通用柜": "W", "书桌": "L", "电视柜": "L", "层板架": "金属层板"}

def _num(s):
    s = s.strip()
    if s.isdigit() or re.fullmatch(r"\d+\.\d+", s): return float(s)
    return float(sum(CN_NUM.get(c, 0) for c in s)) if s else 0

def _mm(v):
    v = float(v); return int(round(v * 1000)) if v < 20 else int(round(v))

def _parse_params(txt):
    out = {}
    for kv in re.split(r"[,，]", txt or ""):
        if "=" not in kv: continue
        k, v = kv.split("=", 1); k, v = k.strip(), v.strip()
        if v.lower() == "true": v = True
        elif v.lower() == "false": v = False
        elif re.fullmatch(r"-?\d+", v): v = int(v)
        elif re.fullmatch(r"-?\d+\.\d+", v): v = float(v)
        elif ";" in v: v = [x.strip() for x in v.split(";") if x.strip()]
        out[k] = v
    return out

def _tables(md):
    """按 ## 小节切分，返回 {小节名: [行(list)]}（跳过表头与分隔行）"""
    secs, cur = {}, None
    for line in md.splitlines():
        if line.startswith("## "): cur = line[3:].strip(); secs[cur] = []; continue
        if cur and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c) or not any(cells): continue
            secs[cur].append(cells)
    for k in secs:
        if secs[k]: secs[k] = secs[k][1:]   # 去表头
    return secs

def load_alias(path=ALIAS_MD):
    md = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    secs = _tables(md)
    rooms = {r[0]: r[1] for r in secs.get("房间别名", []) if len(r) >= 2 and r[0]}
    furn = []
    for r in secs.get("家具别名", []):
        if len(r) < 4 or not r[0]: continue
        furn.append({"简写": r[0], "房间": r[1], "模板": r[2], "标签": r[3] or r[0], "参数": _parse_params(r[4] if len(r) > 4 else "")})
    words = []
    for r in secs.get("配置词", []):
        if len(r) < 3 or not r[0]: continue
        words.append({"词": r[0], "参数": r[1], "值": r[2]})
    return {"房间": rooms, "家具": sorted(furn, key=lambda x: -len(x["简写"])), "配置词": words}

def load_room_names():
    try:
        q = json.load(open(os.path.join(KB, "规则", "问答配置.json"), encoding="utf-8"))
        return [r["名称"] for r in q["房间"]]
    except Exception:
        return ["玄关", "客厅", "餐厅", "厨房", "主卧", "主卧衣帽间", "次卧", "书房", "主卫", "客卫", "卫生间", "洗衣间", "储藏室", "走廊/过厅", "阳台"]

def load_templates():
    try: return json.load(open(os.path.join(KB, "规则", "家具模板.json"), encoding="utf-8"))
    except Exception: return {}

def parse(text, alias=None, templates=None):
    alias = alias or load_alias(); templates = templates or load_templates()
    rooms_canon = load_room_names()
    room_words = sorted([(w, w) for w in rooms_canon] + list(alias["房间"].items()), key=lambda x: -len(x[0]))
    items, cur_room = [], None
    cur_floor = "一层"
    FLOOR_RE = re.compile(r"^(地下[一二三]层|负[一二三]层|B[123]|[一二三四五]层|[一二三四五]楼|[1-5]F|[1-5]层|[1-5]楼|顶层|阁楼|楼梯间)[：:，,\s]*")
    def norm_floor(f):
        f = f.replace("楼", "层").replace("F", "层")
        f = re.sub(r"^负", "地下", f); f = re.sub(r"^B([123])", lambda m: "地下" + "一二三"[int(m.group(1)) - 1] + "层", f)
        return re.sub(r"^([1-5])层", lambda m: "一二三四五"[int(m.group(1)) - 1] + "层", f)
    last_by_room = {}   # 房间 -> 最后一件家具 item（用于“台面”“吊柜”“配件”并入）

    for raw in text.splitlines():
        line = raw.strip().replace("＊", "*").replace("×", "*").replace("x", "*").replace("X", "*")
        if not line: continue
        mf = FLOOR_RE.match(line)
        if mf:
            cur_floor = norm_floor(mf.group(1)); line = line[mf.end():].strip(); cur_room = None
            if not line:   # 整行只有楼层 → 切换上下文
                items.append({"原文": raw.strip(), "房间": None, "楼层": cur_floor, "模板": None, "标签": None, "参数": {}, "配件": [], "状态": "楼层", "说明": [f"以下归入「{cur_floor}」"]}); cur_room = None; continue
        item = {"原文": raw.strip(), "房间": None, "楼层": cur_floor, "模板": None, "标签": None, "参数": {}, "配件": [], "状态": "未识别", "说明": []}
        rest = line
        # 1) 家具：找出行内所有别名命中（互不重叠，长的优先）
        hits, taken = [], []
        for f in alias["家具"]:
            pos = rest.find(f["简写"])
            if pos < 0: continue
            span = (pos, pos + len(f["简写"]))
            if any(not (span[1] <= a or span[0] >= b) for a, b in taken): continue
            hits.append((f, pos)); taken.append(span)
        # 主家具 = 第一个“实体”模板（非配件、非室内门）；配件/门作为附属
        primary = next((h for h in hits if h[0]["模板"] not in ("配件", "室内门") and "." not in h[0]["模板"]), None) \
                  or next((h for h in hits if "." in h[0]["模板"]), None) or (hits[0] if hits else None)
        attach = [h for h in hits if h is not primary]
        # 2) 房间：家具匹配区以外的文字里找房间词
        rm_text = rest
        for f, pos in hits: rm_text = rm_text.replace(f["简写"], "", 1)
        room = None
        for w, canon in room_words:
            if w and w in rm_text: room = canon; rest = rest.replace(w, "", 1); break
        if primary:
            f = primary[0]
            room = room or f["房间"] or cur_room
            item.update({"模板": f["模板"], "标签": f["标签"], "参数": dict(f["参数"])})
        for f, pos in hits: rest = rest.replace(f["简写"], "", 1)
        if room: cur_room = room
        item["房间"] = room or cur_room
        # 附属：同一行里的配件 / 柜门类型
        for f, pos in attach:
            if f["模板"] == "配件": item["配件"].append({"名称": f["标签"], "数量": None})
            elif f["模板"] == "室内门":
                if f["参数"].get("类型", "").endswith("折门"): item["配件"].append({"名称": "折叠门五金", "数量": 1}); item["说明"].append("柜门为折叠门")
                else: item["说明"].append(f"门：{f['标签']}")

        # 3) 尺寸
        m = re.search(r"(\d+(?:\.\d+)?)\s*\*\s*(\d+(?:\.\d+)?)", rest)
        lm = re.search(r"(\d+(?:\.\d+)?)\s*(?:延米|米|m)\b", rest) or re.search(r"(\d+(?:\.\d+)?)\s*延米", rest)
        tpl = item["模板"] or ""
        explicit_dim = bool(m or lm)
        if m:
            a, b = _mm(m.group(1)), _mm(m.group(2))
            keys = DIM_MAP.get(tpl.split(".")[0], ["W", "H"])
            if len(keys) >= 1: item["参数"][keys[0]] = a
            if len(keys) >= 2: item["参数"][keys[1]] = b
            if tpl == "橱柜.吊柜": item["参数"]["吊柜长度"] = a
            rest = rest.replace(m.group(0), "", 1)
        elif lm:
            key = LM_MAP.get(tpl, "W"); item["参数"][key] = _mm(lm.group(1))
            rest = rest.replace(lm.group(0), "", 1)

        # 4) 配置词
        groups = 1
        mg = re.search(r"([一二两三四五六七八九十\d]+)\s*组", rest)
        if mg: groups = int(_num(mg.group(1)) or 1); item["参数"]["组数"] = groups
        md_ = re.search(r"抽屉\s*(\d+)\s*个", rest) or re.search(r"(\d+)\s*个抽屉", rest)
        if md_: item["参数"]["抽屉"] = int(md_.group(1))
        elif "抽屉" in rest: item["参数"]["抽屉"] = 1; item["说明"].append("抽屉数量待确认")
        ml = re.search(r"各\s*(\d+)\s*层", rest) or re.search(r"(\d+)\s*层", rest)
        if ml: item["参数"]["层板"] = int(ml.group(1)) * groups
        for a in item["配件"]:
            if a["数量"] is None: a["数量"] = item["参数"].pop("层板", None) or item["参数"].get("数量") or groups or 1
        for w in alias["配置词"]:
            word = w["词"]
            if "N" in word or "正则" in (w.get("说明") or ""): continue
            if word in rest and w["参数"] not in item["参数"]:
                v = w["值"]; v = True if v == "true" else False if v == "false" else v
                item["参数"][w["参数"]] = v
        colors = re.findall(r"(白色|黑色|灰色|木色|原木色|胡桃色|奶白)", rest)
        if colors: item["说明"].append("颜色：" + "/".join(colors))

        # 5) 归类
        base = tpl.split(".")[0]
        if not tpl:
            # 只有配置词（如“国产岩板台面”）→ 并入上一件带台面的家具
            tgt = last_by_room.get((item["楼层"], item["房间"])) if item["房间"] else None
            if item["参数"] and tgt is not None:
                tgt["参数"].update({k: v for k, v in item["参数"].items() if k in ("台面", "门板材质", "灯带", "抽屉")})
                item["状态"] = "并入"; item["说明"].append(f"并入「{tgt['标签']}」")
            else:
                item["状态"] = "未识别"
        elif tpl == "配件":
            tgt = last_by_room.get((item["楼层"], item["房间"]))
            n = item["参数"].get("层板") or item["参数"].get("数量") or 1
            if tgt is not None:
                tgt["配件"].append({"名称": item["标签"], "数量": n}); item["状态"] = "并入"; item["说明"].append(f"作为「{tgt['标签']}」的配件 ×{n}")
            else:
                item["状态"] = "未识别"; item["说明"].append("前面没有可挂靠的柜子")
        elif "." in tpl:   # 橱柜.吊柜 / 橱柜.中岛 / 浴室柜.镜柜 → 并入同房间的主家具，没有就新建
            tgt = next((it for it in reversed(items) if it["房间"] == item["房间"] and it["楼层"] == item["楼层"] and it["模板"] == base), None)
            sub = {k: v for k, v in item["参数"].items()}
            if tgt is None:
                tgt = {"原文": item["原文"], "房间": item["房间"], "楼层": item["楼层"], "模板": base, "标签": templates.get(base, {}) and base or base, "参数": {}, "配件": [], "状态": "ok", "说明": []}
                items.append(tgt); last_by_room[(item["楼层"], item["房间"])] = tgt
            pkeys = {p["键"] for p in templates.get(base, {}).get("参数", [])}
            tgt["参数"].update({k: v for k, v in sub.items() if k in pkeys}); tgt["说明"] += item["说明"]
            item["状态"] = "并入"; item["说明"].append(f"并入「{tgt['标签']}」")
        else:
            # 同房间里已有同名家具（如“八百库”出现在两行）→ 合并到已有的
            prev = next((it for it in reversed(items) if it["房间"] == item["房间"] and it["楼层"] == item["楼层"] and it["标签"] == item["标签"] and it["状态"] in ("ok", "待补尺寸")), None)
            if prev is not None and not explicit_dim:
                prev["配件"] += item["配件"]; prev["说明"] += item["说明"]
                for k, v in item["参数"].items():
                    if k not in prev["参数"] or not prev["参数"][k]: prev["参数"][k] = v
                item["状态"] = "并入"; item["说明"] = [f"并入「{prev['标签']}」"]; items.append(item); continue
            item["状态"] = "ok"
            # 模板里不存在的参数（如“组数”“层板”“灯带”在非通用柜）转成配件
            tp = templates.get(base, {}); pkeys = {p["键"] for p in tp.get("参数", [])}
            for k in list(item["参数"].keys()):
                if k in pkeys: continue
                v = item["参数"].pop(k)
                if k == "抽屉" and v: item["配件"].append({"名称": "抽屉", "数量": v})
                elif k == "灯带" and v: item["配件"].append({"名称": "灯带", "数量": 1})
                elif k == "层板" and v: item["配件"].append({"名称": "树脂层板" if "树脂" in line else "层板", "数量": v})
                elif k == "组数": pass
                elif k == "门板材质": item["说明"].append(f"门板：{v}")
                elif k == "台面": item["说明"].append(f"台面：{v}（该模板无台面参数）")
            need = DIM_MAP.get(base, ["W", "H"])
            if need and not any(item["参数"].get(k) for k in need[:1]):
                item["状态"] = "待补尺寸"
            last_by_room[(item["楼层"], item["房间"])] = item
        items.append(item)

    # 汇总成向导答案的 房间 结构
    rooms = []
    for it in items:
        if it["状态"] not in ("ok", "待补尺寸"): continue
        r = next((x for x in rooms if x["名称"] == it["房间"] and x["楼层"] == it["楼层"]), None)
        if not r: r = {"名称": it["房间"] or "未分配", "楼层": it.get("楼层", "一层"), "家具": []}; rooms.append(r)
        r["家具"].append({"模板": it["模板"], "标签": it["标签"], "参数": it["参数"], "配件": it["配件"], "_来源": it["原文"], "_待补尺寸": it["状态"] == "待补尺寸"})
    return {"识别": items, "房间": rooms,
            "统计": {"总行数": len(items), "识别": sum(1 for i in items if i["状态"] == "ok"), "待补尺寸": sum(1 for i in items if i["状态"] == "待补尺寸"),
                   "并入": sum(1 for i in items if i["状态"] == "并入"), "未识别": sum(1 for i in items if i["状态"] == "未识别")}}

if __name__ == "__main__":
    import sys
    txt = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    res = parse(txt)
    for it in res["识别"]:
        print(f"[{it['状态']:^4}] {it['原文']:<28} → {it['房间']} / {it['模板']} / {it['标签']} {json.dumps(it['参数'], ensure_ascii=False)} {it['配件'] or ''} {' '.join(it['说明'])}")
    print(json.dumps(res["统计"], ensure_ascii=False))
