/**
 * ��������ϸ
 * �����ݿ�ʽ�Ĺ���
 * Copyright (C) 2019-2020 String.Empty
 */
#include <mutex>
#include <thread>
#include <chrono>
#include <unordered_map>
#include <unordered_set>
#include "BlackListManager.h"
#include "Jsonio.h"
#include "STLExtern.hpp"
#include "DDAPI.h"
#include "DiceEvent.h"
#include "DiceConsole.h"
#include "DiceNetwork.h"

using namespace std;
using namespace nlohmann;

using Mark = DDBlackMark;
using Manager = DDBlackManager;
using Factory = DDBlackMarkFactory;

//�ж�����
int isReliable(long long QQID)
{
	if (!QQID)return 0;
	if (QQID == console.master())return 255;
	if (trustedQQ(QQID) > 2)return trustedQQ(QQID) - 1;
	if (mDiceList.count(QQID))
	{
		if (trustedQQ(mDiceList[QQID]) > 2)return trustedQQ(mDiceList[QQID]) - 1;
		if (console["BelieveDiceList"] || mDiceList[QQID] == QQID)return 1;
	}
	if (blacklist->get_qq_danger(QQID))return -1;
	return 0;
}

//�����û����Ѳ�Ⱥ
void checkGroupWithBlackQQ(const DDBlackMark& mark, long long llQQ)
{
	set<unsigned int> sQQwarning;
	ResList list;
	string strNotice;
	for (auto& [id, grp] : ChatList)
	{
		int authSelf;
		if (grp.isset("����") || grp.isset("δ��") || grp.isset("����") || !grp.isGroup 
			|| !(authSelf = DD::getGroupAuth(id, console.DiceMaid, 0)))continue;
		if (DD::isGroupMember(grp.ID, llQQ, false))	{
			strNotice = printGroup(id);
			if (grp.isset("Э����Ч")) {
				strNotice += "ȺЭ����Ч";
			}
			else if (grp.isset("���")) {
				if (mark.isSource(console.DiceMaid) && !mark.isType("local"))DD::sendGroupMsg(id, mark.warning());
				strNotice += "Ⱥ���";
			}
			else if (int authBlack{ DD::getGroupAuth(id,llQQ,0) }; authBlack < 1 || authSelf < 1) {
				strNotice += "ȺȨ�޻�ȡʧ��";
			}
			else if (authBlack < authSelf) {
				if (mark.isSource(console.DiceMaid && !mark.isType("local")))AddMsgToQueue(
					mark.warning(), id, msgtype::Group);
				strNotice += "�Է�ȺȨ�޽ϵ�";
			}
			else if (authSelf > authBlack)
			{
				DD::sendGroupMsg(id, mark.warning());
				grp.leave("������������������Ա" + printQQ(llQQ) + "\n" + GlobalMsg["strSelfName"] + "��Ԥ������Ⱥ");
				strNotice += "�Է�ȺȨ�޽ϸߣ�����Ⱥ";
				this_thread::sleep_for(1s);
			}
			else if (grp.isset("����"))
			{
				if (mark.isSource(console.DiceMaid) && !mark.isType("local"))AddMsgToQueue(
					mark.warning(), id, msgtype::Group);
				strNotice += "Ⱥ����";
			}
			else if (console["LeaveBlackQQ"])
			{
				DD::sendGroupMsg(id, mark.warning());
				grp.leave("����������������Ա" + printQQ(llQQ) + "��ͬ��ȺȨ�ޣ�\n" + GlobalMsg["strSelfName"] + "��Ԥ������Ⱥ");
				strNotice += "����Ⱥ";
				this_thread::sleep_for(1s);
			}
			else if (mark.isSource(console.DiceMaid) && !mark.isType("local"))AddMsgToQueue(
				mark.warning(), id, msgtype::Group);
			list << strNotice;
		}
	}
	if (!list.empty())
	{
		strNotice = "�������" + printQQ(llQQ) + "��ͬȺ��" + to_string(list.size()) + "����" + list.show();
		console.log(strNotice, 0b100, printSTNow());
	}
}

// warning�������
std::queue<fromMsg> warningQueue;
// ��Ϣ���Ͷ�����
mutex warningMutex;

bool isLoadingExtern = false;

void AddWarning(const string& msg, long long DiceQQ, long long fromGroup)
{
	lock_guard<std::mutex> lock_queue(warningMutex);
	warningQueue.emplace(msg, DiceQQ, fromGroup);
}

void warningHandler()
{
	fromMsg warning;
	while (Enabled)
	{
		if (!warningQueue.empty())
		{
			{
				lock_guard<std::mutex> lock_queue(warningMutex);
				warning = warningQueue.front();
				warningQueue.pop();
			}
			if (warning.strMsg.empty())continue;
			if (warning.fromQQ)console.log("��������" + printQQ(warning.fromQQ) + "��warning:" + warning.strMsg, 0,
			                               printSTNow());
			try
			{
				json j = json::parse(GBKtoUTF8(warning.strMsg));
				if (j.is_array())
				{
					for (auto it : j)
					{
						blacklist->verify(&it, warning.fromQQ);
					}
				}
				else
				{
					blacklist->verify(&j, warning.fromQQ);
				}
				std::this_thread::sleep_for(100ms);
			}
			catch (...)
			{
				console.log("warning����ʧ�ܡ�", 0);
			}
		}
		else std::this_thread::sleep_for(200ms);
	}
}

int getCloudBlackMark(int wid, string& res)
{
	string strObj{"/blacklist/warning.php?wid=" + to_string(wid)};
	string temp;
	const bool reqRes = Network::GET("shiki.stringempty.xyz", strObj.c_str(), 80, temp);
	if (!reqRes)return -1;
	if (temp == "null")return -2;
	res = temp;
	return 1;
}

std::unique_ptr<DDBlackManager> blacklist;
std::mutex blacklistMutex;

map<string, int> credit_limit{
	{"null", 6},
	{"kick", 2}, {"ban", 2}, {"spam", 2}, {"ruler", 2}, {"extern", 2},
	{"other", 3}, {"local", 3}, {"invite", 3}
};

DDBlackMark::DDBlackMark(long long qq, long long group) : type("local"), danger(2), comment("���غ�������¼")
{
	if (qq)fromQQ = {qq, true};
	if (group)fromGroup = {group, true};
}

DDBlackMark::DDBlackMark(void* pJson)
{
	try
	{
		json& j = *static_cast<json*>(pJson);
		bool isAdd = true;
		if (j.count("type"))
		{
			if (j["type"] == "erase")
			{
				isAdd = false;
				isClear = true;
			}
			else if (!credit_limit.count(j["type"].get<string>())) { return; }
			else type = j["type"].get<string>();
		}
		if (j.count("wid")) {
			j["wid"].get_to(wid);
			if (j.count("isErased")) {
				isClear = j["isErased"].get<int>();
				isAdd = !isClear;
			}
		}
		if (j.count("fromGroup"))fromGroup = {j["fromGroup"].get<long long>(), isAdd};
		if (j.count("fromQQ"))fromQQ = {j["fromQQ"].get<long long>(), isAdd};
		if (j.count("inviterQQ"))inviterQQ = {j["inviterQQ"].get<long long>(), isAdd};
		if (j.count("ownerQQ"))ownerQQ = {j["ownerQQ"].get<long long>(), isAdd};

		if (j.count("DiceMaid"))DiceMaid = j["DiceMaid"].get<long long>();
		if (j.count("masterQQ"))masterQQ = j["masterQQ"].get<long long>();

		if (j.count("danger"))
		{
			danger = j["danger"].get<int>();
			if (danger < 1)return;
		}
		else {
			danger = (type == "ruler") ? 3 : 2;
		}

		if (j.count("time"))time = UTF8toGBK(j["time"].get<string>());
		if (j.count("note"))note = UTF8toGBK(j["note"].get<string>());
		if (j.count("comment"))comment = UTF8toGBK(j["comment"].get<string>());
		if (j.count("erase"))
		{
			isClear = true;
			for (auto& key : j["erase"])
			{
				if (key.get<string>() == "fromGroup")fromGroup.second = false;
				else if (key.get<string>() == "fromQQ")fromQQ.second = false;
				else if (key.get<string>() == "inviterQQ")inviterQQ.second = false;
				else if (key.get<string>() == "ownerQQ")ownerQQ.second = false;
			}
			if (fromGroup.second || fromQQ.second || inviterQQ.second || ownerQQ.second)isClear = false;
		}
		isValid = true;
		return;
	}
	catch (...)
	{
		console.log("����������jsonʧ�ܣ�", 0, printSTNow());
		return;
	}
}

DDBlackMark::DDBlackMark(const string& strWarning)
{
	try
	{
		json j = json::parse(strWarning);
		new(this)DDBlackMark(&j);
	}
	catch (...)
	{
		console.log("����������jsonʧ�ܣ�", 0, printSTNow());
		return;
	}
}

string DDBlackMark::printJson(int tab = 0) const
{
	json j;
	if (wid)j["wid"] = wid;
	j["type"] = type;
	j["danger"] = danger;
	vector<string> eraseID;
	if (fromGroup.first)
	{
		j["fromGroup"] = fromGroup.first;
		if (!fromGroup.second)eraseID.push_back("fromGroup");
	}
	if (fromQQ.first)
	{
		j["fromQQ"] = fromQQ.first;
		if (!fromQQ.second)eraseID.push_back("fromQQ");
	}
	if (inviterQQ.first)
	{
		j["inviterQQ"] = inviterQQ.first;
		if (!inviterQQ.second)eraseID.push_back("inviterQQ");
	}
	if (ownerQQ.first)
	{
		j["ownerQQ"] = ownerQQ.first;
		if (!ownerQQ.second)eraseID.push_back("ownerQQ");
	}
	if (!eraseID.empty())j["erase"] = eraseID;
	if (!time.empty())j["time"] = GBKtoUTF8(time);
	if (!note.empty())j["note"] = GBKtoUTF8(note);
	if (DiceMaid)j["DiceMaid"] = DiceMaid;
	if (masterQQ)j["masterQQ"] = masterQQ;
	if (!comment.empty())j["comment"] = GBKtoUTF8(comment);
	if (tab)return UTF8toGBK(j.dump(tab));
	return UTF8toGBK(j.dump());
}

string DDBlackMark::warning() const
{
	json j;
	if (wid)j["wid"] = wid;
	j["type"] = type;
	j["danger"] = danger;
	if (fromGroup.second)j["fromGroup"] = fromGroup.first;
	if (fromQQ.second)j["fromQQ"] = fromQQ.first;
	if (inviterQQ.second)j["inviterQQ"] = inviterQQ.first;
	if (ownerQQ.second)j["ownerQQ"] = ownerQQ.first;
	if (!time.empty())j["time"] = GBKtoUTF8(time);
	if (!note.empty())j["note"] = GBKtoUTF8(note);
	if (DiceMaid)j["DiceMaid"] = DiceMaid;
	if (masterQQ)j["masterQQ"] = masterQQ;
	if (!comment.empty())j["comment"] = GBKtoUTF8(comment);
	return "!warning" + UTF8toGBK(j.dump(2));
}

std::string DDBlackMark::getData() const
{
	std::string data = "fromQQ=" + std::to_string(fromQQ.first) + "&fromGroup=" + std::to_string(fromGroup.first) +
		"&DiceMaid=" + std::to_string(DiceMaid) + "&masterQQ=" + std::to_string(masterQQ) + "&time=" + time;
	return data;
}

void DDBlackMark::fill_note()
{
	if (!note.empty())return;
	if (type == "kick")
	{
		note = time + " " + (fromQQ.first ? printQQ(fromQQ.first) : "") + "��" + printQQ(DiceMaid) + "�Ƴ���Ⱥ" + (
			fromGroup.first ? to_string(fromGroup.first) : "");
	}
	else if (type == "ban")
	{
		note = time + " " + (fromGroup.first ? "��" + printGroup(fromGroup.first) + "��" : "") + (
			fromQQ.first ? printQQ(fromQQ.first) : "") + "��" + printQQ(DiceMaid) + "����";
	}
	else if (type == "spam")
	{
		note = time + " " + (fromQQ.first ? printQQ(fromQQ.first) : "") + "��" + printQQ(DiceMaid) + "��Ƶ����ָ��";
	}
}

bool DDBlackMark::isType() const
{
	return "null" != type;
}

bool DDBlackMark::isType(const string& strType) const
{
	return strType == type;
}

bool DDBlackMark::isSame(const DDBlackMark& other) const
{
	if (wid && other.wid)return other.wid == wid;
	bool isLike = false;
	if (type != other.type && type != "null" && other.type != "null")return false;
	if (time.length() == other.time.length() && time.length() > 0)
	{
		if (time != other.time)return false;
		isLike = true;
	}
	if (fromGroup.first && other.fromGroup.first)
	{
		if (fromGroup.first != other.fromGroup.first)return false;
		isLike = true;
	}
	if (fromQQ.first && other.fromQQ.first)
	{
		if (fromQQ.first != other.fromQQ.first)return false;
		isLike = true;
	}
	if (inviterQQ.first && other.inviterQQ.first)
	{
		if (inviterQQ.first != other.inviterQQ.first)return false;
		isLike = true;
	}
	if (ownerQQ.first && other.ownerQQ.first)
	{
		if (ownerQQ.first != other.ownerQQ.first)return false;
		isLike = true;
	}
	if (DiceMaid && other.DiceMaid && DiceMaid != other.DiceMaid)return false;
	if (note == other.note)return true;
	return isLike;
}

bool DDBlackMark::isSource(long long qq) const
{
	return DiceMaid == qq || masterQQ == qq;
}
void DDBlackMark::check_remit()
{
    if (fromGroup.first && groupset(fromGroup.first, "���") > 0)erase();
    if (fromQQ.first && trustedQQ(fromQQ.first) > 1)erase();
	if (inviterQQ.first && trustedQQ(inviterQQ.first) > 1)inviterQQ = { 0,false };
    if (ownerQQ.first && trustedQQ(ownerQQ.first) > 1)ownerQQ = { 0,false };
}

void DDBlackMark::erase()
{
	fromGroup.second = fromQQ.second = inviterQQ.second = ownerQQ.second = false;
	isClear = true;
}

void DDBlackMark::upload()
{
	std::string info = "&masterQQ=" + std::to_string(masterQQ) + "&time=" +	time + "&note=" + UrlEncode(GBKtoUTF8(note));
	int res{ DD::uploadBlack(console.DiceMaid, fromQQ.first, fromGroup.first, type, info) };
	if (!res) {
		erase();
	}
	else if (res < 0) {
		console.log("�ϴ�������¼ʧ��:" + info, 0b1);
	}
	else {
		wid = res;
	}
}

int DDBlackMark::check_cloud()
{
	std::string frmdata = "fromQQ=" + std::to_string(fromQQ.first) + "&fromGroup=" + std::to_string(fromGroup.first) +
		"&DiceMaid=" + std::to_string(DiceMaid) + "&masterQQ=" + std::to_string(masterQQ) + "&time=" + time;
	string temp;
	const bool reqRes = Network::POST("shiki.stringempty.xyz", "/blacklist/check.php", 80, frmdata.data(), temp);
	if (!reqRes)
	{
		console.log("�Ƽ�¼����ʧ��" + temp, 0);
		return -2;
	}
	if (temp[0] == '?') 
	{
		console.log("ƥ�䵽δȷ���Ƽ�¼:wid" + temp, 0);
		wid = stoi(temp.substr(1));
		return 1;
	}
	else if (temp[0] == '+')
	{
		console.log("ƥ�䵽δע���Ƽ�¼:wid" + temp, 0);
		wid = stoi(temp.substr(1));
		return 1;
	}
	if (temp[0] == '-')
	{
		console.log("ƥ�䵽��ע���Ƽ�¼:wid" + temp, 0);
		wid = stoi(temp.substr(1));
		return 0;
	}
	return -1;
}

int DDBlackManager::find(const DDBlackMark& mark)
{
    std::lock_guard<std::mutex> lock_queue(blacklistMutex);
    unordered_set<unsigned int> sRange;
    if (mark.wid && mCloud.count(mark.wid)) return mCloud[mark.wid];
    if (mark.wid){
        if (mCloud.count(mark.wid)) return mCloud[mark.wid];
        sRange = sIDEmpty;
    }
    if (mark.time.length() == 19) 
	{
        unordered_set<unsigned int> sTimeRange = sTimeEmpty;
        for (auto& [key,id] : multi_range(mTimeIndex, mark.time)) 
		{
            sTimeRange.insert(id);
        }
        if (sRange.empty())
		{
            sRange.swap(sTimeRange);
        }
        else
		{
            unordered_set<unsigned int> sInter;

            for (const auto& ele : sRange)
            {
                if (sTimeRange.count(ele))
                {
                    sInter.insert(ele);
				}
			}
            //std::set_intersection(sRange.begin(), sRange.end(), sTimeRange.begin(), sTimeRange.end(), std::inserter(sInter, sInter.begin()));
            if (sInter.empty())return -1;
            sRange.swap(sInter);
        }
    }
    if (mark.fromGroup.first)
	{
        unordered_set<unsigned int> sGroupRange = sGroupEmpty;
        for (auto& [key, id] : multi_range(mGroupIndex, mark.fromGroup.first))
		{
            sGroupRange.insert(id);
        }
        if (sGroupRange.empty())return -1;
        if (sRange.empty())
		{
            sRange.swap(sGroupRange);
        }
        else 
		{
            unordered_set<unsigned int> sInter;
            
            // O(n)
            for (const auto& ele : sRange)
            {
                if (sGroupRange.count(ele))
                {
                    sInter.insert(ele);
				}
			}
            //std::set_intersection(sRange.begin(), sRange.end(), sGroupRange.begin(), sGroupRange.end(), std::inserter(sInter, sInter.begin()));
            if (sInter.empty())return -1;
            sRange.swap(sInter);
        }
    }
    if (mark.fromQQ.first)
	{
        unordered_set<unsigned int> sQQRange = sQQEmpty;
        for (auto& [key, id] : multi_range(mQQIndex, mark.fromQQ.first)) 
		{
            if (Enabled)console.log("ƥ���û���¼" + to_string(id), 0);
            sQQRange.insert(id);
        }
        if (sQQRange.empty())return -1;
        if (sRange.empty())
		{
            sRange.swap(sQQRange);
        }
        else
		{
            unordered_set<unsigned int> sInter;

            for (const auto& ele : sRange)
            {
                if (sQQRange.count(ele))
                {
                    sInter.insert(ele);
				}
			}
            //std::set_intersection(sRange.begin(), sRange.end(), sQQRange.begin(), sQQRange.end(), std::inserter(sInter, sInter.begin()));
            if (sInter.empty())return -1;
            sRange.swap(sInter);
        }
    }
    for (auto i : sRange) 
	{
        if (vBlackList[i].isSame(mark))return i;
    }
    return -1;
}

DDBlackMark& DDBlackMark::operator<<(const DDBlackMark& mark)
{
    // int delta_danger = mark.danger - danger;
    if (type == "null" && mark.type != "null")type = mark.type;
    if (time.empty() && !mark.time.empty())
	{
        time = mark.time;
    }
    if (note != mark.note &&
        (note.empty() || count_char(note, '?') > count_char(mark.note, '?') || note.length() < mark.note.length())
        )
	{
        note = mark.note;
    }
    if (mark.fromGroup.first)
	{
        fromGroup = mark.fromGroup;
    }
    if (mark.fromQQ.first)
	{
        fromQQ = mark.fromQQ;
    }
    if (mark.inviterQQ.first)
	{
        inviterQQ = mark.inviterQQ;
    }
    if (mark.ownerQQ.first) 
	{
        ownerQQ = mark.ownerQQ;
    }
    if (!DiceMaid && mark.DiceMaid)DiceMaid = mark.DiceMaid;
    if (!masterQQ && mark.masterQQ)masterQQ = mark.masterQQ;
    //save comment if the mark changed at this update
    if (!mark.comment.empty())
	{
        comment = mark.comment;
    }
    return *this;
}

bool DDBlackManager::insert(DDBlackMark& ex_mark)
{
    std::lock_guard<std::mutex> lock_queue(blacklistMutex);
    unsigned id = vBlackList.size();
    vBlackList.push_back(ex_mark);
    DDBlackMark& mark(vBlackList[id]);
    if (mark.wid)mCloud[mark.wid] = id;
    else sIDEmpty.insert(id);
    if (mark.time.length() == 19)mTimeIndex.emplace(mark.time, id);
    else sTimeEmpty.insert(id);
    if (mark.fromGroup.first)
	{
        mGroupIndex.emplace(mark.fromGroup.first, id);
        if (mark.fromGroup.second)
		{
            up_group_danger(mark.fromGroup.first, mark); 
        }
    }
    else
	{
        sGroupEmpty.insert(id);
    }
    if (mark.fromQQ.first) 
	{
        mQQIndex.emplace(mark.fromQQ.first, id);
        if (mark.fromQQ.second)
		{
            up_qq_danger(mark.fromQQ.first, mark); 
        }
    }
    else
	{
        sQQEmpty.insert(id);
    }
    if (mark.inviterQQ.first)
	{
        mQQIndex.emplace(mark.inviterQQ.first, id);
        if (mark.inviterQQ.second)
		{
            up_qq_danger(mark.inviterQQ.first, mark);
        }
    }
    if (mark.ownerQQ.first)
	{
        mQQIndex.emplace(mark.ownerQQ.first, id);
        if (mark.ownerQQ.second)
		{
            up_qq_danger(mark.ownerQQ.first, mark);
        }
    }
    if (Enabled && !isLoadingExtern)blacklist->saveJson(DiceDir + "\\conf\\BlackList.json");
	return !mark.isClear;
}

bool DDBlackManager::update(DDBlackMark& mark, unsigned int id, int credit = 5)
{
    std::lock_guard<std::mutex> lock_queue(blacklistMutex);
    DDBlackMark& old_mark = vBlackList[id];
    int delta_danger = mark.danger - old_mark.danger;
    bool isUpdated = false;
    if (delta_danger)
	{
        old_mark.danger = mark.danger;
        isUpdated = true;
    }
    if (mark.wid && !old_mark.wid)
	{
        sIDEmpty.erase(id);
        old_mark.wid = mark.wid;
        mCloud.emplace(old_mark.wid, id);
        isUpdated = true;
    }
    if (old_mark.type == "null" && mark.type != "null")old_mark.type = mark.type;
    if (old_mark.time.length() < mark.time.length() && mark.time.length() <= 19) {
        old_mark.time = mark.time;
        sTimeEmpty.erase(id);
        if (mark.time.length() == 19)mTimeIndex.emplace(old_mark.time, id);
    }
    if (old_mark.note != mark.note &&
        (old_mark.note.empty() || count_char(old_mark.note, '?') > count_char(mark.note, '?') || old_mark.note.length()
			< mark.note.length())
        )
	{
        old_mark.note = mark.note;
    }
    if (mark.fromGroup.first)
	{
        if (!old_mark.fromGroup.first) 
		{
            sGroupEmpty.erase(id);
            mGroupIndex.emplace(mark.fromGroup.first, id);
            if (mark.fromGroup.second)
			{
                up_group_danger(mark.fromGroup.first, mark);
            }
            old_mark.fromGroup = mark.fromGroup;
            isUpdated = true;
        }
        else if (mark.fromGroup.second != old_mark.fromGroup.second)
		{
            if (old_mark.fromGroup.second)
			{
                old_mark.fromGroup.second = false;
                reset_group_danger(mark.fromGroup.first);
                isUpdated = true;
            }
            else if (delta_danger > 0 || credit > 2)
			{
                old_mark.fromGroup.second = true;
                up_group_danger(mark.fromGroup.first, mark);
                isUpdated = true;
            }
        }
    }
    if (mark.fromQQ.first) 
	{
        if (!old_mark.fromQQ.first) 
		{
            sQQEmpty.erase(id);
            mQQIndex.emplace(mark.fromQQ.first, id);
            old_mark.fromQQ = mark.fromQQ;
            if (mark.fromQQ.second)
			{
                up_qq_danger(mark.fromQQ.first, mark);
            }
            isUpdated = true;
        }
        else if (mark.fromQQ.second != old_mark.fromQQ.second)
		{
            if (old_mark.fromQQ.second)
			{
                old_mark.fromQQ.second = false;
                reset_qq_danger(mark.fromQQ.first);
                isUpdated = true;
            }
            else if (delta_danger > 0 || credit > 2)
			{
                old_mark.fromQQ.second = true;
                up_qq_danger(mark.fromQQ.first, mark);
                isUpdated = true;
            }
        }
    }
    if (mark.inviterQQ.first)
	{
        if (!old_mark.inviterQQ.first)
		{
            mQQIndex.emplace(mark.inviterQQ.first, id);
            old_mark.inviterQQ = mark.inviterQQ;
            if (mark.inviterQQ.second)
			{
                up_qq_danger(mark.inviterQQ.first, mark);
            }
            isUpdated = true;
        }
        else if (mark.inviterQQ.second != old_mark.inviterQQ.second)
		{
            if (old_mark.inviterQQ.second) 
			{
                old_mark.inviterQQ.second = false;
                reset_qq_danger(mark.inviterQQ.first);
                isUpdated = true;
            }
            else if (delta_danger > 0 || credit > 2)
			{
                old_mark.inviterQQ.second = true;
                up_qq_danger(mark.inviterQQ.first, mark);
                isUpdated = true;
            }
        }
    }
    if (mark.ownerQQ.first)
	{
        if (!old_mark.ownerQQ.first)
		{
            sQQEmpty.erase(id);
            mQQIndex.emplace(mark.ownerQQ.first, id);
            old_mark.ownerQQ = mark.ownerQQ;
            if (mark.ownerQQ.second)
			{
                up_qq_danger(mark.ownerQQ.first, mark);
            }
            isUpdated = true;
        }
        else if (mark.ownerQQ.second != old_mark.ownerQQ.second) 
		{
            if (old_mark.ownerQQ.second)
			{
                old_mark.ownerQQ.second = false;
                reset_qq_danger(mark.ownerQQ.first);
                isUpdated = true;
            }
            else if (delta_danger > 0 || credit > 2)
			{
                old_mark.ownerQQ.second = true;
                up_qq_danger(mark.ownerQQ.first, mark);
                isUpdated = true;
            }
        }
    }
    if (!old_mark.DiceMaid && mark.DiceMaid)old_mark.DiceMaid = mark.DiceMaid;
    if (!old_mark.masterQQ && mark.masterQQ)old_mark.masterQQ = mark.masterQQ;
    //save comment if the mark changed at this update
    if (isUpdated)
	{
        if (!mark.comment.empty())old_mark.comment = mark.comment;
		else if (old_mark.comment.empty()) {
			old_mark.comment = printSTNow() + " ����";
		}
		if (Enabled && !isLoadingExtern)blacklist->saveJson(DiceDir + "\\conf\\BlackList.json");
    }
    return isUpdated;
}

void DDBlackManager::reset_group_danger(long long llgroup)
{
	int max_danger = 0;
	for (auto [group, id] : multi_range(mGroupIndex, llgroup))
	{
		if (vBlackList[id].fromGroup.second && vBlackList[id].danger > max_danger)max_danger = vBlackList[id].danger;
	}
	if (max_danger == mGroupDanger[llgroup])return;
	if (max_danger)
	{
		mGroupDanger[llgroup] = max_danger;
		console.log("�ѵ���" + printGroup(llgroup) + "��Σ�յȼ�Ϊ" + to_string(max_danger), 0b10, printSTNow());
	}
	else
	{
		mGroupDanger.erase(llgroup);
		if (Enabled && !isLoadingExtern)console.log("������" + printGroup(llgroup) + "��Σ�յȼ�", 0b10, printSTNow());
	}
}

void DDBlackManager::reset_qq_danger(long long llqq)
{
	int max_danger = 0;
	for (auto [qq, id] : multi_range(mQQIndex, llqq))
	{
		if (vBlackList[id].fromQQ.first == llqq && vBlackList[id].fromQQ.second && vBlackList[id].danger > max_danger)
			max_danger = vBlackList[id].danger;
		if (vBlackList[id].inviterQQ.first == llqq && vBlackList[id].inviterQQ.second && vBlackList[id].danger >
			max_danger)max_danger = vBlackList[id].danger;
		if (vBlackList[id].ownerQQ.first == llqq && vBlackList[id].ownerQQ.second && vBlackList[id].danger > max_danger)
			max_danger = vBlackList[id].danger;
	}
	if (max_danger == mQQDanger[llqq])return;
	if (max_danger)
	{
		mQQDanger[llqq] = max_danger;
		console.log("�ѵ���" + printQQ(llqq) + "��Σ�յȼ�Ϊ" + to_string(max_danger), 0b10, printSTNow());
	}
	else
	{
		mQQDanger.erase(llqq);
		if (Enabled)
		{
			if (!isLoadingExtern)console.log("������" + printQQ(llqq) + "��Σ�յȼ�", 0b10, printSTNow());
			if (UserList.count(llqq))AddMsgToQueue(getMsg("strBlackQQDelNotice", {{"user_nick", getName(llqq)}}), llqq);
		}
	}
}

bool DDBlackManager::up_group_danger(long long llgroup, DDBlackMark& mark)
{
	if (groupset(llgroup, "���") > 0)
	{
		mark.erase();
		return false;
	}
	if (mGroupDanger.count(llgroup) && mGroupDanger[llgroup] >= mark.danger)return false;
	mGroupDanger[llgroup] = mark.danger;
	if (Enabled)
	{
		if (ChatList.count(llgroup) && !chat(llgroup).isset("����"))chat(llgroup).leave(
			mark.warning());
		if(!isLoadingExtern)console.log(GlobalMsg["strSelfName"] + "�ѽ�" + printGroup(llgroup) + "Σ�յȼ�������" + to_string(mark.danger), 0b10,
		            printSTNow());
	}
	return true;
}

bool DDBlackManager::up_qq_danger(long long llqq, DDBlackMark& mark)
{
	if (trustedQQ(llqq) > 1 || llqq == console.master() || llqq == console.DiceMaid)
	{
		if (mark.fromQQ.first == llqq)mark.erase();
		if (mark.inviterQQ.first == llqq)mark.inviterQQ.second = false;
		if (mark.ownerQQ.first == llqq)mark.ownerQQ.second = false;
		return false;
	}
	if (mQQDanger.count(llqq) && mQQDanger[llqq] >= mark.danger)return false;
	mQQDanger[llqq] = mark.danger;
	if (Enabled && mark.danger > 1)
	{
		if (!mQQDanger.count(llqq) && UserList.count(llqq) && mark.danger == 2)
			mark.note.empty()
				? AddMsgToQueue(getMsg("strBlackQQAddNotice", {{"user_nick", getName(llqq)}}), llqq)
				: AddMsgToQueue(getMsg("strBlackQQAddNoticeReason", {
					                       {"0", mark.note}, {"reason", mark.note}, {"user_nick", getName(llqq)}
				                       }), llqq);
		if (!isLoadingExtern) {
			console.log(GlobalMsg["strSelfName"] + "�ѽ�" + printQQ(llqq) + "Σ�յȼ�������" + to_string(mark.danger), 0b10,
						printSTNow());
			checkGroupWithBlackQQ(mark, llqq);
		}
	}
	return true;
}

short DDBlackManager::get_group_danger(long long id) const
{
	if (auto it = mGroupDanger.find(id); it != mGroupDanger.end())return it->second;
	return 0;
}

short DDBlackManager::get_qq_danger(long long id) const
{
	if (auto it = mQQDanger.find(id); it != mQQDanger.end())
		return it->second;
	return 0;
}

void DDBlackManager::rm_black_group(long long llgroup, FromMsg* msg)
{
	std::lock_guard<std::mutex> lock_queue(blacklistMutex);
	if (!mGroupDanger.count(llgroup))
	{
		msg->reply(printGroup(llgroup) + "��δע����¼��");
		return;
	}
	if (mGroupDanger[llgroup] >= msg->trusted && msg->fromQQ != console.master())
	{
		msg->reply("��ע��Ŀ���������Ȩ�޲����");
		return;
	}
	for (auto [key,index] : multi_range(mGroupIndex, llgroup))
	{
		vBlackList[index].fromGroup.second = false;
	}
	mGroupDanger.erase(llgroup);
	msg->note("��ע��" + printGroup(llgroup) + "�ĺ�������¼��");
	blacklist->saveJson(DiceDir + "\\conf\\BlackList.json");
}

void DDBlackManager::rm_black_qq(long long llqq, FromMsg* msg)
{
	std::lock_guard<std::mutex> lock_queue(blacklistMutex);
	if (!mQQDanger.count(llqq))
	{
		msg->reply(printQQ(llqq) + "��δע����¼��");
		return;
	}
	if (mQQDanger[llqq] >= msg->trusted && msg->fromQQ != console.master())
	{
		msg->reply("��ע��Ŀ���������Ȩ�޲����");
		return;
	}
	for (auto [key, index] : multi_range(mQQIndex, llqq))
	{
		if (vBlackList[index].fromQQ.first == llqq)vBlackList[index].fromQQ.second = false;
		if (vBlackList[index].inviterQQ.first == llqq)vBlackList[index].inviterQQ.second = false;
		if (vBlackList[index].ownerQQ.first == llqq)vBlackList[index].ownerQQ.second = false;
	}
	reset_qq_danger(llqq);
	msg->note("��ע��" + printQQ(llqq) + "�ĺ�������¼��");
	blacklist->saveJson(DiceDir + "\\conf\\BlackList.json");
}

void DDBlackManager::isban(FromMsg* msg)
{
	if (msg->strVar["target"].empty())
	{
		msg->reply("�������ѯ�����ID��");
		return;
	}
	long long llID = stoll(msg->strVar["target"]);
	bool isGet = false;
	if (mGroupIndex.count(llID))
	{
		set<int> sRec;
		JsonList jary;
		for (auto& [key, index] : multi_range(mGroupIndex, llID))
		{
			jary << vBlackList[index].printJson();
			sRec.insert(index);
		}
		msg->reply(
			string("��Ⱥ�к�������¼") + to_string(jary.size()) + "��" + (mGroupDanger[llID] ? "��δע����:\n!warning" : "����ע����:\n") +
			(jary.size() == 1 ? vBlackList[*sRec.begin()].printJson(2) : jary.dump()));
		isGet = true;
	}
	if (mQQIndex.count(llID))
	{
		set<int> sRec;
		JsonList jary;
		for (auto& [key, index] : multi_range(mQQIndex, llID))
		{
			jary << vBlackList[index].printJson();
			sRec.insert(index);
		}
		msg->reply(
			string("���û��к�������¼") + to_string(jary.size()) + "��" + (mQQDanger[llID] ? "��δע����:\n!warning" : "����ע����:\n") + (
				jary.size() == 1 ? vBlackList[*sRec.begin()].printJson(2) : jary.dump()));
		isGet = true;
	}
	if (!isGet)
	{
		msg->reply(msg->strVar["target"] + "�޺�������¼");
	}
}

string DDBlackManager::list_group_warning(long long llgroup)
{
	for (auto [group, index] : multi_range(mGroupIndex, llgroup))
	{
		const DDBlackMark& mark = vBlackList[index];
		if (mark.fromGroup.second && mark.danger == mGroupDanger[llgroup] && !mark.isType("local"))return mark.
			warning();
	}
	return "";
}

string DDBlackManager::list_qq_warning(long long llqq)
{
	for (auto [qq, index] : multi_range(mQQIndex, llqq))
	{
		const DDBlackMark& mark = vBlackList[index];
		if (mark.danger != mQQDanger[llqq] || mark.isType("local"))continue;
		if ((mark.fromQQ.first == llqq && mark.fromQQ.second)
			|| (mark.inviterQQ.first == llqq && mark.inviterQQ.second)
			|| (mark.ownerQQ.first == llqq && mark.ownerQQ.second))
			return mark.warning();
	}
	return "";
}

string DDBlackManager::list_self_group_warning(long long llgroup)
{
	for (auto [group, index] : multi_range(mGroupIndex, llgroup))
	{
		const DDBlackMark& mark = vBlackList[index];
		if (mark.isSource(console.DiceMaid) && mark.fromGroup.second && mark.danger == mGroupDanger[llgroup] && !mark.
			isType("local"))return mark.warning();
	}
	return "";
}

string DDBlackManager::list_self_qq_warning(long long llqq)
{
	for (auto [qq, index] : multi_range(mQQIndex, llqq))
	{
		const DDBlackMark& mark = vBlackList[index];
		if (mark.danger != mQQDanger[llqq] || mark.isType("local"))continue;
		if (mark.isSource(console.DiceMaid) &&
			((mark.fromQQ.first == llqq && mark.fromQQ.second)
				|| (mark.inviterQQ.first == llqq && mark.inviterQQ.second)
				|| (mark.ownerQQ.first == llqq && mark.ownerQQ.second)))
			return mark.warning();
	}
	return "";
}

void DDBlackManager::add_black_group(long long llgroup, FromMsg* msg)
{
	if (groupset(llgroup, "���") > 0)
	{
		msg->reply(GlobalMsg["self"] + "�����������Ⱥ��");
		return;
	}
	DDBlackMark mark{0, llgroup};
	mark.danger = 1;
	mark.note = msg->strVar["note"];
	if (!mark.note.empty()) {
		mark.danger = 2;
		mark.type = "other";
	}
	if (mark.danger < get_qq_danger(llgroup))
	{
		msg->reply(GlobalMsg["strSelfName"] + "������Ⱥ" + to_string(llgroup) + "��");
		return;
	}
	mark.time = msg->strVar["time"];
	mark.DiceMaid = console.DiceMaid;
	mark.masterQQ = console.masterQQ;
	mark.comment = printSTNow() + " ��" + printQQ(msg->fromQQ) + "����";
	insert(mark);
	msg->note("�����" + printGroup(llgroup) + "�ĺ�������¼��");
}

void DDBlackManager::add_black_qq(long long llqq, FromMsg* msg)
{
	if (trustedQQ(llqq) > 1)
	{
		msg->reply(GlobalMsg["strSelfName"] + "���������������û���");
		return;
	}
	DDBlackMark mark{llqq, 0};
	mark.danger = 1;
	mark.note = msg->strVar["note"];
	if (!mark.note.empty() && !msg->strVar.count("user")) {
		mark.danger = 2;
		mark.type = "other";
	}
	if (mark.danger < get_qq_danger(llqq))
	{
		msg->reply(GlobalMsg["strSelfName"] + "�������û�" + printQQ(llqq) + "��");
		return;
	}
	mark.time = msg->strVar["time"];
	mark.DiceMaid = console.DiceMaid;
	mark.masterQQ = console.masterQQ;
	mark.comment = printSTNow() + " ��" + printQQ(msg->fromQQ) + "����";
	insert(mark);
	msg->note("�����" + printQQ(llqq) + "�ı��غ�������¼��");
}

void DDBlackManager::verify(void* pJson, long long operatorQQ)
{
    DDBlackMark mark{pJson};
    if (!mark.isValid)return;
    int credit = isReliable(operatorQQ);
    //���ݿ��Ƿ��м�¼:-1=������;0=��ע��;1=δȷ��;2=��ȷ��;
    int is_cloud = -1;
    if (console["CloudBlackShare"])
	{
        if (mark.wid)
		{
            string strInfo;
            if ((is_cloud = getCloudBlackMark(mark.wid, strInfo)) > -1)
			{
                try
				{
                    nlohmann::json j = nlohmann::json::parse(strInfo);
                    if (j["isErased"].get<int>())is_cloud = 0;
                    else if (j["isCheck"].get<int>())is_cloud = 2;
                    if (mark.fromQQ.first) 
					{
                        if (mark.fromQQ.first != j["fromQQ"].get<long long>())return;
                    }
                    else
					{
                        if (!mark.isClear)mark.fromQQ = {j["fromQQ"].get<long long>(), true};
                    }
                    if (mark.fromGroup.first)
					{
                        if (mark.fromGroup.first != j["fromGroup"].get<long long>())return;
                    }
                    else
					{
                        if (!mark.isClear)mark.fromGroup = {j["fromGroup"].get<long long>(), true};
                    }
                    mark.DiceMaid = j["DiceMaid"].get<long long>();
                    mark.masterQQ = j["masterQQ"].get<long long>();
                    mark.type = j["type"].get<string>();
                    mark.time = j["time"].get<string>();
                    if (mark.note.empty())
					{
                         if (j.count("note") && !j["note"].get<string>().empty())mark.note = UTF8toGBK(
							 j["note"].get<string>());
                         else mark.fill_note();
                    }
                    if (credit < 3 || !mark.danger)mark.danger = 2;
                }
                catch (...)
				{
                    console.log("�ƶ�����ͬ��ʧ��:wid=" + to_string(mark.wid), 0);
                    //mark.wid = 0;
                }
            }
            else 
			{
                console.log("�ƶ˺���ʧ��:wid=" + to_string(mark.wid), 0);
                mark.wid = 0;
            }
        }
        else
		{
            is_cloud = mark.check_cloud();
        }
    }
    else
	{
        mark.wid = 0;
    }
    if (credit < 3)
	{
        if ((mark.isType("kick") && !console["ListenGroupKick"]) || (mark.isType("ban") && !console["ListenGroupBan"])
			|| (mark.isType("spam") && !console["ListenSpam"]))return;
        if (mark.type == "local" || mark.type == "other" || mark.isSource(console.DiceMaid)) {
            if (credit > 0)console.log(
				getName(operatorQQ) + "��֪ͨ" + GlobalMsg["strSelfName"] + "������¼(δ����):\n!warning" + UTF8toGBK(
					static_cast<json*>(pJson)->dump()), 1, printSTNow());
            return;
        }
    }
    else if (credit < 5 && mark.danger > credit) mark.danger = credit;
    if (!mark.danger || credit < 3)mark.danger = (mark.type == "ruler" ? 3 : 2);
    mark.check_remit();
    int index = find(mark);
    //�¼�¼
    if (index < 0)
	{
        //�����߻�������һ�к�����
        if (credit < 0 || get_qq_danger(mark.DiceMaid) || get_qq_danger(mark.masterQQ))return;
        if (!mark.isType())return;
        //���ƶ�ȷ�ϼ�¼�Ҳ�������
        if (is_cloud < 0 || is_cloud == 1) 
		{
            if (mark.type == "ruler" || credit == 0)return;
        }
        //�ƶ�ע������ͬ��ע��
        else if (is_cloud == 0)
		{
            if (!mark.isClear && credit < 3)mark.erase();
        }
        if (credit < 3)
		{
            if (is_cloud < 1 && mark.type == "extern")return;
        }
        else
		{
            if (mark.type == "local" && credit < 4)return;
        }
        if (mark.fromGroup.first && (groupset(mark.fromGroup.first, "����") > 0 || groupset(mark.fromGroup.first, "Э����Ч") > 0 || ExceptGroups.count(mark.fromGroup.first)))return;
        insert(mark);
        console.log(getName(operatorQQ) + "��֪ͨ" + GlobalMsg["strSelfName"] + "������¼" + to_string(vBlackList.size() - 1) + ":\n!warning" + UTF8toGBK(((json*)pJson)->dump()), 1, printSTNow());
    }
    else 
	{ 
		//���м�¼
        DDBlackMark& old_mark = vBlackList[index];
        bool isSource = operatorQQ == old_mark.DiceMaid || operatorQQ == old_mark.masterQQ;
        //����Σ�յȼ���Ȩ�޸�
        if (old_mark.danger > credit && credit < 255) {
            if (old_mark.danger != 2)return;
            //������Ȩ��
            if (isSource) {
                mark.fromQQ.second &= old_mark.fromQQ.second;
                mark.fromGroup.second &= old_mark.fromGroup.second;
            }
            //ͬ���ƶ�ע��
            else if (!is_cloud) {
                mark.erase();
            }
            else return;
        }
        //������
        if (credit < 1) {
            mark.inviterQQ = { 0,false };
            mark.ownerQQ = { 0,false };
        }
        //��Ȩ����Σ�յȼ�
        if (mark.danger != old_mark.danger && credit < 3) { 
            mark.danger = old_mark.danger; 
        }
        if(update(mark,index,credit))console.log(getName(operatorQQ) + "�Ѹ���" + GlobalMsg["strSelfName"] + "������¼" + to_string(index) + ":\n!warning" + UTF8toGBK(((json*)pJson)->dump()), 1, printSTNow());
    }
}

void DDBlackManager::create(DDBlackMark& mark) 
{
    if (mark.check_remit(); mark.isClear)return;
    if (console["CloudBlackShare"] && mark.isSource(console.DiceMaid))mark.upload();
    console.log(mark.warning(), 0b100000);
    insert(mark);
}

int DDBlackManager::loadJson(string strPath, bool isExtern)
{
	json j = freadJson(strPath);
	if (j.is_null())return -1;
	if (j.size() > vBlackList.capacity())vBlackList.reserve(j.size() * 2);
	int cnt(0);
	for (auto& item : j)
	{
		DDBlackMark mark{&item};
		if (!mark.isValid)continue;
		if (!mark.danger)mark.danger = 2;
		//�²�������
		isLoadingExtern = true;
		if (int res = find(mark); res < 0)
		{
			if(insert(mark))cnt++;
		}
		else
		{
			if (isExtern) {
				if (mark.isSource(console.DiceMaid))continue;	//�漰����Ĳ�����
				if (mark.danger != vBlackList[res].danger)continue;	//Σ�յȼ��ر�Ķ��Ĳ�����
			}
			if (update(mark, res))cnt++;
		}
		isLoadingExtern = false;
	}
	if (isExtern) {
		filesystem::remove(strPath);
		console.log("������Դ������¼��Ŀ" + to_string(cnt) + "��", 1, printSTNow());
		blacklist->saveJson(DiceDir + "\\conf\\BlackList.json");
	}
	return cnt;
}

int DDBlackManager::loadHistory(const string& strLoc)
{
	long long id;
	std::ifstream fgroup(strLoc + "BlackGroup.RDconf");
	if (fgroup)
	{
		while (fgroup >> id)
		{
			if (mGroupDanger.count(id))continue;
			DDBlackMark mark{0, id};
			insert(mark);
		}
	}
	fgroup.close();
	std::ifstream fqq(strLoc + "BlackQQ.RDconf");
	if (fqq)
	{
		while (fqq >> id)
		{
			if (mQQDanger.count(id))continue;
			DDBlackMark mark{id, 0};
			insert(mark);
		}
	}
	fqq.close();
	return vBlackList.size();
}

void DDBlackManager::saveJson(const string& strPath) const
{
	std::ofstream fout(strPath);
	JsonList jary;
	for (auto& mark : vBlackList)
	{
		jary << GBKtoUTF8(mark.printJson());
	}
	fout << jary.dump();
}

Factory& DDBlackMarkFactory::sign()
{
	mark.DiceMaid = console.DiceMaid;
	mark.masterQQ = console.master();
	return *this;
}
