"""生成 xlsx：复用 知识库/skill/build_quote.py；历史报价列表；打开 / 另存。"""
import os, sys, json, glob, subprocess, shutil, platform, datetime, re, copy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "输出")
SKILL = os.path.join(ROOT, "知识库", "skill")
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, SKILL)
import build_quote          # noqa: E402
import engine               # noqa: E402
import kb                   # noqa: E402

def _safe_name(s): return re.sub(r"[\\/:*?\"<>|\s]+", "_", s)[:40]

def build(cfg_clean, tiers=None):
    """cfg_clean: 干净的报价配置 JSON。tiers: None 或 ['基础','中配','高配']（三档时重新取价）。返回文件列表。"""
    os.makedirs(OUT, exist_ok=True)
    files = []
    variants = [(cfg_clean["配置档位"], cfg_clean)]
    if tiers:
        variants = []
        ans = cfg_clean.get("_答案")
        for t in tiers:
            if ans:
                a = copy.deepcopy(ans); a["档位"] = t
                c = engine.strip_private(engine.build_config(a)); c["配置档位"] = t
            else:
                c = copy.deepcopy(cfg_clean); c["配置档位"] = t
            variants.append((t, c))
    for tier, c in variants:
        c = copy.deepcopy(c)
        name = f"{_safe_name(c['meta']['客户名'])}_{c['meta']['报价日期'].replace('-', '')}" + (f"_{tier}" if tiers else "")
        jp = os.path.join(OUT, name + ".json"); xp = os.path.join(OUT, "报价_" + name + ".xlsx")
        json.dump(c, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        build_quote.build(jp, xp)
        files.append({"tier": tier, "json": os.path.basename(jp), "xlsx": os.path.basename(xp)})
    return files

def learn(cfg_clean, answers, customs):
    """学习回路：自定义配件 → 价格档位.json（待定价）；导入时用户指认的简写 → 别名表。"""
    out = {"新增取价键": [], "新增别名": []}
    src = f"{cfg_clean['meta'].get('客户名','')} {cfg_clean['meta'].get('报价日期','')}"
    out["新增取价键"] = kb.register_customs(customs, src)
    for a in (answers or {}).get("_新别名", []):
        r = kb.alias_append("家具别名", [a.get("简写", ""), a.get("房间", ""), a.get("模板", ""), a.get("标签", a.get("简写", "")), a.get("参数", "")])
        if r.get("ok") and not r.get("skipped"): out["新增别名"].append(a.get("简写"))
    return out

def history():
    out = []
    for jp in sorted(glob.glob(os.path.join(OUT, "*.json")), key=os.path.getmtime, reverse=True):
        try:
            c = json.load(open(jp, encoding="utf-8"))
            if "分组" not in c: continue
            xp = os.path.join(OUT, "报价_" + os.path.basename(jp)[:-5] + ".xlsx")
            out.append({"json": os.path.basename(jp), "xlsx": os.path.basename(xp) if os.path.exists(xp) else None,
                        "客户名": c["meta"].get("客户名"), "日期": c["meta"].get("报价日期"), "组织方式": c.get("组织方式"),
                        "档位": c.get("配置档位"), "分组数": len(c["分组"]), "mtime": os.path.getmtime(jp),
                        "有答案": bool(c.get("_答案"))})
        except Exception:
            pass
    return out

def load(name):
    p = os.path.join(OUT, os.path.basename(name))
    return json.load(open(p, encoding="utf-8"))

def open_local(name, reveal=False):
    p = os.path.join(OUT, os.path.basename(name))
    if not os.path.exists(p): return {"ok": False, "error": "文件不存在"}
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            cmd = ["open", "-R", p] if reveal else ["open", p]
        elif sysname == "Windows":
            os.startfile(p); return {"ok": True}
        else:
            cmd = ["xdg-open", p]
        subprocess.Popen(cmd); return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def save_as(name, dest_dir):
    p = os.path.join(OUT, os.path.basename(name))
    d = os.path.expanduser(dest_dir)
    home = os.path.expanduser("~")
    if not os.path.abspath(d).startswith(home): return {"ok": False, "error": "只允许保存到用户目录下"}
    os.makedirs(d, exist_ok=True)
    shutil.copy2(p, os.path.join(d, os.path.basename(p)))
    return {"ok": True, "path": os.path.join(d, os.path.basename(p))}
