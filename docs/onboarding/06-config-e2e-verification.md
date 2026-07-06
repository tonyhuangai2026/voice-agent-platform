# 06 · 端到端集成验证报告

> 验证范围: T1 + T2 + T3 + T4 + T5 (runtime_config + demo_loader + Admin REST API
> + Vue Admin SPA + 部署集成) 是否真正贯通, 满足"配置 / 演示分离 + per-call hot-reload"的承诺。
>
> 7 个场景中, **场景 1–2、4–7** 通过 FastAPI TestClient 在本机直接执行了真实流程;
> **场景 3 (Phone per-call hot-reload)** 通过等价的 RUNTIME_CONFIG 快照语义验证 + 代码审查
> 替代实拨电话 (实拨需要 Chime VC 已配且 IP 路由通; 留待 deploy 后人工补做)。

执行时间: 2026-05-18 (UTC)
运行时栈: Python 3.13 / FastAPI / pytest / Vue 3 build dist mounted

---

## 场景 1 · 首次启动 seed ✅

**步骤**:

1. 删除 `config/runtime.json` (如存在)
2. 启动 bot.py (本场景用 TestClient 触发 import 即可)
3. 检查文件自动出现, 内容是 fallback 默认值
4. `GET /api/admin/config` 返回 `{web, phone}` 非空

**实际观察**:

```text
config/runtime.json exists at startup? False    # 启动前无文件
GET /api/admin/config status: 200
Web segment keys: ['engine', 'lang', 'minimax_model', 'model', 'provider', 'scenario', 'voice']
Phone segment keys: ['engine', 'lang', 'minimax_model', 'model', 'provider', 'scenario', 'voice']
config/runtime.json now:
{
  "web": {
    "lang": "en-US",
    "engine": "nova-sonic",
    "scenario": "acme-security-support",
    ...
  },
  "phone": { ... },
  "_meta": { "version": 1, "updated_at": "2026-05-18T09:58:27.159222Z" }
}
```

- [x] 通过 — 文件自动 seed, 字段齐全, `_meta` 含 schema version + ISO timestamp。

---

## 场景 2 · Web 端默认热更新 ✅

**步骤**:

1. 启动状态: web.engine = nova-sonic
2. `PUT /api/admin/config/web {"engine": "pipeline"}`
3. `GET /api/config` 返回 default_engine = pipeline (无需重启)
4. (浏览器手动验证 — 刷新页面 UI 默认 engine = pipeline; 留给最后回归)

**实际观察**:

```text
Initial web.engine: nova-sonic
PUT response engine: pipeline
GET /api/config default_engine = pipeline       # 同进程, 无重启
```

- [x] 通过 — runtime_config 内存缓存写入 + 落盘 + 下游 GET 立即看到新值。

---

## 场景 3 · Phone 端 per-call hot-reload ✅ (等价验证)

**说明**: 真正实拨电话需要 Chime VC + 公网 IP 路由通, 留给 deploy 后人工补;
**本机替代验证**用代码语义 + RUNTIME_CONFIG 快照证明:

```python
# phone_ws_endpoint 进入时:
p = RUNTIME_CONFIG.get_phone_defaults()   # 返回 dict 副本
p_engine = p['engine']                     # 局部变量, in-flight call 持有
# ...
_build_*_pipeline(..., p_engine, ...)      # 闭包捕获局部变量
```

之后管理员改 phone.engine, RUNTIME_CONFIG._cache 被覆盖, 但局部变量 p_engine
不变 (Python dict + locals semantics)。

**实际观察 (本机模拟)**:

```text
=== SCENARIO 3: Phone per-call snapshot semantics ===
Snapshot A (held by hypothetical in-flight call): {'engine': 'nova-sonic', 'lang': 'en-US', 'scenario': 'acme-security-support'}
PUT /api/admin/config/phone {"engine": "pipeline"}
Snapshot B (next /phone/ws would read this): {'engine': 'pipeline', 'lang': 'en-US', 'scenario': 'acme-security-support'}
Snapshot A engine still: nova-sonic (in-flight call unaffected; dict copy returned by get_*)
```

`bot.py:phone_ws_endpoint` 真实代码 (line 1759-1772):

```python
p = RUNTIME_CONFIG.get_phone_defaults()
p_engine   = p.get("engine",   DEFAULT_ENGINE)
p_lang     = p.get("lang",     DEFAULT_LANG)
p_scenario = p.get("scenario", DEFAULT_SCENARIO)
# ...
logger.info(f"phone WS using runtime config: engine={p_engine} lang={p_lang} ...")
if p_engine == "nova-sonic":
    task = _build_nova_sonic_pipeline(websocket, p_lang, p_voice, ...)
else:
    task = _build_pipeline(websocket, p_lang, p_model, p_voice, p_provider, ...)
```

- [x] 通过 (等价语义) — get_phone_defaults 返回的 dict 是 RUNTIME_CONFIG._fallback 与
  cache 合并的新 dict; 端点把字段拆到 7 个局部变量, 后续 _build_*_pipeline 调用只看
  这些局部变量。中途 admin 改值, 这些 locals 不会被改。
- [ ] 留待 deploy 后实拨补充 — 见 §"待补"。

---

## 场景 4 · KB 多语言迁移回归 (B1 验证) ✅

**步骤**: 对每个语言调用 `bot._resolve_kb_scenario("acme-security-support", lang)`,
检查得到的 (system, greeting) 是否对应该语言。

**实际观察**:

```text
zh-HK: greeting len=66  sys len=735  preview="用粵語開場:先講「你好,我係ACME 安防技術支援嘅 Tina」..."
zh-CN: greeting len=70  sys len=736  preview="用普通话开场:先说「您好,我是ACME 安防技术支持的 Tina」..."
en-US: greeting len=168 sys len=1803 preview="Greet the customer warmly in English: \"Hi, this is..."
ja-JP: greeting len=91  sys len=816  preview="日本語で挨拶してください。「お電話ありがとうございます、ACME技術..."
```

并且 T2 单测 `test_byte_equal_with_legacy_kb_scenarios` 已经断言 demo_loader 路径
与 KB_SCENARIOS 路径**逐字符相等**, 4 个语言全部通过。

- [x] 通过 — 4 语言全部命中 demo_loader 路径; 内容与原 KB_SCENARIOS byte-equal;
  不存在丢语言的 B1 风险。

---

## 场景 5 · 新 demo 热加载 ✅

**步骤**: mkdir + manifest + kb.md → POST rescan → PUT scenario → 验证生效。

**实际操作**:

```bash
mkdir data/test-bank-demo
cat > data/test-bank-demo/manifest.yaml <<'YAML'
id: test-bank-demo
label: 测试银行 Demo
lang: zh-CN
system:
  zh-CN: |
    你是测试银行的智能客服, 用普通话回答问题.
greeting:
  zh-CN: 您好, 测试银行客服, 请问有什么可以帮您?
YAML
echo '# 测试 KB\n业务时间 9:00-17:00.' > data/test-bank-demo/kb.md
```

**API 响应快照**:

```text
POST /api/admin/demos/rescan -> filtered to test-bank-demo:
[{"id": "test-bank-demo", "label": "测试银行 Demo", "lang": "zh-CN", "kb_chars": 24}]

PUT /api/admin/config/web {"scenario": "test-bank-demo"} -> 200
GET /api/config default_scenario = test-bank-demo

bot._resolve_kb_scenario("test-bank-demo", "zh-CN") greeting:
"您好, 测试银行客服, 请问有什么可以帮您?"
```

- [x] 通过 — 不重启服务, 新 demo 在 admin UI / API / runtime config 三处同步可见,
  pipeline 实际能拿到正确 system / greeting。

---

## 场景 6 · 鉴权 ✅

**步骤**: 试 (a) 无 header, (b) 错密码, (c) 对密码; 然后试 ADMIN_PASSWORD 为空时的 503。

**实际观察 (TestClient)**:

```text
=== SCENARIO 6: Auth ===
No header:  401 admin auth required
Wrong pwd:  401
Right pwd:  200
```

**ADMIN_PASSWORD 空 → 503 (单独由 test_admin_disabled_when_password_empty 验证)**:

```python
# tests/test_admin_api.py
monkeypatch.setenv("ADMIN_PASSWORD", "")
client.get("/api/admin/config")  # → 503
client.get("/api/admin/health")  # → 503
```

curl 等价命令 (生产环境):

```bash
# 空密码部署
curl -i https://<host>/api/admin/config
# HTTP/2 503
# {"detail":"admin disabled (ADMIN_PASSWORD not set)"}

# 设了密码, 错输
curl -i -u admin:wrong https://<host>/api/admin/config
# HTTP/2 401
# WWW-Authenticate: Basic realm="Voice Bot Admin"
# {"detail":"admin auth required"}

# 对密码
curl -i -u admin:correct https://<host>/api/admin/config
# HTTP/2 200
# {"web":{...},"phone":{...}}
```

`/admin/` 静态资源同样受 admin_path_guard middleware 保护 (路径前缀匹配)。

- [x] 通过 — 503 / 401 / 200 三态全部正确, WWW-Authenticate header 触发浏览器原生
  Basic Auth 弹窗。

---

## 场景 7 · 失败恢复 ✅

**步骤**: corrupt JSON 后 GET → 自动 reseed; (chmod -w 测试见说明)

**实际观察 (corrupt JSON)**:

```text
# 写入 "{ corrupt"
runtime_config: /home/ubuntu/test_audio_framework/config/runtime.json unreadable
  (JSONDecodeError: Expecting property name enclosed in double quotes:
   line 1 column 3 (char 2)); reseeding
Corrupt JSON re-read engine: nova-sonic (fallback + reseed)
File rewritten valid: nova-sonic
```

**chmod -w 写失败说明**: 在 root 权限下 chmod -w 不阻止写, 用 unittest.mock 替代
更可靠 — 单测 `test_runtime_config.py` 的 atomic write 路径已覆盖 (_write_atomic 在
异常时 unlink tmp 文件, 不破坏 cache)。生产路径的"磁盘满"可由 OS layer 检测,
admin API 会返回 500, RUNTIME_CONFIG._cache 不更新。

- [x] 通过 — 损坏 JSON 自动 reseed 不让服务崩;
  写失败的兜底已在 RuntimeConfig._write_atomic 里通过 try/except + tmp cleanup 处理。

---

## 总览

| 场景 | 状态 | 说明 |
|---|---|---|
| 1. 首次启动 seed | ✅ 通过 | 文件自动出现, 字段齐全 |
| 2. Web 默认热更新 | ✅ 通过 | PUT 后同进程 GET 立即反映 |
| 3. Phone per-call hot-reload | ✅ 等价通过 | 代码 + 快照语义证明; 实拨 deploy 后补 |
| 4. KB 多语言回归 (B1 验证) | ✅ 通过 | 4 语言全部命中 + byte-equal 单测 |
| 5. 新 demo 热加载 | ✅ 通过 | mkdir → rescan → 立即可用 |
| 6. 鉴权 (503/401/200) | ✅ 通过 | TestClient + 单测全覆盖 |
| 7. 失败恢复 | ✅ 通过 | 损坏 JSON 自动 reseed |

**单元测试总数**: 24 (runtime_config 6 + demo_loader 8 + admin_api 10), **全过**。

---

## 待补 (留给 deploy 后人工)

- [ ] **场景 3 实拨电话**: 拨打 +1 555-000-1111, 通话 A 进行中调 admin PUT 改 phone.engine,
  确认 voicebot.log 显示 A 仍 nova-sonic; 挂断 + 再拨, B 应 pipeline。需 Chime VC origination
  指向新 IP 后才能跑。
- [ ] **场景 4 实拨电话各 4 语言**: 用 zh-HK / zh-CN / en-US / ja-JP 各拨一通ACME 安防 demo,
  听 bot 是否用对应语言开场。本地已用 _resolve_kb_scenario 等价验证, 但实际 TTS 输出
  最终归 deploy 后听感 (不影响 B1 BLOCKER 修复的逻辑正确性)。
- [ ] **浏览器手动 UI 验证**: 真打开 /admin/, 用浏览器 Basic Auth 进入, 三页面交互正常,
  保存按钮触发 toast, 暗色 / 浅色切换 + 主题色 #0084FF 视觉确认。

---

## 相关

- T1 单测: [tests/test_runtime_config.py](../../tests/test_runtime_config.py)
- T2 单测: [tests/test_demo_loader.py](../../tests/test_demo_loader.py)
- T3 单测: [tests/test_admin_api.py](../../tests/test_admin_api.py)
- T4 Admin UI: [static/admin/](../../static/admin/)
- T5 部署: [deploy/deploy.sh](../../deploy/deploy.sh) + [deploy/cloudformation.yaml](../../deploy/cloudformation.yaml)
- 操作 runbook: [03-runbook.md §6 Admin UI](03-runbook.md)
- 配置清单: [05-config-and-env.md](05-config-and-env.md)
