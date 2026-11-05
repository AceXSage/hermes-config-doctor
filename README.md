# hermes-config-doctor

一个 Python 文件，干三件事：体检 Hermes 的 `config.yaml`、给它存备份、坏了从备份还原。
单文件，不装框架，复制走就能跑。

## 为什么写

我的配置是手改的。改错一次缩进、把 key 贴成占位符、provider 换了名字忘了同步，Hermes 就起不来，
而报错只说解析失败，剩下的靠猜。所以我把踩过的坑排成固定 10 项，每项给一句结论，能修的顺手给修法。

它不定位到行号。第 2 项只把 YAML 异常的第一行截 70 个字打出来，行号经常被切掉。
要精确到行列，还是自己跑一句 `python -c "import yaml,sys;yaml.safe_load(open(sys.argv[1],encoding='utf-8').read())" 你的config.yaml`。

## 环境要求

- Windows 上用 `hermes-config-doctor.cmd`；macOS / Linux 直接 `python3 hermes_config_doctor.py`，没有 `.cmd`，而且要自己给 `--config`（原因见第四条）
- Python 3.7 以上。脚本用了 `subprocess.run(capture_output=True, text=True)`，这两个参数是 3.7 才加的；我只在 3.14 上跑过，`.cmd` 里的提示写的是 3.8+
- 第三方依赖只有一个 PyYAML。其余全是标准库：`datetime` `glob` `json` `os` `shutil` `subprocess` `sys` `unicodedata`。脚本自己不联网
- 配置路径是这么拼的：`os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")` 再加 `config.yaml`。
  Windows 上是 `%LOCALAPPDATA%\hermes\config.yaml`，一般是 `C:\Users\<你>\AppData\Local\hermes\config.yaml`。
  脚本没有 XDG 那套逻辑——Linux / macOS 上 `LOCALAPPDATA` 是空的，拼出来就是相对路径 `hermes/config.yaml`，
  等于在你当前目录下面找。所以非 Windows 必须用 `--config` 指过去，比如
  `python3 hermes_config_doctor.py check --config ~/.local/share/hermes/config.yaml`。
  备份目录同理，始终是 `%LOCALAPPDATA%\hermes\config-backups`，跟 `--config` 无关

没装 PyYAML 的症状：脚本不提示「缺依赖」，第 2 项直接判 `[失败] 解析失败：No module named 'yaml'`，
第 4/5/6/7/8/10 项跟着变「跳过」，第 9 项把已有备份标成「已损坏」。看到这个组合先去装 PyYAML，别改配置文件。

## 三步跑起来

一、装依赖。想干净就建个 venv（`.venv/` 已经在 .gitignore 里）：

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install pyyaml
```

macOS / Linux：

```
python3 -m venv .venv
.venv/bin/python -m pip install pyyaml
```

二、拿代码：

```
git clone https://github.com/AceXSage/hermes-config-doctor.git
cd hermes-config-doctor
```

三、跑第一次体检：

```
.venv\Scripts\python hermes_config_doctor.py check
```

Windows 上如果系统 Python 里已经有 pyyaml，直接双击 `hermes-config-doctor.cmd` 也行。
但 `.cmd` 固定先找 `py -3`、找不到再找 `python`，不会用你建的 `.venv`；
要走 venv 就按上面显式调 `.venv\Scripts\python`。

装 PyYAML 那句别写成光秃秃的 `pip install pyyaml`。机器上有好几个 Python 时，它装到哪个解释器看运气，
装错的表现就是 `.cmd` 报 `[ERROR] PyYAML missing`。

## 首次运行会生成什么

- `check` 不写文件、不建目录。我用临时 `LOCALAPPDATA` 比对过跑前跑后，目录里只有原来那份 `config.yaml`
- `backup` 才建 `config-backups/`，文件名 `config-<YYYYmmdd-HHMMSS>.yaml`，内容是原样复制。
  存完按文件名排序，只留最后 20 份（含刚存的那份），删掉的逐行打印「清理旧备份：…」。实测堆 25 份再跑一次 backup，剩 20
- `restore` 覆盖之前，把当前这份配置复制成 `%LOCALAPPDATA%\hermes\config-broken-<YYYYmmdd-HHMMSS>.yaml`。
  它放在 hermes 根目录，不在 config-backups 里，`list` 看不到，要自己翻
- 没有 `config.yaml` 的时候跑 `backup`，会甩一个 FileNotFoundError 栈（退出码 1），不会给一句人话提示

## 检查项（10 项，固定顺序，名字照抄程序输出）

| # | 输出名 | 查什么 | 什么算警告、什么算失败 |
|---|---|---|---|
| 1 | 配置文件存在 | `os.path.isfile`，文件大小，最后修改时间 | 小于等于 500 字节 → 警告（怕被截断）；文件不在 → 失败，而且只出这一项，2-10 全不跑 |
| 2 | YAML 语法 | 整份文件丢给 `yaml.safe_load` | 顶层不是 dict → 失败；抛异常 → 失败，只打异常第一行前 70 字 |
| 3 | 编码与换行 | 数 BOM、`\r\n` 行数、孤立 `\n`、孤立 `\r` | 有孤立 LF 或孤立 CR → 警告。不带 BOM 不扣分；整个文件是 LF 会一直挂这一条（修法写的是统一成 CRLF） |
| 4 | 默认模型字段 | `model.default` / `model.provider` / `model.base_url` / `model.api_key` 四个都非空 | 缺哪个列哪个 → 失败 |
| 5 | 自定义 provider | `custom_providers` 每条的 `api_key`、`base_url`，以及 `models` 里的键数 | 列表为空 → 警告（只用内置厂商时正常）；有条目缺 key 或 base_url → 失败 |
| 6 | 模型与服务商对齐 | 拿 `model.provider` 去 `custom_providers` 里按 `name` 找，找到再比 `base_url`（去掉尾部 `/`）和 `api_key` | 名字找不到 → 失败；找到了但 base_url 或 api_key 有一处不同 → 警告；`model.provider` 空 → 警告「未比对」 |
| 7 | Hermes 自检 | 调 `hermes config check`（shell，90 秒超时），抓 `Config version` 那行和退出码 | 输出里出现 `error`（不分大小写）或退出码非 0 → 失败；`hermes` 不在 PATH 上也算这条，显示「无版本信息，退出码 1」；调用本身抛异常（比如卡过 90 秒）→ 警告；用 `--config` 指到别的文件 → 打 `[ OK ]` 写「跳过（这次分析的是外部文件，不跑自检）」 |
| 8 | 凭据池 | `auth.json` 里 `credential_pool["custom:<model.provider>"]` 的每条：有没有 `access_token` 或 `source: config:*`、`last_status`、`last_error_code` | 没有 auth.json → 警告；provider 对不上池子，或条目全空 → 失败；有能用的但存在 exhausted → 警告；其余 OK。每条显示 `可用` / `已耗尽(429)` / `空条目` |
| 9 | 配置备份 | `config-backups/config-*.yaml` 的份数，最新那份的名字、多少小时前、能不能 safe_load | 一份都没有 → 警告；能解析且在 14 天以内 → OK，超期或最新那份坏了 → 警告 |
| 10 | 风险项 | 只扫 `custom_providers`：`api_key` 非空、不以 `http` 开头、长度小于 20 的；`base_url` 不是 `https://` 开头的；几个 provider 共用同一把 key 的 | 命中任意一条 → 警告；都没命中 → OK。它不看 `model.api_key` |

代码里四个状态的常量是 `OK / 警告 / 失败 / 跳过`，屏幕上是 `[ OK ]` `[警告]` `[失败]` `[跳过]`。
`跳过` 只在第 2 项解析失败时出现，落在第 4、5、6、7、8、10 项，文字统一是「无法判断：先修第 2 项 YAML 语法」。
只有警告和失败下面会多一行「↳ 怎么修」。

退出码只有 0 和 1 两种（`sys.exit(0 if main() == 0 else 1)`，内部返回值大于 1 也折成 1）：

- `check`：有失败项 → 1；只有警告和跳过 → 0。警告不算失败，我那份 5 条警告的配置退出码就是 0
- `restore` 还原成功：它紧接着再体检一次，退出码用那次体检的结果，所以还原完配置还是坏的，照样 1
- `restore` 没有备份、指定的文件名不存在、备份全都解析不了 → 1
- `backup` 成功、`list` → 0
- 命令拼错 → 打印 usage，1；`--config` 后面没跟路径 → IndexError 栈，1

## 用法

```
hermes-config-doctor.cmd                              # 双击；没参数时最后会 pause 等你按回车
hermes-config-doctor.cmd check
hermes-config-doctor.cmd backup
hermes-config-doctor.cmd list
hermes-config-doctor.cmd restore --latest-good

python hermes_config_doctor.py check
python hermes_config_doctor.py backup
python hermes_config_doctor.py list
python hermes_config_doctor.py restore --latest-good
python hermes_config_doctor.py restore config-20261105-153000.yaml
python hermes_config_doctor.py check --config D:/tmp/other-config.yaml
```

- `list`：一张表，列是 备份文件 / 大小 / 状态 / 改于。状态只有 `正常` 和 `损坏`，判据是能不能 safe_load 成 dict。没有备份就一句提示
- `restore --latest-good`：按文件名从新到旧走，碰到解析不了的打「跳过损坏的备份」继续往下，拿第一份好的覆盖上去；
  覆盖前留 `config-broken-<ts>.yaml`；覆盖后立刻体检并打印
- 不带参数就是 `check`，写 `体检` 也认
- `--config` 放在命令前后都行（`check --config X` 和 `--config X check` 都试过）。它只换体检对象：
  备份照旧写进默认的 config-backups，还原时往你给的路径写，而那份 `config-broken-*` 留档还是落在 hermes 根目录
- `.cmd` 会先 `chcp 65001` 再 `cd` 到脚本所在目录，所以中文不乱码，给相对路径的 `--config` 是相对仓库算的

## 适用范围

- 是为 Hermes Agent 的 `config.yaml` 写的。第 4-6、8、10 项读 `model` / `custom_providers` / auth.json 里的 `credential_pool`，第 7 项找的是 PATH 上的 `hermes` 命令，第 9 项看 hermes 目录下的 `config-backups`
- 拿它体检别的 YAML 基本没用：第 1、2、3、9、10 项还能给点信息，第 4 项会因为缺 `model.*` 直接判失败（不是跳过），第 5、6 项给警告，退出码 1。要通用校验 YAML 换个工具
- 三种会崩、只在 stderr 留栈的情况：顶层解析成非空 list 或纯标量（第 4 项对 data 调 `.get()`）；`config.yaml` 不存在时跑 `backup`；`config.yaml` 不存在时跑 `restore`（复制当前文件那步会抛）。这三种退出码都是 1，但不出报告
- 第 7 项跑的是机器上真实的 `hermes config check`，看的是默认路径那份配置，和 `--config` 指谁无关——所以指到别处时它干脆跳过。没装 Hermes 的机器上这项必然失败（`hermes` 命令找不到，退出码 1），所以别把它接到没有 Hermes 的 CI 上。至少在我这台机器上，这个命令没改过 `config.yaml` 的修改时间

## 验证方式

不用碰真配置也能复现：把 `LOCALAPPDATA` 临时指到一个空目录，脚本就会去那儿找 `hermes/config.yaml`。

```
# Windows cmd
set LOCALAPPDATA=D:\tmp\lab
mkdir %LOCALAPPDATA%\hermes
python hermes_config_doctor.py check & echo 退出码 %errorlevel%

# bash
export LOCALAPPDATA=/d/tmp/lab && mkdir -p "$LOCALAPPDATA/hermes"
python hermes_config_doctor.py check; echo "退出码 $?"
```

我按这个办法造样本跑过的结果：

- 文件不存在：只打第 1 项，退出码 1。这个分支会把报告打两遍（`run_check` 里 render 一次，`main` 里又 render 一次）
- 少缩进的 YAML：第 2 项失败，4/5/6/7/8/10 跳过，第 9 项照常，退出码 1
- 缺 `model.api_key`：第 4 项失败，退出码 1
- `model.provider` 写成列表里没有的名字：第 6 项失败，退出码 1
- 池子里条目全是空：第 8 项失败，退出码 1
- 只有警告的配置（文件偏小、LF 换行、没备份）：退出码 0
- 堆 25 份备份再 backup：剩 20 份
- 把最新那份备份写坏再 `restore --latest-good`：跳过坏的、还原次新的一份、留 `config-broken-*.yaml`、还原后体检退出 0

依赖就 PyYAML 一个，其余标准库。
