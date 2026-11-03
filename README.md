# 大鄂智能 · 报价系统 (dae_intelligence)

Python 标准库后端 + 原生前端，登录 → 报价向导 → 生成 Excel。

本地运行：`python3 demo系统/backend/server.py 8764` → http://localhost:8764
默认账号 `heqiang`，初始密码取环境变量 `DAE_ADMIN_PASSWORD`（未设置则为 `heqiang123`，请务必修改）。

云端部署见 render.yaml（Render 免费 Web Service）。环境变量：`HOST=0.0.0.0`、`DAE_ADMIN_PASSWORD`。
