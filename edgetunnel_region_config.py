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
import csv
import getpass
import io
import ipaddress
import json
import random
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SOURCE = "https://zoroaaa.github.io/cf-bestip/ip_candidates.json"
DEFAULT_SOURCE_BASE = "https://zoroaaa.github.io/cf-bestip"
DEFAULT_CACHE_TTL_SECONDS = 15 * 60
COUNTRY_PRESETS_FILE = Path(__file__).with_name("edgetunnel_countries.json")
ADD_RECORDS_FILE = Path(__file__).with_name("edgetunnel_add_records.json")
PROXY_TYPE_PRIORITY = {"socks5": 0, "http": 1, "https": 2}

AUTO_PROXY_SOURCE_TEMPLATES = [
    {
        "name": "cf-bestip-country",
        "url": DEFAULT_SOURCE_BASE + "/proxy_{country}.txt",
        "format": "txt",
    },
    {
        "name": "proxifly-all-json",
        "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.json",
        "format": "json",
    },
    {
        "name": "proxifly-socks5-json",
        "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.json",
        "format": "json",
    },
    {
        "name": "proxifly-country",
        "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/{country}/data.txt",
        "format": "txt",
    },
    {
        "name": "iplocate-all",
        "url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/all-proxies.txt",
        "format": "txt",
    },
    {
        "name": "iplocate-socks5",
        "url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks5.txt",
        "format": "txt",
    },
    {
        "name": "iplocate-country",
        "url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/countries/{country}/proxies.txt",
        "format": "txt",
    },
    {
        "name": "proxyradar-socks5",
        "url": "https://proxyradar.net/proxies/socks5.txt",
        "format": "txt",
    },
    {
        "name": "stormsia-socks5",
        "url": "https://stormsia.github.io/proxy-list/socks5.txt",
        "format": "txt",
    },
]

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

BUILTIN_COUNTRY_PRESETS = [
    {"label": "日本", "code": "JP", "colos": ["NRT", "KIX", "FUK"], "custom": False},
    {"label": "美国", "code": "US", "colos": ["LAX", "SJC", "SEA", "ORD", "DFW", "IAD", "EWR"], "custom": False},
    {"label": "印尼", "code": "ID", "colos": ["CGK"], "custom": False},
    {"label": "英国", "code": "GB", "colos": ["LHR", "MAN", "EDI"], "custom": False},
    {"label": "香港", "code": "HK", "colos": ["HKG"], "custom": False},
    {"label": "新加坡", "code": "SG", "colos": ["SIN"], "custom": False},
    {"label": "韩国", "code": "KR", "colos": ["ICN"], "custom": False},
    {"label": "德国", "code": "DE", "colos": ["FRA", "MUC"], "custom": False},
    {"label": "法国", "code": "FR", "colos": ["CDG"], "custom": False},
]


def normalize_country(value: str) -> str:
    key = value.strip().lower()
    alias = COUNTRY_ALIASES.get(key)
    if alias:
        return alias
    if len(value.strip()) != 2:
        try:
            for item in load_country_presets():
                if key in (str(item.get("label") or "").lower(), str(item.get("code") or "").lower()):
                    return str(item["code"]).upper()
        except Exception:
            pass
    return value.strip().upper()


def parse_countries(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        raw_parts = re.split(r"[\s,;|，、]+", value.strip())
    else:
        raw_parts = [str(x) for x in value]
    countries: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        if not part.strip():
            continue
        code = normalize_country(part)
        if code and code not in seen:
            countries.append(code)
            seen.add(code)
    return countries


def _split_country_colos(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw_parts = re.split(r"[\s,;|，、]+", value.strip())
    else:
        raw_parts = [str(x) for x in value]
    colos: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        colo = part.strip().upper()
        if not colo:
            continue
        if not re.fullmatch(r"[A-Z0-9]{3,8}", colo):
            raise ValueError("Colo 必须是 3-8 位字母/数字，例如 NRT,KIX,FUK")
        if colo not in seen:
            colos.append(colo)
            seen.add(colo)
    return colos


def validate_country_preset(label: str, code: str, colos: str | Iterable[str] | None = None) -> dict[str, Any]:
    clean_label = str(label or "").strip()
    clean_code = str(code or "").strip().upper()
    if not clean_label:
        raise ValueError("国家名称不能为空")
    if len(clean_label) > 32:
        raise ValueError("国家名称不能超过 32 个字符")
    if not re.fullmatch(r"[A-Z]{2}", clean_code):
        raise ValueError("国家代码必须是 2 位字母，例如 JP、US、ID")
    return {"label": clean_label, "code": clean_code, "colos": _split_country_colos(colos), "custom": True}


def _read_custom_country_data(path: str | Path = COUNTRY_PRESETS_FILE) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"custom": []}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"国家配置文件格式错误: {e}") from e
    if isinstance(data, list):
        return {"custom": data}
    if isinstance(data, dict) and isinstance(data.get("custom"), list):
        return data
    raise ValueError("国家配置文件必须是 JSON 对象，且包含 custom 数组")


def _write_custom_country_data(data: dict[str, Any], path: str | Path = COUNTRY_PRESETS_FILE) -> None:
    file_path = Path(path)
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_country_presets(path: str | Path = COUNTRY_PRESETS_FILE) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {item["code"]: dict(item) for item in BUILTIN_COUNTRY_PRESETS}
    data = _read_custom_country_data(path)
    for raw in data.get("custom", []):
        if not isinstance(raw, dict):
            continue
        item = validate_country_preset(raw.get("label", ""), raw.get("code", ""), raw.get("colos", []))
        merged[item["code"]] = item
    return list(merged.values())


def save_custom_country_preset(entry: dict[str, Any], path: str | Path = COUNTRY_PRESETS_FILE) -> dict[str, Any]:
    item = validate_country_preset(entry.get("label", ""), entry.get("code", ""), entry.get("colos", []))
    data = _read_custom_country_data(path)
    custom = []
    replaced = False
    for raw in data.get("custom", []):
        if not isinstance(raw, dict):
            continue
        existing = validate_country_preset(raw.get("label", ""), raw.get("code", ""), raw.get("colos", []))
        if existing["code"] == item["code"]:
            custom.append(item)
            replaced = True
        else:
            custom.append(existing)
    if not replaced:
        custom.append(item)
    payload = {"custom": custom}
    _write_custom_country_data(payload, path)
    return payload


def _read_json_file(path: str | Path, default: dict[str, Any]) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return dict(default)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"JSON 文件格式错误: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON 文件必须是对象")
    return data


def _write_json_file(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_add_txt_lines(add_txt: str) -> str:
    lines = [line.strip() for line in str(add_txt or "").splitlines() if line.strip()]
    if not lines:
        raise ValueError("ADD.txt 内容不能为空")
    for line in lines:
        address_part = line.split("#", 1)[0].strip()
        if not re.fullmatch(r"(\[[\da-fA-F:]+\]|[\d.]+|[A-Za-z0-9][A-Za-z0-9.-]*)(:\d{1,5})?", address_part):
            raise ValueError(f"ADD.txt 行格式无效: {line}")
        node = parse_ip_line(line)
        if node is None or not 1 <= int(node.get("port") or 0) <= 65535:
            raise ValueError(f"ADD.txt 行格式无效: {line}")
    return "\n".join(lines) + "\n"


def validate_add_record(name: str, mode: str, add_txt: str, countries: Iterable[str] | None = None) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    clean_mode = str(mode or "entry").strip().lower()
    if not clean_name:
        raise ValueError("记录名称不能为空")
    if len(clean_name) > 64:
        raise ValueError("记录名称不能超过 64 个字符")
    if clean_mode not in {"entry", "exit", "both", "custom"}:
        raise ValueError("记录模式必须是 entry、exit、both 或 custom")
    normalized_countries = parse_countries(countries or [])
    normalized_add_txt = _validate_add_txt_lines(add_txt)
    return {
        "name": clean_name,
        "mode": clean_mode,
        "countries": normalized_countries,
        "add_txt": normalized_add_txt,
        "line_count": len(normalized_add_txt.splitlines()),
        "updated_at": int(time.time()),
    }


def load_add_records(path: str | Path = ADD_RECORDS_FILE) -> list[dict[str, Any]]:
    data = _read_json_file(path, {"records": []})
    records: list[dict[str, Any]] = []
    for raw in data.get("records", []):
        if not isinstance(raw, dict):
            continue
        item = validate_add_record(raw.get("name", ""), raw.get("mode", "entry"), raw.get("add_txt", ""), raw.get("countries", []))
        item["updated_at"] = int(raw.get("updated_at") or item["updated_at"])
        records.append(item)
    records.sort(key=lambda item: (str(item.get("name") or "").lower()))
    return records


def save_add_record(record: dict[str, Any], path: str | Path = ADD_RECORDS_FILE) -> dict[str, Any]:
    item = validate_add_record(record.get("name", ""), record.get("mode", "entry"), record.get("add_txt", ""), record.get("countries", []))
    existing = load_add_records(path)
    records = [r for r in existing if r["name"] != item["name"]]
    records.append(item)
    records.sort(key=lambda r: r["name"].lower())
    payload = {"records": records}
    _write_json_file(path, payload)
    return payload


def delete_add_record(name: str, path: str | Path = ADD_RECORDS_FILE) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("记录名称不能为空")
    records = [r for r in load_add_records(path) if r["name"] != clean_name]
    payload = {"records": records}
    _write_json_file(path, payload)
    return payload


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


def parse_colos(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw_parts = re.split(r"[\s,;|，、]+", value.strip())
    else:
        raw_parts = [str(x) for x in value]
    colos: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        colo = part.strip().upper()
        if not colo:
            continue
        if not re.fullmatch(r"[A-Z0-9]{3,8}", colo):
            continue
        if colo not in seen:
            colos.append(colo)
            seen.add(colo)
    return colos


def default_colos_for_country(country: str) -> list[str]:
    country_code = normalize_country(country)
    return sorted([colo for colo, mapped_country in COLO_COUNTRY.items() if mapped_country == country_code])


def entry_targets(country: str = "", colos: str | Iterable[str] | None = None) -> dict[str, set[str]]:
    countries = set(parse_countries(country)) if country else set()
    colo_set = set(parse_colos(colos))
    return {"countries": countries, "colos": colo_set}


def _count_by_key(nodes: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        value = str(node.get(key) or "").upper()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def filter_entry_scan_results(nodes: list[dict[str, Any]], country: str = "", colos: str | Iterable[str] | None = None, limit: int = 16) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    targets = entry_targets(country, colos)
    target_countries = targets["countries"]
    target_colos = targets["colos"]

    def is_match(node: dict[str, Any]) -> bool:
        region = str(node.get("region") or "").upper()
        colo = str(node.get("colo") or "").upper()
        return (bool(target_countries) and region in target_countries) or (bool(target_colos) and colo in target_colos)

    dedup: dict[str, dict[str, Any]] = {}
    for node in nodes:
        key = f"{node.get('ip')}:{node.get('port')}"
        if key not in dedup or float(node.get("latency") or 10**9) < float(dedup[key].get("latency") or 10**9):
            dedup[key] = node
    all_ok = sorted(dedup.values(), key=lambda n: float(n.get("latency") or 10**9))
    matched = [n for n in all_ok if is_match(n)]
    limited = matched[: max(limit, 1)]
    report = {
        "target_countries": sorted(target_countries),
        "target_colos": sorted(target_colos),
        "ok_count": len(all_ok),
        "match_count": len(matched),
        "returned_count": len(limited),
        "regions": _count_by_key(all_ok, "region"),
        "colos": _count_by_key(all_ok, "colo"),
        "message_type": "ok" if limited else ("warn" if all_ok else "err"),
    }
    return limited, report


def scan_entry_nodes(
    country: str,
    colos: str | Iterable[str] | None = None,
    limit: int = 16,
    candidates: int = 180,
    concurrency: int = 32,
    timeout: float = 4.0,
    ports: list[int] | None = None,
    scanner=None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    scanner = scanner or speedtest_country_nodes
    country_code = normalize_country(country)
    if scanner is speedtest_country_nodes:
        _matched_unused, all_ok = scanner(country_code, candidates=candidates, limit=limit, concurrency=concurrency, timeout=timeout, ports=ports)
    else:
        _matched_unused, all_ok = scanner(candidates, concurrency, timeout, ports)
    matched, report = filter_entry_scan_results(all_ok, country_code, colos, limit)
    report.update({
        "country_code": country_code,
        "candidates": candidates,
        "concurrency": concurrency,
        "timeout": timeout,
        "ports": ports or CF_TLS_PORTS,
    })
    add_txt = format_add_txt(matched, country_code) if matched else ""
    return matched, report, add_txt


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


def proxy_source_urls(countries: Iterable[str], proxy_sources: str | Iterable[str] | None = None) -> list[dict[str, str]]:
    if proxy_sources and proxy_sources != "auto":
        if isinstance(proxy_sources, str):
            urls = [x.strip() for x in re.split(r"[\s,]+", proxy_sources) if x.strip()]
        else:
            urls = [str(x).strip() for x in proxy_sources if str(x).strip()]
        return [{"name": url, "url": url, "format": "auto"} for url in urls]

    urls: list[dict[str, str]] = []
    seen: set[str] = set()
    for country in countries:
        country_code = normalize_country(country)
        for template in AUTO_PROXY_SOURCE_TEMPLATES:
            url = template["url"].format(country=country_code)
            if url in seen:
                continue
            urls.append({"name": template["name"], "url": url, "format": template.get("format", "auto")})
            seen.add(url)
    return urls


def _proxy_address(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host and not host.startswith("[") else f"{host}:{port}"


def _remark_country(remark: str) -> str:
    for token in re.split(r"[\s,_#:/()|;-]+", remark):
        if not token:
            continue
        code = normalize_country(token)
        if len(code) == 2:
            return code
    return ""


def _proxy_from_address(raw: str, default_type: str = "socks5", remark: str = "", source: str = "", country_hint: str = "") -> dict[str, Any] | None:
    addr = raw.strip()
    if not addr:
        return None

    ptype = default_type.lower()
    for prefix in ("socks5://", "http://", "https://"):
        if addr.lower().startswith(prefix):
            ptype = prefix[:-3]
            addr = addr[len(prefix):]
            break

    auth = ""
    if "@" in addr:
        auth, addr = addr.rsplit("@", 1)

    host = ""
    port = ""
    if addr.startswith("[") and "]:" in addr:
        host, port = addr[1:].split("]:", 1)
    elif ":" in addr:
        host, port = addr.rsplit(":", 1)
    else:
        return None

    try:
        port_i = int(str(port).strip())
    except ValueError:
        return None
    if not host.strip() or not 1 <= port_i <= 65535:
        return None

    country = normalize_country(country_hint) if country_hint else _remark_country(remark)
    host = host.strip().strip("[]")
    if ptype not in PROXY_TYPE_PRIORITY:
        return None

    return {
        "type": ptype,
        "host": host,
        "port": port_i,
        "auth": auth,
        "remark": remark,
        "country": country,
        "source": source,
        "address": _proxy_address(host, port_i),
    }


def _proxy_from_mapping(item: dict[str, Any], source: str = "", country_hint: str = "") -> dict[str, Any] | None:
    raw = item.get("proxy") or item.get("url") or item.get("address") or item.get("addr")
    ptype = str(item.get("protocol") or item.get("type") or item.get("scheme") or "socks5").lower()
    country = (
        item.get("country")
        or item.get("country_code")
        or item.get("countryCode")
        or item.get("loc")
        or item.get("region")
        or country_hint
        or ""
    )
    remark = str(item.get("remark") or item.get("note") or item.get("source") or "")
    if raw:
        return _proxy_from_address(str(raw), ptype, remark, source, str(country))

    host = item.get("ip") or item.get("host") or item.get("hostname")
    port = item.get("port")
    if not host or port is None:
        return None
    return _proxy_from_address(f"{host}:{port}", ptype, remark, source, str(country))


def _json_proxy_items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("proxies", "data", "nodes", "result", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if any(k in data for k in ("ip", "host", "address", "proxy", "url")):
            return [data]
    return []


def parse_proxy_candidates(text: str, source: str = "", country_hint: str = "", default_type: str = "socks5") -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []

    candidates: list[dict[str, Any]] = []
    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
        for item in _json_proxy_items(data):
            if isinstance(item, str):
                proxy = _proxy_from_address(item, default_type, "", source, country_hint)
            elif isinstance(item, dict):
                proxy = _proxy_from_mapping(item, source, country_hint)
            else:
                proxy = None
            if proxy:
                candidates.append(proxy)
        return candidates

    lines = [line for line in text.splitlines() if line.strip()]
    first_line = lines[0].lower() if lines else ""
    if "," in first_line and any(field in first_line for field in ("ip", "host", "proxy", "address", "port")):
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            proxy = _proxy_from_mapping(row, source, country_hint)
            if proxy:
                candidates.append(proxy)
        return candidates

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        remark = line.split("#", 1)[1].strip() if "#" in line else ""
        addr = line.split("#", 1)[0].strip()
        proxy = _proxy_from_address(addr, default_type, remark, source, country_hint)
        if proxy:
            candidates.append(proxy)
    return candidates


def parse_proxy_lines(text: str, default_type: str = "socks5") -> list[dict[str, Any]]:
    return parse_proxy_candidates(text, default_type=default_type)


def default_proxy_source(country: str) -> str:
    return f"{DEFAULT_SOURCE_BASE}/proxy_{country}.txt"


def dedupe_proxy_candidates(proxies: Iterable[dict[str, Any]], countries: Iterable[str] | None = None) -> list[dict[str, Any]]:
    target_countries = set(countries or [])
    chosen: dict[str, dict[str, Any]] = {}
    for proxy in proxies:
        country = str(proxy.get("country") or "").upper()
        if target_countries and country and country not in target_countries:
            continue
        ptype = str(proxy.get("type") or "socks5").lower()
        address = proxy.get("address") or _proxy_address(str(proxy.get("host") or ""), int(proxy.get("port") or 0))
        if not address or ":0" in address:
            continue
        key = address.lower()
        current = chosen.get(key)
        if current is None or PROXY_TYPE_PRIORITY.get(ptype, 99) < PROXY_TYPE_PRIORITY.get(str(current.get("type") or ""), 99):
            chosen[key] = {**proxy, "type": ptype, "address": address}
    return sorted(
        chosen.values(),
        key=lambda p: (
            PROXY_TYPE_PRIORITY.get(str(p.get("type") or ""), 99),
            str(p.get("country") or "ZZ"),
            str(p.get("address") or ""),
        ),
    )


def parse_proxy_excludes(exclude: str | Iterable[str] | None = None) -> set[str]:
    if not exclude:
        return set()
    if isinstance(exclude, str):
        raw_parts = re.split(r"[\s,;|，、]+", exclude.strip())
    else:
        raw_parts = [str(x) for x in exclude]
    return {part.strip().lower().removeprefix("socks5://").removeprefix("http://").removeprefix("https://").strip("[]") for part in raw_parts if part.strip()}


def filter_proxy_candidates(proxies: Iterable[dict[str, Any]], exclude: str | Iterable[str] | None = None) -> list[dict[str, Any]]:
    excludes = parse_proxy_excludes(exclude)
    if not excludes:
        return list(proxies)
    filtered: list[dict[str, Any]] = []
    for proxy in proxies:
        host = str(proxy.get("host") or "").strip().strip("[]").lower()
        address = str(proxy.get("address") or "").strip().lower()
        normalized_address = address.removeprefix("socks5://").removeprefix("http://").removeprefix("https://").strip("[]")
        if host in excludes or normalized_address in excludes:
            continue
        filtered.append(proxy)
    return filtered


class ProxyCheckCache:
    def __init__(self, ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS, now=None):
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.now = now or time.time
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}

    def _key(self, proxy: dict[str, Any]) -> str:
        return f"{str(proxy.get('type') or 'socks5').lower()}://{proxy.get('address') or ''}".lower()

    def get(self, proxy: dict[str, Any]) -> dict[str, Any] | None:
        item = self._items.get(self._key(proxy))
        if not item:
            return None
        checked_at, data = item
        if self.ttl_seconds and self.now() - checked_at > self.ttl_seconds:
            self._items.pop(self._key(proxy), None)
            return None
        return dict(data)

    def set(self, proxy: dict[str, Any], result: dict[str, Any]) -> None:
        self._items[self._key(proxy)] = (self.now(), dict(result))


GLOBAL_PROXY_CHECK_CACHE = ProxyCheckCache()


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


def fetch_proxy_candidates(countries: Iterable[str], proxy_sources: str | Iterable[str] | None = None, timeout: int = 20) -> tuple[list[dict[str, Any]], list[str]]:
    country_codes = list(countries)
    all_candidates: list[dict[str, Any]] = []
    source_urls: list[str] = []
    for source_info in proxy_source_urls(country_codes, proxy_sources):
        url = source_info["url"]
        source_urls.append(url)
        country_hint = ""
        if "{country}" not in source_info.get("url", "") and source_info["name"].endswith("-country"):
            country_hint = country_codes[0] if len(country_codes) == 1 else ""
        if source_info["name"] == "cf-bestip-country" and len(country_codes) == 1:
            country_hint = country_codes[0]
        try:
            text = fetch_text(url, timeout=timeout)
        except Exception:
            continue
        all_candidates.extend(parse_proxy_candidates(text, source=url, country_hint=country_hint))
    return dedupe_proxy_candidates(all_candidates, country_codes), source_urls


def validate_proxy_candidates(
    base_url: str,
    admin_password: str,
    countries: Iterable[str],
    proxies: Iterable[dict[str, Any]],
    limit_per_country: int = 8,
    validate_limit: int = 80,
    timeout: int = 25,
    validate_concurrency: int = 8,
    cache: ProxyCheckCache | None = None,
    checker=None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    country_codes = set(countries)
    cache = cache or GLOBAL_PROXY_CHECK_CACHE
    checker = checker or check_edgetunnel_proxy
    checked: list[dict[str, Any]] = []
    matched: dict[str, list[dict[str, Any]]] = {country: [] for country in country_codes}

    selected = list(proxies)[: max(validate_limit, 1)]

    def check_one(proxy: dict[str, Any]) -> dict[str, Any]:
        cached = cache.get(proxy)
        if cached is not None:
            return {**proxy, **cached, "cache": True}
        try:
            res = checker(base_url, admin_password, proxy, timeout=timeout)
        except Exception as e:
            res = {**proxy, "success": False, "error": str(e)}
        cache.set(proxy, res)
        return res

    with ThreadPoolExecutor(max_workers=max(1, min(validate_concurrency, len(selected) or 1))) as ex:
        futures = [ex.submit(check_one, proxy) for proxy in selected]
        for fut in as_completed(futures):
            res = fut.result()
            checked.append(res)

            loc = str(res.get("loc") or "").upper()
            if not res.get("success") or loc not in country_codes:
                continue
            bucket = matched.setdefault(loc, [])
            if len(bucket) < max(limit_per_country, 1):
                bucket.append(res)

    for country, items in matched.items():
        items.sort(key=lambda p: (float(p.get("responseTime") or 10**9), PROXY_TYPE_PRIORITY.get(str(p.get("type") or ""), 99)))
    return matched, checked


def proxy_test_countries(
    base_url: str,
    admin_password: str,
    countries: Iterable[str],
    sources: str | Iterable[str] | None = None,
    limit_per_country: int = 8,
    validate_limit: int = 80,
    timeout: int = 8,
    cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
    validate_concurrency: int = 8,
    exclude: str | Iterable[str] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    country_codes = list(countries)
    candidates, source_urls = fetch_proxy_candidates(country_codes, sources, timeout=20)
    candidates = filter_proxy_candidates(candidates, exclude)
    cache = GLOBAL_PROXY_CHECK_CACHE if cache_ttl == DEFAULT_CACHE_TTL_SECONDS else ProxyCheckCache(cache_ttl)
    matched, checked = validate_proxy_candidates(
        base_url,
        admin_password,
        country_codes,
        candidates,
        limit_per_country=limit_per_country,
        validate_limit=validate_limit,
        timeout=timeout,
        validate_concurrency=validate_concurrency,
        cache=cache,
    )
    return matched, checked, source_urls, candidates


def proxy_test_country(base_url: str, admin_password: str, country: str, source: str | None = None, limit: int = 3, timeout: int = 25) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    country_code = normalize_country(country)
    source_url = source or default_proxy_source(country_code)
    proxies = parse_proxy_candidates(fetch_text(source_url), source=source_url, country_hint=country_code)
    proxies = dedupe_proxy_candidates(proxies, [country_code])
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
    matched = [p for p in checked if p.get("success") and str(p.get("loc") or "").upper() == country_code]
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


def format_proxy_exit_add_txt(entry_nodes: list[dict[str, Any]], proxy: dict[str, Any] | list[dict[str, Any]], country: str, limit: int | None = None) -> str:
    proxies = proxy if isinstance(proxy, list) else [proxy]
    proxies = [p for p in proxies if p]
    if not proxies:
        return ""
    lines = []
    selected_nodes = entry_nodes[: limit or len(entry_nodes)]
    for i, n in enumerate(selected_nodes, 1):
        active_proxy = proxies[(i - 1) % len(proxies)]
        ptype = active_proxy.get("type") or "socks5"
        address = active_proxy.get("address") or f"{active_proxy['host']}:{active_proxy['port']}"
        response_time = active_proxy.get("responseTime")
        proxy_ip = active_proxy.get("ip") or ""
        proxy_loc = active_proxy.get("loc") or country
        ip = str(n["ip"]).strip()
        port = int(n.get("port") or 443)
        host = f"[{ip}]" if ":" in ip and not ip.startswith("[") else ip
        rt = f"-{response_time}ms" if response_time is not None else ""
        out = f"-{proxy_ip}" if proxy_ip else ""
        remark = f"EXIT-{proxy_loc}{rt}{out}-{i} ${ptype}://{address}"
        lines.append(f"{host}:{port}#{remark}")
    return "\n".join(lines) + "\n"


def format_multi_country_proxy_exit_add_txt(entry_nodes: list[dict[str, Any]], proxies_by_country: dict[str, list[dict[str, Any]]], per_country_limit: int = 8) -> str:
    chunks: list[str] = []
    for country in sorted(proxies_by_country):
        proxies = proxies_by_country.get(country) or []
        if not proxies:
            continue
        chunk = format_proxy_exit_add_txt(entry_nodes, proxies, country, limit=per_country_limit).strip()
        if chunk:
            chunks.append(chunk)
    return "\n".join(chunks) + ("\n" if chunks else "")


def proxy_pool_summary(countries: Iterable[str], candidates: list[dict[str, Any]], checked: list[dict[str, Any]], matched: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for country in countries:
        candidate_count = sum(1 for p in candidates if not p.get("country") or str(p.get("country")).upper() == country)
        checked_country = [p for p in checked if not p.get("country") or str(p.get("country")).upper() == country or str(p.get("loc") or "").upper() == country]
        protocols: dict[str, int] = {}
        for p in checked_country or [p for p in candidates if not p.get("country") or str(p.get("country")).upper() == country]:
            ptype = str(p.get("type") or "socks5")
            protocols[ptype] = protocols.get(ptype, 0) + 1
        best = (matched.get(country) or [{}])[0]
        rows.append({
            "country": country,
            "candidates": candidate_count,
            "checked": len(checked_country),
            "matched": len(matched.get(country) or []),
            "protocols": protocols,
            "best_proxy": f"{best.get('type', '')}://{best.get('address', '')}".strip(":/"),
            "best_time": best.get("responseTime"),
            "checked_at": int(time.time()) if checked_country else None,
        })
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="按国家/地区自动配置 edgetunnel /admin/ADD.txt")
    p.add_argument("--base-url", "-u", help="edgetunnel 地址，例如 https://edt.example.com")
    p.add_argument("--admin-password", "-p", help="管理员密码；不传则交互输入")
    p.add_argument("--country", "-c", help="单个国家/地区，例如 日本、美国、JP、US；兼容旧用法")
    p.add_argument("--countries", help="多个国家/地区，用逗号或空格分隔，例如 US,JP,SG,GB")
    p.add_argument("--mode", choices=("entry", "exit", "both"), default="entry", help="生成模式：entry 入口 IP，exit 出口代理，both 两者都生成")
    p.add_argument("--source", "-s", default=DEFAULT_SOURCE, help=f"IP 数据源 URL，默认 {DEFAULT_SOURCE}")
    p.add_argument("--entry-scan", action="store_true", help="入口使用当前网络本地实测，不使用公开源筛选")
    p.add_argument("--entry-colos", help="目标 Cloudflare colo，逗号分隔，例如 NRT,KIX,FUK")
    p.add_argument("--entry-candidates", type=int, default=180, help="入口本地扫描候选数量，默认 180")
    p.add_argument("--entry-concurrency", type=int, default=32, help="入口本地扫描并发，默认 32")
    p.add_argument("--entry-timeout", type=float, default=4.0, help="入口本地扫描单个连接超时秒数，默认 4")
    p.add_argument("--proxy-sources", default="auto", help="出口代理源：auto 或逗号分隔 URL 列表")
    p.add_argument("--proxy-exclude", help="排除不稳定出口代理，支持逗号分隔 host 或 host:port")
    p.add_argument("--validate-limit", type=int, default=80, help="每次最多验证的代理候选数，默认 80")
    p.add_argument("--validate-concurrency", type=int, default=8, help="出口代理验证并发，默认 8")
    p.add_argument("--proxy-timeout", type=int, default=8, help="单个出口代理检查超时秒数，默认 8")
    p.add_argument("--cache-ttl", type=int, default=DEFAULT_CACHE_TTL_SECONDS, help="代理检查缓存秒数，默认 900")
    p.add_argument("--limit", "-n", type=int, default=16, help="写入数量，默认 16")
    p.add_argument("--restore-default", action="store_true", help="清空 ADD.txt，恢复 edgetunnel 默认逻辑")
    p.add_argument("--dry-run", action="store_true", help="只打印将写入的 ADD.txt，不提交")
    args = p.parse_args()

    countries = parse_countries(args.countries or args.country or "")
    if args.restore_default:
        if not args.base_url:
            print("[!] --restore-default 需要 --base-url", file=sys.stderr)
            return 2
        password = args.admin_password or getpass.getpass("edgetunnel 管理员密码: ")
        if args.dry_run:
            print("[*] dry-run：将清空 ADD.txt 以恢复默认。", file=sys.stderr)
            return 0
        restore_default_add_txt(args.base_url, password)
        print("[OK] 已恢复默认 ADD.txt", file=sys.stderr)
        return 0

    if not countries:
        print("[!] 请提供 --country 或 --countries", file=sys.stderr)
        return 2

    needs_edgetunnel = (not args.dry_run) or args.mode in ("exit", "both")
    if needs_edgetunnel and not args.base_url:
        print("[!] 当前模式需要 --base-url", file=sys.stderr)
        return 2
    password = ""
    if needs_edgetunnel:
        password = args.admin_password or getpass.getpass("edgetunnel 管理员密码: ")

    add_chunks: list[str] = []

    if args.mode in ("entry", "both"):
        if args.entry_scan:
            for country in countries:
                print(f"[*] 当前网络入口扫描: {country} colos={args.entry_colos or '未指定'}", file=sys.stderr)
                matched, report, entry_add = scan_entry_nodes(
                    country,
                    colos=args.entry_colos,
                    limit=args.limit,
                    candidates=max(args.entry_candidates, 1),
                    concurrency=max(args.entry_concurrency, 1),
                    timeout=max(args.entry_timeout, 1.0),
                )
                print(
                    f"[*] {country}: 成功连接 {report['ok_count']}，命中 {report['match_count']}，地区 {report['regions']}，Colo {report['colos']}",
                    file=sys.stderr,
                )
                if not matched:
                    print("[!] 当前网络环境没有测到目标入口。可以增加 --entry-candidates，指定 --entry-colos，或换网络。", file=sys.stderr)
                    continue
                add_chunks.append(entry_add.strip())
        else:
            print(f"[*] 拉取入口 IP 数据源: {args.source}", file=sys.stderr)
            nodes = parse_source(fetch_text(args.source))
            if not nodes:
                print("[!] 入口数据源没有解析到任何节点", file=sys.stderr)
                return 2
            for country in countries:
                matched, regions, fallback_url = select_country_nodes(nodes, country, args.limit, args.source)
                if fallback_url:
                    print(f"[*] {country} 已自动使用兜底源: {fallback_url}", file=sys.stderr)
                if not matched:
                    print(f"[!] 入口数据源里没有 {country} 节点。当前可用地区: {', '.join(regions) or '无'}", file=sys.stderr)
                    continue
                add_chunks.append(format_add_txt(matched, country).strip())

    if args.mode in ("exit", "both"):
        print(f"[*] 正在验证出口代理候选: {', '.join(countries)}", file=sys.stderr)
        matched_by_country, checked, source_urls, candidates = proxy_test_countries(
            args.base_url,
            password,
            countries,
            sources=args.proxy_sources,
            limit_per_country=min(max(args.limit, 1), 8),
            validate_limit=max(args.validate_limit, 1),
            timeout=max(args.proxy_timeout, 1),
            cache_ttl=max(args.cache_ttl, 0),
            validate_concurrency=max(args.validate_concurrency, 1),
            exclude=args.proxy_exclude,
        )
        summary = proxy_pool_summary(countries, candidates, checked, matched_by_country)
        for row in summary:
            print(f"[*] {row['country']}: 候选 {row['candidates']}，已检查 {row['checked']}，命中 {row['matched']}", file=sys.stderr)
        exit_add = format_multi_country_proxy_exit_add_txt(top_cf_entry_nodes(args.limit), matched_by_country, per_country_limit=min(max(args.limit, 1), 8))
        if exit_add.strip():
            add_chunks.append(exit_add.strip())

    add_txt = "\n".join(chunk for chunk in add_chunks if chunk.strip()) + ("\n" if add_chunks else "")
    if not add_txt.strip():
        print("[!] 没有生成可写入的 ADD.txt 内容", file=sys.stderr)
        return 3
    print(add_txt)

    if args.dry_run:
        print("[*] dry-run：未提交到 edgetunnel。", file=sys.stderr)
        return 0

    print(f"[*] 正在提交到 {args.base_url.rstrip('/')}/admin/ADD.txt", file=sys.stderr)
    post_to_edgetunnel(args.base_url, password, add_txt)
    print(f"[OK] 已写入 {len(add_txt.splitlines())} 条节点到 ADD.txt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
