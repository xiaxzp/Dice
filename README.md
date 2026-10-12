# Dice!
QQ Dice Robot For TRPG Based on CoolQ/Mirai/XQ

[![License](https://img.shields.io/github/license/Dice-Developer-Team/Dice.svg)](http://www.gnu.org/licenses)
[![Downloads](https://img.shields.io/github/downloads/Dice-Developer-Team/dice/total.svg)](https://github.com/Dice-Developer-Team/Dice/releases)
[![GitHub contributors](https://img.shields.io/github/contributors/Dice-Developer-Team/dice.svg)](https://github.com/Dice-Developer-Team/Dice/graphs/contributors)
[![GitHub last commit](https://img.shields.io/github/last-commit/Dice-Developer-Team/dice.svg)](https://github.com/Dice-Developer-Team/Dice/commits)

## 简介

Dice!是一款基于酷Q/Mirai/go-cqhttp/OneBot协议的跑团掷骰机器人

论坛: <https://forum.kokona.tech>

Latest Stable Release: [![GitHub release](https://img.shields.io/github/release/Dice-Developer-Team/dice.svg)](https://github.com/w4123/Dice-Developer-Team/releases) [![GitHub Release Date](https://img.shields.io/github/release-date/Dice-Developer-Team/dice.svg)](https://github.com/Dice-Developer-Team/Dice/releases)

Latest Release: [![GitHub release](https://img.shields.io/github/release-pre/Dice-Developer-Team/dice.svg)](https://github.com/Dice-Developer-Team/Dice/releases) [![GitHub Release Date](https://img.shields.io/github/release-date-pre/Dice-Developer-Team/dice.svg)](https://github.com/Dice-Developer-Team/Dice/releases)

## 开发者

贡献者:w4123溯洄 Shiki jh123111 緋色月下、スイカを食う

感谢:Flandre Cirno 回転 他是王家乐。白いとう 哞哞哞哞哞哞哞哞哞哞哞哞 丸子 黯星 一盏大师 初音py2001 Coxxs orzFly [水纹霖霖CauchyDOOM](https://github.com/Dice-Developer-Team/Dice/commits?author=CauchyDOOM) 等(排名不分先后)(如有缺漏请务必联系色子:3258528467) 

## 编译须知

1. 安装CMake(v3.15+), git和一个合适的支持C++17的编译器
2. clone此repo，请注意此repo含有submodule，```git clone https://github.com/Dice-Developer-Team/Dice --recursive```
3. 如果你在Cross-compile，请先执行```./vcpkg/bootstrap-vcpkg.sh```，以防止Cross-compiler冲突。如果你没在Cross-compile，你可以直接运行下一步，vcpkg会自动被安装。
4. 执行```cmake .```，如果你在交叉编译，你可能需要设置```CC```, ```CXX```, ```VCPKG_TARGET_TRIPLET```等环境变量到对应的参数才能正常编译。
5. 执行```cmake --build .```完成编译

在大多数情况下，你不需要自行编译。你可以在Github Releases 以及 Github Actions中找到编译好的二进制版本。

## 独立 Python 骰子模块

`dice_core_py/` 是与 QQ/OneBot 消息逻辑解耦的 Python 3 模块，提供骰子表达式、奖惩骰、人物卡/昵称来源绑定和 JSON 持久化。详见 `dice_core_py/README.md`。

Python 模块还提供平台无关的指令总入口 `CommandRouter`，可通过参数传入 `.r`、`.rc`、`.coc`、`.st` 等完整指令，由 QQ 适配器负责把返回结果转换成消息。

其中 `dice_core_py/` 根目录可直接作为 MaiBot 插件目录使用：MaiBot 会从根目录的 `_manifest.json` 和 `plugin.py` 发现插件，监听 QQ 消息，命中 `.`、`/`、`。` 等前缀后调用 `CommandRouter` 并直接回复结果。安装和配置说明见 `dice_core_py/maibot_plugin/README.md`。

## Issue提交

提交Issue前请务必确认没有其他人提交过相同的Issue, 善用搜索功能 提交Bug时最好附有截图以及问题复现方法, 同时也欢迎新功能建议

## License

Dice! QQ Dice Robot for TRPG

Copyright (C) 2018-2022 w4123溯洄 Shiki

This program is free software: you can redistribute it and/or modify it under the terms
of the GNU Affero General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this
program. If not, see <http://www.gnu.org/licenses/>.
