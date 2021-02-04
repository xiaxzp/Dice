//#pragma comment(lib, "lua.lib")  
extern "C"{
#include <lua.h>  
#include <lualib.h>  
#include <lauxlib.h>  
};
#include "ManagerSystem.h"
#include "DiceEvent.h"
#include "RandomGenerator.h"
#include "CharacterCard.h"
#include "CardDeck.h"
#include "DiceSession.h"

unordered_set<lua_State*> UTF8Luas;

class LuaState {
	lua_State* state;
	//bool isValid;
public:
	LuaState(const char* file);
	//operator bool()const { return isValid; }
	operator lua_State* () { return state; }
	~LuaState() {
		if(state)lua_close(state);
		UTF8Luas.erase(state);
	}
	void regist();
};

void lua_push_string(lua_State* L, const string& str) {
	if (UTF8Luas.count(L))
		lua_pushstring(L, GBKtoUTF8(str).c_str());
	else
		lua_pushstring(L, str.c_str());
}
void lua_set_field(lua_State* L, int idx, const string& str) {
	if (UTF8Luas.count(L))
		lua_setfield(L, idx, GBKtoUTF8(str).c_str());
	else
		lua_setfield(L, idx, str.c_str());
}

void lua_push_msg(lua_State* L, FromMsg* msg) {
	lua_newtable(L);
	//lua_pushnumber(L, (double)msg->fromQQ);
	lua_push_string(L, to_string(msg->fromQQ));
	lua_setfield(L, -2, "fromQQ");
	//lua_pushnumber(L, (double)msg->fromGroup);
	lua_push_string(L, to_string(msg->fromGroup));
	lua_setfield(L, -2, "fromGroup");
	lua_push_string(L, msg->strMsg);
	lua_setfield(L, -2, "fromMsg");
}
void CharaCard::pushTable(lua_State* L) {
	lua_newtable(L);
	for (auto& [key, val] : Info) {
		lua_push_string(L, val);
		lua_set_field(L, -2, key.c_str());
	}
	for (auto& [key, val] : Attr) {
		lua_pushnumber(L, val);
		lua_set_field(L, -2, key.c_str());
	}
}
void CharaCard::toCard(lua_State* L) {

}
//��ȡָ��lua�ļ��ĺ���������
bool lua_msg_order(FromMsg* msg, const char* file, const char* func) {
	LuaState L(file);
	if (!L)return false;
	lua_getglobal(L, func); 
	lua_push_msg(L, msg);
	if (lua_pcall(L, 1, 2, 0)) {
		const char* pErrorMsg = lua_tostring(L, -1);
		console.log(GlobalMsg["strSelfName"] + "����" + file + "����" + func + "ʧ��!\n" + pErrorMsg, 1);
		msg->reply(GlobalMsg["strOrderLuaErr"]);
		return false;
	}
	if (lua_gettop(L) && lua_type(L, 1) != LUA_TNIL) {
		if (!lua_isstring(L, 1)) {
			console.log(GlobalMsg["strSelfName"] + "����" + file + "����" + func + "����ֵ��ʽ����!", 1);
			msg->reply(GlobalMsg["strOrderLuaErr"]);
			return false;
		}
		if (!(msg->strVar["msg_reply"] = UTF8toGBK(lua_tostring(L, 1), true)).empty()) {
			msg->reply(msg->strVar["msg_reply"]);
		}
		if (lua_type(L, 2) != LUA_TNIL) {
			if (!lua_isstring(L, 2)) {
				console.log(GlobalMsg["strSelfName"] + "����" + file + "����" + func + "����ֵ��ʽ����!", 1);
				return false;
			}
			if (!(msg->strVar["msg_hidden"] = UTF8toGBK(lua_tostring(L, 2), true)).empty()) {
				msg->replyHidden(msg->strVar["msg_hidden"]);
			}
		}
	}
	return true;
}

/**
 * ��lua���õĺ���
 */

 //��������lua�ű�
int loadLua(lua_State* L) {
	string nameFile{ UTF8toGBK(lua_tostring(L, -1),true) };
	string pathFile = DiceDir + "\\plugin\\" + nameFile + ".lua";
	if (!std::filesystem::exists(pathFile) && nameFile.find('/') == string::npos && nameFile.find('\\') == string::npos)
		pathFile = DiceDir + "\\plugin\\" + nameFile + "\\init.lua";
	if (luaL_loadfile(L, pathFile.c_str())) {
		const char* pErrorMsg = lua_tostring(L, -1);
		console.log(GlobalMsg["strSelfName"] + "��ȡlua�ļ�" + pathFile + "ʧ��:"+ pErrorMsg, 0b10);
		return 0;
	}
	if (lua_pcall(L, 0, 1, 0)) {
		const char* pErrorMsg = lua_tostring(L, -1);
		console.log(GlobalMsg["strSelfName"] + "����lua�ļ�" + pathFile + "ʧ��:"+ pErrorMsg, 0b10);
		return 1;
	}
	return 1;
}
 //��ȡDiceMaid
int getDiceQQ(lua_State* L) {
	lua_push_string(L, to_string(console.DiceMaid));
	return 1;
}
//��ȡDiceDir�浵Ŀ¼
int getDiceDir(lua_State* L) {
	lua_push_string(L, DiceDir);
	return 1;
}
int mkDirs(lua_State* L) {
	string dir{ UTF8toGBK(lua_tostring(L, -1),true) };
	mkDir(dir);
	return 0;
}
int getUserConf(lua_State* L) {
	long long qq{ (long long)lua_tonumber(L, 1) };
	string item{ UTF8toGBK(lua_tostring(L, 2),true) };
	User& user{ getUser(qq) };
	if (user.intConf.count(item)) {
		lua_pushnumber(L, (double)user.intConf[item]);
	}
	else if (user.strConf.count(item)) {
		lua_push_string(L, user.strConf[item].c_str());
	}
	else {
		lua_pushnil(L);
		lua_insert(L, 3);
	}
	return 1;
}
int setUserConf(lua_State* L) {
	long long qq{ (long long)lua_tonumber(L, -3) };
	string item{ UTF8toGBK(lua_tostring(L, -2),true) };
	if (lua_isnumber(L, -1)) {
		getUser(qq).setConf(item, (int)lua_tonumber(L, -1));
	}
	else if (lua_isstring(L, -1)) {
		getUser(qq).setConf(item, UTF8toGBK(lua_tostring(L, -1), true));
	}
	return 0;
}
int getUserToday(lua_State* L) {
	long long qq{ (long long)lua_tonumber(L, 1) };
	string item{ UTF8toGBK(lua_tostring(L, 2),true) };
	if (item == "jrrp")
		lua_pushnumber(L, today->getJrrp(qq));
	else
		lua_pushnumber(L, today->get(qq, item));
	return 1;
}
int setUserToday(lua_State* L) {
	long long qq{ (long long)lua_tonumber(L, -3) };
	string item{ UTF8toGBK(lua_tostring(L, -2),true) };
	int val{ (int)lua_tonumber(L, -1) };
	today->set(qq, item, val);
	return 0;
}

int getPlayerCardAttr(lua_State* L) {
	long long plQQ{ (long long)lua_tonumber(L, 1) };
	long long group{ (long long)lua_tonumber(L, 2) };
	string key{ UTF8toGBK(lua_tostring(L, 3),true) };
	CharaCard& pc = getPlayer(plQQ)[group];
	if (pc.Info.count(key)) {
		lua_push_string(L, pc.Info.find(key)->second);
		return 3;
	}
	else if (key == "note") {
		lua_push_string(L, pc.Note);
		return 2;
	}
	else if (pc.DiceExp.count(key)) {
		lua_push_string(L, pc.DiceExp.find(key)->second);
	}
	else if (key = pc.standard(key); pc.Attr.count(key)) {
		lua_pushnumber(L, (double)pc.Attr.find(key)->second);
	}
	else {
		lua_pushnil(L);
		lua_insert(L, 4);
	}
	return 1;
}
int getPlayerCard(lua_State* L) {
	long long plQQ{ (long long)lua_tonumber(L, 1) };
	long long group{ (long long)lua_tonumber(L, 2) };
	if (PList.count(plQQ)) {
		getPlayer(plQQ)[group].pushTable(L);
		return 1;
	}
	return 0;
}
int setPlayerCardAttr(lua_State* L) {
	long long plQQ{ (long long)lua_tonumber(L, 1) };
	long long group{ (long long)lua_tonumber(L, 2) };
	string item{ UTF8toGBK(lua_tostring(L, 3),true) };
	CharaCard& pc = getPlayer(plQQ)[group];
	if (lua_isnumber(L, -1)) {
		pc.set(item, (int)lua_tonumber(L, -1));
	}
	else if (lua_isstring(L, -1)) {
		if (item.empty())return 0;
		else if (item[0] == '&')pc.setExp(item.substr(1), UTF8toGBK(lua_tostring(L, -1), true));
		else pc.setInfo(item, UTF8toGBK(lua_tostring(L, -1), true));
	}
	return 0;
}

//ȡ�����
int ranint(lua_State* L) {
	int l{ (int)lua_tonumber(L, -2) };
	int r{ (int)lua_tonumber(L, -1) };
	lua_pushnumber(L, RandomGenerator::Randint(l,r));
	return 1;
}
//�̵߳ȴ�
int sleepTime(lua_State* L) {
	int ms{ (int)lua_tonumber(L, -1) };
	std::this_thread::sleep_for(std::chrono::milliseconds(ms));
	return 0;
}

int drawDeck(lua_State* L) {
	long long fromGroup{ (long long)lua_tonumber(L, -3) };
	long long fromQQ{ (long long)lua_tonumber(L, -2) };
	string nameDeck{ UTF8toGBK(lua_tostring(L, -1),true) };
	long long fromSession{ fromGroup ? fromGroup : ~fromQQ };
	if (gm->has_session(fromSession)) {
		lua_push_string(L, gm->session(fromSession).deck_draw(nameDeck));
	}
	else if (CardDeck::findDeck(nameDeck)) {
		vector<string>& deck = CardDeck::mPublicDeck[nameDeck];
		lua_push_string(L, CardDeck::draw(deck[RandomGenerator::Randint(0, deck.size() - 1)]));
	}
	else {
		lua_push_string(L, "{" + nameDeck + "}");
	}
	return 1;
}

int eventMsg(lua_State* L) {
	string fromMsg{ UTF8toGBK(lua_tostring(L, -3),true) };
	long long fromGroup{ (long long)lua_tonumber(L, -2) };
	long long fromQQ{ (long long)lua_tonumber(L, -1) };
	msgtype type{ fromGroup ?
		chat(fromGroup).isGroup ? msgtype::Group : msgtype::Discuss
		: msgtype::Private };
	FromMsg* Msg = new FromMsg(fromGroup ? FromMsg(fromMsg, fromGroup, type, fromQQ)
							   : FromMsg(fromMsg, fromQQ));
	std::thread th(*Msg);
	th.detach();
	return 0;
}

void LuaState::regist() {
	const luaL_Reg Dicelibs[] = {
		{"loadLua", loadLua},
		{"getDiceQQ", getDiceQQ},
		{"getDiceDir", getDiceDir},
		{"mkDirs", mkDirs},
		{"getUserConf", getUserConf},
		{"setUserConf", setUserConf},
		{"getUserToday", getUserToday},
		{"setUserToday", setUserToday},
		{"getPlayerCardAttr", getPlayerCardAttr},
		{"setPlayerCardAttr", setPlayerCardAttr},
		{"getPlayerCard", getPlayerCard},
		{"ranint", ranint},
		{"sleepTime", sleepTime},
		{"drawDeck", drawDeck},
		{"eventMsg", eventMsg},
		{nullptr, nullptr},
	};
	for (const luaL_Reg* lib = Dicelibs; lib->func; lib++) {
		lua_register(state, lib->name, lib->func);
	}
	lua_getglobal(state, "package");
	lua_getfield(state, -1, "path");
	string strPath(DiceDir + "\\plugin\\?.lua;" + lua_tostring(state, -1));
	lua_pushstring(state, strPath.c_str());
	lua_setfield(state, -3, "path");
	lua_pop(state, 2);
}

LuaState::LuaState(const char* file) {//:isValid(false) {
	state = luaL_newstate();
	if (!state)return;
	if (luaL_loadfile(state, file)) {
		const char* pErrorMsg = lua_tostring(state, -1);
		console.log(GlobalMsg["strSelfName"] + "��ȡlua�ļ�" + file + "ʧ��:" + pErrorMsg, 0b10);
		lua_close(state);
		state = nullptr;
		return;
	}
	luaL_openlibs(state);
	regist();
	if (lua_pcall(state, 0, 0, 0)) {
		const char* pErrorMsg = lua_tostring(state, -1);
		console.log(GlobalMsg["strSelfName"] + "����lua�ļ�" + file + "ʧ��:" + pErrorMsg, 0b10);
		lua_close(state);
		state = nullptr;
		return;
	}
	ifstream fs(file);
	stringstream ss; 
	ss << fs.rdbuf(); 
	string strCheck = ss.str(); 
	if (checkUTF8(strCheck))UTF8Luas.insert(state);
}

int lua_readStringTable(const char* file, const char* var, std::unordered_map<std::string, std::string>& tab) {
	LuaState L(file);
	if (!L)return -1;
	lua_getglobal(L, var);
	if (lua_type(L, 1) == LUA_TNIL) {
		return 0;
	}
	if (lua_type(L, 1) != LUA_TTABLE) {
		return -2;
	}
	try {
		lua_pushnil(L);
		while (lua_next(L, -2)) {
			if (!lua_isstring(L, -1) || !lua_isstring(L, -2)) {
				return -1;
			}
			string key = UTF8toGBK(lua_tostring(L, -2), true);
			string value = UTF8toGBK(lua_tostring(L, -1), true);
			tab[key] = value;
			lua_pop(L, 1);
		}
		return tab.size();
	} catch (...) {
		return -3;
	}
}