import json
import tempfile
import time
import unittest
from pathlib import Path

import edgetunnel_region_config as cfg


class ProxyPoolTests(unittest.TestCase):
    def test_parse_countries_accepts_aliases_and_commas(self):
        self.assertEqual(cfg.parse_countries("美国, JP sg\n英国"), ["US", "JP", "SG", "GB"])

    def test_country_presets_validate_and_persist_custom_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "countries.json"
            entry = cfg.validate_country_preset("越南", "vn", "SGN,HAN")

            saved = cfg.save_custom_country_preset(entry, path=path)
            loaded = cfg.load_country_presets(path=path)

        self.assertEqual(entry, {"label": "越南", "code": "VN", "colos": ["SGN", "HAN"], "custom": True})
        self.assertTrue(any(item["code"] == "VN" and item["label"] == "越南" for item in saved["custom"]))
        self.assertTrue(any(item["code"] == "VN" and item["colos"] == ["SGN", "HAN"] for item in loaded))

    def test_country_presets_reject_bad_formats(self):
        with self.assertRaises(ValueError):
            cfg.validate_country_preset("", "VN", "SGN")
        with self.assertRaises(ValueError):
            cfg.validate_country_preset("越南", "VNM", "SGN")
        with self.assertRaises(ValueError):
            cfg.validate_country_preset("越南", "VN", "SGN,!BAD")

    def test_add_records_persist_update_and_delete_by_name(self):
        add_txt = "104.18.1.1:443#JP-NRT-1\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.json"
            saved = cfg.save_add_record({"name": "日本入口", "mode": "entry", "countries": ["JP"], "add_txt": add_txt}, path=path)
            updated = cfg.save_add_record({"name": "日本入口", "mode": "entry", "countries": ["JP"], "add_txt": "104.18.2.2:443#JP-NRT-2\n"}, path=path)
            loaded = cfg.load_add_records(path=path)
            deleted = cfg.delete_add_record("日本入口", path=path)

        self.assertEqual(saved["records"][0]["name"], "日本入口")
        self.assertEqual(len(updated["records"]), 1)
        self.assertIn("104.18.2.2:443", loaded[0]["add_txt"])
        self.assertEqual(deleted["records"], [])

    def test_add_records_reject_invalid_name_or_add_txt(self):
        with self.assertRaises(ValueError):
            cfg.validate_add_record("", "entry", "104.18.1.1:443#ok\n")
        with self.assertRaises(ValueError):
            cfg.validate_add_record("空内容", "entry", "")
        with self.assertRaises(ValueError):
            cfg.validate_add_record("坏行", "entry", "not a node\n")

    def test_parse_proxy_candidates_supports_text_json_and_csv(self):
        text_candidates = cfg.parse_proxy_candidates(
            "socks5://user:pass@1.2.3.4:1080#fast\n"
            "http://5.6.7.8:8080\n"
            "[2001:db8::1]:1080#US\n",
            source="txt",
            country_hint="US",
        )
        self.assertEqual(
            [(p["type"], p["host"], p["port"], p["country"]) for p in text_candidates],
            [
                ("socks5", "1.2.3.4", 1080, "US"),
                ("http", "5.6.7.8", 8080, "US"),
                ("socks5", "2001:db8::1", 1080, "US"),
            ],
        )
        self.assertEqual(text_candidates[0]["auth"], "user:pass")

        json_candidates = cfg.parse_proxy_candidates(
            json.dumps([
                {"protocol": "socks5", "ip": "9.9.9.9", "port": 1080, "country": "Japan"},
                {"type": "https", "host": "8.8.8.8", "port": "8443", "country_code": "GB"},
            ]),
            source="json",
        )
        self.assertEqual([(p["type"], p["country"]) for p in json_candidates], [("socks5", "JP"), ("https", "GB")])

        csv_candidates = cfg.parse_proxy_candidates(
            "ip,port,protocol,country\n7.7.7.7,3128,http,SG\n",
            source="csv",
        )
        self.assertEqual(csv_candidates[0]["address"], "7.7.7.7:3128")
        self.assertEqual(csv_candidates[0]["country"], "SG")

    def test_dedupe_proxy_candidates_prefers_socks5_and_country_match(self):
        proxies = cfg.parse_proxy_candidates(
            "http://1.2.3.4:1080#US\nsocks5://1.2.3.4:1080#US\nsocks5://5.6.7.8:1080#JP",
            source="txt",
        )
        deduped = cfg.dedupe_proxy_candidates(proxies, countries=["US"])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["type"], "socks5")

    def test_filter_proxy_candidates_excludes_unstable_hosts_or_addresses(self):
        proxies = cfg.parse_proxy_candidates(
            "socks5://103.142.255.32:1080#ID\n"
            "socks5://103.156.16.120:8199#ID\n"
            "socks5://103.119.60.219:1080#ID",
            source="txt",
        )

        filtered = cfg.filter_proxy_candidates(proxies, exclude="103.142.255.32,103.119.60.219:1080")

        self.assertEqual([p["address"] for p in filtered], ["103.156.16.120:8199"])

    def test_proxy_check_cache_honors_ttl(self):
        now = [1000.0]
        cache = cfg.ProxyCheckCache(ttl_seconds=15, now=lambda: now[0])
        proxy = {"type": "socks5", "address": "1.2.3.4:1080"}
        cache.set(proxy, {"success": True, "loc": "US"})

        self.assertEqual(cache.get(proxy)["loc"], "US")
        now[0] = 1016.0
        self.assertIsNone(cache.get(proxy))

    def test_validate_proxy_candidates_can_run_checks_concurrently(self):
        proxies = [
            {"type": "socks5", "address": f"1.2.3.{i}:1080"}
            for i in range(1, 6)
        ]

        def slow_checker(_base_url, _password, proxy, timeout=25):
            time.sleep(0.05)
            return {**proxy, "success": True, "loc": "ID", "responseTime": 50}

        started = time.perf_counter()
        matched, checked = cfg.validate_proxy_candidates(
            "https://example.com",
            "pw",
            ["ID"],
            proxies,
            limit_per_country=5,
            validate_limit=5,
            validate_concurrency=5,
            checker=slow_checker,
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(len(checked), 5)
        self.assertEqual(len(matched["ID"]), 5)
        self.assertLess(elapsed, 0.18)

    def test_auto_proxy_sources_include_verified_country_paths(self):
        urls = [x["url"] for x in cfg.proxy_source_urls(["US"])]
        self.assertIn("https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/US/data.txt", urls)
        self.assertIn("https://raw.githubusercontent.com/iplocate/free-proxy-list/main/all-proxies.txt", urls)
        self.assertIn("https://raw.githubusercontent.com/iplocate/free-proxy-list/main/countries/US/proxies.txt", urls)
        self.assertIn("https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks5.txt", urls)

    def test_entry_targets_include_country_and_colo(self):
        targets = cfg.entry_targets("日本", "NRT,KIX")
        self.assertEqual(targets["countries"], {"JP"})
        self.assertEqual(targets["colos"], {"NRT", "KIX"})

    def test_filter_entry_scan_results_matches_country_or_colo(self):
        all_ok = [
            {"ip": "1.1.1.1", "port": 443, "region": "US", "colo": "SJC", "latency": 80},
            {"ip": "2.2.2.2", "port": 443, "region": "JP", "colo": "NRT", "latency": 100},
            {"ip": "3.3.3.3", "port": 443, "region": "SG", "colo": "NRT", "latency": 60},
        ]
        matched, report = cfg.filter_entry_scan_results(all_ok, country="JP", colos=["NRT"], limit=8)

        self.assertEqual([n["ip"] for n in matched], ["3.3.3.3", "2.2.2.2"])
        self.assertEqual(report["target_countries"], ["JP"])
        self.assertEqual(report["target_colos"], ["NRT"])
        self.assertEqual(report["ok_count"], 3)
        self.assertEqual(report["match_count"], 2)
        self.assertEqual(report["regions"]["US"], 1)
        self.assertEqual(report["colos"]["NRT"], 2)

    def test_scan_entry_nodes_uses_injected_scanner_for_diagnostics(self):
        def scanner(candidates, concurrency, timeout, ports):
            return [], [
                {"ip": "4.4.4.4", "port": 443, "region": "US", "colo": "SJC", "latency": 70},
                {"ip": "5.5.5.5", "port": 443, "region": "JP", "colo": "KIX", "latency": 90},
            ]

        matched, report, add_txt = cfg.scan_entry_nodes(
            country="JP",
            colos=["NRT", "KIX"],
            limit=4,
            candidates=20,
            concurrency=2,
            timeout=3,
            scanner=scanner,
        )

        self.assertEqual([n["ip"] for n in matched], ["5.5.5.5"])
        self.assertIn("#JP-KIX", add_txt)
        self.assertEqual(report["message_type"], "ok")

    def test_format_proxy_exit_add_txt_rotates_multiple_proxies(self):
        entry_nodes = [
            {"ip": "104.18.1.1", "port": 443},
            {"ip": "104.18.2.2", "port": 443},
            {"ip": "104.18.3.3", "port": 443},
        ]
        proxies = [
            {"type": "socks5", "address": "1.1.1.1:1080", "loc": "US", "responseTime": 100},
            {"type": "http", "address": "2.2.2.2:8080", "loc": "US", "responseTime": 120},
        ]

        add_txt = cfg.format_proxy_exit_add_txt(entry_nodes, proxies, "US")

        self.assertIn("$socks5://1.1.1.1:1080", add_txt)
        self.assertIn("$http://2.2.2.2:8080", add_txt)
        self.assertEqual(add_txt.count("\n"), 3)

    def test_format_multi_country_exit_add_txt_groups_by_country(self):
        entry_nodes = [{"ip": "104.18.1.1", "port": 443}, {"ip": "104.18.2.2", "port": 443}]
        add_txt = cfg.format_multi_country_proxy_exit_add_txt(
            entry_nodes,
            {
                "US": [{"type": "socks5", "address": "1.1.1.1:1080", "loc": "US"}],
                "JP": [{"type": "socks5", "address": "2.2.2.2:1080", "loc": "JP"}],
            },
            per_country_limit=1,
        )

        self.assertIn("#EXIT-US", add_txt)
        self.assertIn("#EXIT-JP", add_txt)
        self.assertEqual(add_txt.count("\n"), 2)


if __name__ == "__main__":
    unittest.main()
