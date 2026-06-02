# edgetunnel IP Config UI

一个用于配置 [cmliu/edgetunnel](https://github.com/cmliu/edgetunnel) `/admin/ADD.txt` 的本地 Web UI 工具。

功能分为两类，避免混淆：

- **入口设置**：配置 Cloudflare 入口优选 IP，优化连接 Cloudflare 的入口速度；不保证最终查询 IP 国家。
- **出口设置**：测试 SOCKS5/HTTP 出口代理，生成带 `$socks5://...` 的节点，让最终查询 IP 更接近指定国家。

> 默认只监听 `127.0.0.1`。管理员密码仅用于当次请求，不保存。

## 文件

- `edgetunnel_region_config.py`：核心逻辑脚本，可命令行使用。
- `edgetunnel_region_ui.py`：本地 Web UI。

## 快速启动

```bash
python3 edgetunnel_region_ui.py
```

打开：

```text
http://127.0.0.1:8765
```

## 命令行用法

公开源预览 / 写入入口 ADD.txt：

```bash
python3 edgetunnel_region_config.py \
  --base-url https://你的-edgetunnel-域名 \
  --country 美国 \
  --dry-run
```

真正写入时去掉 `--dry-run`，并传入或交互输入管理员密码：

```bash
python3 edgetunnel_region_config.py \
  --base-url https://你的-edgetunnel-域名 \
  --country 美国
```

## 入口 vs 出口

### 入口设置

入口设置写入的是 Cloudflare 优选 IP，例如：

```text
104.18.1.1:443#US-1
```

这只影响客户端连接 Cloudflare 的入口，不保证访问网站时显示的出口国家。

### 出口设置

出口设置会生成带链式代理标记的节点，例如：

```text
104.18.1.1:443#EXIT-US-1 $socks5://1.2.3.4:1080
```

edgetunnel 会识别备注里的 `$socks5://...`，让该节点通过 SOCKS5 出口访问目标网站。最终查询 IP 国家由这个出口代理决定。

## 数据源

默认公开源：

```text
https://zoroaaa.github.io/cf-bestip/ip_candidates.json
```

部分国家使用同站兜底源：

```text
https://zoroaaa.github.io/cf-bestip/ip_JP.txt
https://zoroaaa.github.io/cf-bestip/ip_GB.txt
https://zoroaaa.github.io/cf-bestip/proxy_US.txt
https://zoroaaa.github.io/cf-bestip/proxy_JP.txt
https://zoroaaa.github.io/cf-bestip/proxy_GB.txt
```

也可以在 UI 里填自定义纯文本/JSON 数据源。

## 恢复默认

UI 提供 **恢复默认 ADD.txt** 按钮，会清空 `/admin/ADD.txt`。edgetunnel 会回退到默认随机/内置优选逻辑。

## 免责声明

仅用于个人网络测试和学习。请遵守所在地法律法规。公开 SOCKS5/HTTP 代理可能不稳定且不可控，不建议用于敏感账号或隐私场景。
