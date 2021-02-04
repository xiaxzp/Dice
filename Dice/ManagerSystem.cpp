/*
 * ��̨ϵͳ
 * Copyright (C) 2019-2020 String.Empty
 */
#include <windows.h>
#include <xutility>
#include <string_view>
#include "ManagerSystem.h"

#include "CardDeck.h"
#include "GlobalVar.h"
#include "DDAPI.h"
#include "CQTools.h"

string dirExe;
string DiceDir = "DiceData";
 //�����õ�ͼƬ�б�
unordered_set<string> sReferencedImage;

const map<string, short> mChatConf{
	//0-Ⱥ����Ա��2-����2����3-����3����4-����Ա��5-ϵͳ����
	{"����", 4},
	{"������Ϣ", 0},
	{"ͣ��ָ��", 0},
	{"���ûظ�", 0},
	{"����jrrp", 0},
	{"����draw", 0},
	{"����me", 0},
	{"����help", 0},
	{"����ob", 0},
	{"���ʹ��", 1},
	{"δ���", 1},
	{"����", 2},
	{"���", 4},
	{"Э����Ч", 3},
	{"δ��", 5},
	{"����", 5}
};

User& getUser(long long qq)
{
	if (!UserList.count(qq))UserList[qq].id(qq);
	return UserList[qq];
}
short trustedQQ(long long qq) 
{
	if (qq == console.master())return 256;
	if (qq == console.DiceMaid)return 255;
	else if (!UserList.count(qq))return 0;
	else return UserList[qq].nTrust;
}

int clearUser()
{
	vector<long long> QQDelete;
	for (const auto& [qq, user] : UserList)
	{
		if (user.empty())
		{
			QQDelete.push_back(qq);
		}
	}
	for (const auto& qq : QQDelete)
	{
		UserList.erase(qq);
	}
	return QQDelete.size();
}

string getName(long long QQ, long long GroupID)
{
	if (QQ == console.DiceMaid)return getMsg("strSelfCall");
	string nick;
	if (UserList.count(QQ) && getUser(QQ).getNick(nick, GroupID))return nick;
	if (GroupID && !(nick = DD::getGroupNick(GroupID, QQ)).empty()
		&& !(nick = strip(msg_decode(nick))).empty())return nick;
	if (nick = DD::getQQNick(QQ); !(nick = strip(msg_decode(nick))).empty())return nick;
	return GlobalMsg["stranger"] + "(" + to_string(QQ) + ")";
}
void filter_CQcode(string& nick, long long fromGroup)
{
	size_t posL(0);
	while ((posL = nick.find(CQ_AT)) != string::npos)
	{
		//���at��ʽ
		if (size_t posR = nick.find(']',posL); posR != string::npos) 
		{
			std::string_view stvQQ(nick);
			stvQQ = stvQQ.substr(posL + 10, posR - posL - 10);
			//���QQ�Ÿ�ʽ
			bool isDig = true;
			for (auto ch: stvQQ) 
			{
				if (!isdigit(static_cast<unsigned char>(ch)))
				{
					isDig = false;
					break;
				}
			}
			//ת��
			if (isDig && posR - posL < 29) 
			{
				nick.replace(posL, posR - posL + 1, "@" + getName(stoll(string(stvQQ)), fromGroup));
			}
			else if (stvQQ == "all") 
			{
				nick.replace(posL, posR - posL + 1, "@ȫ���Ա");
			}
			else
			{
				nick.replace(posL, posR - posL + 1, "@");
			}
		}
		else return;
	}
	while ((posL = nick.find(CQ_IMAGE)) != string::npos) {
		//���at��ʽ
		if (size_t posR = nick.find(']', posL); posR != string::npos) {
			nick.replace(posL, posR - posL + 1, "[ͼƬ]");
		}
		else return;
	}
	while ((posL = nick.find("[CQ:")) != string::npos)
	{
		if (size_t posR = nick.find(']', posL); posR != string::npos) 
		{
			nick.erase(posL, posR - posL + 1);
		}
		else return;
	}
}

Chat& chat(long long id)
{
	if (!ChatList.count(id))ChatList[id].id(id);
	return ChatList[id];
}
Chat& Chat::id(long long grp) {
	ID = grp;
	Name = DD::getGroupName(grp);
	if (!Enabled)return *this;
	if (DD::getGroupIDList().count(grp)) {
		isGroup = true;
	}
	else {
		boolConf.insert("δ��");
	}
	return *this;
}

void Chat::leave(const string& msg) {
	if (!msg.empty()) {
		if (isGroup)DD::sendGroupMsg(ID, msg);
		else DD::sendDiscussMsg(ID, msg);
		Sleep(500);
	}
	isGroup ? DD::setGroupLeave(ID) : DD::setDiscussLeave(ID);
	set("����");
}
bool Chat::is_except()const {
	return boolConf.count("���") || boolConf.count("Э����Ч");
}

int groupset(long long id, const string& st)
{
	if (!ChatList.count(id))return -1;
	return ChatList[id].isset(st);
}

string printChat(Chat& grp)
{
	string name{ DD::getGroupName(grp.ID) };
	if (!name.empty())return "[" + name + "](" + to_string(grp.ID) + ")";
	if (!grp.Name.empty())return "[" + grp.Name + "](" + to_string(grp.ID) + ")";
	if (grp.isGroup) return "Ⱥ(" + to_string(grp.ID) + ")";
	return "������(" + to_string(grp.ID) + ")";
}

void scanImage(const string& s, unordered_set<string>& list) {
	int l = 0, r = 0;
	while ((l = s.find('[', r)) != string::npos && (r = s.find(']', l)) != string::npos)
	{
		if (s.substr(l, 15) != CQ_IMAGE)continue;
		string strFile = s.substr(l + 15, r - l - 15);
		if (strFile.length() > 35)strFile += ".cqimg";
		list.insert(strFile);
	}
}

void scanImage(const vector<string>& v, unordered_set<string>& list) {
	for (const auto& it : v)
	{
		scanImage(it, sReferencedImage);
	}
}

DWORD getRamPort()
{
	MEMORYSTATUSEX memory_status;
	memory_status.dwLength = sizeof(memory_status);
	GlobalMemoryStatusEx(&memory_status);
	return memory_status.dwMemoryLoad;
}

__int64 compareFileTime(const FILETIME& ft1, const FILETIME& ft2)
{
	__int64 t1 = ft1.dwHighDateTime;
	t1 = t1 << 32 | ft1.dwLowDateTime;
	__int64 t2 = ft2.dwHighDateTime;
	t2 = t2 << 32 | ft2.dwLowDateTime;
	return t1 - t2;
}

long long getWinCpuUsage() 
{
	FILETIME preidleTime;
	FILETIME prekernelTime;
	FILETIME preuserTime;
	FILETIME idleTime;
	FILETIME kernelTime;
	FILETIME userTime;

	if (!GetSystemTimes(&idleTime, &kernelTime, &userTime)) return -1;
	preidleTime = idleTime;
	prekernelTime = kernelTime;
	preuserTime = userTime;	

	Sleep(1000);
	if (!GetSystemTimes(&idleTime, &kernelTime, &userTime)) return -1;

	const __int64 idle = compareFileTime(idleTime, preidleTime);
	const __int64 kernel = compareFileTime(kernelTime, prekernelTime);
	const __int64 user = compareFileTime(userTime, preuserTime);

	return (kernel + user - idle) * 1000 / (kernel + user);
}

long long getProcessCpu()
{
	const HANDLE hProcess = GetCurrentProcess();
	//if (INVALID_HANDLE_VALUE == hProcess){return -1;}

	SYSTEM_INFO si;
	GetSystemInfo(&si);
	const __int64 iCpuNum = si.dwNumberOfProcessors;

	FILETIME ftPreKernelTime, ftPreUserTime;
	FILETIME ftKernelTime, ftUserTime;
	FILETIME ftCreationTime, ftExitTime;
	std::ofstream log("System.log");

	if (!GetProcessTimes(hProcess, &ftCreationTime, &ftExitTime, &ftPreKernelTime, &ftPreUserTime)) { return -1; }
	log << ftPreKernelTime.dwLowDateTime << "\n" << ftPreUserTime.dwLowDateTime << "\n";
	Sleep(1000);
	if (!GetProcessTimes(hProcess, &ftCreationTime, &ftExitTime, &ftKernelTime, &ftUserTime)) { return -1; }
	log << ftKernelTime.dwLowDateTime << "\n" << ftUserTime.dwLowDateTime << "\n";
	const __int64 ullKernelTime = compareFileTime(ftKernelTime, ftPreKernelTime);
	const __int64 ullUserTime = compareFileTime(ftUserTime, ftPreUserTime);
	log << ullKernelTime << "\n" << ullUserTime << "\n" << iCpuNum;
	return (ullKernelTime + ullUserTime) / (iCpuNum * 10);
}

//��ȡ����Ӳ��(ǧ�ֱ�)
long long getDiskUsage(double& mbFreeBytes, double& mbTotalBytes){
	/*int sizStr = GetLogicalDriveStrings(0, NULL);//��ñ��������̷�����Drive������
	char* chsDrive = new char[sizStr];//��ʼ���������Դ洢�̷���Ϣ
	GetLogicalDriveStrings(sizStr, chsDrive);
	int DType;
	int si = 0;*/
	BOOL fResult;
	unsigned _int64 i64FreeBytesToCaller;
	unsigned _int64 i64TotalBytes;
	unsigned _int64 i64FreeBytes;
	fResult = GetDiskFreeSpaceEx(
		NULL,
		(PULARGE_INTEGER)&i64FreeBytesToCaller,
		(PULARGE_INTEGER)&i64TotalBytes,
		(PULARGE_INTEGER)&i64FreeBytes);
	//GetDiskFreeSpaceEx���������Ի�ȡ���������̵Ŀռ�״̬,�������ص��Ǹ�BOOL��������
	if (fResult) {
		mbTotalBytes = i64TotalBytes * 1000 / 1024 / 1024 / 1024 / 1000.0;//����������
		mbFreeBytes = i64FreeBytesToCaller * 1000 / 1024 / 1024 / 1024 / 1000.0;//����ʣ��ռ�
		return 1000 - 1000 * i64FreeBytesToCaller / i64TotalBytes;
	}
	return 0;
}