import subprocess
import sys
import unittest
from pathlib import Path

import edgetunnel_region_ui as ui


class UiCliTests(unittest.TestCase):
    def test_ui_tracks_latest_mode_and_does_not_apply_empty_fallback(self):
        self.assertIn("latestMode", ui.HTML)
        self.assertIn("没有可写入的当前结果", ui.HTML)
        self.assertNotIn("return run(false)", ui.HTML)

    def test_cli_exposes_multi_country_node_pool_options(self):
        result = subprocess.run(
            [sys.executable, "edgetunnel_region_config.py", "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn("--mode", result.stdout)
        self.assertIn("--countries", result.stdout)
        self.assertIn("--proxy-sources", result.stdout)
        self.assertIn("--proxy-exclude", result.stdout)
        self.assertIn("--validate-limit", result.stdout)
        self.assertIn("--validate-concurrency", result.stdout)
        self.assertIn("--proxy-timeout", result.stdout)
        self.assertIn("--cache-ttl", result.stdout)
        self.assertIn("--entry-colos", result.stdout)
        self.assertIn("--entry-timeout", result.stdout)

    def test_ui_exposes_target_entry_colo_scan_controls(self):
        self.assertIn("目标入口 Colo", ui.HTML)
        self.assertIn("entryColos", ui.HTML)
        self.assertIn("entryTimeout", ui.HTML)
        self.assertIn('data-colos="NRT,KIX,FUK"', ui.HTML)
        self.assertIn("lastAutoEntryColos", ui.HTML)
        self.assertIn("当前网络环境没有测到目标入口", ui.HTML)

    def test_ui_exposes_persistent_country_management(self):
        self.assertIn("addCountryLabel", ui.HTML)
        self.assertIn("addCountryCode", ui.HTML)
        self.assertIn("addCountryColos", ui.HTML)
        self.assertIn("/api/countries", ui.HTML)
        self.assertIn("/api/countries/add", ui.HTML)

    def test_ui_exposes_persistent_add_records(self):
        self.assertIn("recordName", ui.HTML)
        self.assertIn("recordsList", ui.HTML)
        self.assertIn("recordEditor", ui.HTML)
        self.assertIn("/api/records", ui.HTML)
        self.assertIn("/api/records/save", ui.HTML)
        self.assertIn("/api/records/delete", ui.HTML)

    def test_ui_separates_saved_records_from_direct_add_write(self):
        self.assertIn('class="workspace-grid"', ui.HTML)
        self.assertIn('class="results-stack"', ui.HTML)
        self.assertIn('id="scanRecordsSection"', ui.HTML)
        self.assertIn('class="record-grid"', ui.HTML)
        self.assertLess(ui.HTML.index("写入 / 恢复"), ui.HTML.index("扫描记录"))

    def test_ui_exposes_bounded_proxy_validation_controls(self):
        self.assertIn("proxyExclude", ui.HTML)
        self.assertIn("proxyTimeout", ui.HTML)
        self.assertIn("validateConcurrency", ui.HTML)
        self.assertIn('id="validateLimit" type="number" min="1" max="500" value="30"', ui.HTML)

    def test_double_click_toggle_script_exists(self):
        script = Path("toggle_edgetunnel_ui.command")
        self.assertTrue(script.exists())
        text = script.read_text()
        self.assertIn("PORT=\"${EDGETUNNEL_UI_PORT:-8765}\"", text)
        self.assertIn(".edgetunnel-ui.pid", text)
        self.assertIn(".edgetunnel-ui.log", text)
        self.assertIn("open \"http://${HOST}:${PORT}/\"", text)


if __name__ == "__main__":
    unittest.main()
