#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edgetunnel 按国家/地区自动配置 ADD.txt

用法示例：
  python3 edgetunnel_region_config.py --base-url https://你的域名 --admin-password '你的管理员密码' --country 日本
  python3 edgetunnel_region_config.py --base-url https://你的域名 --admin-password '你的管理员密码' --country US --limit 20
  python3 edgetunnel_region_config.py --base-url https://你的域名 --admin-password '你的管理员密码' --country 英国 --dry-run

说明：
- 默认从 https://zoroaaa.github.io/cf-bestip/ip_candidates.json 拉取候选 Cloudflare 优选 IP。
- 脚本会按 region 过滤，并写入 edgetunnel 后台 /admin/ADD.txt。
- Cloudflare 是 Anycast，所谓地区主要依据数据源里的 region/colo 标记，不等于传统 VPS 固定出口国家。
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import random
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

DEFAULT_SOURCE = "https://zoroaaa.github.io/cf-bestip/ip_candidates.json"
DEFAULT_SOURCE_BASE = "https://zoroaaa.github.io/cf-bestip"

COUNTRY_ALIASES = {
    # Japan
    "日本": "JP", "jp": "JP", "japan": "JP", "日本国": "JP", "东京": "JP", "大阪": "JP",
    # United States
    "美国": "US", "美國": "US", "us": "US", "usa": "US", "united states": "US", "america": "US", "美": "US",
    # United Kingdom
    "英国": "GB", "英國": "GB", "uk": "GB", "gb": "GB", "united kingdom": "GB", "britain": "GB", "england": "GB", "伦敦": "GB",
    # Indonesia
    "印度尼西亚": "ID", "印尼": "ID", "id": "ID", "indonesia": "ID", "雅加达": "ID",
    # India, avoid confusing with Indonesia
    "印度": "IN", "in": "IN", "india": "IN",
    # Common extras present in the default source
    "加拿大": "CA", "ca": "CA", "canada": "CA",
    "香港": "HK", "hk": "HK", "hong kong": "HK",
    "德国": "DE", "de": "DE", "germany": "DE",
    "法国": "FR", "fr": "FR", "france": "FR",
    "意大利": "IT", "it": "IT", "italy": "IT",
    "荷兰": "NL", "nl": "NL", "netherlands": "NL",
    "俄罗斯": "RU", "ru": "RU", "russia": "RU",
    "新加坡": "SG", "sg": "SG", "singapore": "SG",
    "韩国": "KR", "kr": "KR", "korea": "KR",
}

# Cloudflare COLO -> country/region fallback. 只列常用项；数据源有 region 时优先用 region。
CF_IPV4_CIDRS = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
]
CF_TLS_PORTS = [443, 2053, 2083, 2087, 2096, 8443]

COLO_COUNTRY = {
    "NRT": "JP", "KIX": "JP", "FUK": "JP",
    "CGK": "ID",
    "LHR": "GB", "MAN": "GB", "EDI": "GB",
    "LAX": "US", "SJC": "US", "SEA": "US", "ORD": "US", "DFW": "US", "IAD": "US", "EWR": "US", "ATL": "US", "MIA": "US", "JFK": "US", "BOS": "US", "DEN": "US", "PHX": "US",
    "SIN": "SG", "HKG": "HK", "ICN": "KR", "TPE": "TW", "BKK": "TH", "KUL": "MY", "MNL": "PH",
    "FRA": "DE", "MUC": "DE", "CDG": "FR", "AMS": "NL", "MAD": "ES", "ARN": "SE", "MXP": "IT", "FCO": "IT",
}


def normalize_country(value: str) -> str:
    key = value.strip().lower()
    return COUNTRY_ALIASES.get(key, value.strip().upper())


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 edgetunnel-region-config/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_source(text: str) -> list[dict[str, Any]]:
    """支持 JSON nodes / 纯文本 IP 列表。"""
    text = text.strip()
    if not text:
        return []

    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
        if isinstance(data, dict):
            nodes = data.get("nodes") or data.get("data") or data.get("result") or []
        else:
            nodes = data

        parsed: list[dict[str, Any]] = []
        for item in nodes:
            if isinstance(item, str):
                node = parse_ip_line(item)
                if node:
                    parsed.append(node)
                continue
            if not isinstance(item, dict):
                continue
            ip = item.get("ip") or item.get("host") or item.get("address") or item.get("IP地址") or item.get("IP")
            port = item.get("port") or item.get("端口") or 443
            if not ip:
                continue
            colo = str(item.get("colo") or item.get("数据中心") or "").upper()
            region = str(item.get("region") or item.get("country") or item.get("国家") or "").upper()
            if not region and colo:
                region = COLO_COUNTRY.get(colo, "")
            latency = first_number(item.get("latencies") or item.get("latency") or item.get("延迟"))
            score = item.get("score") or item.get("分数")
            parsed.append({
                "ip": str(ip).strip(),
                "port": int(str(port).strip()),
                "region": region,
                "colo": colo,
                "latency": latency,
                "score": score,
            })
        return parsed

    parsed = []
    for line in text.splitlines():
        node = parse_ip_line(line)
        if node:
            parsed.append(node)
    return parsed


def parse_ip_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    before_remark = line.split("#", 1)[0].strip()
    remark = line.split("#", 1)[1].strip() if "#" in line else ""
    if ":" in before_remark and not before_remark.startswith("["):
        ip, port = before_remark.rsplit(":", 1)
    elif before_remark.startswith("[") and "]:" in before_remark:
        ip, port = before_remark.rsplit(":", 1)
        ip = ip.strip("[]")
    else:
        ip, port = before_remark, "443"
    try:
        port_i = int(port)
    except ValueError:
        port_i = 443
    region = ""
    for token in remark.replace("-", " ").replace("_", " ").split():
        code = normalize_country(token)
        if len(code) == 2:
            region = code
            break
    return {"ip": ip.strip(), "port": port_i, "region": region, "colo": "", "latency": None, "score": None}


def first_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, list) and value:
        return first_number(value[0])
    try:
        return float(str(value).replace("ms", "").strip())
    except Exception:
        return None


def available_regions(nodes: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({str(n.get("region") or "").upper() for n in nodes if n.get("region")})


def select_country_nodes(nodes: list[dict[str, Any]], country: str, limit: int, source: str = DEFAULT_SOURCE) -> tuple[list[dict[str, Any]], list[str], str | None]:
    """按国家选择节点；默认 JSON 源缺国家时，自动尝试 ip_XX.txt 兜底。"""
    regions = available_regions(nodes)
    matched = [n for n in nodes if str(n.get("region") or "").upper() == country]
    fallback_url = None

    if not matched and source.rstrip("/") == DEFAULT_SOURCE:
        candidate = f"{DEFAULT_SOURCE_BASE}/ip_{country}.txt"
        try:
            fallback_nodes = parse_source(fetch_text(candidate))
            fallback_matched = [n for n in fallback_nodes if str(n.get("region") or "").upper() == country]
            if fallback_matched:
                matched = fallback_matched
                fallback_url = candidate
                regions = sorted(set(regions + available_regions(fallback_nodes)))
        except Exception:
            pass

    matched.sort(key=lambda n: (-(float(n.get("score") or 0)), float(n.get("latency") or 10**9)))
    return matched[: max(limit, 1)], regions, fallback_url


def random_cf_targets(count: int, ports: list[int] | None = None) -> list[tuple[str, int]]:
    ports = ports or CF_TLS_PORTS
    targets: list[tuple[str, int]] = []
    nets = [ipaddress.ip_network(c) for c in CF_IPV4_CIDRS]
    for _ in range(max(count, 1)):
        net = random.choice(nets)
        # 避免网络地址/广播地址；Cloudflare CIDR 都足够大
        offset = random.randint(1, max(int(net.num_addresses) - 2, 1))
        targets.append((str(net.network_address + offset), random.choice(ports)))
    return targets


def trace_cf_ip(ip: str, port: int, timeout: float = 4.0, host: str = "speed.cloudflare.com") -> dict[str, Any] | None:
    start = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                req = f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {host}\r\nUser-Agent: edgetunnel-region-ui/1.0\r\nConnection: close\r\n\r\n"
                ssock.sendall(req.encode("ascii"))
                data = b""
                while len(data) < 8192:
                    chunk = ssock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
        latency = (time.perf_counter() - start) * 1000
        text = data.decode("utf-8", "replace")
        if "HTTP/1.1 200" not in text and "HTTP/2 200" not in text:
            return None
        body = text.split("\r\n\r\n", 1)[-1]
        trace = {}
        for line in body.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                trace[k.strip()] = v.strip()
        colo = (trace.get("colo") or "").upper()
        loc = (trace.get("loc") or COLO_COUNTRY.get(colo, "")).upper()
        if not colo and not loc:
            return None
        return {"ip": ip, "port": port, "region": loc, "colo": colo, "latency": round(latency, 1), "score": round(1000 / max(latency, 1), 4)}
    except Exception:
        return None


def speedtest_country_nodes(country: str, candidates: int = 120, limit: int = 16, concurrency: int = 24, timeout: float = 4.0, ports: list[int] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """随机生成 CF IP 并用 /cdn-cgi/trace 测试，返回目标国家命中和全部成功结果。"""
    targets = random_cf_targets(candidates, ports)
    ok_nodes: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futures = [ex.submit(trace_cf_ip, ip, port, timeout) for ip, port in targets]
        for fut in as_completed(futures):
            node = fut.result()
            if node:
                ok_nodes.append(node)
    # 去重：同 IP:port 只留最快
    dedup: dict[str, dict[str, Any]] = {}
    for n in ok_nodes:
        key = f"{n['ip']}:{n['port']}"
        if key not in dedup or float(n.get("latency") or 10**9) < float(dedup[key].get("latency") or 10**9):
            dedup[key] = n
    all_ok = sorted(dedup.values(), key=lambda n: float(n.get("latency") or 10**9))
    matched = [n for n in all_ok if str(n.get("region") or "").upper() == country]
    return matched[: max(limit, 1)], all_ok


def format_add_txt(nodes: list[dict[str, Any]], country: str) -> str:
    lines = []
    for i, n in enumerate(nodes, 1):
        ip = str(n["ip"]).strip()
        port = int(n.get("port") or 443)
        colo = str(n.get("colo") or "").upper()
        latency = n.get("latency")
        score = n.get("score")
        remark_parts = [country]
        if colo:
            remark_parts.append(colo)
        if latency is not None:
            remark_parts.append(f"{latency:g}ms")
        if score is not None:
            remark_parts.append(f"score={score}")
        remark = "-".join(remark_parts) + f"-{i}"
        # IPv6 需要 [] 包起来
        host = f"[{ip}]" if ":" in ip and not ip.startswith("[") else ip
        lines.append(f"{host}:{port}#{remark}")
    return "\n".join(lines) + "\n"


def login_edgetunnel(base_url: str, admin_password: str, timeout: int = 20):
    base = base_url.rstrip("/")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    login_data = urllib.parse.urlencode({"password": admin_password}).encode("utf-8")
    login_req = urllib.request.Request(
        base + "/login",
        data=login_data,
        headers={
            "User-Agent": "Mozilla/5.0 edgetunnel-region-config/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json,text/plain,*/*",
        },
        method="POST",
    )
    with opener.open(login_req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        if resp.status >= 400 or '"success"' not in body:
            raise RuntimeError(f"登录失败，HTTP {resp.status}: {body[:200]}")
    return opener


def post_to_edgetunnel(base_url: str, admin_password: str, add_txt: str, timeout: int = 20) -> None:
    base = base_url.rstrip("/")
    opener = login_edgetunnel(base_url, admin_password, timeout)
    add_req = urllib.request.Request(
        base + "/admin/ADD.txt",
        data=add_txt.encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0 edgetunnel-region-config/1.0",
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json,text/plain,*/*",
        },
        method="POST",
    )
    with opener.open(add_req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        if resp.status >= 400 or '"success"' not in body:
            raise RuntimeError(f"保存 ADD.txt 失败，HTTP {resp.status}: {body[:300]}")


def restore_default_add_txt(base_url: str, admin_password: str, timeout: int = 20) -> None:
    # 写入空字符串。edgetunnel 读取 ADD.txt 时使用 `KV.get('ADD.txt') || 'null'`，空值会回退到默认随机/内置 IP 逻辑。
    post_to_edgetunnel(base_url, admin_password, "", timeout=timeout)


def parse_proxy_lines(text: str, default_type: str = "socks5") -> list[dict[str, Any]]:
    proxies: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        remark = line.split("#", 1)[1].strip() if "#" in line else ""
        addr = line.split("#", 1)[0].strip()
        ptype = default_type.lower()
        for prefix in ("socks5://", "http://", "https://"):
            if addr.lower().startswith(prefix):
                ptype = prefix[:-3]
                addr = addr[len(prefix):]
                break
        if ":" not in addr:
            continue
        host, port = addr.rsplit(":", 1)
        try:
            port_i = int(port)
        except ValueError:
            continue
        proxies.append({"type": ptype, "host": host.strip(), "port": port_i, "remark": remark, "address": f"{host.strip()}:{port_i}"})
    return proxies


def default_proxy_source(country: str) -> str:
    return f"{DEFAULT_SOURCE_BASE}/proxy_{country}.txt"


def check_edgetunnel_proxy(base_url: str, admin_password: str, proxy: dict[str, Any], timeout: int = 25) -> dict[str, Any]:
    base = base_url.rstrip("/")
    opener = login_edgetunnel(base_url, admin_password, timeout)
    ptype = proxy.get("type") or "socks5"
    address = proxy.get("address") or f"{proxy['host']}:{proxy['port']}"
    qs = urllib.parse.urlencode({ptype: address})
    req = urllib.request.Request(
        base + f"/admin/check?{qs}",
        headers={"User-Agent": "Mozilla/5.0 edgetunnel-region-config/1.0", "Accept": "application/json,text/plain,*/*"},
    )
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except Exception:
            raise RuntimeError(f"代理检查响应不是 JSON: {body[:200]}")
    return {**proxy, **data}


def proxy_test_country(base_url: str, admin_password: str, country: str, source: str | None = None, limit: int = 3, timeout: int = 25) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    source_url = source or default_proxy_source(country)
    proxies = parse_proxy_lines(fetch_text(source_url), "socks5")
    if not proxies:
        return [], [], source_url
    checked: list[dict[str, Any]] = []
    # 串行检查：避免短时间打爆 Worker，也避免免费代理源被并发压垮。
    for proxy in proxies:
        try:
            res = check_edgetunnel_proxy(base_url, admin_password, proxy, timeout=timeout)
        except Exception as e:
            res = {**proxy, "success": False, "error": str(e)}
        checked.append(res)
    matched = [p for p in checked if p.get("success") and str(p.get("loc") or "").upper() == country]
    matched.sort(key=lambda p: float(p.get("responseTime") or 10**9))
    return matched[: max(limit, 1)], checked, source_url


def top_cf_entry_nodes(limit: int = 16) -> list[dict[str, Any]]:
    try:
        nodes = parse_source(fetch_text(DEFAULT_SOURCE))
    except Exception:
        nodes = []
    if not nodes:
        nodes = [{"ip": ip, "port": port, "region": "CF", "colo": "", "latency": None, "score": None} for ip, port in random_cf_targets(limit)]
    nodes.sort(key=lambda n: (-(float(n.get("score") or 0)), float(n.get("latency") or 10**9)))
    return nodes[: max(limit, 1)]


def format_proxy_exit_add_txt(entry_nodes: list[dict[str, Any]], proxy: dict[str, Any], country: str) -> str:
    ptype = proxy.get("type") or "socks5"
    address = proxy.get("address") or f"{proxy['host']}:{proxy['port']}"
    response_time = proxy.get("responseTime")
    proxy_ip = proxy.get("ip") or ""
    proxy_loc = proxy.get("loc") or country
    lines = []
    for i, n in enumerate(entry_nodes, 1):
        ip = str(n["ip"]).strip()
        port = int(n.get("port") or 443)
        host = f"[{ip}]" if ":" in ip and not ip.startswith("[") else ip
        rt = f"-{response_time}ms" if response_time is not None else ""
        out = f"-{proxy_ip}" if proxy_ip else ""
        remark = f"EXIT-{proxy_loc}{rt}{out}-{i} ${ptype}://{address}"
        lines.append(f"{host}:{port}#{remark}")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="按国家/地区自动配置 edgetunnel /admin/ADD.txt")
    p.add_argument("--base-url", "-u", required=True, help="edgetunnel 地址，例如 https://edt.example.com")
    p.add_argument("--admin-password", "-p", help="管理员密码；不传则交互输入")
    p.add_argument("--country", "-c", required=True, help="国家/地区，例如 日本、美国、印尼、英国、JP、US、ID、UK")
    p.add_argument("--source", "-s", default=DEFAULT_SOURCE, help=f"IP 数据源 URL，默认 {DEFAULT_SOURCE}")
    p.add_argument("--limit", "-n", type=int, default=16, help="写入数量，默认 16")
    p.add_argument("--dry-run", action="store_true", help="只打印将写入的 ADD.txt，不提交")
    args = p.parse_args()

    country = normalize_country(args.country)
    password = args.admin_password or getpass.getpass("edgetunnel 管理员密码: ")

    print(f"[*] 拉取 IP 数据源: {args.source}", file=sys.stderr)
    nodes = parse_source(fetch_text(args.source))
    if not nodes:
        print("[!] 数据源没有解析到任何节点", file=sys.stderr)
        return 2

    matched, regions, fallback_url = select_country_nodes(nodes, country, args.limit, args.source)

    if fallback_url:
        print(f"[*] 默认 JSON 未命中，已自动使用兜底源: {fallback_url}", file=sys.stderr)

    if not matched:
        print(f"[!] 数据源里没有 {args.country} / {country} 的节点。", file=sys.stderr)
        print(f"    当前可用地区: {', '.join(regions) or '无'}", file=sys.stderr)
        print("    你可以换一个 --source，或先用 CloudflareSpeedTest 跑出该地区列表后提供纯文本 URL。", file=sys.stderr)
        return 3

    add_txt = format_add_txt(matched, country)
    print(add_txt)

    if args.dry_run:
        print("[*] dry-run：未提交到 edgetunnel。", file=sys.stderr)
        return 0

    print(f"[*] 正在提交到 {args.base_url.rstrip('/')}/admin/ADD.txt", file=sys.stderr)
    post_to_edgetunnel(args.base_url, password, add_txt)
    print(f"[OK] 已写入 {len(matched)} 条 {args.country} / {country} 节点到 ADD.txt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
