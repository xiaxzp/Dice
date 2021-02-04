#include <set>
#include "DiceMod.h"
#include "GlobalVar.h"
#include "ManagerSystem.h"
#include "Jsonio.h"
#include "DiceFile.hpp"
#include "DiceEvent.h"
#include "DiceLua.h"
using std::set;

bool DiceMsgOrder::exec(FromMsg* msg) {
	if (type == OrderType::Lua) {
		//std::thread th(lua_msg_order, msg, fileLua.c_str(), funcLua.c_str());
		//th.detach();
		lua_msg_order(msg, fileLua.c_str(), funcLua.c_str());
		return true;
	}
	return false;
}

DiceModManager::DiceModManager() : helpdoc(HelpDoc)
{
}

string DiceModManager::format(string s, const map<string, string, less_ci>& dict, const char* mod_name = "") const
{
	//ֱ���ض���
	if (s[0] == '&')
	{
		const string key = s.substr(1);
		const auto it = dict.find(key);
		if (it != dict.end())
		{
			return format(it->second, dict, mod_name);
		}
		//���ñ�mod����
	}
	int l = 0, r = 0;
	int len = s.length();
	while ((l = s.find('{', r)) != string::npos && (r = s.find('}', l)) != string::npos)
	{
		if (s[l - 1] == 0x5c)
		{
			s.replace(l - 1, 1, "");
			continue;
		}
		string key = s.substr(l + 1, r - l - 1), val;
		auto it = dict.find(key);
		if (it != dict.end())
		{
			val = format(it->second, dict, mod_name);
		}
		else if (auto func = strFuncs.find(key); func != strFuncs.end())
		{
			val = func->second();
		}
		else continue;
		s.replace(l, r - l + 1, val);
		r = l + val.length();
		//���ñ�mod����
	}
	return s;
}

string DiceModManager::get_help(const string& key) const
{
	if (const auto it = helpdoc.find(key); it != helpdoc.end())
	{
		return format(it->second, helpdoc);
	}
	return "{strHelpNotFound}";
}

struct help_sorter {
	bool operator()(const string& _Left, const string& _Right) const {
		if (fmt->cntHelp.count(_Right) && !fmt->cntHelp.count(_Left))
			return true;
		else if (fmt->cntHelp.count(_Left) && !fmt->cntHelp.count(_Right))
			return false;
		else if (fmt->cntHelp.count(_Left) && fmt->cntHelp.count(_Right) && fmt->cntHelp[_Left] != fmt->cntHelp[_Right])
			return fmt->cntHelp[_Left] < fmt->cntHelp[_Right];
		else if (_Left.length() != _Right.length()) {
			return _Left.length() > _Right.length();
		}
		else return _Left > _Right;
	}
};

void DiceModManager::_help(const shared_ptr<DiceJobDetail>& job) {
	if ((*job)["help_word"].empty()) {
		job->reply(string(Dice_Short_Ver) + "\n" + GlobalMsg["strHlpMsg"]);
		return;
	}
	else if (const auto it = helpdoc.find((*job)["help_word"]); it != helpdoc.end()) {
		job->reply(format(it->second, helpdoc));
	}
	else if (unordered_set<string> keys = querier.search((*job)["help_word"]);!keys.empty()) {
		if (keys.size() == 1) {
			(*job)["redirect_key"] = *keys.begin();
			(*job)["redirect_res"] = get_help(*keys.begin());
			job->reply("{strHelpRedirect}");
		}
		else {
			std::priority_queue<string, vector<string>, help_sorter> qKey;
			for (auto key : keys) {
				qKey.emplace(".help " + key);
			}
			ResList res;
			while (!qKey.empty()) {
				res << qKey.top();
				qKey.pop();
				if (res.size() > 20)break;
			}
			(*job)["res"] = res.dot("/").show(1);
			job->reply("{strHelpSuggestion}");
		}
	}
	else job->reply("{strHelpNotFound}");
	cntHelp[(*job)["help_word"]] += 1;
	saveJMap(DiceDir + "\\user\\HelpStatic.json",cntHelp);
}

void DiceModManager::set_help(const string& key, const string& val)
{
	if (!helpdoc.count(key))querier.insert(key);
	helpdoc[key] = val;
}

void DiceModManager::rm_help(const string& key)
{
	helpdoc.erase(key);
}

bool DiceModManager::listen_order(DiceJobDetail* msg) {
	string nameOrder;
	if(!gOrder.match_head(msg->strMsg, nameOrder))return false;
	if (((FromMsg*)msg)->WordCensor()) {
		return true;
	}
	msgorder[nameOrder].exec((FromMsg*)msg);
	return true;
}
string DiceModManager::list_order() { 
	return "��չָ��:" + listKey(msgorder);
}

int DiceModManager::load(ResList* resLog) 
{
	vector<std::filesystem::path> sModFile;
	//��ȡmod
	vector<string> sModErr;
	int cntFile = listDir(DiceDir + "\\mod\\", sModFile);
	int cntItem{0};
	if (cntFile > 0) {
		for (auto& pathFile : sModFile) {
			nlohmann::json j = freadJson(pathFile);
			if (j.is_null()) {
				sModErr.push_back(pathFile.filename().string());
				continue;
			}
			if (j.count("dice_build")) {
				if (j["dice_build"] > Dice_Build) {
					sModErr.push_back(pathFile.filename().string() + "(Dice�汾����)");
					continue;
				}
			}
			if (j.count("helpdoc")) {
				cntItem += readJMap(j["helpdoc"], helpdoc);
			}
			if (j.count("global_char")) {
				cntItem += readJMap(j["global_char"], GlobalChar);
			}
		}
		*resLog << "��ȡ\\mod\\�е�" + std::to_string(cntFile) + "���ļ�, ��" + std::to_string(cntItem) + "����Ŀ";
		if (!sModErr.empty()) {
			*resLog << "��ȡʧ��" + std::to_string(sModErr.size()) + "��:";
			for (auto& it : sModErr) {
				*resLog << it;
			}
		}
	}
	//��ȡplugin
	vector<std::filesystem::path> sLuaFile;
	int cntLuaFile = listDir(DiceDir + "\\plugin\\", sLuaFile);
	int cntOrder{ 0 };
	if (cntLuaFile <= 0)return cntLuaFile;
	vector<string> sLuaErr; 
	msgorder.clear();
	for (auto& pathFile : sLuaFile) {
		string fileLua = pathFile.string();
		if (fileLua.rfind(".lua") != fileLua.length() - 4) {
			sLuaErr.push_back(pathFile.filename().string());
			continue;
		}
		std::unordered_map<std::string, std::string> mOrder;
		int cnt = lua_readStringTable(fileLua.c_str(), "msg_order", mOrder);
		if (cnt > 0) {
			for (auto& [key, func] : mOrder) {
				msgorder[key] = { fileLua,func };
			}
			cntOrder += mOrder.size();
		}
		else if (cnt < 0) {
			sLuaErr.push_back(pathFile.filename().string());
		}
	}
	*resLog << "��ȡ\\plugin\\�е�" + std::to_string(cntLuaFile) + "���ű�, ��" + std::to_string(cntOrder) + "��ָ��";
	if (!sLuaErr.empty()) {
		*resLog << "��ȡʧ��" + std::to_string(sLuaErr.size()) + "��:";
		for (auto& it : sLuaErr) {
			*resLog << it;
		}
	}
	std::thread factory(&DiceModManager::init,this);
	factory.detach();
	if (cntHelp.empty()) {
		cntHelp.reserve(helpdoc.size());
		loadJMap(DiceDir + "\\user\\HelpStatic.json", cntHelp);
	}
	return cntFile;
}
void DiceModManager::init() {
	isIniting = true;
	for (auto& [key, word] : helpdoc) {
		querier.insert(key);
	}
	gOrder.build(msgorder);
	isIniting = false;
}
void DiceModManager::clear()
{
	helpdoc.clear();
	msgorder.clear();
}
