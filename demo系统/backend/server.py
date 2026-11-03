#!/usr/bin/env python3
"""大鄂智能 · 报价演示系统 后端。纯标准库。
启动： python3 server.py [端口]   默认 8765，只监听 127.0.0.1
"""
import os, sys, json, mimetypes, urllib.parse, http.cookies, shutil
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "vendor"))
import auth, kb, engine, quote, parse_notes   # noqa: E402

ROOTDIR = os.path.abspath(os.path.join(HERE, ".."))
UI_VERSIONS = sorted(d[len("frontend_"):] for d in os.listdir(ROOTDIR) if d.startswith("frontend_") and os.path.isdir(os.path.join(ROOTDIR, d)))
DEFAULT_UI = (sys.argv[2] if len(sys.argv) > 2 else None) or (UI_VERSIONS[-1] if UI_VERSIONS else "v0.1")
def front_dir(ver): return os.path.join(ROOTDIR, "frontend_" + ver)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8765))
HOST = os.environ.get("HOST", "127.0.0.1")   # 云端部署时设 HOST=0.0.0.0
mimetypes.add_type("application/javascript", ".js")

class H(BaseHTTPRequestHandler):
    server_version = "DaE/0.1"
    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    # ---- helpers ----
    def _json(self, obj, code=200, headers=None):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
    def _tok(self):
        c = http.cookies.SimpleCookie(self.headers.get("Cookie") or "")
        return c["dae"].value if "dae" in c else None
    def _sess(self):
        return auth.session(self._tok() or "")
    def _need(self, admin=False):
        s = self._sess()
        if not s: self._json({"error": "未登录"}, 401); return None
        if admin and s["role"] != "admin": self._json({"error": "需要管理员"}, 403); return None
        return s
    def _file(self, path):
        if not os.path.exists(path) or os.path.isdir(path): self.send_error(404); return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f: data = f.read()
        self.send_response(200); self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or "javascript" in ctype else ""))
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    # ---- routing ----
    def _path(self):
        try: return self.path.encode("latin-1").decode("utf-8")
        except Exception: return self.path
    def do_GET(self):
        u = urllib.parse.urlparse(self._path()); p = u.path; q = urllib.parse.parse_qs(u.query)
        if p.startswith("/api/"):
            return self.api("GET", p, q, {})
        # static：/ → 默认版本；/v0.1/... → 指定版本（便于新旧 UI 对比）
        ver, rel = DEFAULT_UI, p.lstrip("/")
        seg = rel.split("/", 1)
        if seg[0] in UI_VERSIONS:
            ver, rel = seg[0], (seg[1] if len(seg) > 1 else "")
        rel = rel or "index.html"
        base = front_dir(ver)
        full = os.path.abspath(os.path.join(base, rel))
        if not full.startswith(base): return self.send_error(403)
        self._file(full)
    def do_POST(self):
        u = urllib.parse.urlparse(self._path())
        self.api("POST", u.path, urllib.parse.parse_qs(u.query), self._body())
    def do_PUT(self):
        u = urllib.parse.urlparse(self._path())
        self.api("PUT", u.path, urllib.parse.parse_qs(u.query), self._body())
    def do_DELETE(self):
        u = urllib.parse.urlparse(self._path())
        self.api("DELETE", u.path, urllib.parse.parse_qs(u.query), {})

    def api(self, m, p, q, body):
        try:
            return self._api(m, p, q, body)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._json({"error": str(e)}, 500)

    def _api(self, m, p, q, body):
        # --- auth ---
        if p == "/api/login" and m == "POST":
            tok = auth.login(body.get("username", ""), body.get("password", ""))
            if not tok: return self._json({"error": "用户名或密码错误"}, 401)
            s = auth.session(tok)
            return self._json({"ok": True, "user": s["user"], "role": s["role"]}, headers={"Set-Cookie": f"dae={tok}; Path=/; HttpOnly; SameSite=Lax"})
        if p == "/api/logout": auth.logout(self._tok() or ""); return self._json({"ok": True}, headers={"Set-Cookie": "dae=; Path=/; Max-Age=0"})
        if p == "/api/me":
            s = self._sess(); return self._json({"user": s["user"], "role": s["role"]} if s else {"user": None})
        s = self._need()
        if not s: return
        # --- users (admin) ---
        if p == "/api/users":
            if m == "GET": return self._json(auth.list_users())
            if not self._need(admin=True): return
            if m == "POST": auth.upsert_user(body["username"], body.get("password"), body.get("role")); return self._json({"ok": True})
            if m == "DELETE": return self._json({"ok": auth.delete_user(q.get("username", [""])[0])})
        # --- knowledge base ---
        if p == "/api/kb/alias" and m == "POST":
            return self._json(kb.alias_append(body.get("section", "家具别名"), body.get("cells", [])))
        if p == "/api/kb/pending":
            if m == "GET": return self._json(kb.pending_prices())
            if m == "PUT": return self._json(kb.set_price(body["键"], body.get("价格", {})))
        if p == "/api/kb" and m == "GET": return self._json(kb.list_files())
        if p.startswith("/api/kb/"):
            rel = urllib.parse.unquote(p[len("/api/kb/"):])
            if m == "GET": return self._json(kb.read_file(rel))
            if m == "PUT": return self._json(kb.write_file(rel, body.get("content", ""), body.get("mtime")))
        # --- wizard ---
        if p == "/api/wizard/config":
            templates, prices, wiz = engine.load_rules()
            catalog = [{"键": k, "名称": k.split(".")[-1], "单位": v.get("单位", ""), "类别": v.get("类别", ""), "待定价": bool(v.get("_待定价"))}
                       for k, v in prices.items() if isinstance(v, dict) and v.get("_配件")]
            return self._json({"问答配置": wiz, "家具模板": {k: {"说明": v.get("说明", ""), "参数": v["参数"], "支持配件": bool(v.get("支持配件")), "默认配件": v.get("默认配件", [])} for k, v in templates.items() if not k.startswith("_")},
                               "价格档位": prices, "配件目录": catalog})
        if p == "/api/notes/parse" and m == "POST":
            return self._json(parse_notes.parse(body.get("text", "")))
        if p == "/api/quote/expand" and m == "POST":
            cfg = engine.build_config(body)
            return self._json(cfg)
        if p == "/api/quote/build" and m == "POST":
            ans = body.get("答案") or body
            tiers = ["基础", "中配", "高配"] if (ans.get("档位") == "三档都出" or body.get("三档")) else None
            if tiers: ans = dict(ans); ans["档位"] = "中配"
            full = engine.build_config(ans); cfg = engine.strip_private(full); cfg["_答案"] = ans
            files = quote.build(cfg, tiers)
            learned = quote.learn(cfg, ans, full["_摘要"].get("自定义项", []))
            return self._json({"ok": True, "files": files, "摘要": full["_摘要"], "学习": learned})
        if p == "/api/quote/history": return self._json(quote.history())
        if p.startswith("/api/quote/load/"): return self._json(quote.load(urllib.parse.unquote(p.rsplit("/", 1)[1])))
        if p.startswith("/api/quote/download/"):
            name = os.path.basename(urllib.parse.unquote(p.rsplit("/", 1)[1]))
            full = os.path.join(quote.OUT, name)
            if not os.path.exists(full): return self._json({"error": "文件不存在"}, 404)
            data = open(full, "rb").read()
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(name))
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if p == "/api/quote/open" and m == "POST": return self._json(quote.open_local(body["name"], body.get("reveal", False)))
        if p == "/api/quote/saveas" and m == "POST": return self._json(quote.save_as(body["name"], body["dir"]))
        self._json({"error": "未知接口 " + p}, 404)

if __name__ == "__main__":
    auth.load_users()
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print(f"大鄂智能 报价演示系统已启动：http://localhost:{PORT}   默认 UI {DEFAULT_UI}；可用版本 {', '.join(UI_VERSIONS)}（如 http://localhost:{PORT}/v0.1/）  Ctrl+C 停止")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
