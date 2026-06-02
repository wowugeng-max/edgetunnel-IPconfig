#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edgetunnel 地区 IP 配置 Web UI

启动：
  cd /Users/ruiyaosong/.openclaw/workspace
  python3 edgetunnel_region_ui.py

然后打开：
  http://127.0.0.1:8765

说明：
- 默认只监听 127.0.0.1，避免暴露管理员密码。
- 密码只在提交请求时使用，不写入文件、不保存。
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from edgetunnel_region_config import (
    DEFAULT_SOURCE,
    available_regions,
    fetch_text,
    format_add_txt,
    normalize_country,
    parse_source,
    post_to_edgetunnel,
    select_country_nodes,
    speedtest_country_nodes,
    proxy_test_country,
    top_cf_entry_nodes,
    format_proxy_exit_add_txt,
    default_proxy_source,
    restore_default_add_txt,
)

HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>edgetunnel 地区 IP 配置</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --card2: #0b1220;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --line: #243041;
      --blue: #60a5fa;
      --green: #34d399;
      --red: #fb7185;
      --yellow: #fbbf24;
      --input: #020617;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: radial-gradient(circle at 20% 0%, #1e3a8a 0, transparent 34%), var(--bg);
      min-height: 100vh;
      padding: 28px;
    }
    .wrap { max-width: 1080px; margin: 0 auto; }
    h1 { margin: 0 0 8px; font-size: 30px; letter-spacing: -.03em; }
    .sub { color: var(--muted); margin-bottom: 22px; line-height: 1.6; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } body { padding: 16px; } }
    .card, .section {
      background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(2,6,23,.94));
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 20px 60px rgba(0,0,0,.22);
    }
    .section { margin-bottom: 18px; }
    .section h2 { margin: 0 0 4px; font-size: 18px; letter-spacing: -.01em; }
    .section-desc { color: var(--muted); font-size: 13px; line-height: 1.6; margin-bottom: 12px; }
    .badge { display:inline-flex; align-items:center; gap:6px; border:1px solid #334155; border-radius:999px; padding:3px 9px; font-size:12px; color:#bfdbfe; background:rgba(96,165,250,.08); margin-left:8px; font-weight:500; }
    label { display: block; color: #cbd5e1; font-size: 13px; margin: 14px 0 7px; }
    input, select, textarea {
      width: 100%;
      border: 1px solid #334155;
      background: var(--input);
      color: var(--text);
      border-radius: 12px;
      padding: 12px 13px;
      outline: none;
      font-size: 14px;
    }
    input:focus, select:focus, textarea:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(96,165,250,.16); }
    .row { display: grid; grid-template-columns: 1fr 130px; gap: 12px; }
    .quick { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .chip {
      border: 1px solid #334155;
      color: #dbeafe;
      background: rgba(96,165,250,.08);
      border-radius: 999px;
      padding: 7px 11px;
      cursor: pointer;
      font-size: 13px;
      user-select: none;
    }
    .chip:hover { border-color: var(--blue); }
    .actions { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
    button {
      border: 0;
      border-radius: 12px;
      padding: 12px 16px;
      color: #06111f;
      font-weight: 700;
      cursor: pointer;
      background: var(--green);
      font-size: 14px;
    }
    button.secondary { background: var(--blue); color: #07121f; }
    button.ghost { background: #1f2937; color: var(--text); border: 1px solid #334155; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .hint { color: var(--muted); font-size: 12px; line-height: 1.55; margin-top: 8px; }
    .status {
      padding: 12px 14px;
      border-radius: 12px;
      background: rgba(96,165,250,.08);
      border: 1px solid rgba(96,165,250,.22);
      color: #bfdbfe;
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 14px;
      white-space: pre-wrap;
    }
    .status.ok { background: rgba(52,211,153,.1); border-color: rgba(52,211,153,.25); color: #bbf7d0; }
    .status.err { background: rgba(251,113,133,.1); border-color: rgba(251,113,133,.25); color: #fecdd3; }
    .status.warn { background: rgba(251,191,36,.1); border-color: rgba(251,191,36,.25); color: #fde68a; }
    pre {
      margin: 0;
      min-height: 420px;
      max-height: 620px;
      overflow: auto;
      background: #020617;
      border: 1px solid #1e293b;
      border-radius: 14px;
      padding: 14px;
      color: #d1fae5;
      line-height: 1.55;
      font-size: 13px;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .mini { color: var(--muted); font-size: 12px; margin-top: 10px; }
    .footer { color: var(--muted); font-size: 12px; margin-top: 16px; line-height: 1.7; }
    code { color: #bfdbfe; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>edgetunnel 地区 IP 配置</h1>
    <div class="sub">把 <b>入口优选 IP</b> 和 <b>出口代理</b> 分开配置，避免混淆。两者都会生成并写入 <code>/admin/ADD.txt</code>。</div>

    <div class="section">
      <h2>公共配置</h2>
      <div class="section-desc">所有功能共用。管理员密码只在请求时使用，不保存。</div>
      <div id="status" class="status">准备就绪。先选择入口或出口功能，生成结果后再「应用当前结果到 ADD.txt」。</div>
      <label>edgetunnel 地址</label>
      <input id="baseUrl" placeholder="https://edt.example.com" autocomplete="off" />
      <label>管理员密码</label>
      <input id="password" type="password" placeholder="ADMIN 密码；不会保存" autocomplete="current-password" />
      <div class="row">
        <div>
          <label>国家/地区</label>
          <input id="country" placeholder="例如：日本 / 美国 / 印尼 / 英国 / JP / US / ID / UK" value="美国" />
        </div>
        <div>
          <label>生成节点数量</label>
          <input id="limit" type="number" min="1" max="200" value="16" />
        </div>
      </div>
      <div class="quick">
        <span class="chip" data-country="日本">日本</span>
        <span class="chip" data-country="美国">美国</span>
        <span class="chip" data-country="印尼">印尼</span>
        <span class="chip" data-country="英国">英国</span>
        <span class="chip" data-country="香港">香港</span>
        <span class="chip" data-country="新加坡">新加坡</span>
        <span class="chip" data-country="韩国">韩国</span>
        <span class="chip" data-country="德国">德国</span>
        <span class="chip" data-country="法国">法国</span>
      </div>
    </div>

    <div class="grid">
      <div>
        <div class="section">
          <h2>入口设置 <span class="badge">Cloudflare 入口优选 IP</span></h2>
          <div class="section-desc">优化你连接 Cloudflare 的入口。适合测速、找更快入口；<b>不保证最终查询 IP 国家</b>。</div>
          <label>入口 IP 数据源 URL</label>
          <input id="source" value="''' + DEFAULT_SOURCE + r'''" />
          <div class="hint">默认源不一定每次都有所有国家。若公开源为空，可以用本地测速生成。</div>
          <div class="row">
            <div>
              <label>本地测速候选数量</label>
              <input id="candidates" type="number" min="10" max="2000" value="180" />
            </div>
            <div>
              <label>并发</label>
              <input id="concurrency" type="number" min="1" max="100" value="32" />
            </div>
          </div>
          <div class="hint">本地测速会随机生成 Cloudflare IP，连接 <code>/cdn-cgi/trace</code> 判断 colo/国家并按延迟排序。</div>
          <div class="actions">
            <button class="secondary" id="previewBtn">入口：公开源预览</button>
            <button class="ghost" id="speedtestBtn">入口：本地测速生成</button>
            <button class="ghost" id="regionsBtn">查看入口源可用地区</button>
          </div>
        </div>

        <div class="section">
          <h2>出口设置 <span class="badge">最终查询 IP 国家</span></h2>
          <div class="section-desc">测试 SOCKS5/HTTP 出口代理。适合让最终查询 IP 显示指定国家；会生成带 <code>$socks5://...</code> 的节点。</div>
          <label>出口代理源 URL</label>
          <input id="proxySource" placeholder="留空则自动使用 proxy_国家代码.txt；也可填自定义 socks5 列表 URL" />
          <div class="hint">出口代理测速会调用你的 edgetunnel <code>/admin/check?socks5=...</code>，验证代理出口国家。</div>
          <div class="actions">
            <button class="ghost" id="proxyExitBtn">出口：代理测速生成</button>
          </div>
        </div>

        <div class="section">
          <h2>写入 / 恢复</h2>
          <div class="section-desc">入口或出口生成结果都会显示在右侧。确认后再写入 ADD.txt。</div>
          <div class="actions">
            <button id="applyBtn">应用当前结果到 ADD.txt</button>
            <button class="ghost" id="copyBtn">复制当前结果</button>
            <button class="ghost" id="restoreBtn">恢复默认 ADD.txt</button>
          </div>
          <div class="footer">
            安全提示：这个 UI 默认监听 <code>127.0.0.1</code>，不要用 <code>--host 0.0.0.0</code> 暴露到公网。<br />
            入口=Cloudflare 入口；出口=最终查询 IP。要稳定指定国家，优先用出口设置。
          </div>
        </div>
      </div>

      <div class="card">
        <label style="margin-top:0">生成结果 / 日志</label>
        <pre id="output">尚未生成。</pre>
        <div class="mini" id="meta"></div>
      </div>
    </div>
  </div>

<script>
const $ = id => document.getElementById(id);
const statusEl = $('status');
const outputEl = $('output');
const metaEl = $('meta');
let latestAddTxt = '';

function setStatus(text, type='') {
  statusEl.className = 'status' + (type ? ' ' + type : '');
  statusEl.textContent = text;
}
function payload() {
  return {
    base_url: $('baseUrl').value.trim(),
    admin_password: $('password').value,
    country: $('country').value.trim(),
    source: $('source').value.trim(),
    limit: Number($('limit').value || 16),
    candidates: Number($('candidates').value || 180),
    concurrency: Number($('concurrency').value || 32),
    proxy_source: $('proxySource').value.trim(),
  };
}
async function callApi(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {})
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(text || '响应不是 JSON'); }
  if (!res.ok || !data.ok) throw new Error(data.error || '请求失败');
  return data;
}
async function run(dryRun) {
  const p = payload();
  if (!p.base_url) return setStatus('请填写 edgetunnel 地址。', 'err');
  if (!p.country) return setStatus('请填写国家/地区。', 'err');
  if (!dryRun && !p.admin_password) return setStatus('应用到 ADD.txt 需要填写管理员密码。', 'err');
  $('previewBtn').disabled = $('applyBtn').disabled = true;
  setStatus(dryRun ? '正在生成预览…' : '正在登录并写入 ADD.txt…');
  try {
    const data = await callApi('/api/apply', {...p, dry_run: dryRun});
    latestAddTxt = data.add_txt || '';
    outputEl.textContent = latestAddTxt || '(空)';
    metaEl.textContent = `国家代码：${data.country_code} ｜ 命中：${data.count} 条 ｜ 可用地区：${data.available_regions.join(', ') || '无'}`;
    const fallbackNote = data.fallback_url ? `\n已自动使用兜底源：${data.fallback_url}` : '';
    setStatus((dryRun ? '预览完成。确认无误后可以点「应用到 ADD.txt」。' : '已成功写入 edgetunnel /admin/ADD.txt。') + fallbackNote, 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('previewBtn').disabled = $('applyBtn').disabled = false;
  }
}
async function speedtest() {
  const p = payload();
  if (!p.country) return setStatus('请填写国家/地区。', 'err');
  $('speedtestBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = true;
  setStatus(`正在本地测速生成 ${p.country} IP…\n候选 ${p.candidates} 个，并发 ${p.concurrency}。这可能需要几十秒。`, 'warn');
  try {
    const data = await callApi('/api/speedtest', p);
    latestAddTxt = data.add_txt || '';
    outputEl.textContent = latestAddTxt || '(没有命中目标地区，可增加候选数量重试)';
    metaEl.textContent = `国家代码：${data.country_code} ｜ 命中：${data.count} 条 ｜ 成功连接：${data.ok_count} 条 ｜ 成功地区：${data.available_regions.join(', ') || '无'}`;
    setStatus(data.count ? '测速完成。确认无误后可以点「应用到 ADD.txt」。' : '测速完成，但没有命中目标国家。建议增加候选数量，或换一个国家/地区。', data.count ? 'ok' : 'warn');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('speedtestBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = false;
  }
}

async function proxyExitTest() {
  const p = payload();
  if (!p.base_url) return setStatus('出口代理测速需要填写 edgetunnel 地址。', 'err');
  if (!p.admin_password) return setStatus('出口代理测速需要管理员密码，用于调用 /admin/check。', 'err');
  if (!p.country) return setStatus('请填写国家/地区。', 'err');
  $('proxyExitBtn').disabled = $('speedtestBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = true;
  setStatus(`正在测试 ${p.country} 出口代理…\n这会逐个调用 edgetunnel /admin/check，可能需要几十秒。`, 'warn');
  try {
    const data = await callApi('/api/proxy_exit', p);
    latestAddTxt = data.add_txt || '';
    outputEl.textContent = latestAddTxt || (data.checked_text || '(没有可用代理或没有命中目标国家)');
    metaEl.textContent = `国家代码：${data.country_code} ｜ 命中代理：${data.count} 条 ｜ 已检查：${data.checked_count} 条 ｜ 代理源：${data.source}`;
    setStatus(data.count ? `出口代理测速完成，已用最快代理生成 ADD.txt。\n最快代理：${data.best_proxy}` : `未找到 ${data.country_code} 可用出口代理。可换代理源 URL 或自备 SOCKS5。`, data.count ? 'ok' : 'warn');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('proxyExitBtn').disabled = $('speedtestBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = false;
  }
}

async function regions() {
  setStatus('正在读取数据源可用地区…');
  try {
    const data = await callApi('/api/regions', {source: $('source').value.trim()});
    outputEl.textContent = JSON.stringify(data.regions, null, 2);
    metaEl.textContent = `总节点：${data.total}`;
    setStatus('已读取可用地区。', 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  }
}

document.querySelectorAll('.chip').forEach(x => x.addEventListener('click', () => {$('country').value = x.dataset.country;}));
$('previewBtn').addEventListener('click', () => run(true));
$('applyBtn').addEventListener('click', async () => {
  const p = payload();
  if (!p.base_url) return setStatus('请填写 edgetunnel 地址。', 'err');
  if (!p.admin_password) return setStatus('应用到 ADD.txt 需要填写管理员密码。', 'err');
  if (!latestAddTxt) return run(false);
  $('previewBtn').disabled = $('applyBtn').disabled = $('speedtestBtn').disabled = $('proxyExitBtn').disabled = true;
  setStatus('正在写入当前预览结果到 ADD.txt…');
  try {
    await callApi('/api/write_add', {base_url: p.base_url, admin_password: p.admin_password, add_txt: latestAddTxt});
    setStatus('已成功写入当前结果到 edgetunnel /admin/ADD.txt。', 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('previewBtn').disabled = $('applyBtn').disabled = $('speedtestBtn').disabled = $('proxyExitBtn').disabled = false;
  }
});
$('speedtestBtn').addEventListener('click', speedtest);
$('proxyExitBtn').addEventListener('click', proxyExitTest);
$('regionsBtn').addEventListener('click', regions);
$('restoreBtn').addEventListener('click', async () => {
  const p = payload();
  if (!p.base_url) return setStatus('请填写 edgetunnel 地址。', 'err');
  if (!p.admin_password) return setStatus('恢复默认需要管理员密码。', 'err');
  if (!confirm('确认恢复默认 ADD.txt？这会清空当前自定义 IP/出口代理列表，让 edgetunnel 回到默认随机/内置优选逻辑。')) return;
  $('restoreBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = $('speedtestBtn').disabled = $('proxyExitBtn').disabled = true;
  setStatus('正在恢复默认 ADD.txt…');
  try {
    await callApi('/api/restore_default', {base_url: p.base_url, admin_password: p.admin_password});
    latestAddTxt = '';
    outputEl.textContent = '已恢复默认：ADD.txt 已清空，edgetunnel 会回退到默认随机/内置优选逻辑。';
    metaEl.textContent = '';
    setStatus('已恢复默认 ADD.txt。', 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('restoreBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = $('speedtestBtn').disabled = $('proxyExitBtn').disabled = false;
  }
});

$('copyBtn').addEventListener('click', async () => {
  await navigator.clipboard.writeText(outputEl.textContent || '');
  setStatus('已复制结果。', 'ok');
});
</script>
</body>
</html>'''


def json_response(handler: BaseHTTPRequestHandler, status: int, data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "edgetunnel-region-ui/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.address_string()}] {fmt % args}", file=sys.stderr)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8", "replace")
            data = json.loads(raw or "{}")
            if path == "/api/regions":
                self.handle_regions(data)
            elif path == "/api/apply":
                self.handle_apply(data)
            elif path == "/api/speedtest":
                self.handle_speedtest(data)
            elif path == "/api/write_add":
                self.handle_write_add(data)
            elif path == "/api/proxy_exit":
                self.handle_proxy_exit(data)
            elif path == "/api/restore_default":
                self.handle_restore_default(data)
            else:
                json_response(self, 404, {"ok": False, "error": "Not found"})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def handle_regions(self, data: dict) -> None:
        source = (data.get("source") or DEFAULT_SOURCE).strip()
        nodes = parse_source(fetch_text(source))
        regions = available_regions(nodes)
        json_response(self, 200, {"ok": True, "regions": regions, "total": len(nodes)})

    def handle_write_add(self, data: dict) -> None:
        base_url = (data.get("base_url") or "").strip()
        password = data.get("admin_password") or ""
        add_txt = data.get("add_txt") or ""
        if not base_url:
            json_response(self, 400, {"ok": False, "error": "缺少 edgetunnel 地址"})
            return
        if not password:
            json_response(self, 400, {"ok": False, "error": "缺少管理员密码"})
            return
        if not add_txt.strip():
            json_response(self, 400, {"ok": False, "error": "没有可写入的 ADD.txt 内容"})
            return
        post_to_edgetunnel(base_url, password, add_txt)
        json_response(self, 200, {"ok": True})

    def handle_speedtest(self, data: dict) -> None:
        country_raw = (data.get("country") or "").strip()
        limit = int(data.get("limit") or 16)
        candidates = max(1, min(int(data.get("candidates") or 180), 2000))
        concurrency = max(1, min(int(data.get("concurrency") or 32), 100))
        if not country_raw:
            json_response(self, 400, {"ok": False, "error": "缺少国家/地区"})
            return
        country = normalize_country(country_raw)
        matched, all_ok = speedtest_country_nodes(country, candidates=candidates, limit=limit, concurrency=concurrency)
        regions = available_regions(all_ok)
        add_txt = format_add_txt(matched, country) if matched else ""
        json_response(self, 200, {
            "ok": True,
            "country_code": country,
            "count": len(matched),
            "ok_count": len(all_ok),
            "available_regions": regions,
            "add_txt": add_txt,
        })

    def handle_restore_default(self, data: dict) -> None:
        base_url = (data.get("base_url") or "").strip()
        password = data.get("admin_password") or ""
        if not base_url:
            json_response(self, 400, {"ok": False, "error": "缺少 edgetunnel 地址"})
            return
        if not password:
            json_response(self, 400, {"ok": False, "error": "缺少管理员密码"})
            return
        restore_default_add_txt(base_url, password)
        json_response(self, 200, {"ok": True})

    def handle_proxy_exit(self, data: dict) -> None:
        base_url = (data.get("base_url") or "").strip()
        password = data.get("admin_password") or ""
        country_raw = (data.get("country") or "").strip()
        proxy_source = (data.get("proxy_source") or "").strip() or None
        limit = int(data.get("limit") or 16)
        if not base_url:
            json_response(self, 400, {"ok": False, "error": "缺少 edgetunnel 地址"})
            return
        if not password:
            json_response(self, 400, {"ok": False, "error": "缺少管理员密码"})
            return
        if not country_raw:
            json_response(self, 400, {"ok": False, "error": "缺少国家/地区"})
            return
        country = normalize_country(country_raw)
        matched, checked, source_url = proxy_test_country(base_url, password, country, source=proxy_source, limit=3)
        checked_lines = []
        for p in checked:
            status = "OK" if p.get("success") else "FAIL"
            loc = p.get("loc") or "?"
            rt = p.get("responseTime") or "-"
            err = p.get("error") or ""
            checked_lines.append(f"{status} {p.get('type','socks5')}://{p.get('address')} loc={loc} time={rt} {err}")
        add_txt = ""
        best_proxy = ""
        if matched:
            best = matched[0]
            best_proxy = f"{best.get('type','socks5')}://{best.get('address')} loc={best.get('loc')} ip={best.get('ip')} time={best.get('responseTime')}ms"
            entries = top_cf_entry_nodes(limit)
            add_txt = format_proxy_exit_add_txt(entries, best, country)
        json_response(self, 200, {
            "ok": True,
            "country_code": country,
            "count": len(matched),
            "checked_count": len(checked),
            "source": source_url,
            "best_proxy": best_proxy,
            "checked_text": "\n".join(checked_lines),
            "add_txt": add_txt,
        })

    def handle_apply(self, data: dict) -> None:
        base_url = (data.get("base_url") or "").strip()
        password = data.get("admin_password") or ""
        country_raw = (data.get("country") or "").strip()
        source = (data.get("source") or DEFAULT_SOURCE).strip()
        limit = int(data.get("limit") or 16)
        dry_run = bool(data.get("dry_run"))

        if not country_raw:
            json_response(self, 400, {"ok": False, "error": "缺少国家/地区"})
            return
        if not dry_run and not base_url:
            json_response(self, 400, {"ok": False, "error": "缺少 edgetunnel 地址"})
            return
        if not dry_run and not password:
            json_response(self, 400, {"ok": False, "error": "缺少管理员密码"})
            return

        country = normalize_country(country_raw)
        nodes = parse_source(fetch_text(source))
        regions = available_regions(nodes)
        matched, regions, fallback_url = select_country_nodes(nodes, country, limit, source)

        if not matched:
            json_response(self, 400, {
                "ok": False,
                "error": f"数据源里没有 {country_raw} / {country} 的节点。当前可用地区：{', '.join(regions) or '无'}。可以换数据源，或用 CloudflareSpeedTest 跑出列表后提供纯文本 URL。",
                "available_regions": regions,
            })
            return

        add_txt = format_add_txt(matched, country)
        if not dry_run:
            post_to_edgetunnel(base_url, password, add_txt)

        json_response(self, 200, {
            "ok": True,
            "dry_run": dry_run,
            "country_code": country,
            "count": len(matched),
            "available_regions": regions,
            "fallback_url": fallback_url,
            "add_txt": add_txt,
        })


def main() -> int:
    parser = argparse.ArgumentParser(description="edgetunnel 地区 IP 配置 Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"edgetunnel 地区 IP 配置 UI 已启动： http://{args.host}:{args.port}")
    print("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
