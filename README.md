# hermes-config-doctor · 配置文件体检脚本

一个 Python 单文件，用来在改配置前后跑一遍，确认没把 Hermes 的 `config.yaml` 改坏。

## 为什么写

配置文件是手改的，一次拼错缩进、一次把 key 贴成占位符，重启后就起不来了，
而且报错只说“解析失败”，看不出是第几行、哪一项。所以写了个固定顺序的体检表。

## 检查项（10 项，固定顺序）

1. 文件存在：字节数、最后修改时间
2. YAML 语法：能不能解析、顶层是不是 mapping
3. 编码与换行：有没有 BOM、CRLF 行数、孤立 LF / 孤立 CR
4. 默认模型字段：`model.default` / `provider` / `base_url` / `api_key` 缺一即失败
5. 自定义 provider：每个的 key、base_url、模型数量
6. 模型与服务商对齐：provider 名在不在列表、base_url / api_key 是否与条目一致
7. 自检：调用 `hermes config check`，看版本号与退出码
8. 凭据池：目标 provider 有几把 key，各自可用 / 已耗尽 / 空条目
9. 配置备份：份数、最新时间、能不能解析
10. 风险项：占位符 key、明文 http、多 provider 复用同一把 key

每项输出 `[ OK ] / [警告] / [失败] / [跳过]` 四态，失败和警告下面直接写怎么修。
**任何一项失败，退出码为 1**，可以直接接到更新脚本后面。

## 用法

```
python hermes_config_doctor.py                 # 体检
python hermes_config_doctor.py backup          # 备份到 config-backups/，留最近 20 份
python hermes_config_doctor.py list            # 列出备份，标正常/损坏
python hermes_config_doctor.py restore --latest-good   # 从最近一个能解析的备份还原
python hermes_config_doctor.py --config <路径> # 体检任意配置文件
```

## 验证方式

构造了三份坏配置跑过：坏 YAML（少缩进）、缺 `api_key`、provider 名不存在。
三种情况的报错项和跳过的后续项都与预期一致，退出码都是 1。

纯标准库 + PyYAML，没有第三方依赖，不联网。
