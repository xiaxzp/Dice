/*
 *  _______     ________    ________    ________    __
 * |   __  \   |__    __|  |   _____|  |   _____|  |  |
 * |  |  |  |     |  |     |  |        |  |_____   |  |
 * |  |  |  |     |  |     |  |        |   _____|  |__|
 * |  |__|  |   __|  |__   |  |_____   |  |_____    __
 * |_______/   |________|  |________|  |________|  |__|
 *
 * Dice! QQ Dice Robot for TRPG
 * Copyright (C) 2018-2019 w4123���
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
#ifndef DICE_MSG_FORMAT
#define DICE_MSG_FORMAT
#include <string>
#include <map>
#include <unordered_map>
#include <utility>
#include <vector>
using std::string;

extern std::map<string, string> GlobalChar;
typedef string(*GobalTex)();
extern std::map<string, GobalTex> strFuncs;

std::string format(std::string str, const std::initializer_list<const std::string>& replace_str);

template <typename sort>
std::string format(std::string s, const std::map<std::string, std::string, sort>& replace_str,
                   const std::unordered_map<std::string, std::string>& str_tmp = {})
{
	if (s[0] == '&')
	{
		string key = s.substr(1);
		auto it = replace_str.find(key);
		if (it != replace_str.end())
		{
			return format(it->second, replace_str, str_tmp);
		}
		if (auto uit = str_tmp.find(key); uit != str_tmp.end())
		{
			return uit->second;
		}
	}
	int l = 0, r = 0;
	while ((l = s.find('{', r)) != string::npos && (r = s.find('}', l)) != string::npos) {
		//������ǰ�ӡ�\����ʾ���������ݲ�ת��
		if (l - 1 >= 0 && s[l - 1] == 0x5c) {
			s.replace(l - 1, 1, "");
			continue;
		}
		string key = s.substr(l + 1, r - l - 1);
		string val;
		auto it = replace_str.find(key);
		if (it != replace_str.end()) 
		{
			val = format(it->second, replace_str, str_tmp);
		}
		else if ((it = GlobalChar.find(key)) != GlobalChar.end()) 
		{
			val = it->second;
		}
		else if (auto uit = str_tmp.find(key); uit != str_tmp.end())
		{
			if (key == "res")val = format(uit->second, replace_str, str_tmp);
			else val = uit->second;
		}
		else if (auto func = strFuncs.find(key); func != strFuncs.end())
		{
			val = func->second();
		}
		else continue;
		s.replace(l, r - l + 1, val);
		r = l + val.length();
	}
	return s;
}

class ResList
{
	std::vector<std::string> vRes;
	unsigned int intMaxLen = 0;
	bool isLineBreak = false;
	unsigned int intLineLen = 10;
	static unsigned int intPageLen;
	string sHead = "";
	string sDot = " ";
	string strLongSepa = "\n";
public:
	ResList() = default;

	ResList(const std::string& s, std::string dot) : sDot(std::move(dot))
	{
		vRes.push_back(s);
		intMaxLen = s.length();
	}

	ResList& operator<<(std::string s);

	std::string show(size_t = 0)const;

	ResList& head(string s) {
		sHead = s;
		return *this;
	}
	ResList& dot(string s)
	{
		sDot = std::move(s);
		return *this;
	}

	ResList& linebreak()
	{
		isLineBreak = true;
		return *this;
	}

	ResList& line(unsigned int l)
	{
		intLineLen = l;
		return *this;
	}

	void setDot(string s, string sLong)
	{
		sDot = std::move(s);
		strLongSepa = std::move(sLong);
	}

	[[nodiscard]] bool empty() const
	{
		return vRes.empty();
	}

	[[nodiscard]] size_t size() const
	{
		return vRes.size();
	}
};

//�������������Ŀ
class AttrList {
	std::unordered_map<string, string> mItem;
	std::vector<string> vKey;
public:
	string show() {
		string res;
		int index = 0;
		for (auto& key : vKey) {
			res += "\n" + key + "=" + mItem[key];
		}
		return res;
	}
};

template <typename T, typename sort>
std::string listKey(std::map<std::string, T, sort> m)
{
	ResList list;
	list.setDot("/", "/");
	for (auto& [key,val] : m)
	{
		if (key[0] == '_')continue;
		list << key;
	}
	return list.show();
}

std::string to_binary(int b);
std::string strip(std::string);
#endif /*DICE_MSG_FORMAT*/
