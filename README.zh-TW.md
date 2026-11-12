# localize

[English](README.md) | [简体中文](README.zh-CN.md) | **繁體中文**

一個 [Agent Skills](https://agentskills.io) skill（可在 Claude Code、Codex、Gemini CLI、OpenCode 以及其他支援此格式的 agent 中使用），用於將網站、網頁應用程式、行動應用程式和桌面軟體在地化為其他語言，並透過一系列檢查確保翻譯準確。

準確的介面翻譯總會以可預見的方式出錯：單一詞的標籤脫離上下文被翻譯，一個產品術語被譯成三種說法，`{placeholder}` 遭到破壞，俄語或阿拉伯語的複數用錯，德語標籤長到塞不進按鈕。這個 skill 在每一種問題前面都放了一道檢查或一個上下文來源：

| 風險 | skill 的對策 |
|---|---|
| 意思模糊的短標籤 | `context` 找出每個字串在程式碼中的使用位置 |
| 術語不一致 | 由 `check` 強制執行的術語表（品牌名稱和命令列選項不參與比對，並可列出多個可接受的形式） |
| 預留位置和標記（markup）遭到破壞 | `check` 比對 `{x}`、`{{x}}`、`%s`、`%1$s`、`%@`、ICU 引數、HTML 標籤和換行 |
| 意思偏移 | `blind` 和 `backtrans`：盲回譯，並依偏移程度排序 |
| 複數 | `check` 知道 75 種語言各需要哪些複數形式，ICU 複數、i18next 的 `_one`/`_few` 群組、gettext 的 `msgstr[i]` 組或 Android 的 `<plurals>` 缺少其中任何一種都會報錯 |
| 長度和書寫系統問題 | 字串過長或未使用目標書寫系統時發出警告；去掉或多加結尾的 `…` 會報錯 |
| 英文原文有修改 | `rekey` 在英文只改了大小寫、標點或空格時沿用原有翻譯，其他修改都連同舊譯文一起列出 |
| 審閱時改得太多 | 工作流程將修正和偏好分開，`diff` 為審閱者列出每一處修改 |
| 地區變體 | `regional` 只保留 es-MX 相對於 es 改動過的列，並拒絕處理書寫系統不同的變體 |
| 由右至左（RTL）和版面配置 | 工作流程中的一份檢查清單；介面必須親眼看過 |
| 可靠性聲明 | 專案中的審閱狀態紀錄，使用從 `machine` 到 `native-line-by-line` 的固定等級；法律、付款和醫療文字交給母語審閱者 |
| README 與文件 | `md-split` 和 `md-build` 會把 Markdown 拆成片段（包含程式碼註解和圖片的替代文字），再組合回去；行內程式碼、連結或 URL 遭到修改，頁內錨點失效，或粗體無法正常顯示時，都會報錯 |
| 簡體與繁體中文 | 用錯書寫系統的字會發出警告，另附 zh-TW 的用詞與排版指南 |

## 格式

JSON（扁平或巢狀）以及 `.arb`、`.po`/`.pot`、`.properties`、Android `strings.xml`、iOS `.strings`、`.tsv`，以英文原文為鍵的 JS 或 Python 表格，還有 README 之類的 Markdown 文件。複數項目依每個形式一個 id 讀入。其他格式可以先轉換成扁平 JSON；所有檢查都作用於 `{id: text}`。

## 安裝

複製（clone）到你的 agent 讀取的 skills 資料夾：Codex、Gemini CLI、OpenCode 和大多數其他 agent 使用 `~/.agents/skills/`，Claude Code 使用 `~/.claude/skills/`。

```bash
git clone https://github.com/chrisye96/localize-skill ~/.agents/skills/localize
```

接著請你的 agent 為某個專案新增一種語言（「把這個應用程式翻譯成西班牙文」）。腳本只需要 Python 3.8+ 和標準函式庫：

```bash
python scripts/l10n.py --help
```

## 目錄結構

```
SKILL.md                              agent 遵循的工作流程
scripts/l10n.py                       export, context, check, emit, md-split, md-build, rekey, regional, diff, blind, backtrans
references/english-keyed-tables.md    以英文原文為鍵的專案
references/readme.md                  翻譯 README 或其他 Markdown 文件
references/chinese.md                 簡體與繁體中文：用詞、排版、如何引用介面文字
references/review-status.md           審閱狀態紀錄：等級和範本
references/phone-remote.md            建置和測試這個 skill 時使用的實際案例
tests/test_l10n.py                    python -m unittest discover -s tests
```

## 測試情況

在 [phone-remote](https://github.com/chrisye96/phone-remote) 的暫存副本中新增西班牙文和阿拉伯文：所有檢查都通過，專案本身的 79 項測試都通過，兩種語言都在瀏覽器中以手機寬度檢查過。這次執行發現了什麼，請見 `references/phone-remote.md`。

> 本文由英文版機器翻譯而來，尚未經過母語人士逐行審閱。如有出入，以 [English](README.md) 版本為準。
