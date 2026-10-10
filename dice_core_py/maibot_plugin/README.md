# MaiBot 适配器

这个目录是 MaiBot 第三方插件。MaiBot 自己负责通过 QQ 平台接收消息；插件监听
`ON_MESSAGE_PRE_PROCESS`，命中骰子前缀后调用 `trpg-dice-core` 的 `CommandRouter`，
再通过 `ctx.send.text()` 回复到原聊天流，并阻止消息继续进入 MaiBot 对话链。

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

默认前缀与原 Dice! 核心一致，并额外支持 MaiBot 常用的 `/`：`.`、`/`、`。`、`．`、`!`、`！`。例如：

```text
.r 2d6+3
。rc 幸运
.coc7
.st name50
```

任意以配置前缀开头的消息都会交给骰子核心；包括未知指令在内，都会回复错误信息并
被插件拦截，不会继续触发 MaiBot 的普通对话。

## 版本说明

适配器依赖 `maibot-plugin-sdk >= 2.0` 的 `EventHandler` 接口。它不导入 MaiBot 的
`src.*` 私有模块，只使用公开 SDK 和 `trpg-dice-core`，因此 QQ/OneBot 传输逻辑仍由
MaiBot 负责。
