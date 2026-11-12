# localize

[English](README.md) | **简体中文** | [繁體中文](README.zh-TW.md)

一个 [Agent Skills](https://agentskills.io) skill（可在 Claude Code、Codex、Gemini CLI、OpenCode 以及其他支持该格式的 agent 中使用），用于把网站、Web 应用、移动应用和桌面软件本地化成其他语言，并通过一系列检查保证翻译准确。

准确的界面翻译总会以可预见的方式出错：单个词的标签脱离上下文被翻译，一个产品术语被译成三种说法，`{placeholder}` 被破坏，俄语或阿拉伯语的复数用错，德语标签长得塞不进按钮。这个 skill 在每一种问题前面都放了一道检查或一个上下文来源：

| 风险 | skill 的对策 |
|---|---|
| 含义模糊的短标签 | `context` 找出每个字符串在代码中的使用位置 |
| 术语不一致 | 由 `check` 强制执行的术语表（品牌名和命令行选项不参与匹配，并可列出多个可接受的形式） |
| 占位符和标记（markup）被破坏 | `check` 比对 `{x}`、`{{x}}`、`%s`、`%1$s`、`%@`、ICU 参数、HTML 标签和换行 |
| 含义偏移 | `blind` 和 `backtrans`：盲回译，并按偏移程度排序 |
| 复数 | `check` 知道 75 种语言各需要哪些复数形式，ICU 复数、i18next 的 `_one`/`_few` 组、gettext 的 `msgstr[i]` 组或 Android 的 `<plurals>` 缺少其中任何一种都会报错 |
| 长度和书写系统问题 | 字符串过长或没有使用目标书写系统时发出警告；去掉或多加结尾的 `…` 会报错 |
| 英文原文有改动 | `rekey` 在英文只改了大小写、标点或空格时沿用原有翻译，其他改动都连同旧译文一起列出 |
| 审校时改得太多 | 工作流程把纠错和偏好分开，`diff` 为审校者列出每一处改动 |
| 地区变体 | `regional` 只保留 es-MX 相对 es 改动过的行，并拒绝处理书写系统不同的变体 |
| 从右到左（RTL）和布局 | 工作流程中的一份检查清单；界面必须亲眼看过 |
| 可靠性声明 | 项目中的审校状态记录，使用从 `machine` 到 `native-line-by-line` 的固定档位；法律、支付和医疗文本交给母语审校者 |
| README 和文档 | `md-split` 和 `md-build` 把 Markdown 拆成片段（包括代码注释和图片的替代文本）再拼回去；行内代码、链接或 URL 被改动，页内锚点失效，或粗体无法正常显示时都会报错 |
| 简体和繁体中文 | 用错书写系统的字会发出警告，另附 zh-TW 的用词和排版指南 |

## 格式

JSON（扁平或嵌套）以及 `.arb`、`.po`/`.pot`、`.properties`、Android `strings.xml`、iOS `.strings`、`.tsv`，以英文原文为键的 JS 或 Python 表，还有 README 之类的 Markdown 文档。复数条目按每个形式一个 id 读入。其他格式可以先转换成扁平 JSON；所有检查都作用于 `{id: text}`。

## 安装

克隆到你的 agent 读取的 skills 目录：Codex、Gemini CLI、OpenCode 和大多数其他 agent 用 `~/.agents/skills/`，Claude Code 用 `~/.claude/skills/`。

```bash
git clone https://github.com/chrisye96/localize-skill ~/.agents/skills/localize
```

然后让你的 agent 给某个项目添加一种语言（“把这个应用翻译成西班牙语”）。脚本只需要 Python 3.8+ 和标准库：

```bash
python scripts/l10n.py --help
```

## 目录结构

```
SKILL.md                              agent 遵循的工作流程
scripts/l10n.py                       export, context, check, emit, md-split, md-build, rekey, regional, diff, blind, backtrans
references/english-keyed-tables.md    以英文原文为键的项目
references/readme.md                  翻译 README 或其他 Markdown 文档
references/chinese.md                 简体和繁体中文：用词、排版、如何引用界面文字
references/review-status.md           审校状态记录：档位和模板
references/phone-remote.md            构建并测试这个 skill 时用的实际案例
tests/test_l10n.py                    python -m unittest discover -s tests
```

## 测试情况

在 [phone-remote](https://github.com/chrisye96/phone-remote) 的临时副本中添加西班牙语和阿拉伯语：所有检查都通过，项目自身的 79 个测试都通过，两种语言都在浏览器中以手机宽度检查过。这次运行发现了什么，见 `references/phone-remote.md`。

> 本文由英文版机器翻译而来，尚未经过母语者逐行审校。如有出入，以 [English](README.md) 版本为准。
