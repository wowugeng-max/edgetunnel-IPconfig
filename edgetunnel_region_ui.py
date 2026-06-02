#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edgetunnel 地区 IP 配置 Web UI

启动：
  cd /Users/ruiyaosong/edgetunnel-IPconfig
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
    format_multi_country_proxy_exit_add_txt,
    load_add_records,
    load_country_presets,
    normalize_country,
    parse_countries,
    parse_source,
    post_to_edgetunnel,
    proxy_pool_summary,
    proxy_test_countries,
    scan_entry_nodes,
    select_country_nodes,
    save_add_record,
    save_custom_country_preset,
    top_cf_entry_nodes,
    delete_add_record,
    restore_default_add_txt,
    validate_country_preset,
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
    .workspace-grid { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(360px, .92fr); gap: 18px; align-items: start; }
    .control-stack, .results-stack { display: grid; gap: 18px; }
    .control-stack .section, .results-stack .section { margin-bottom: 0; }
    .record-grid { display: grid; grid-template-columns: minmax(260px, .78fr) minmax(320px, 1.22fr); gap: 18px; align-items: start; }
    .record-editor textarea { min-height: 260px; resize: vertical; }
    .write-section .actions { margin-top: 14px; }
    @media (max-width: 900px) {
      .workspace-grid, .record-grid { grid-template-columns: 1fr; }
      body { padding: 16px; }
    }
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
    .country-add { display: grid; grid-template-columns: 1fr 80px 1fr auto; gap: 10px; align-items: end; margin-top: 12px; }
    @media (max-width: 860px) { .country-add { grid-template-columns: 1fr; } }
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
    .output-card pre { min-height: 500px; }
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
          <label>国家/地区（可多选）</label>
          <input id="country" placeholder="例如：US, JP, SG, HK, GB / 日本 美国 新加坡" value="美国" />
        </div>
        <div>
          <label>生成节点数量</label>
          <input id="limit" type="number" min="1" max="200" value="16" />
        </div>
      </div>
      <div class="quick" id="countryChips">
        <span class="chip" data-country="日本" data-colos="NRT,KIX,FUK">日本</span>
        <span class="chip" data-country="美国" data-colos="LAX,SJC,SEA,ORD,DFW,IAD,EWR">美国</span>
        <span class="chip" data-country="印尼" data-colos="CGK">印尼</span>
        <span class="chip" data-country="英国" data-colos="LHR,MAN,EDI">英国</span>
        <span class="chip" data-country="香港" data-colos="HKG">香港</span>
        <span class="chip" data-country="新加坡" data-colos="SIN">新加坡</span>
        <span class="chip" data-country="韩国" data-colos="ICN">韩国</span>
        <span class="chip" data-country="德国" data-colos="FRA,MUC">德国</span>
        <span class="chip" data-country="法国" data-colos="CDG">法国</span>
      </div>
      <div class="country-add">
        <div>
          <label>添加国家名称</label>
          <input id="addCountryLabel" placeholder="例如：越南" />
        </div>
        <div>
          <label>代码</label>
          <input id="addCountryCode" placeholder="VN" maxlength="2" />
        </div>
        <div>
          <label>入口 Colo（可选）</label>
          <input id="addCountryColos" placeholder="例如：SGN,HAN" />
        </div>
        <button class="ghost" id="addCountryBtn">添加国家</button>
      </div>
      <div class="hint">国家代码必须是 2 位字母；Colo 用逗号分隔，格式为 3-8 位字母/数字。自定义国家会保存到本地 JSON 文件。</div>
    </div>

    <div class="workspace-grid">
      <div class="control-stack">
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
          <div class="row">
            <div>
              <label>目标入口 Colo</label>
              <input id="entryColos" placeholder="例如：NRT,KIX,FUK；留空则只按国家筛选" />
            </div>
            <div>
              <label>超时秒数</label>
              <input id="entryTimeout" type="number" min="1" max="15" value="4" />
            </div>
          </div>
          <div class="hint">本地测速会随机生成 Cloudflare IP，连接 <code>/cdn-cgi/trace</code> 判断 colo/国家。入口按当前网络环境实测，换办公室后结果可能不同。</div>
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
          <input id="proxySource" placeholder="留空/auto 则使用多个公开免费源；也可填逗号分隔自定义 URL" />
          <label>排除出口代理</label>
          <input id="proxyExclude" placeholder="例如：103.142.255.32 或 103.119.60.219:1080，逗号分隔" />
          <div class="row">
            <div>
              <label>最多验证候选</label>
              <input id="validateLimit" type="number" min="1" max="500" value="30" />
            </div>
            <div>
              <label>缓存秒数</label>
              <input id="cacheTtl" type="number" min="0" max="3600" value="900" />
            </div>
          </div>
          <div class="row">
            <div>
              <label>单个代理超时秒数</label>
              <input id="proxyTimeout" type="number" min="1" max="30" value="8" />
            </div>
            <div>
              <label>验证并发</label>
              <input id="validateConcurrency" type="number" min="1" max="20" value="8" />
            </div>
          </div>
          <div class="hint">出口代理测速会调用你的 edgetunnel <code>/admin/check?socks5=...</code>，验证代理出口国家；免费代理只作为候选，实测通过才会写入。</div>
          <div class="actions">
            <button class="ghost" id="proxyExitBtn">出口：代理测速生成</button>
            <button class="ghost" id="nodePoolBtn">查看节点池</button>
          </div>
        </div>
      </div>

      <div class="results-stack">
        <div class="card output-card">
          <label style="margin-top:0">生成结果 / 日志</label>
          <pre id="output">尚未生成。</pre>
          <div class="mini" id="meta"></div>
        </div>

        <div class="section write-section">
          <h2>写入 / 恢复</h2>
          <div class="section-desc">只处理右侧当前结果。保存历史快照请使用下方“扫描记录”。</div>
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
    </div>

    <div class="section records-section" id="scanRecordsSection">
      <h2>扫描记录</h2>
      <div class="section-desc">把入口或出口扫描结果保存成快照；以后可以直接加载到当前结果，再写入 ADD.txt。</div>
      <div class="record-grid">
        <div>
          <label>保存记录名称</label>
          <input id="recordName" placeholder="例如：JP 入口 NRT 2026-06-02 / 印尼出口可用 1" />
          <div class="actions">
            <button class="ghost" id="saveRecordBtn">保存当前结果</button>
            <button class="ghost" id="loadRecordsBtn">刷新记录</button>
          </div>
          <label>已保存记录</label>
          <select id="recordsList"></select>
          <div class="actions">
            <button class="ghost" id="loadRecordBtn">加载到当前结果</button>
            <button class="ghost" id="updateRecordBtn">保存编辑</button>
            <button class="ghost" id="deleteRecordBtn">删除记录</button>
          </div>
        </div>
        <div class="record-editor">
          <label>记录内容编辑</label>
          <textarea id="recordEditor" rows="8" placeholder="选择记录后可编辑 ADD.txt 内容；每行需是 ip:port#备注，可带 $socks5://..."></textarea>
          <div class="hint">记录保存到本地 <code>edgetunnel_add_records.json</code>，只保存 ADD.txt 内容和元数据，不保存 edgetunnel 地址或管理员密码。加载记录后可直接写入 ADD.txt，无需重新扫描。</div>
        </div>
      </div>
    </div>
  </div>

<script>
const $ = id => document.getElementById(id);
const statusEl = $('status');
const outputEl = $('output');
const metaEl = $('meta');
let latestAddTxt = '';
let latestMode = '';
let lastAutoEntryColos = '';
let savedRecords = [];

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
    entry_colos: $('entryColos').value.trim(),
    entry_timeout: Number($('entryTimeout').value || 4),
    proxy_source: $('proxySource').value.trim(),
    proxy_exclude: $('proxyExclude').value.trim(),
    validate_limit: Number($('validateLimit').value || 30),
    proxy_timeout: Number($('proxyTimeout').value || 8),
    validate_concurrency: Number($('validateConcurrency').value || 8),
    cache_ttl: Number($('cacheTtl').value || 900),
  };
}
function setLatest(addTxt, mode) {
  latestAddTxt = addTxt || '';
  latestMode = latestAddTxt ? mode : '';
}
function recordModeForApi() {
  if (latestMode.includes('出口')) return 'exit';
  if (latestMode.includes('入口')) return 'entry';
  return 'custom';
}
function recordModeLabel(mode) {
  return {entry: '入口', exit: '出口', both: '入口+出口', custom: '自定义'}[mode] || mode || '未知';
}
function formatTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString();
}
function selectedRecord() {
  const name = $('recordsList').value;
  return savedRecords.find(item => item.name === name) || null;
}
function formatMap(obj) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return '无';
  return entries.map(([k, v]) => `${k}:${v}`).join(', ');
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
function bindCountryChip(chip) {
  chip.addEventListener('click', () => {
    $('country').value = chip.dataset.country;
    const currentColos = $('entryColos').value.trim();
    if (!currentColos || currentColos === lastAutoEntryColos) {
      $('entryColos').value = chip.dataset.colos || '';
      lastAutoEntryColos = $('entryColos').value.trim();
    }
  });
}
function renderCountryChips(items) {
  const box = $('countryChips');
  box.innerHTML = '';
  (items || []).forEach(item => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.dataset.country = item.code;
    chip.dataset.colos = (item.colos || []).join(',');
    chip.textContent = item.custom ? `${item.label} (${item.code})` : item.label;
    bindCountryChip(chip);
    box.appendChild(chip);
  });
}
async function loadCountries() {
  try {
    const data = await callApi('/api/countries', {});
    renderCountryChips(data.countries || []);
  } catch (e) {
    setStatus(`读取国家配置失败：${e.message}`, 'warn');
    document.querySelectorAll('.chip').forEach(bindCountryChip);
  }
}
async function addCountry() {
  const label = $('addCountryLabel').value.trim();
  const code = $('addCountryCode').value.trim();
  const colos = $('addCountryColos').value.trim();
  try {
    const data = await callApi('/api/countries/add', {label, code, colos});
    renderCountryChips(data.countries || []);
    $('country').value = data.country.code;
    $('entryColos').value = (data.country.colos || []).join(',');
    lastAutoEntryColos = $('entryColos').value.trim();
    $('addCountryLabel').value = '';
    $('addCountryCode').value = '';
    $('addCountryColos').value = '';
    setStatus(`已添加国家：${data.country.label} (${data.country.code})`, 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  }
}
function renderRecords(records) {
  savedRecords = records || [];
  const list = $('recordsList');
  const selected = list.value;
  list.innerHTML = '';
  if (!savedRecords.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '暂无保存记录';
    list.appendChild(option);
    $('recordEditor').value = '';
    return;
  }
  savedRecords.forEach(item => {
    const option = document.createElement('option');
    option.value = item.name;
    option.textContent = `${item.name} · ${recordModeLabel(item.mode)} · ${item.line_count || 0} 行 · ${formatTime(item.updated_at)}`;
    list.appendChild(option);
  });
  if (selected && savedRecords.some(item => item.name === selected)) {
    list.value = selected;
  }
  showSelectedRecord();
}
async function loadRecords(silent=false) {
  try {
    const data = await callApi('/api/records', {});
    renderRecords(data.records || []);
    if (!silent) setStatus(`已读取 ${savedRecords.length} 条保存记录。`, 'ok');
  } catch (e) {
    setStatus(`读取保存记录失败：${e.message}`, 'err');
  }
}
function showSelectedRecord() {
  const record = selectedRecord();
  if (!record) {
    $('recordName').value = '';
    $('recordEditor').value = '';
    return;
  }
  $('recordName').value = record.name;
  $('recordEditor').value = record.add_txt || '';
}
async function saveCurrentRecord() {
  const name = $('recordName').value.trim();
  if (!latestAddTxt) return setStatus('没有可保存的当前结果。请先生成入口 IP 或出口代理。', 'err');
  try {
    const data = await callApi('/api/records/save', {
      name,
      mode: recordModeForApi(),
      countries: payload().country,
      add_txt: latestAddTxt,
    });
    renderRecords(data.records || []);
    $('recordsList').value = data.record.name;
    showSelectedRecord();
    setStatus(`已保存记录：${data.record.name}`, 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  }
}
async function updateSelectedRecord() {
  const record = selectedRecord();
  const name = $('recordName').value.trim();
  const addTxt = $('recordEditor').value.trim();
  if (!record && !name) return setStatus('请选择记录或填写记录名称。', 'err');
  try {
    let data = await callApi('/api/records/save', {
      name: name || record.name,
      mode: record ? record.mode : recordModeForApi(),
      countries: record ? record.countries : payload().country,
      add_txt: addTxt,
    });
    if (record && name && name !== record.name) {
      data = await callApi('/api/records/delete', {name: record.name});
      await loadRecords(true);
    } else {
      renderRecords(data.records || []);
    }
    $('recordsList').value = name || (record && record.name) || '';
    showSelectedRecord();
    setStatus(`已更新记录：${name || (record && record.name)}`, 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  }
}
function loadSelectedRecordToCurrent() {
  const record = selectedRecord();
  if (!record) return setStatus('请选择要加载的记录。', 'err');
  setLatest(record.add_txt, recordModeLabel(record.mode));
  outputEl.textContent = latestAddTxt;
  metaEl.textContent = `已加载记录：${record.name} ｜ 模式：${recordModeLabel(record.mode)} ｜ 国家：${(record.countries || []).join(', ') || '未标注'} ｜ 行数：${record.line_count}`;
  setStatus('已加载保存记录到当前结果。可以直接「应用当前结果到 ADD.txt」。', 'ok');
}
async function deleteSelectedRecord() {
  const record = selectedRecord();
  if (!record) return setStatus('请选择要删除的记录。', 'err');
  if (!confirm(`确认删除记录「${record.name}」？`)) return;
  try {
    const data = await callApi('/api/records/delete', {name: record.name});
    renderRecords(data.records || []);
    setStatus(`已删除记录：${record.name}`, 'ok');
  } catch (e) {
    setStatus(e.message, 'err');
  }
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
    setLatest(data.add_txt, '入口 IP');
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
    setLatest(data.add_txt, '入口本地测速');
    const reportText = `入口扫描报告
目标国家：${data.report.target_countries.join(', ') || data.country_code}
目标 Colo：${data.report.target_colos.join(', ') || '未指定'}
成功连接：${data.report.ok_count}
命中数量：${data.report.match_count}
返回数量：${data.report.returned_count}
成功地区：${formatMap(data.report.regions)}
成功 Colo：${formatMap(data.report.colos)}

${latestAddTxt || '(没有命中目标入口)'}`;
    outputEl.textContent = reportText;
    metaEl.textContent = `国家代码：${data.country_code} ｜ 命中：${data.count} 条 ｜ 成功连接：${data.report.ok_count} 条 ｜ 目标 Colo：${data.report.target_colos.join(', ') || '未指定'}`;
    setStatus(data.count ? '入口扫描完成。确认无误后可以点「应用当前结果到 ADD.txt」。' : '当前网络环境没有测到目标入口。可增加候选数量、指定 NRT/KIX/FUK 等 Colo、换端口/网络；这不是出口国家问题。', data.count ? 'ok' : 'warn');
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
    setLatest(data.add_txt, data.multi_country ? '多国家出口代理' : '出口代理');
    outputEl.textContent = latestAddTxt || (data.checked_text || '(没有可用代理或没有命中目标国家)');
    metaEl.textContent = `模式：${latestMode || '未生成'} ｜ 国家：${data.country_codes.join(', ')} ｜ 命中代理：${data.count} 条 ｜ 已检查：${data.checked_count} 条 ｜ 候选：${data.candidate_count} 条`;
    setStatus(data.count ? `出口代理测速完成，已轮换可用代理生成 ADD.txt。\n${data.summary_text}` : `未找到可用出口代理。可换代理源 URL 或自备 SOCKS5。`, data.count ? 'ok' : 'warn');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('proxyExitBtn').disabled = $('speedtestBtn').disabled = $('previewBtn').disabled = $('applyBtn').disabled = false;
  }
}

async function nodePool() {
  const p = payload();
  if (!p.base_url) return setStatus('查看节点池需要填写 edgetunnel 地址。', 'err');
  if (!p.admin_password) return setStatus('查看节点池需要管理员密码，用于调用 /admin/check。', 'err');
  if (!p.country) return setStatus('请填写国家/地区。', 'err');
  $('nodePoolBtn').disabled = $('proxyExitBtn').disabled = $('applyBtn').disabled = true;
  setStatus(`正在验证节点池：${p.country}…\n候选 ${p.validate_limit} 个，并发 ${p.validate_concurrency}，单个超时 ${p.proxy_timeout} 秒。`, 'warn');
  try {
    const data = await callApi('/api/proxy_pool', p);
    setLatest('', '');
    outputEl.textContent = data.pool_text || '(没有候选)';
    metaEl.textContent = `国家：${data.country_codes.join(', ')} ｜ 已检查：${data.checked_count} 条 ｜ 候选：${data.candidate_count} 条`;
    setStatus('节点池验证完成。需要写入时请使用「出口：代理测速生成」。', data.count ? 'ok' : 'warn');
  } catch (e) {
    setStatus(e.message, 'err');
  } finally {
    $('nodePoolBtn').disabled = $('proxyExitBtn').disabled = $('applyBtn').disabled = false;
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

document.querySelectorAll('.chip').forEach(bindCountryChip);
$('previewBtn').addEventListener('click', () => run(true));
$('addCountryBtn').addEventListener('click', addCountry);
$('recordsList').addEventListener('change', showSelectedRecord);
$('saveRecordBtn').addEventListener('click', saveCurrentRecord);
$('loadRecordsBtn').addEventListener('click', () => loadRecords(false));
$('loadRecordBtn').addEventListener('click', loadSelectedRecordToCurrent);
$('updateRecordBtn').addEventListener('click', updateSelectedRecord);
$('deleteRecordBtn').addEventListener('click', deleteSelectedRecord);
$('applyBtn').addEventListener('click', async () => {
  const p = payload();
  if (!p.base_url) return setStatus('请填写 edgetunnel 地址。', 'err');
  if (!p.admin_password) return setStatus('应用到 ADD.txt 需要填写管理员密码。', 'err');
  if (!latestAddTxt) return setStatus('没有可写入的当前结果。请先生成入口 IP 或出口代理预览。', 'err');
  $('previewBtn').disabled = $('applyBtn').disabled = $('speedtestBtn').disabled = $('proxyExitBtn').disabled = true;
  setStatus(`正在写入当前结果到 ADD.txt…\n模式：${latestMode}`);
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
$('nodePoolBtn').addEventListener('click', nodePool);
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
    setLatest('', '');
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
loadCountries();
loadRecords(true);
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
            elif path == "/api/countries":
                self.handle_countries(data)
            elif path == "/api/countries/add":
                self.handle_country_add(data)
            elif path == "/api/records":
                self.handle_records(data)
            elif path == "/api/records/save":
                self.handle_record_save(data)
            elif path == "/api/records/delete":
                self.handle_record_delete(data)
            elif path == "/api/apply":
                self.handle_apply(data)
            elif path == "/api/speedtest":
                self.handle_speedtest(data)
            elif path == "/api/write_add":
                self.handle_write_add(data)
            elif path == "/api/proxy_exit":
                self.handle_proxy_exit(data)
            elif path == "/api/proxy_pool":
                self.handle_proxy_pool(data)
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

    def handle_countries(self, data: dict) -> None:
        json_response(self, 200, {"ok": True, "countries": load_country_presets()})

    def handle_country_add(self, data: dict) -> None:
        try:
            country = validate_country_preset(data.get("label") or "", data.get("code") or "", data.get("colos") or "")
            save_custom_country_preset(country)
            json_response(self, 200, {"ok": True, "country": country, "countries": load_country_presets()})
        except ValueError as e:
            json_response(self, 400, {"ok": False, "error": str(e)})

    def handle_records(self, data: dict) -> None:
        json_response(self, 200, {"ok": True, "records": load_add_records()})

    def handle_record_save(self, data: dict) -> None:
        try:
            payload = save_add_record({
                "name": data.get("name") or "",
                "mode": data.get("mode") or "custom",
                "countries": data.get("countries") or [],
                "add_txt": data.get("add_txt") or "",
            })
            record = next((r for r in payload["records"] if r["name"] == str(data.get("name") or "").strip()), None)
            json_response(self, 200, {"ok": True, "record": record, "records": payload["records"]})
        except ValueError as e:
            json_response(self, 400, {"ok": False, "error": str(e)})

    def handle_record_delete(self, data: dict) -> None:
        try:
            payload = delete_add_record(data.get("name") or "")
            json_response(self, 200, {"ok": True, "records": payload["records"]})
        except ValueError as e:
            json_response(self, 400, {"ok": False, "error": str(e)})

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
        entry_colos = (data.get("entry_colos") or "").strip()
        entry_timeout = max(1.0, min(float(data.get("entry_timeout") or 4), 15.0))
        if not country_raw:
            json_response(self, 400, {"ok": False, "error": "缺少国家/地区"})
            return
        country = normalize_country(country_raw)
        matched, report, add_txt = scan_entry_nodes(
            country,
            colos=entry_colos,
            candidates=candidates,
            limit=limit,
            concurrency=concurrency,
            timeout=entry_timeout,
        )
        json_response(self, 200, {
            "ok": True,
            "country_code": country,
            "count": len(matched),
            "ok_count": report["ok_count"],
            "available_regions": sorted(report["regions"]),
            "report": report,
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
        self._handle_proxy_pool(data, generate_add=True)

    def handle_proxy_pool(self, data: dict) -> None:
        self._handle_proxy_pool(data, generate_add=False)

    def _handle_proxy_pool(self, data: dict, generate_add: bool) -> None:
        base_url = (data.get("base_url") or "").strip()
        password = data.get("admin_password") or ""
        country_raw = (data.get("country") or "").strip()
        proxy_source = (data.get("proxy_source") or "").strip() or "auto"
        proxy_exclude = (data.get("proxy_exclude") or "").strip()
        limit = int(data.get("limit") or 16)
        validate_limit = max(1, min(int(data.get("validate_limit") or 30), 500))
        proxy_timeout = max(1, min(int(data.get("proxy_timeout") or 8), 30))
        validate_concurrency = max(1, min(int(data.get("validate_concurrency") or 8), 20))
        cache_ttl = max(0, min(int(data.get("cache_ttl") or 900), 3600))
        if not base_url:
            json_response(self, 400, {"ok": False, "error": "缺少 edgetunnel 地址"})
            return
        if not password:
            json_response(self, 400, {"ok": False, "error": "缺少管理员密码"})
            return
        if not country_raw:
            json_response(self, 400, {"ok": False, "error": "缺少国家/地区"})
            return
        countries = parse_countries(country_raw)
        if not countries:
            json_response(self, 400, {"ok": False, "error": "国家/地区格式无效"})
            return
        matched_by_country, checked, source_urls, candidates = proxy_test_countries(
            base_url,
            password,
            countries,
            sources=proxy_source,
            limit_per_country=min(max(limit, 1), 8),
            validate_limit=validate_limit,
            timeout=proxy_timeout,
            validate_concurrency=validate_concurrency,
            exclude=proxy_exclude,
            cache_ttl=cache_ttl,
        )
        summary = proxy_pool_summary(countries, candidates, checked, matched_by_country)
        checked_lines = []
        for p in checked:
            status = "OK" if p.get("success") else "FAIL"
            loc = p.get("loc") or "?"
            rt = p.get("responseTime") or "-"
            err = p.get("error") or ""
            checked_lines.append(f"{status} {p.get('type','socks5')}://{p.get('address')} loc={loc} time={rt} {err}")
        summary_lines = []
        for row in summary:
            protocols = ", ".join(f"{k}:{v}" for k, v in sorted(row["protocols"].items())) or "-"
            best = row["best_proxy"] or "-"
            summary_lines.append(
                f"{row['country']} 候选={row['candidates']} 已检={row['checked']} 命中={row['matched']} 协议={protocols} 最快={best} {row['best_time'] or '-'}ms"
            )
        add_txt = ""
        if generate_add and any(matched_by_country.values()):
            entries = top_cf_entry_nodes(limit)
            add_txt = format_multi_country_proxy_exit_add_txt(entries, matched_by_country, per_country_limit=min(max(limit, 1), 8))
        pool_text = "\n".join(summary_lines + ["", "检查明细:"] + checked_lines).strip()
        json_response(self, 200, {
            "ok": True,
            "country_codes": countries,
            "multi_country": len(countries) > 1,
            "count": sum(len(v) for v in matched_by_country.values()),
            "checked_count": len(checked),
            "candidate_count": len(candidates),
            "proxy_exclude": proxy_exclude,
            "proxy_timeout": proxy_timeout,
            "validate_concurrency": validate_concurrency,
            "sources": source_urls,
            "summary": summary,
            "summary_text": "\n".join(summary_lines),
            "pool_text": pool_text,
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
