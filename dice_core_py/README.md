# TRPG Dice Core

`TRPG Dice Core` 是从原 QQ TRPG 骰子项目中拆出的 Python 3 领域模块。它只负责骰子、人物卡、来源绑定、会话状态和 JSON 持久化，不负责接收或发送 QQ/OneBot 消息。

外部适配器的职责只有两步：

1. 将平台消息转换成 `ActorRef`、`MessageSource`、`MessageContext`。
2. 调用本模块并处理结构化返回值。

核心源码不依赖 QQ SDK、OneBot、CQ 码、网络接口、GUI 或消息事件对象。

## 目录

- [安装和运行](#安装和运行)
- [功能总览](#功能总览)
- [骰子表达式](#骰子表达式)
- [奖励骰和惩罚骰](#奖励骰和惩罚骰)
- [Fate/Fudge 骰](#fatefudge-骰)
- [骰池和 COC 检定](#骰池和-coc-检定)
- [随机源](#随机源)
- [结构化结果](#结构化结果)
- [来源、用户和昵称](#来源用户和昵称)
- [人物卡](#人物卡)
- [DiceEngine 门面](#diceengine-门面)
- [命令总入口](#命令总入口)
- [消息模板](#消息模板)
- [MaiBot 适配器](#maibot-适配器)
- [轮盘骰](#轮盘骰)
- [牌堆](#牌堆)
- [L5R 特殊骰](#l5r-特殊骰)
- [会话](#会话)
- [JSON 存储](#json-存储)
- [错误类型](#错误类型)
- [测试](#测试)
- [当前不包含的功能](#当前不包含的功能)

## 安装和运行

### 初始化 Python 3 环境

```bash
cd dice_core_py
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

项目只使用 Python 标准库，没有第三方运行时依赖。开发环境要求 Python `>=3.10`。

### 命令行

安装后可以直接运行：

```bash
trpg-dice
trpg-dice '2d6+3'
trpg-dice 'b2+4' --json
```

不带表达式时默认投 `1d100`。普通模式输出人类可读文本，`--json` 输出结构化 JSON。

也可以不安装脚本，直接运行模块：

```bash
python -m trpg_dice.cli '4d6k3'
python -m trpg_dice.cli '1d100' --json
```

### Python 导入

所有主要类型都从 `trpg_dice` 顶层导出：

```python
from trpg_dice import DiceRoller, SequenceRandomSource

roller = DiceRoller(SequenceRandomSource([4, 5]))
result = roller.roll("2d6")
print(result.total)
```

## 功能总览

| 功能 | 公开入口 | 独立测试脚本 |
| --- | --- | --- |
| 通用骰子和算术表达式 | `DiceRoller.roll()`、`normalize()` | `tests/test_roll_expressions.py`、`tests/test_roller.py` |
| 奖励骰/惩罚骰 | `DiceRoller.bonus()`、`penalty()`、`B/P` 语法 | `tests/test_bonus_penalty.py` |
| Fate/Fudge 骰 | `F`、`DF`、`NdF`、`Nf` | `tests/test_fate_dice.py` |
| 骰池、爆骰 | `DiceRoller.pool()` | `tests/test_pool_and_coc.py` |
| COC 成功等级 | `coc_success_level()`、`coc_check()` | `tests/test_pool_and_coc.py` |
| 随机源 | `SystemRandomSource`、`SeededRandomSource`、`SequenceRandomSource` | `tests/test_randomness.py` |
| 身份模型和返回模型 | `ActorRef`、`MessageSource`、`MessageContext`、结果类 | `tests/test_models.py` |
| 昵称解析和管理 | `NicknameService` | `tests/test_profiles.py`、`tests/test_identity.py` |
| 人物卡 CRUD 和绑定 | `CharacterService` | `tests/test_profiles.py`、`tests/test_identity.py` |
| 统一调用门面 | `DiceEngine` | `tests/test_engine.py` |
| 无放回轮盘骰 | `Roulette` | `tests/test_roulette.py` |
| 带权重牌堆 | `Deck`、`DeckEntry` | `tests/test_deck.py` |
| L5R 白骰/黑骰 | `L5RDicePool`、`L5RDie` | `tests/test_l5r.py` |
| 会话和会话成员 | `DiceSession` | `tests/test_session.py` |
| JSON 文件存储 | `JsonStore`、`ProfileRepository`、`SessionRepository` | `tests/test_storage.py` |
| CLI | `trpg_dice.cli` | `tests/test_cli.py` |
| 指令总入口 | `CommandRouter`、`CommandRequest`、`CommandResponse` | `tests/test_commands.py`、`tests/test_command_cli.py` |

原有的 `tests/test_roller.py`、`tests/test_identity.py`、`tests/test_special.py` 是兼容性回归测试；按功能拆分的脚本提供更细的覆盖。

## 骰子表达式

### 基本语法

`DiceRoller` 支持整数、标准骰子、加减乘除、括号和保留最高骰：

| 语法 | 含义 | 示例 |
| --- | --- | --- |
| `dM` | 投一颗 `M` 面骰 | `d100` |
| `NdM` | 投 `N` 颗 `M` 面骰并求和 | `2d6` |
| 整数 | 常数项 | `+3`、`-10` |
| `+`、`-` | 加减项 | `2d6+3-1d4` |
| `*`、`x`、`X` | 乘法 | `2d6x3` |
| `/` | 整数除法 | `2d6/2` |
| `(...)` | 分组 | `(2d6+3)*2` |
| `NdMKk` | 投 `N` 颗、保留最高 `k` 颗 | `4d6k3` |

运算符优先级与普通算术一致：乘除高于加减，括号最高。除法向零截断，例如 `-5/2 == -2`。表达式中的空白会被忽略，字母不区分大小写，`x`/`X` 会规范化为 `*`。

```python
from trpg_dice import DiceRoller, SequenceRandomSource

roller = DiceRoller(SequenceRandomSource([1, 6]))
result = roller.roll("2d6+3")
assert result.total == 10
assert result.terms[0].rolls == (1, 6)
```

### 默认值和规范化

```python
roller = DiceRoller(default_sides=20)
assert roller.normalize("") == "1d20"
assert roller.normalize("D") == "1d20"
assert roller.normalize("2D6x3") == "2d6*3"
```

默认面数为 `100`，可以通过 `default_sides` 修改。`normalize()` 只解析和规范化，不消耗随机源。

### 保留最高骰

`4d6k3` 会投四颗 D6，只把最高三颗计入总和。结果中的 `kept` 和 `dropped` 保存保留与舍弃的点数；当点数相同，按原始投掷顺序稳定处理。

### 限制

默认安全限制由 `RollLimits` 定义：

| 配置 | 默认值 | 说明 |
| --- | ---: | --- |
| `max_expression_length` | `512` | 表达式最大字符数 |
| `max_dice_count` | `1000` | 单个骰子项最大骰数 |
| `max_sides` | `1000000` | 最大面数 |
| `max_special_dice` | `9` | 单个奖励/惩罚骰项最大额外骰数 |
| `max_total_rolls` | `10000` | 一次表达式最多实际随机次数 |
| `max_abs_total` | `10**15` | 结果绝对值上限 |

可以注入自定义限制：

```python
from trpg_dice import DiceRoller, RollLimits

roller = DiceRoller(limits=RollLimits(max_dice_count=20))
```

## 奖励骰和惩罚骰

这是原项目 COC 十位骰语义的独立实现：先投一颗 D100，再投额外十位骰。

| 语法 | 含义 |
| --- | --- |
| `B` 或 `B1` | 一个奖励骰 |
| `B2` | 两个奖励骰 |
| `P` 或 `P1` | 一个惩罚骰 |
| `P2` | 两个惩罚骰 |

- 奖励骰选择最小十位。
- 惩罚骰选择最大十位。
- 个位为 `0` 时，额外骰的 `1..10` 直接作为十位，其中 `10` 表示十位 `0` 的 `100` 语义。
- 个位非 `0` 时，额外骰 `1..10` 转换为 `0..9`。
- 额外骰数量范围为 `1..9`。

```python
from trpg_dice import DiceRoller, SequenceRandomSource

bonus = DiceRoller(SequenceRandomSource([56, 3])).bonus()
assert bonus.total == 26

penalty = DiceRoller(SequenceRandomSource([56, 8])).penalty()
assert penalty.total == 76
```

奖励/惩罚骰也可以作为表达式项使用，例如 `B2+5`。

## Fate/Fudge 骰

支持以下等价或兼容写法：

| 写法 | 含义 |
| --- | --- |
| `F` | 四颗 Fate 骰 |
| `DF` | 四颗 Fate 骰 |
| `4DF` | 四颗 Fate 骰 |
| `6F`、`6f` | 六颗 Fate 骰 |

每颗骰子等概率产生 `-1`、`0`、`+1`，结果中的 `rolls` 保存每颗骰子的值，`subtotal` 为总和。

```python
result = DiceRoller(SequenceRandomSource([-1, 0, 1, 1])).roll("4df")
assert result.total == 1
assert result.terms[0].rolls == (-1, 0, 1, 1)
```

## 骰池和 COC 检定

### 骰池

`pool()` 默认使用 D10，达到目标值算一个成功，达到 `explode_at` 会追加投掷：

```python
from trpg_dice import DiceRoller, SequenceRandomSource

pool = DiceRoller(SequenceRandomSource([8, 10, 7])).pool(2)
assert pool.rolls == (8, 10, 7)
assert pool.successes == 2
```

参数：

- `count`：初始骰数。
- `sides`：面数，默认 `10`。
- `target`：成功阈值，默认 `8`。
- `explode_at`：达到该值追加投掷，默认 `10`；传 `None` 关闭爆骰。
- `max_explosions`：爆骰保护上限，默认 `1000`。

`PoolResult` 返回 `count`、`sides`、`target`、`explode_at`、全部 `rolls` 和 `successes`。

### COC 成功等级

```python
from trpg_dice import DiceRoller, SequenceRandomSource, coc_success_level

assert coc_success_level(1, 50) == "critical"
assert coc_success_level(100, 50) == "fumble"
check = DiceRoller(SequenceRandomSource([1])).coc_check(50)
assert check.success
```

`coc_success_level(result, target, rule)` 支持规则编号 `0..7`，返回：

- `critical`
- `extreme_success`
- `hard_success`
- `regular_success`
- `failure`
- `fumble`

`coc_check()` 返回 `CheckResult`，包括目标值、实际 `RollResult`、等级、规则编号和 `success` 布尔值。可以传 `bonus_dice` 或 `penalty_dice`，二者不能同时使用。

## 随机源

所有随机源均实现 `randint(lower, upper)`，上下界都是包含的。

| 类型 | 用途 |
| --- | --- |
| `SystemRandomSource` | 生产环境，使用操作系统随机源 |
| `SeededRandomSource(seed)` | 可复现模拟和调试 |
| `SequenceRandomSource(values)` | 单元测试固定序列 |

```python
source = SequenceRandomSource([1, 6])
roller = DiceRoller(source)
assert roller.roll("2d6").total == 7
```

固定序列耗尽会抛出 `RuntimeError`，固定值超出当前 `randint()` 区间会抛出 `ValueError`。生产代码建议使用 `SystemRandomSource`，测试代码建议使用 `SequenceRandomSource`。

## 结构化结果

### `DiceTermResult`

每个骰子项包含：

- `notation`：规范化项，例如 `2d6`、`B1`。
- `kind`：`dice`、`bonus`、`penalty` 或 `fate`。
- `subtotal`：项小计。
- `rolls`：原始点数。
- `kept`、`dropped`：保留骰和舍弃骰。
- `count`、`sides`：骰数和面数。
- `base_roll`、`extra_tens`：奖惩骰的基础 D100 和额外十位。

### `RollResult`

- `expression`：调用方原始表达式。
- `normalized_expression`：规范化表达式。
- `total`：最终总和。
- `terms`：所有随机项的 `DiceTermResult`。
- `to_dict()`：转换为 JSON 可序列化字典。
- `render()`：生成简单人类可读文本。

### 其他结果

- `PoolResult`：骰池结果。
- `CheckResult`：COC 检定结果。
- `RollResponse`：`DiceEngine` 返回的身份、卡片和骰点结果。

核心接口返回数据，不负责发送消息，也不生成 CQ 码。

## 来源、用户和昵称

### `ActorRef`

```python
actor = ActorRef(platform="qq", user_id="10000000000000000001")
```

`platform` 和 `user_id` 都按字符串保存。这样可以避免 JSON/JavaScript 处理大整数 ID 时丢失精度。`actor.key` 是稳定键。

### `MessageSource`

```python
group = MessageSource("qq", "group", "7788")
channel = MessageSource("qq", "channel", "7788", channel_id="9900")
private = MessageSource("qq", "private", "10000000000000000001")
```

字段：

- `platform`：平台名，例如 `qq`、`discord`。
- `kind`：来源类型，例如 `private`、`group`、`channel`、`dm`。
- `source_id`：群、频道、私聊或其他来源 ID。
- `channel_id`：可选的频道子 ID。

完整来源键包含平台、类型、来源 ID 和频道 ID；相同数字 ID 在不同平台或不同来源类型下不会冲突。

### `MessageContext`

```python
context = MessageContext(
    actor=actor,
    source=group,
    account_nickname="账号昵称",
    source_nickname="群内昵称",
)
```

`actor.platform` 必须与 `source.platform` 相同。QQ 适配器可以把收到的 `uid/gid/chid` 转换为这些字段，但核心不会主动查询 QQ 昵称。

### 昵称服务

`NicknameService` 提供：

- `set(actor, name, source=None)`：设置全局或来源级昵称。
- `remove(actor, source=None)`：删除昵称，返回是否实际删除。
- `resolve(context)`：按优先级解析昵称。

解析顺序：

1. 来源级自定义昵称。
2. 全局自定义昵称。
3. `context.source_nickname`。
4. `context.account_nickname`。
5. `陌生人(<user_id>)`。

## 人物卡

### `CharacterCard`

字段：

- `card_id`：字符串 ID。
- `name`：人物卡名称，同一个用户内大小写不敏感且不能重复。
- `system`：规则系统名，默认 `generic`，例如 `COC7`。
- `attributes`：JSON 可序列化属性字典，例如 `{"力量": 60}`。
- `locks`：锁集合；`n` 禁止重命名，`q` 禁止更新和删除。
- `updated_at`：UTC 更新时间。

### `CharacterService`

```python
repository = ProfileRepository("data")
characters = CharacterService(repository)

card = characters.create(
    actor,
    "调查员",
    system="COC7",
    attributes={"力量": 60, "敏捷": 70, "__DefaultDice": "d100"},
)
characters.update(actor, card.card_id, attributes={"力量": 65})
characters.rename(actor, card.card_id, "新调查员")
characters.bind(actor, group, card.card_id)
```

公开操作：

- `list(actor)`：列出人物卡。
- `get(actor, card_id)`：读取单张卡。
- `create(actor, name, system, attributes, locks)`：新建人物卡。
- `update(actor, card_id, attributes, system)`：更新属性或系统。
- `rename(actor, card_id, name)`：重命名。
- `delete(actor, card_id)`：删除并清理绑定。
- `bind(actor, source, card_id)`：绑定到完整消息来源。
- `bind_global(actor, card_id)`：全局绑定。
- `unbind(actor, source=None)`：解除来源或全局绑定。
- `resolve(context)`：按来源绑定、全局绑定顺序取得当前卡；没有绑定时返回 `None`。

人物卡只按调用方传入的身份和来源工作，不知道 QQ 群名片、QQ 昵称或 QQ API。

## DiceEngine 门面

`DiceEngine` 是给消息适配器使用的统一入口：

```python
identities = IdentityServices(ProfileRepository("data"))
engine = DiceEngine(identities, DiceRoller())
response = engine.roll(RollRequest(context, "2d6+3", reason="伤害"))
```

`roll()` 的行为：

1. 根据 `MessageContext` 解析昵称。
2. 根据来源解析人物卡。
3. 如果表达式为空并且人物卡有 `__DefaultDice` 属性，则使用该默认表达式。
4. 投骰并返回 `RollResponse`。

`RollRequest` 包含 `context`、`expression` 和可选 `reason`。`RollResponse` 包含 `display_name`、`card_id`、`card_name`、原始请求和 `RollResult`。

## 命令总入口

`CommandRouter` 是消息适配层调用的总入口。它接收完整指令字符串作为参数，不读取 QQ 消息对象，不发送消息，也不生成 CQ 码：

```python
from trpg_dice import (
    ActorRef,
    CommandRouter,
    DiceEngine,
    DiceRoller,
    IdentityServices,
    MessageContext,
    MessageSource,
    ProfileRepository,
    RollRequest,
)

actor = ActorRef("qq", "123456")
source = MessageSource("qq", "group", "7788")
context = MessageContext(actor, source, account_nickname="玩家")
router = CommandRouter(
    DiceEngine(IdentityServices(ProfileRepository("data")), DiceRoller())
)

response = router.execute(context, ".r 2d6+3 伤害")
print(response.command)
print(response.result)
print(response.rendered)
```

也可以显式传 `CommandRequest`：

```python
request = CommandRequest(context=context, text="。rc 困难幸运")
response = router.dispatch(request)
```

`CommandResponse` 包含：

- `command`：规范化后的命令名。
- `args`：命令参数原文。
- `result`：对应领域结果，例如 `RollResponse`、`CheckResult`、`CharacterCard` 或列表。
- `rendered`：默认的人类可读文本；适配器可以自行改写。
- `metadata`：隐藏、重复次数、模式、目标值等路由信息。
- `to_dict()`：递归转换为 JSON 可序列化字典。

### 指令前缀

支持以下前缀：`.`、`。`、`．`、`!`。命令名不区分大小写，参数原文会保留在 `args` 中。

### `.r` 通用骰总入口

`.r` 是普通骰子的总入口，参数会传给 `DiceEngine`：

| 指令 | 作用 | 示例 |
| --- | --- | --- |
| `.r` | 使用人物卡默认骰或默认 D100 | `.r` |
| `.r 表达式` | 投指定表达式 | `.r 2d6+3` |
| `.r 表达式 原因` | 附带原因 | `.r 1d8 伤害` |
| `.rN#表达式` | 重复投掷 N 次，N 为 1..10 | `.r3#d100` |
| `.rh 表达式` | 隐藏结果元数据 | `.rh d100` |
| `.rs 表达式` | 短结果元数据 | `.rs 2d6` |
| `.rb`、`.rbN` | 奖励骰；省略数量默认为 `1` | `.rb`、`.rb2` |
| `.rp`、`.rpN` | 惩罚骰；省略数量默认为 `1` | `.rp`、`.rp2` |
| `.roll 表达式` | `.r` 的英文长别名 | `.roll d20` |

`rh` 和 `rs` 不会在核心层隐藏或修改结果，只在 `metadata` 中分别标记 `hidden=True`、`short=True`，由外部适配器决定如何展示。

### `.rc` 检定总入口

`.rc` 使用人物卡属性或直接给定成功率执行 COC 检定：

| 指令 | 作用 | 示例 |
| --- | --- | --- |
| `.rc 成功率` | 直接按成功率检定 | `.rc 50` |
| `.rc 属性` | 从当前人物卡读取属性 | `.rc 幸运` |
| `.rc 困难属性` | 成功率乘以 `0.5` | `.rc 困难幸运` |
| `.rc 极难属性` | 成功率乘以 `0.2` | `.rc 极难幸运` |
| `.rc _属性` | 标记为隐藏检定 | `.rc _心理学` |
| `.ra ...` | `.rc` 的奖励骰模式 | `.ra 幸运` |
| `.rcb ...` | `.rc` 的紧凑奖励骰模式 | `.rcb 幸运` |
| `.rcbN ...` | 使用 N 个奖励骰 | `.rcb2 幸运` |
| `.rcp ...` | `.rc` 的惩罚骰模式 | `.rcp 幸运` |
| `.rcpN ...` | 使用 N 个惩罚骰 | `.rcp2 幸运` |
| `.rcN#属性` | 重复检定 N 次 | `.rc3#幸运` |

属性表达式可以使用 `+ - * /` 和人物卡中的数值属性，例如 `.rc 体质*5`。`.rc` 的 `metadata` 包含 `skill`、`target`、`difficulty`、`hidden`、`mode` 和 `repeat`。

### `.coc` 人物卡生成总入口

| 指令 | 作用 |
| --- | --- |
| `.coc` | 生成一张 COC7 人物卡 |
| `.coc 3` | 生成三张 COC7 人物卡 |
| `.cocd` | 生成一张 COC7 详细卡 |
| `.coc6` | 生成一张 COC6 人物卡 |
| `.coc6d` | 生成一张 COC6 详细卡 |

数量范围为 `1..10`。第一张生成卡会绑定到当前 `MessageSource`。生成属性包括力量、体质、体型、敏捷、外貌、意志、教育、智力、幸运、生命、理智/SAN、魔法、闪避、灵感和知识，并设置 `__Type`、`__DefaultDice`。

### `.st` 属性记录总入口

`.st` 操作当前来源绑定的人物卡；如果没有当前卡，会按当前昵称自动创建一张卡：

| 指令 | 作用 | 示例 |
| --- | --- | --- |
| `.st 属性:值 ...` | 设置属性 | `.st 力量:50 敏捷:40` |
| `.st 属性=值` | 设置属性的等价写法 | `.st san=60` |
| `.st 属性+表达式` | 在原值上增加 | `.st san+1d6` |
| `.st 名称数字...` | 无分隔符连续设置属性 | `.st 射击40斗殴50` |
| `.st 属性-表达式` | 在原值上减少 | `.st hp-1` |
| `.st show` | 查看全部属性 | `.st show` |
| `.st show 属性` | 查看单个属性 | `.st show 幸运` |
| `.st del 属性 ...` | 删除属性 | `.st del 幸运` |
| `.st clr` | 清空全部属性 | `.st clr` |

### `.sc` San 检定总入口

`.sc 成功损失/失败损失 [当前San]` 投一颗 D100，按当前 SAN 判定成功或失败，然后更新人物卡的 `san` 或 `理智` 属性：

```text
.sc 0/1 70
.sc 1d6/1d100
```

如果省略当前 SAN，路由器会从人物卡的 `san` 或 `理智` 属性读取；如果两者都没有则返回 `CommandError`。

### `.ri` 先攻总入口

`.ri[加值] [重复次数#]名称` 使用 D20 生成先攻结果并返回结构化列表：

```text
.ri 调查员
.ri+2 调查员
.ri+2 3#木乃伊
```

返回项包含 `name` 和 `value`。当前核心返回结果，不自动写入外部战斗表。

### 用户手册其余核心指令

已按 Dice! 用户手册逐项核对，并为可脱离 QQ 的指令提供了路由和回归测试：

| 文档指令 | Python 核心状态 | 说明 | 覆盖测试 |
| --- | --- | --- | --- |
| `.ob` | 已实现 | 会话旁观者的 join/exit/list/clr/on/off | `test_command_manual_coverage.py` |
| `.set` | 已实现 | 用户或当前人物卡的默认骰面数 | `test_command_manual_coverage.py` |
| `.name`、`.nn`、`.nnn` | 已实现 | 确定性随机昵称和来源级称呼 | `test_command_manual_coverage.py` |
| `.dnd`、`.pc` | 已实现 | DND 属性生成、人物卡 CRUD/绑定、`type/temp/tojson/stat` | `test_command_manual_coverage.py` |
| `.setcoc`、`.ti`、`.li`、`.en` | 已实现 | 房规、C 风格疯狂症状表和成长检定 | `test_command_manual_coverage.py` |
| `.init` | 已实现 | 查看或清空当前会话先攻列表 | `test_command_manual_coverage.py` |
| `.w`、`.ww` | 已实现 | 10 面骰池和详细骰点结果 | `test_command_manual_coverage.py` |
| `.me`、`.jrrp`、`.welcome` | 已实现 | 结构化动作、每日人品和欢迎词状态 | `test_command_manual_coverage.py` |
| `.draw`、`.deck` | 已实现 | 公共/自定义牌堆抽取、删除、重置、清空和 range 牌堆 | `test_command_manual_coverage.py`、`test_deck.py` |
| `.ak` | 已实现 | 分歧的新建、增删选项、随机抽取和清空 | `test_command_manual_coverage.py` |
| `.rule`、`.rules`、`.log` | 核心状态已实现 | 规则别名/默认项和日志状态可持久化；规则词库、日志文件上传由适配器提供 | `test_command_manual_coverage.py` |
| `.game` | 已实现 | 会话生命周期、GM/PL、设置、轮盘骰及历史状态 | `test_command_manual_coverage.py`、`test_session.py` |

上表中的紧凑写法也有回归覆盖：`.r3#p`、`.rb`、`.rp`、`.nnn jp`、`.ak#/+/-/=`、`.drawh` 和 `.ri2DK`。

### 用户手册中的平台边界指令

以下命令已被 `CommandRouter` 识别，但不会在核心模块中伪造 QQ 或其他平台能力。它们返回 `metadata["platform_boundary"] == True`，由适配器负责权限、消息发送、群操作和扩展脚本：

`.admin`、`.cloud`、`.bot`、`.reply`、`.dismiss`、`!authorize`、`.send`、`.group`、`.link`、`.mod`、`.user`、`.system`，以及扩展指令 `.rdc`、`.rdx`、`.rsr`、`.rnc`、`.rfc`、`.rbh`、`.rws`。

这些边界命令和未知帮助词条建议均有 `tests/test_command_manual_coverage.py` 回归测试。当前核心仍不包含 QQ 权限、CQ 码、远程规则词库、日志上传或原项目 Lua/脚本扩展执行。

## MaiBot 适配器

`dice_core_py/` 根目录本身就是可复制到 MaiBot `plugins/` 目录的第三方插件目录，
其中 `_manifest.json` 和 `plugin.py` 位于插件根目录。它监听
`ON_MESSAGE_PRE_PROCESS`，将 MaiBot 的 QQ 群聊/私聊消息转换为 `MessageContext`，
调用本模块的 `CommandRouter`，再用 `ctx.send.text()` 回复到原聊天流。命中前缀后会
阻止消息继续进入 MaiBot 的普通对话链。

安装独立核心并复制插件目录：

```bash
python -m pip install -e dice_core_py
cp -R dice_core_py /path/to/MaiBot/plugins/trpg-dice
```

适配器实现、配置、兼容说明和前缀列表见 `maibot_plugin/README.md`。默认支持 `.`、`/`、
`。`、`．`、`!`、`！`；人物卡和昵称数据使用 MaiBot 注入的插件专属 `data_dir`。

### `.help` 和自定义命令

`.help` 返回内置命令说明：

```text
.help
.help rc
```

可以使用 `router.register(name, handler)` 增加适配器或业务自定义命令。处理函数签名为：

```python
def handler(context: MessageContext, args: str, metadata: dict) -> CommandResponse:
    ...
```

自定义处理函数同样只返回数据，不发送消息。

### 命令行参数入口

安装项目后可使用 `trpg-dice-command`：

```bash
trpg-dice-command '.r 2d6+3' --json
trpg-dice-command '。rc 50' --platform qq --user-id 123 --source-kind group --source-id 7788
trpg-dice-command '.coc6d' --seed 123 --data-dir ./data
```

可用参数：

- `command`：必填的完整指令字符串。
- `--platform`、`--user-id`：输入身份，默认 `cli`/`local-user`。
- `--source-kind`、`--source-id`、`--channel-id`：输入消息来源。
- `--nickname`：输入昵称，默认 `本地用户`。
- `--data-dir`：人物卡 JSON 目录，默认 `data`。
- `--seed`：可复现随机种子。
- `--json`：输出结构化 JSON。

## 轮盘骰

`Roulette` 是无放回随机骰。每个面在耗尽前不会重复，耗尽后自动重置：

```python
roulette = Roulette(sides=6, copies=1)
value = roulette.roll()
print(roulette.remaining)
roulette.reset()
```

- `sides`：面数。
- `copies`：每个面出现的份数。
- `remaining`：当前剩余数量。
- `roll()`：抽取一个剩余面，耗尽后自动重置。
- `reset()`：立即重置。
- `to_dict()`/`from_dict()`：保存和恢复池状态。

`DiceSession.roll(sides)` 在该会话配置了对应轮盘时使用轮盘，否则使用会话随机源。

## 牌堆

### `DeckEntry`

```python
entry = DeckEntry(value="获得线索", weight=3)
```

`value` 是牌面文本，`weight` 是正整数权重。

### `Deck`

```python
deck = Deck(
    [DeckEntry("稀有", 1), DeckEntry("普通", 3)],
    replace=False,
)
entry = deck.draw()
```

- `replace=False`：不放回；抽完自动重置。
- `replace=True`：放回；每次抽取都保留全部牌。
- `draw()`：按权重抽牌。
- `reset()`：恢复全部牌。
- `remaining`：不放回模式下剩余牌数。
- `to_dict()`/`from_dict()`：保存和恢复剩余索引。

当前 `Deck` 是纯牌堆服务；牌面文本不会自动解析或执行消息命令。

## L5R 特殊骰

`L5RDicePool` 实现原项目的《Legend of the Five Rings》白骰和黑骰：

```python
pool = L5RDicePool()
pool.insert_white(3)
pool.insert_black(2)
pool.insert_white(1, additional=True)
rolled = pool.roll()
```

公开操作：

- `insert_white(count, additional=False)`：加入白色十二面骰。
- `insert_black(count, additional=False)`：加入黑色六面骰。
- `roll()`：投掷所有未弃置的普通骰；追加骰使用加入时的结果。
- `reroll(position)`：重投指定位置。
- `drop(position)`：弃置指定位置。
- `result_symbols()`：读取当前非弃置骰的符号。
- `to_dict()`/`from_dict()`：JSON 状态。
- `encode()`/`decode()`：兼容原项目风格的 Base64 状态。

`L5RDie` 的 `color` 为 `white`/`black`，`status` 为 `normal`、`additional`、`rolled` 或 `dropped`。

## 会话

`DiceSession` 是平台无关的 TRPG 房间状态：

```python
session = DiceSession("campaign-1")
session.add_source(group)
session.add_gm(actor)
session.add_player(other_actor)
session.add_observer(observer)
session.configure_roulette(100)
session.configure_deck("clues", [DeckEntry("线索 A"), DeckEntry("线索 B")])
```

成员操作：

- `add_source()`、`remove_source()`：关联消息来源。
- `add_gm()`、`remove_gm()`：管理 GM；GM 不会同时保留玩家/旁观者身份。
- `add_player()`、`remove_player()`：管理玩家。
- `add_observer()`：管理旁观者；已经是 GM 或玩家时不会加入。

状态和玩法操作：

- `data`：自定义 JSON 数据字典。
- `roll(sides)`：使用会话轮盘或普通随机源投骰。
- `configure_roulette(sides, copies=1)`：配置指定面数的无放回轮盘。
- `configure_deck(name, entries, replace=False)`：配置牌堆。
- `draw(name)`：从已配置牌堆抽牌。
- `to_dict()`/`from_dict()`：序列化整个会话。

## JSON 存储

### `JsonStore`

```python
store = JsonStore("data")
store.write("example.json", {"schema_version": 1, "名称": "调查员"})
value = store.read("example.json")
store.delete("example.json")
```

特性：

- UTF-8 编码。
- JSON 根节点必须是对象。
- 写入到同目录临时文件，`flush`/`fsync` 后使用 `os.replace` 原子替换。
- 写入失败时保留原文件。
- 读取损坏 JSON 时抛出 `StorageError`，不会静默删除文件。
- 禁止通过相对路径逃逸存储根目录。

### 人物卡文件

`ProfileRepository` 保存到 `profiles/<sha256(actor.key)>.json`。结构如下：

```json
{
  "schema_version": 1,
  "actor": {"platform": "qq", "user_id": "123456"},
  "nicknames": {
    "global": "调查员",
    "qq:group:7788": "群内昵称"
  },
  "cards": {
    "1": {
      "id": "1",
      "name": "Alice",
      "system": "COC7",
      "attributes": {"力量": 60, "__DefaultDice": "d100"},
      "locks": [],
      "updated_at": "2026-01-01T00:00:00Z"
    }
  },
  "bindings": {"qq:group:7788": "1"},
  "next_card_id": 2
}
```

### 会话文件

`SessionRepository` 保存到 `sessions/<sha256(session_id)>.json`，包含：

- `schema_version`、`session_id`、创建/更新时间。
- `sources`、`game_masters`、`players`、`observers`。
- 自定义 `data`。
- `roulettes` 及剩余池。
- `decks` 及剩余索引。

人物卡和会话 ID 都使用哈希文件名，避免外部 ID 直接构造路径；JSON 内仍保留可读的原始字符串 ID。

## 错误类型

| 异常 | 用途 |
| --- | --- |
| `DiceError` | 所有领域异常基类 |
| `DiceExpressionError` | 表达式、参数或骰子规则错误 |
| `DiceLimitError` | 超过表达式、骰子数、面数或安全限制 |
| `DivisionByZeroError` | 表达式除零 |
| `IdentityError` | 身份、来源、昵称、卡片操作错误 |
| `NotFoundError` | 人物卡、牌堆等对象不存在 |
| `ConflictError` | 人物卡名称等对象冲突 |
| `StorageError` | JSON 读写、损坏数据或路径安全错误 |

建议适配器捕获领域异常并自行转换为平台消息；核心模块不会替适配器发送错误消息。

## 测试

### 一次运行全部测试

在 `dice_core_py` 目录执行：

```bash
. .venv/bin/activate
python -m unittest discover -s tests -v
```

当前测试脚本覆盖 17 个功能面，共 101 项测试：

| 测试脚本 | 覆盖内容 |
| --- | --- |
| `tests/test_models.py` | 身份、来源、上下文、结果对象、序列化 |
| `tests/test_randomness.py` | 系统、种子、固定序列随机源及边界 |
| `tests/test_roll_expressions.py` | 默认骰、算术、括号、保留骰、限制、渲染 |
| `tests/test_bonus_penalty.py` | 奖励/惩罚骰、十位规则、边界 |
| `tests/test_fate_dice.py` | Fate/Fudge 语法、映射、限制 |
| `tests/test_pool_and_coc.py` | 骰池、爆骰、COC 八种规则、结构化检定 |
| `tests/test_profiles.py` | 昵称服务、人物卡 CRUD、锁、绑定、删除清理 |
| `tests/test_storage.py` | UTF-8、损坏 JSON、原子失败保护、删除、路径安全 |
| `tests/test_roulette.py` | 无放回轮盘、复制数、恢复和伪造状态校验 |
| `tests/test_deck.py` | 权重、不放回/放回、重置、恢复和状态校验 |
| `tests/test_l5r.py` | L5R 加骰、追加骰、符号、重投、弃骰、JSON/Base64 |
| `tests/test_engine.py` | 默认骰、显式表达式覆盖、无消息发送的结构化门面 |
| `tests/test_session.py` | 会话来源、成员、轮盘、牌堆和 JSON 恢复 |
| `tests/test_cli.py` | CLI 人类可读和 JSON 输出 |
| `tests/test_commands.py` | `.r/.rc/.ra/.rcp/.coc/.st/.sc/.ri/.help`、别名、重复、隐藏、自定义命令 |
| `tests/test_command_manual_coverage.py` | 用户手册核心指令、紧凑别名、状态操作、人物卡、牌堆和平台边界 |
| `tests/test_command_cli.py` | 通过命令行参数输入完整指令 |
| `tests/test_maibot_adapter.py` | MaiBot 消息映射、QQ 群聊/私聊、前缀拦截和回复发送 |

另外保留：

- `tests/test_roller.py`：早期骰子核心回归测试。
- `tests/test_identity.py`：早期身份和人物卡回归测试。
- `tests/test_special.py`：早期轮盘、牌堆、L5R 回归测试。

运行单个功能脚本：

```bash
python tests/test_roll_expressions.py
python tests/test_profiles.py
python tests/test_l5r.py
```

测试中的 `SequenceRandomSource` 保证结果确定，不依赖真实随机分布。

## 当前不包含的功能

以下内容仍属于外部适配器、独立服务或迁移工具，没有放入本 Python 核心：

- QQ/OneBot 消息接收、消息匹配、CQ 码转换和消息发送。
- QQ 权限、管理员、冷却、黑白名单、敏感词和限流策略。
- Lua、JavaScript、动态 Python 脚本执行。
- 远程规则手册查询和依赖 QQ 登录态的网络请求。
- 原 C++ `PlayerCards.RDconf`、`UserConf.dat` 二进制文件直接读取。
- 原项目 QQ/网络权限相关的动态机器人管理、GUI、网络服务，以及 Lua/JS 扩展运行时。

这些能力可以在核心模块之上实现适配器，但不应反向把平台对象或消息事件引入 `trpg_dice`。

## 消息模板

`CommandRouter` 使用 `MessageCatalog` 恢复原 Dice! 的可配置回执。自定义内容保存在
数据目录的 `config/custom_messages.json`，不会写入源码目录；构造新的路由器后仍会自动加载。

通过 `.str` 管理模板：

```text
.str                         列出默认和自定义键
.str strRollDice             查看当前文本
.str strRollDice show         查看当前文本
.str strRollDice 新文本       设置文本
.str strRollDice NULL         设置为空
.str strRollDice reset        恢复默认文本
```

常用默认键包括 `strRollDice`、`strRollDiceReason`、`strRollMultiDice`、
`strRollSkill`、`strRollSkillHidden`、`strSanityRoll`、`strEnRoll*`、`strRollInit`、
`strNameGenerator`、`strDrawCard`、`strDrawHidden`、`strJrrp`、`strTempInsane` 和
`strLongInsane`。模板支持 `{pc}`、`{nick}`、`{res}`、`{reason}`、`{br}`、`{FormFeed}`、
`{sample:a|b}`、`{ran:1~10}`、`{case:key?value=text&else=other}`、
`{grade:key?threshold=text&else=other}`、`{var:name?value}`、`{at:value}`、`{len:value}`、
`{print:value}` 以及通过 `&` 重定向到其他消息键。
