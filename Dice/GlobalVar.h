/*
 *  _______     ________    ________    ________    __
 * |   __  \   |__    __|  |   _____|  |   _____|  |  |
 * |  |  |  |     |  |     |  |        |  |_____   |  |
 * |  |  |  |     |  |     |  |        |   _____|  |__|
 * |  |__|  |   __|  |__   |  |_____   |  |_____    __
 * |_______/   |________|  |________|  |________|  |__|
 *
 * Dice! QQ Dice Robot for TRPG
 * Copyright (C) 2018-2020 w4123���
 * Copyright (C) 2019-2020 String.Empty
 *
 * This program is free software: you can redistribute it and/or modify it under the terms
 * of the GNU Affero General Public License as published by the Free Software Foundation,
 * either version 3 of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License along with this
 * program. If not, see <http://www.gnu.org/licenses/>.
 */
#pragma once
#ifndef DICE_GLOBAL_VAR
#define DICE_GLOBAL_VAR
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <map>
#include <unordered_map>
#include "STLExtern.hpp"

/*
 * �汾��Ϣ
 * �����޸�Dice_Build, Dice_Ver_Without_Build��DiceRequestHeader�Լ�Dice_Ver����
 * ���޸�Dice_Short_Ver��Dice_Full_Ver�����Դﵽ�汾�Զ���
 */
const unsigned short Dice_Build = 575u;
inline const std::string Dice_Ver_Without_Build = "2.5.0";
constexpr auto DiceRequestHeader = "Dice/2.5.0";
inline const std::string Dice_Ver = Dice_Ver_Without_Build + "(" + std::to_string(Dice_Build) + ")";
inline const std::string Dice_Short_Ver = "Dice! by ��� & Shiki Ver " + Dice_Ver;

#ifdef __clang__

#ifdef _MSC_VER
const std::string Dice_Full_Ver = Dice_Short_Ver + " [CLANG " + std::to_string(__clang_major__) + "." + std::to_string(__clang_minor__) + "." + std::to_string(__clang_patchlevel__) + " with MSVC " + std::to_string(_MSC_VER) + " " + __DATE__ + " " + __TIME__;
#elif defined(__GNUC__)
const std::string Dice_Full_Ver = Dice_Short_Ver + " [CLANG " + std::to_string(__clang_major__) + "." + std::to_string(__clang_minor__) + "." + std::to_string(__clang_patchlevel__) +  " with GNUC " + std::to_string(__GNUC__) + "." + std::to_string(__GNUC_MINOR__) + "." + std::to_string(__GNUC_PATCHLEVEL__) + " " + __DATE__ + " " + __TIME__;
#else
const std::string Dice_Full_Ver = Dice_Short_Ver + " [CLANG " + std::to_string(__clang_major__) + "." + std::to_string(__clang_minor__) + "." + std::to_string(__clang_patchlevel__);
#endif

#else

#ifdef _MSC_VER
const std::string Dice_Full_Ver = std::string(Dice_Short_Ver) + "[MSVC " + std::to_string(_MSC_VER) + " " + __DATE__ +
	" " + __TIME__ + "]";
#elif defined(__GNUC__)
const std::string Dice_Full_Ver = Dice_Short_Ver + " [GNUC " + std::to_string(__GNUC__) + "." + std::to_string(__GNUC_MINOR__) + "." + std::to_string(__GNUC_PATCHLEVEL__) + " " + __DATE__ + " " + __TIME__;
#else
const std::string Dice_Full_Ver = Dice_Short_Ver + " [UNKNOWN COMPILER";
#endif

#endif

// DLL hModule
extern HMODULE hDllModule;

// Ӧ���Ƿ�����
extern bool Enabled;

// ���л���
//enum class QQFrame { CoolQ, Mirai, XianQu };
//extern QQFrame frame;

// Dice�������İ汾�ַ���
extern std::string Dice_Full_Ver_On;

// ��ִ���ļ�λ��
//extern std::string strModulePath;

// ��Ϣ�����߳��Ƿ���������
extern bool msgSendThreadRunning;

// �ظ���Ϣ, �����ݿ���ͨ��CustomMsg�����޸Ķ������޸�Դ����
extern std::map<std::string, std::string> GlobalMsg;
// �޸ĺ��Global���
extern std::map<std::string, std::string> EditedMsg;
// �����ĵ�
extern const std::map<std::string, std::string, less_ci> HelpDoc;
// �޸ĺ�İ����ĵ�
inline std::map<std::string, std::string, less_ci> CustomHelp;
std::string getMsg(const std::string& key, const std::unordered_map<std::string, std::string>& tmp = {});

#endif /*DICE_GLOBAL_VAR*/
