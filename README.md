# edgetunnel IP Config UI

一个用于配置 [cmliu/edgetunnel](https://github.com/cmliu/edgetunnel) `/admin/ADD.txt` 的本地 Web UI 工具。

功能分为两类，避免混淆：

- **入口设置**：配置 Cloudflare 入口优选 IP，优化连接 Cloudflare 的入口速度；不保证最终查询 IP 国家。
- **出口设置**：从多个公开免费代理源抓取 SOCKS5/HTTP 候选，调用 edgetunnel `/admin/check` 实测后，生成带 `$socks5://...` / `$http://...` 的节点，让最终查询 IP 更接近指定国家。

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

多国家入口预览：

```bash
python3 edgetunnel_region_config.py \
  --mode entry \
  --countries US,JP,SG,GB \
  --dry-run
```

当前网络实测日本入口：

```bash
python3 edgetunnel_region_config.py \
  --mode entry \
  --entry-scan \
  --country JP \
  --entry-colos NRT,KIX,FUK \
  --entry-candidates 1000 \
  --entry-concurrency 48 \
  --entry-timeout 4 \
  --dry-run
```

多国家出口代理验证并生成：

```bash
python3 edgetunnel_region_config.py \
  --mode exit \
  --base-url https://你的-edgetunnel-域名 \
  --admin-password '你的管理员密码' \
  --countries US,JP,SG \
  --limit 8 \
  --validate-limit 80 \
  --dry-run
```

入口和出口一起生成：

```bash
python3 edgetunnel_region_config.py \
  --mode both \
  --base-url https://你的-edgetunnel-域名 \
  --admin-password '你的管理员密码' \
  --countries US,JP,SG \
  --limit 8
```

## 入口 vs 出口

### 入口设置

入口设置写入的是 Cloudflare 优选 IP，例如：

```text
104.18.1.1:443#US-1
```

这只影响客户端连接 Cloudflare 的入口，不保证访问网站时显示的出口国家。

入口扫描按当前网络环境实测。比如同一个 edgetunnel，在 A 办公室可能测到日本入口，在 B 办公室可能只测到美国入口。要在 B 办公室寻找日本入口，应使用 **入口：本地测速生成**，并设置：

- 国家/地区：`JP`
- 目标入口 Colo：`NRT,KIX,FUK`
- 候选数量：建议从 `500` 到 `2000` 逐步增加

如果报告显示没有命中目标入口，说明当前网络到 Cloudflare 的路由没有测到日本入口；可以增加候选数量、调整端口/超时、换网络，或者后续用出口代理解决最终国家。

### 出口设置

出口设置会生成带链式代理标记的节点，例如：

```text
104.18.1.1:443#EXIT-US-1 $socks5://1.2.3.4:1080
```

edgetunnel 会识别备注里的 `$socks5://...` / `$http://...`，让该节点通过代理出口访问目标网站。最终查询 IP 国家由这个出口代理决定。

现在出口设置会：

1. 从多个公开源抓取候选。
2. 统一解析 TXT / JSON / CSV 格式。
3. 按协议优先级去重，优先 SOCKS5。
4. 调用你的 edgetunnel `/admin/check` 验证代理是否可用、出口国家是否匹配。
5. 用多个通过验证的代理轮换生成 ADD.txt，避免所有节点依赖同一个代理。

推荐顺序：

1. 先用入口扫描找到当前网络可用的目标入口，写入 ADD.txt。
2. 如果目标网站最终查询 IP 仍不是目标国家，再启用出口代理。
3. 出口代理必须实测通过才写入，免费代理不保证长期稳定。

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

出口代理自动候选源包括：

- `https://zoroaaa.github.io/cf-bestip/proxy_国家代码.txt`
- `proxifly/free-proxy-list`
- `iplocate/free-proxy-list`
- `ProxyRadar`
- `Stormsia proxy-list`

这些源只提供候选；是否写入取决于 `/admin/check` 的实测结果。

## 节点池

UI 提供 **查看节点池**，会按国家显示：

- 候选数量
- 已验证数量
- 命中数量
- 协议分布
- 最快代理和延迟

查看节点池不会写入 ADD.txt；要写入请先生成入口或出口结果，再点 **应用当前结果到 ADD.txt**。如果当前没有有效生成结果，UI 不会自动回退到入口公开源写入。

## 扫描记录

UI 支持把入口或出口生成结果保存成命名记录，持久化到本地 `edgetunnel_add_records.json`。

- **保存当前结果**：把右侧当前生成的 ADD.txt 快照保存为自定义名称。
- **自动命名**：入口/出口生成后会按 `国家-入口/出口-时间` 填入记录名。
- **添加到预选**：把选中的保存记录加入“预选内容”，多个记录会合并成预选 ADD.txt 预览。
- **删除选中结果**：从预选内容移除某条记录，便于确认最终哪些内容会写入 ADD.txt。
- **应用预选到 ADD.txt**：只写入预选内容，和上方“应用当前结果到 ADD.txt”分开。
- **保存编辑**：修改记录里的 ADD.txt 文本，适合删除 timeout 或失效节点。
- **删除记录**：移除不再需要的入口/出口结果。

记录只保存 ADD.txt 内容、模式、国家和更新时间，不保存 edgetunnel 地址或管理员密码。保存时会校验每一行节点格式，明显错误的内容不会写入文件。

## 自定义国家

UI 支持添加自定义国家快捷项，并持久化保存到本地 `edgetunnel_countries.json`。格式要求：

- 国家名称不能为空，例如 `越南`。
- 国家代码必须是 2 位字母，例如 `VN`、`AU`、`BR`。
- 入口 Colo 可选，多个用逗号分隔，例如 `SGN,HAN`；每个 Colo 必须是 3-8 位字母/数字。

添加后会出现在国家快捷按钮里。点击自定义国家会把国家代码写入输入框，并自动填入配置的 Colo。

## 恢复默认

UI 提供 **恢复默认 ADD.txt** 按钮，会清空 `/admin/ADD.txt`。edgetunnel 会回退到默认随机/内置优选逻辑。

## 免责声明

仅用于个人网络测试和学习。请遵守所在地法律法规。公开 SOCKS5/HTTP 代理可能不稳定且不可控，不建议用于敏感账号或隐私场景。

免费公开代理的可用性、安全性和出口国家都会快速变化。这个工具会先验证再写入，但验证通过不代表长期稳定，也不代表代理可信。相关研究可参考 [Free Proxies Unmasked](https://arxiv.org/abs/2403.02445)。
