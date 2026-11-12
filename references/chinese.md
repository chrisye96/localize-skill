# Simplified and Traditional Chinese

For UI strings and documents alike. `check` warns when a zh-CN text contains Traditional characters or a zh-TW text Simplified ones (code spans excepted); everything else here is judgement.

## Pick the variant

- zh-CN (Simplified, mainland China) and zh-TW (Traditional, Taiwan) are two localizations, not one text in two scripts. zh-HK is a third: Traditional characters with Hong Kong vocabulary. When the user says "繁体" without a region, pick zh-TW and say so.
- Write zh-TW from the English, never by converting the zh-CN. Converted text has Traditional characters and mainland words, which a Taiwan reader notices at once.

## Vocabulary that differs

| English | zh-CN | zh-TW |
|---|---|---|
| file / folder | 文件 / 文件夹 | 檔案 / 資料夾 |
| project / code / program | 项目 / 代码 / 程序 | 專案 / 程式碼 / 程式 |
| app / software | 应用 / 软件 | 應用程式 / 軟體 |
| default / support / settings | 默认 / 支持 / 设置 | 預設 / 支援 / 設定 |
| interface / menu / screen | 界面 / 菜单 / 屏幕 | 介面 / 選單 / 螢幕 |
| network / information / quality | 网络 / 信息 / 质量 | 網路 / 資訊 / 品質 |
| user / string / type (data) | 用户 / 字符串 / 类型 | 使用者 / 字串 / 型別 |
| install / log in / upload | 安装 / 登录 / 上传 | 安裝 / 登入 / 上傳 |
| repository / directory / command line | 仓库 / 目录 / 命令行 | 儲存庫 / 目錄 / 命令列 |
| video / mouse / click | 视频 / 鼠标 / 点击 | 影片 / 滑鼠 / 點選 |
| shortcut / plugin / dependency | 快捷键 / 插件 / 依赖 | 快速鍵 / 外掛程式 / 相依套件 |
| port / local machine / backspace | 端口 / 本地 / 退格键 | 連接埠 / 本機 / 倒退鍵 |
| license / via / create / optimize | 许可证 / 通过 / 创建 / 优化 | 授權條款 / 透過 / 建立 / 最佳化 |
| table row / table column | 行 / 列 | 列 / 欄 (reversed) |
| daylight saving time | 夏令时 | 日光節約時間 |

Place names differ too (Calgary: 卡尔加里, 卡加利). A product's own terminology overrides this table: Lightroom Classic says 檔案夾 and 增效模組 in zh-TW, not 資料夾 and 外掛程式.

## Typography

- Full-width punctuation in Chinese sentences: ，。：；（）！？. Quotation marks: zh-CN “ ”, zh-TW 「 」.
- A space between Chinese and Latin letters or digits (`在 iPad 上`, `79 个测试`), none next to full-width punctuation. Follow the project's existing Chinese text if it does otherwise.
- Dashes: follow the project's existing Chinese text. Where it has none, an English — becomes a comma, colon or parentheses rather than ——.
- Markdown bold: put punctuation outside the bold (`**完成**。`), or a space after it; see `readme.md`.

## Quoting a UI the product does not show in this variant

A README or help text often quotes labels (「有新版本」). When the product's own UI exists in this variant, quote it exactly. When it does not (the app only ships zh-CN, or English), quote what the reader will actually see:

- The app shows Simplified Chinese to Taiwan users: quote that wording in Traditional characters (「開機自動啟動」 for 开机自动启动, not the Taiwan phrasing 「登入時自動啟動」), so the reader can match it on screen. The prose around it stays in Taiwan wording.
- The app shows English: keep the English label (**Profile**), with a Chinese gloss once where it helps. The glossary accepts an English term kept as it is.
- An example the user types into the product stays in the script the product understands, even in a zh-TW text, when the product only parses Simplified (`完成项目报告`). Say so in your report, and suggest localizing the product's UI if Taiwan readers matter.
