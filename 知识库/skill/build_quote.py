#!/usr/bin/env python3
"""报价配置 JSON → 好特客格式 xlsx（订单首页 + 明细）。
用法: python3 build_quote.py 配置.json [输出.xlsx]
结构说明见 报价配置_schema.md。所有金额都写成 Excel 公式，客户改数量/单价会自动重算。
"""
import sys, os, json, re, datetime
try:
    import openpyxl  # noqa
except ImportError:  # 新电脑没装 openpyxl 时，用随项目携带的纯 Python 副本
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../demo系统/backend/vendor")))
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

SUPPLIER = {
    "名称": "北京好特客科技有限公司",
    "税号": "91110108MAEH665682",
    "地址": "北京市海淀区紫金数码园3号楼8层0810",
    "电话": "13051984059",
    "开户行": "交通银行股份有限公司北京西坝河支行",
    "账号": "110062113013008080951",
}
thin = Side(style="thin", color="999999")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
HEAD_FILL = PatternFill("solid", fgColor="DDEBF7")
GROUP_FILL = PatternFill("solid", fgColor="F2F2F2")
BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(vertical="center", wrap_text=True)

def load(path):
    cfg = json.load(open(path, encoding="utf-8"))
    cfg.setdefault("组织方式", "按楼层"); cfg.setdefault("配置档位", "自定义"); cfg.setdefault("价格口径", "牌价")
    cfg.setdefault("折扣", {"方式": "无"}); cfg.setdefault("不含项", []); cfg.setdefault("说明", [])
    m = cfg.setdefault("meta", {})
    m.setdefault("报价日期", datetime.date.today().isoformat())
    if not m.get("订单编号"):
        m["订单编号"] = "HTBJ" + m["报价日期"].replace("-", "") + "001"
    m.setdefault("生产周期", "60工作日（订单下单付全款开始计算）"); m.setdefault("付款条件", "全款支付")
    m.setdefault("税", "含税"); m.setdefault("担当", "鄂"); m.setdefault("客户抬头", m.get("客户名", ""))
    pid = 0
    for g in cfg["分组"]:
        for p in g["部件"]:
            p.setdefault("类别", "木作"); p.setdefault("材质", ""); p.setdefault("尺寸", ""); p.setdefault("说明", ""); p.setdefault("备注", "")
            p["数量"] = str(p.get("数量", "1")); p["_id"] = pid; pid += 1
        for p in g["部件"]:   # =@X 只在“原始分组”内解析：引用本组名称含 X 的其它行
            q = p["数量"].strip()
            if q.startswith("=@"):
                key = q[2:]
                p["_refs"] = [o["_id"] for o in g["部件"] if key in o["名称"] and o is not p]
    return cfg

def regroup(cfg):
    """按组织方式决定一级分组标题。JSON 已按分组给出时直接用；按区域/按大类时用 房间/类别 字段重新聚合。"""
    mode = cfg["组织方式"]
    if mode == "按楼层":
        return cfg["分组"]
    multi = len({g.get("楼层", "一层") for g in cfg["分组"]}) > 1
    key = (lambda g, p: ((g.get("楼层", "") if multi else "") + (g.get("房间") or g["名称"]))) if mode == "按区域" else (lambda g, p: p.get("类别", "木作"))
    out, idx = [], {}
    for g in cfg["分组"]:
        for p in g["部件"]:
            k = key(g, p)
            if k not in idx:
                idx[k] = len(out); out.append({"名称": k, "部件": []})
            q = dict(p)
            if mode == "按大类" and g.get("楼层"): q["名称"] = f"{g.get('楼层')} {g.get('房间','')} {q['名称']}".strip()
            elif mode == "按区域" and g.get("家具") and g["家具"] not in q["名称"]: q["名称"] = f"{g['家具']}-{q['名称']}"
            out[idx[k]]["部件"].append(q)
    return out

def write_detail(ws, cfg, groups):
    m = cfg["meta"]
    ws.merge_cells("A1:L1"); ws["A1"] = "好 特 客 住 空 間 體 驗 館"; ws["A1"].font = Font(size=14, bold=True); ws["A1"].alignment = CENTER
    ws.merge_cells("A2:L2"); ws["A2"] = "御  見 積 書"; ws["A2"].font = Font(size=13, bold=True); ws["A2"].alignment = CENTER
    ws["A3"] = "客户名称："; ws["B3"] = m.get("客户名", ""); ws["F3"] = "项目所在地："; ws["G3"] = m.get("项目地址", "")
    ws["A4"] = "报价日期："; ws["B4"] = m["报价日期"]; ws["F4"] = "供货方："; ws["G4"] = SUPPLIER["名称"]
    ws["A5"] = "订单编号："; ws["B5"] = m["订单编号"]; ws["F5"] = "配置档位："; ws["G5"] = cfg["配置档位"]
    heads = ["NO", "项目", "内容", "颜色/材质", "尺寸(mm)", "数量", "单位", cfg["价格口径"], "合计金额（元）", "说明", "类别", "备注"]
    for c, h in enumerate(heads, 1):
        cell = ws.cell(6, c, h); cell.font = BOLD; cell.fill = HEAD_FILL; cell.alignment = CENTER; cell.border = BORDER
    r = 7; no = 0; subtotal_cells = []; cat_cells = {}
    for g in groups:
        start = r
        id2row = {}
        for p in g["部件"]:
            id2row[p["_id"]] = r; r += 1
        r = start
        for p in g["部件"]:
            no += 1
            qty = p["数量"].strip()
            if qty.startswith("=@"):   # 引用同一原始分组内其它行的数量（load() 已解析为 _refs）
                refs = [f"F{id2row[i]}" for i in p.get("_refs", []) if i in id2row]
                qty = "=" + "+".join(refs) if refs else "0"
            elif not qty.startswith("="):
                try: qty = float(qty)
                except ValueError: pass
            price = p["单价"] if p["单价"] not in (None, "") else None   # 待定价：单价留空，金额公式仍写入，Excel 显示 0
            vals = [no, g["名称"], p["名称"], p["材质"], p["尺寸"], qty, p["单位"], price, f"=H{r}*F{r}", p["说明"], p["类别"], p["备注"]]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(r, c, v); cell.border = BORDER; cell.alignment = CENTER if c in (1, 6, 7, 8, 9, 11) else LEFT
            ws.cell(r, 8).number_format = "#,##0.00"; ws.cell(r, 9).number_format = "#,##0.00"; ws.cell(r, 6).number_format = "0.00##"
            cat_cells.setdefault(p["类别"], []).append(f"I{r}")
            r += 1
        end = r - 1
        if end > start: ws.merge_cells(start_row=start, start_column=2, end_row=end, end_column=2)
        ws.cell(start, 2).alignment = CENTER
        ws.cell(r, 3, f"{g['名称']} 小计").font = BOLD
        ws.cell(r, 9, f"=SUM(I{start}:I{end})").font = BOLD; ws.cell(r, 9).number_format = "#,##0.00"
        for c in range(1, 13): ws.cell(r, c).fill = GROUP_FILL; ws.cell(r, c).border = BORDER
        g["_subtotal"] = f"I{r}"; subtotal_cells.append(f"I{r}"); r += 1
    ws.cell(r, 3, "合计").font = BOLD
    ws.cell(r, 9, "=" + "+".join(subtotal_cells)).font = BOLD; ws.cell(r, 9).number_format = "#,##0.00"
    total_cell = f"I{r}"; r += 1
    # 类别合计（供首页按类别折扣用）
    cat_total = {}
    for cat, cells in cat_cells.items():
        ws.cell(r, 3, f"其中：{cat}"); ws.cell(r, 9, "=" + "+".join(cells)); ws.cell(r, 9).number_format = "#,##0.00"
        cat_total[cat] = f"I{r}"; r += 1
    r += 1
    if cfg["不含项"]:
        ws.cell(r, 2, "不含项：").font = BOLD; r += 1
        for t in cfg["不含项"]: ws.cell(r, 3, "· " + t); r += 1
    if cfg["说明"]:
        ws.cell(r, 2, "说明：").font = BOLD; r += 1
        for t in cfg["说明"]: ws.cell(r, 3, "· " + t); r += 1
    for col, w in zip("ABCDEFGHIJKL", [5, 16, 26, 16, 16, 10, 7, 11, 14, 22, 7, 20]): ws.column_dimensions[col].width = w
    ws.freeze_panes = "A7"
    return total_cell, cat_total

def write_cover(ws, cfg, groups, detail_name, total_cell, cat_total):
    m = cfg["meta"]; d = cfg["折扣"]
    ws.merge_cells("A1:H1"); ws["A1"] = "好特客产品订货单"; ws["A1"].font = Font(size=16, bold=True); ws["A1"].alignment = CENTER
    ws["G2"] = "订单编号." + m["订单编号"]
    ws["A3"] = m.get("客户抬头", ""); ws["A3"].font = Font(size=12, bold=True); ws["D3"] = "御中"
    rows = [("項目名：", m.get("项目名", "")), ("金額（人民币:元）", None), ("生产周期", m["生产周期"]),
            ("運送場所", m.get("项目地址", "")), ("付款条件", m["付款条件"]), ("其他", "详细条款依据好特客产品代理合作协议")]
    r = 5
    for k, v in rows:
        ws.cell(r, 1, k).font = BOLD
        if v is not None: ws.cell(r, 2, v)
        r += 1
    amount_row = 6
    ws["F5"] = "采购方：（盖章/签字）"; ws["F7"] = "供应方：" + SUPPLIER["名称"]; ws["F9"] = "日期：" + m["报价日期"]
    r = 13
    for c, h in enumerate(["NO", "項目", "内容", "数量", "単位", "牌价合计（元）", "折扣", "折后金額（元）"], 1):
        cell = ws.cell(r, c, h); cell.font = BOLD; cell.fill = HEAD_FILL; cell.alignment = CENTER; cell.border = BORDER
    r += 1; first = r
    mode = d.get("方式", "无")
    if mode == "按类别":
        rates = d.get("按类别", {})
        for i, (cat, cell) in enumerate(cat_total.items(), 1):
            rate = rates.get(cat, 1.0)
            vals = [i, cat, "", 1, "项", f"='{detail_name}'!{cell}", rate, f"=F{r}*G{r}"]
            for c, v in enumerate(vals, 1): ws.cell(r, c, v).border = BORDER
            r += 1
    else:
        rate = d.get("整单折扣", 1.0) if mode == "整单" else 1.0
        for i, g in enumerate(groups, 1):
            vals = [i, g["名称"], "后附明细", 1, "项", f"='{detail_name}'!{g['_subtotal']}", rate, f"=F{r}*G{r}"]
            for c, v in enumerate(vals, 1): ws.cell(r, c, v).border = BORDER
            r += 1
    last = r - 1
    ws.cell(r, 2, "合计").font = BOLD
    ws.cell(r, 6, f"=SUM(F{first}:F{last})"); ws.cell(r, 8, f"=SUM(H{first}:H{last})")
    sum_row = r; r += 1
    if mode == "谈判整数":
        ws.cell(r, 2, "成交价（谈判整数）").font = BOLD; ws.cell(r, 8, d.get("成交价", 0)); ws.cell(r, 7, f"=H{r}/F{sum_row}"); ws.cell(r, 7).number_format = "0.0%"
        final = f"H{r}"; r += 1
    else:
        final = f"H{sum_row}"
    ws.cell(amount_row, 2, f"={final}"); ws.cell(amount_row, 2).font = Font(size=14, bold=True)
    for rr in range(first, r):
        for c in (6, 8): ws.cell(rr, c).number_format = "#,##0.00"
    r += 1
    ws.cell(r, 1, "付款单位及开票信息：").font = BOLD; ws.cell(r, 5, "付款信息：").font = BOLD; r += 1
    ws.cell(r, 1, "公司名称：\n税号：\n地址电话：\n法人代表：\n电话：\n开户银行账号：").alignment = LEFT
    ws.cell(r, 5, "名称：{名称}\n纳税人识别号：{税号}\n地址：{地址}\n电话：{电话}\n开户行：{开户行}\n账号：{账号}".format(**SUPPLIER)).alignment = LEFT
    ws.row_dimensions[r].height = 100
    for col, w in zip("ABCDEFGH", [16, 30, 12, 7, 7, 16, 8, 16]): ws.column_dimensions[col].width = w

def build(json_path, out_path=None):
    cfg = load(json_path)
    groups = regroup(cfg)
    wb = Workbook()
    cover = wb.active; cover.title = "订单首页"
    detail_name = {"按楼层": "内容", "按区域": "零售价", "按大类": "附件"}.get(cfg["组织方式"], "内容")
    detail = wb.create_sheet(detail_name)
    total_cell, cat_total = write_detail(detail, cfg, groups)
    write_cover(cover, cfg, groups, detail_name, total_cell, cat_total)
    if not out_path:
        d = cfg["meta"]["报价日期"].replace("-", "")
        out_path = os.path.join(os.path.dirname(os.path.abspath(json_path)), f"报价_{cfg['meta'].get('客户名','客户')}_{cfg['组织方式']}_{d}.xlsx")
    wb.save(out_path)
    # 用 python 回算一次总额，方便在没有 Excel 的环境里核对
    def ev(q):
        q = str(q)
        return eval(q[1:]) if q.startswith("=") and re.fullmatch(r"=[\d\.\+\-\*/\(\) ]+", q) else (float(q) if not q.startswith("=") else None)
    tot = 0; unknown = 0
    for g in groups:
        for p in g["部件"]:
            v = ev(p["数量"])
            if v is None: unknown += 1
            else: tot += v * float(p["单价"] or 0)
    print(f"已生成 {out_path}\n明细牌价合计（python回算）= {tot:,.2f}" + (f"（另有 {unknown} 行为引用公式，需在 Excel 中查看）" if unknown else ""))
    return out_path

if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
