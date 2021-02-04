/*
 * �ļ���д
 * Copyright (C) 2019-2020 String.Empty
 */
#pragma once
#include <fstream>
#include <sstream>
#include <cstdio>
#include <vector>
#include <map>
#include <set>
#include <filesystem>
#include <unordered_set>
#include <unordered_map>
#include <variant>
#include <io.h>
#include <direct.h>
#include <cstdio>
#include "DiceXMLTree.h"
#include "StrExtern.hpp"
#include "MsgFormat.h"

using std::ifstream;
using std::ofstream;
using std::ios;
using std::stringstream;
using std::enable_if;
using std::map;
using std::multimap;
using std::set;
using std::unordered_set;
using std::unordered_map;

int mkDir(const std::string& dir);

int clrDir(const std::string& dir, const unordered_set<std::string>& exceptList);

template <typename TKey, typename TVal, typename sort>
void map_merge(map<TKey, TVal, sort>& m1, const map<TKey, TVal, sort>& m2)
{
	for (auto& [k,v] : m2)
	{
		m1[k] = v;
	}
}

template <typename TKey, typename TVal>
TVal get(const map<TKey, TVal>& m, TKey key, TVal def)
{
	return (m.count(key) ? m.at(key) : def);
	/*auto it = m.find(key);
	if (it == m.end())return def;
	else return it->second;*/
}

vector<string> getLines(const string& s);

string printLine(string s);

template <typename T>
//typename std::enable_if<std::is_integral<T>::value, bool>::type fscan(std::ifstream& fin, T& t) {
bool fscan(std::ifstream& fin, T& t)
{
	if (fin >> t)
	{
		return true;
	}
	return false;
}

//template<>
bool fscan(std::ifstream& fin, std::string& t);

template <class C, bool(C::* U)(std::ifstream&) = &C::load>
bool fscan(std::ifstream& fin, C& obj)
{
	if (obj.load(fin))return true;
	return false;
}

using var = std::variant<std::monostate, int, double, string>;

// ��ȡ�������ļ�����������������
template <typename T>
std::enable_if_t<std::is_fundamental_v<T>, T> fread(ifstream& fin)
{
	T t;
	fin.read(reinterpret_cast<char*>(&t), sizeof(T));
	return t;
}

// ��ȡ�������ļ�����std::string����
template <typename T>
std::enable_if_t<std::is_same_v<T, std::string>, T> fread(ifstream& fin)
{
	const short len = fread<short>(fin);
	char* buff = new char[len];
	fin.read(buff, sizeof(char) * len);
	std::string s(buff, len);
	delete[] buff;
	return s;
}
template <typename T>
std::enable_if_t<std::is_same_v<T, var>, T> fread(ifstream& fin) {
	const short len = fread<short>(fin);
	if (len >= 0) {
		char* buff = new char[len];
		fin.read(buff, sizeof(char) * len);
		std::string s(buff, len);
		delete[] buff;
		return s;
	}
	switch (len) {
	case -1:
		return fread<int>(fin);
	case -2:
		return fread<double>(fin);
	default:
		return {};
	}
}

// ��ȡ�������ļ�������readb����������
template <class C, void(C::* U)(std::ifstream&) = &C::readb>
C fread(ifstream& fin)
{
	C obj;
	obj.readb(fin);
	return obj;
}

// ��ȡ�������ļ�����std::map����
template <typename T1, typename T2>
std::map<T1, T2> fread(ifstream& fin)
{
	std::map<T1, T2> m;
	short len = fread<short>(fin);
	if (len < 0)return m;
	while (len--)
	{
		T1 key = fread<T1>(fin);
		T2 val = fread<T2>(fin);
		m[key] = val;
	}
	return m;
}
template <typename T1, typename T2, typename sort>
void fread(ifstream& fin, std::map<T1, T2, sort>& dir) {
	short len = fread<short>(fin);
	if (len < 0)return;
	while (len--) {
		T1 key = fread<T1>(fin);
		T2 val = fread<T2>(fin);
		dir[key] = val;
	}
}

// ��ȡ�������ļ�����std::set����
template <typename T, bool isLib>
std::set<T> fread(ifstream& fin)
{
	short len = fread<short>(fin);
	if (len < 0)return {};
	set<T> s{};
	while (len--)
	{
		const T item = fread<T>(fin);
		s.insert(item);
	}
	return s;
}

template <typename T1, typename T2>
void readini(string& line, std::pair<T1, T2>& p)
{
	const int pos = line.find('=');
	if (pos == std::string::npos)return;
	std::istringstream sin(line.substr(0, pos));
	sin >> p.first;
	sin.clear();
	sin.str(line.substr(pos + 1));
	sin >> p.second;
}

void readini(ifstream& fin, std::string& s);

template <typename T1, typename T2>
void readini(string s, std::map<T1, T2>& m)
{
	std::pair<T1, T2> p;
	string line;
	stringstream ss(s);
	while (getline(ss, line))
	{
		readini(line, p);
		m[p.first] = p.second;
	}
}

template <typename T>
void readini(string s, std::vector<T>& v)
{
	T p;
	string line;
	stringstream ss(s);
	while (getline(ss, line))
	{
		readini(line, p);
		v.push_back(p);
	}
}

template <typename T>
int loadFile(std::string strPath, std::set<T>& setTmp)
{
	std::ifstream fin(strPath);
	if (fin)
	{
		int Cnt = 0;
		T item;
		while (fscan(fin, item))
		{
			setTmp.insert(item);
			Cnt++;
		}
		return Cnt;
	}
	fin.close();
	return -1;
}

template <typename T>
int loadFile(std::string strPath, std::unordered_set<T>& setTmp)
{
	std::ifstream fin(strPath);
	if (fin)
	{
		int Cnt = 0;
		T item;
		while (fscan(fin, item))
		{
			setTmp.insert(item);
			Cnt++;
		}
		return Cnt;
	}
	fin.close();
	return -1;
}

template <typename T1, typename T2>
int loadFile(std::string strPath, std::map<T1, T2>& mapTmp)
{
	std::ifstream fin(strPath);
	if (fin)
	{
		int Cnt = 0;
		T1 key;
		while (fin >> key)
		{
			fscan(fin, mapTmp[key]);
			Cnt++;
		}
		return Cnt;
	}
	fin.close();
	return -1;
}

template <typename T1, typename T2>
int loadFile(std::string strPath, std::unordered_map<T1, T2>& mapTmp) 
{
	std::ifstream fin(strPath);
	if (fin)
	{
		int Cnt = 0;
		T1 key;
		while (fin >> key)
		{
			fscan(fin, mapTmp[key]);
			Cnt++;
		}
		return Cnt;
	}
	fin.close();
	return -1;
}

template <typename T1, typename T2>
void loadFile(std::string strPath, std::multimap<T1, T2>& mapTmp)
{
	std::ifstream fin(strPath);
	if (fin)
	{
		T1 key;
		T2 Val;
		while (fin >> key >> Val)
		{
			mapTmp.insert({key, Val});
		}
	}
	fin.close();
}

template <typename T, class C, void(C::* U)(std::ifstream&) = &C::readb>
int loadBFile(std::string strPath, std::map<T, C>& m)
{
	std::ifstream fin(strPath, std::ios::in | std::ios::binary);
	if (!fin)return -1;
	const int len = fread<int>(fin);
	int Cnt = 0;
	T key;
	C val;
	while (fin.peek() != EOF && len > Cnt++)
	{
		key = fread<T>(fin);
		m[key].readb(fin);
	}
	fin.close();
	return Cnt;
}

template <typename T, class C, void(C::* U)(std::ifstream&) = &C::readb>
int loadBFile(std::string strPath, std::unordered_map<T, C>& m)
{
	std::ifstream fin(strPath, std::ios::in | std::ios::binary);
	if (!fin)return -1;
	const int len = fread<int>(fin);
	int Cnt = 0;
	T key;
	C val;
	while (fin.peek() != EOF && len > Cnt++)
	{
		key = fread<T>(fin);
		m[key].readb(fin);
	}
	fin.close();
	return Cnt;
}

//��ȡαini
template <class C>
int loadINI(std::string strPath, std::map<std::string, C>& m)
{
	std::ifstream fin(strPath, std::ios::in | std::ios::binary);
	if (!fin)return -1;
	std::string s, name;
	C val;
	getline(fin, s);
	readini(fin, name);
	val.readi(fin);
	m[name] = val;
	fin.close();
	return 1;
}

bool rdbuf(const string& strPath, string& s);

//��ȡαxml
template <class C, std::string(C::* U)() = &C::getName>
int loadXML(const std::string& strPath, std::map<std::string, C>& m)
{
	string s;
	if (!rdbuf(strPath, s))return -1;
	DDOM xml(s);
	C obj(xml);
	m[obj.getName()].readt(xml);
	return 1;
}

//�����ļ���
int listDir(const string& dir, vector<std::filesystem::path>& files, bool isSub = false);

template <typename T1, typename T2>
int _loadDir(int (*load)(const std::string&, T2&), const std::string& strDir, T2& tmp, int& intFile, int& intFailure,
             int& intItem, std::vector<std::string>& files)
{
	std::error_code err;
	for (const auto& p : T1(strDir, err))
	{
		if (p.is_regular_file())
		{
			intFile++;
			string path = convert_w2a(p.path().filename().wstring().c_str());
			const int Cnt = load(strDir + path, tmp);
			if (Cnt < 0)
			{
				files.push_back(path);
				intFailure++;
			}
			else intItem += Cnt;
		}
	}
	if (err) return -1;
	return 0;
}

//��ȡ�ļ���
template <typename T>
int loadDir(int (*load)(const std::string&, T&), const std::string& strDir, T& tmp, ResList& logList,
            bool isSubdir = false)
{
	int intFile = 0, intFailure = 0, intItem = 0;
	std::vector<std::string> files;
	if (isSubdir)
	{
		if (_loadDir<std::filesystem::recursive_directory_iterator>(load, strDir, tmp, intFile, intFailure, intItem,
		                                                            files) == -1) return 0;
	}
	else
	{
		if (_loadDir<std::filesystem::directory_iterator>(load, strDir, tmp, intFile, intFailure, intItem, files) == -1)
			return 0;
	}

	if (!intFile)return 0;
	logList << "��ȡ" + strDir + "�е�" + std::to_string(intFile) + "���ļ�, ��" + std::to_string(intItem) + "����Ŀ";
	if (intFailure)
	{
		logList << "��ȡʧ��" + std::to_string(intFailure) + "��:";
		for (auto& it : files)
		{
			logList << it;
		}
	}
	return intFile;
}

//save
template <typename T>
void fprint(std::ofstream& fout, const T& t)
{
	fout << t;
}

template <class C, void(C::* U)(std::ofstream&) = &C::save>
void fprint(std::ofstream& fout, C obj)
{
	obj.save(fout);
}

void fprint(std::ofstream& fout, std::string s);

template <typename T1, typename T2>
void fprint(std::ofstream& fout, std::pair<T1, T2> t)
{
	fprint(fout, t.first);
	fout << "\t";
	fprint(fout, t.second);
}

template <typename T>
bool clrEmpty(std::string strPath, const T& tmp)
{
	if (tmp.empty())
	{
		std::ifstream fin(strPath);
		if (fin)
		{
			fin.close();
			remove(strPath.c_str());
		}
		return true;
	}
	return false;
}

template <typename T>
typename std::enable_if<!std::is_class<T>::value, void>::type fwrite(ofstream& fout, T t)
{
	T val = t;
	fout.write(reinterpret_cast<char*>(&val), sizeof(T));
}


void fwrite(ofstream& fout, const std::string& s);
void fwrite(ofstream& fout, const var& var);

template <class C, void(C::* U)(std::ofstream&) = &C::writeb>
void fwrite(ofstream& fout, C& obj)
{
	obj.writeb(fout);
}

template <typename T1, typename T2, typename sort>
void fwrite(ofstream& fout, const std::map<T1, T2, sort>& m)
{
	const auto len = static_cast<short>(m.size());
	fwrite(fout, len);
	for (const auto& it : m)
	{
		fwrite(fout, it.first);
		fwrite(fout, it.second);
	}
}

template <typename T>
void fwrite(ofstream& fout, const std::set<T>& s)
{
	const auto len = static_cast<short>(s.size());
	fwrite(fout, len);
	for (const auto& it : s)
	{
		fwrite(fout, it);
	}
}

template <typename T>
void saveFile(std::string strPath, const T& setTmp)
{
	if (clrEmpty(strPath, setTmp))return;
	std::ofstream fout(strPath);
	for (const auto& it : setTmp)
	{
		fprint(fout, it);
		fout << std::endl;
	}
	fout.close();
}

template <typename TKey, typename TVal>
void saveFile(std::string strPath, const map<TKey, TVal>& mTmp)
{
	if (clrEmpty(strPath, mTmp))return;
	std::ofstream fout(strPath);
	for (const auto& [key,val] : mTmp)
	{
		fout << key << "\t";
		fprint(fout, val);
		fout << std::endl;
	}
	fout.close();
}


template <typename TKey, typename TVal>
void saveFile(std::string strPath, const unordered_map<TKey, TVal>& mTmp)
{
	if (clrEmpty(strPath, mTmp))return;
	std::ofstream fout(strPath);
	for (const auto& [key, val] : mTmp)
	{
		fout << key << "\t";
		fprint(fout, val);
		fout << std::endl;
	}
	fout.close();
}

template <typename T, class C, void(C::* U)(std::ofstream&) = &C::writeb>
void saveBFile(std::string strPath, std::map<T, C>& m)
{
	if (clrEmpty(strPath, m))return;
	std::ofstream fout(strPath, ios::out | ios::trunc | ios::binary);
	const int len = m.size();
	fwrite<int>(fout, len);
	for (auto& [key,val] : m)
	{
		fwrite(fout, key);
		fwrite(fout, val);
	}
	fout.close();
}

template <typename T, class C, void(C::* U)(std::ofstream&) = &C::writeb>
void saveBFile(std::string strPath, std::unordered_map<T, C>& m)
{
	if (clrEmpty(strPath, m))return;
	std::ofstream fout(strPath, ios::out | ios::trunc | ios::binary);
	const int len = m.size();
	fwrite<int>(fout, len);
	for (auto& [key, val] : m)
	{
		fwrite(fout, key);
		fwrite(fout, val);
	}
	fout.close();
}

//��ȡαxml
template <class C, std::string(C::* U)() = &C::writet>
void saveXML(std::string strPath, C& obj)
{
	std::ofstream fout(strPath);
	fout << obj.writet();
}
