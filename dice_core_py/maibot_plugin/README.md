# MaiBot 适配器

这个目录是 MaiBot 第三方插件。MaiBot 自己负责通过 QQ 平台接收消息；插件监听
`@Command` 组件使用正则只匹配以 `.` 或 `。` 前缀开头的消息，命中后调用
`trpg-dice-core` 的 `CommandRouter`，再通过 `ctx.send.text()` 回复到原聊天流，并以命令
拦截级别阻止消息继续进入 MaiBot 对话链。

## 安装

1. 安装独立骰子核心（建议在 MaiBot 使用的同一个 Python 环境中执行）：

   ```bash
   python -m pip install -e /path/to/Dice/dice_core_py
   ```

2. 将整个 `maibot_plugin/` 目录复制到 MaiBot 的 `plugins/` 目录，目录结构必须保留：

   ```text
   plugins/
   └── maibot_plugin/
       ├── _manifest.json
       ├── plugin.py
       └── adapter.py
   ```

3. 启动或重载 MaiBot 插件。首次加载后，在插件配置中可以调整是否只处理 QQ、
   以及触发前缀。

插件数据使用 MaiBot 提供的 `ctx.paths.data_dir`，人物卡、昵称和绑定会保存在该插件
专属目录，不会写入源码目录。

## 支持的触发形式

为了不劫持其他插件的命令，本插件的 `@Command` 匹配规则只接受以 `.` 或 `。` 开头的
指令，其余符号（如 `/`、`!`、`．`）前缀的消息一律不进入本插件。例如：

```text
.r 2d6+3
。rc 幸运
.coc7
.st name50
```

`.bot off` 可关闭当前群的骰子指令处理，`.bot on` 恢复处理。开关状态保存在插件
数据目录的 `config/bot_state.json`，只对当前群生效；私聊不支持该开关。

只有以配置前缀开头、且命中骰子命令的消息才会交给骰子核心并被拦截。
未知指令（如 `.hello`、`.random`、`.status`）不回复、不拦截，交由其他插件或
MaiBot 的普通对话处理。已识别骰子命令的参数错误（如 `.r 1d0`）仍会回复错误提示。

## 版本说明

骰子核心的回执支持原版消息模板。模板按插件数据目录保存于
`config/custom_messages.json`，可在 QQ 中使用 `.str` 查看、设置、重置消息键；
例如 `.str strRollDice {pc} => {res}`。模板支持 `{pc}`、`{nick}`、`{res}`、`{reason}`、
`{sample}`、`{ran}`、`{case}`、`{grade}`、`{br}`、`{at}` 等占位符。

适配器依赖 `maibot-plugin-sdk >= 2.0` 的 `EventHandler` 接口。它不导入 MaiBot 的
`src.*` 私有模块，只使用公开 SDK 和 `trpg-dice-core`，因此 QQ/OneBot 传输逻辑仍由
MaiBot 负责。`.admin`、`.cloud`、`.link`、`.mod`、`.user`、`.system`、`.bot`、`.reply`
等平台边界命令不由本插件匹配或拦截，交由其他插件或宿主平台提供；独立核心仍可
返回明确的边界结果。
