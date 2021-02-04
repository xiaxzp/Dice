#pragma once
#include "DiceJob.h"
#include "DiceConsole.h"
#include <TlHelp32.h>
#include <Psapi.h>
#include "StrExtern.hpp"
#include "DDAPI.h"
#include "ManagerSystem.h"
#include "DiceCloud.h"
#include "BlackListManager.h"
#include "GlobalVar.h"
#include "CardDeck.h"
#include "DiceMod.h"
#include "DiceNetwork.h"
#include "S3PutObject.h"
#pragma warning(disable:28159)

using namespace std;

int sendSelf(const string msg) {
	static long long selfQQ = DD::getLoginQQ();
	DD::sendPrivateMsg(selfQQ, msg);
	return 0;
}

void cq_exit(DiceJob& job) {
	job.note("����" + getMsg("self") + "��5�����ɱ", 1);
	std::this_thread::sleep_for(5s);
	dataBackUp();
	DD::killme();
}

inline PROCESSENTRY32 getProcess(int pid) {
	PROCESSENTRY32 pe32;
	pe32.dwSize = sizeof(pe32);
	HANDLE hParentProcess = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
	Process32First(hParentProcess, &pe32);
	return pe32;
}
void frame_restart(DiceJob& job) {
	if (!job.fromQQ) {
		if (console["AutoFrameRemake"] <= 0) {
			sch.add_job_for(60 * 60, job);
			return;
		}
		else if (int tWait{ console["AutoFrameRemake"] * 60 * 60 - int(time(nullptr) - llStartTime) }; tWait > 0) {
			sch.add_job_for(tWait, job);
			return;
		}
	}
	Enabled = false;
	dataBackUp();
	std::this_thread::sleep_for(3s);
	DD::remake();
}

void frame_reload(DiceJob& job){
	if(DD::reload())
		job.note("����" + getMsg("self") + "��ɡ�", 1);
	else
		job.note("����" + getMsg("self") + "ʧ�ܡ�", 0b10);
}

void auto_save(DiceJob& job) {
	if (sch.is_job_cold("autosave"))return;
	dataBackUp();
	console.log(GlobalMsg["strSelfName"] + "���Զ�����", 0, printSTNow());
	if (console["AutoSaveInterval"] > 0) {
		sch.refresh_cold("autosave", time(NULL) + console["AutoSaveInterval"]);
		sch.add_job_for(console["AutoSaveInterval"] * 60, "autosave");
	}
}

void check_system(DiceJob& job) {
	static int perRAM(0), perLastRAM(0);
	static double  perLastCPU(0), perLastDisk(0),
		 perCPU(0), perDisk(0);
	static bool isAlarmRAM(false), isAlarmCPU(false), isAlarmDisk(false);
	static double mbFreeBytes = 0, mbTotalBytes = 0;
	//�ڴ���
	if (console["SystemAlarmRAM"] > 0) {
		perRAM = getRamPort();
		if (perRAM > console["SystemAlarmRAM"] && perRAM > perLastRAM) {
			console.log("���棺" + GlobalMsg["strSelfName"] + "����ϵͳ�ڴ�ռ�ô�" + to_string(perRAM) + "%", 0b1000, printSTime(stNow));
			perLastRAM = perRAM;
			isAlarmRAM = true;
		}
		else if (perLastRAM > console["SystemAlarmRAM"] && perRAM < console["SystemAlarmRAM"]) {
			console.log("���ѣ�" + GlobalMsg["strSelfName"] + "����ϵͳ�ڴ�ռ�ý���" + to_string(perRAM) + "%", 0b10, printSTime(stNow));
			perLastRAM = perRAM;
			isAlarmRAM = false;
		}
	}
	//CPU���
	if (console["SystemAlarmCPU"] > 0) {
		perCPU = getWinCpuUsage() / 10.0;
		if (perCPU > console["SystemAlarmCPU"] && (!isAlarmCPU || perCPU > perLastCPU + 1)) {
			console.log("���棺" + GlobalMsg["strSelfName"] + "����ϵͳCPUռ�ô�" + toString(perCPU) + "%", 0b1000, printSTime(stNow));
			perLastCPU = perCPU;
			isAlarmCPU = true;
		}
		else if (perLastCPU > console["SystemAlarmCPU"] && perCPU < console["SystemAlarmCPU"]) {
			console.log("���ѣ�" + GlobalMsg["strSelfName"] + "����ϵͳCPUռ�ý���" + toString(perCPU) + "%", 0b10, printSTime(stNow));
			perLastCPU = perCPU;
			isAlarmCPU = false;
		}
	}
	//Ӳ�̼��
	if (console["SystemAlarmRAM"] > 0) {
		perDisk = getDiskUsage(mbFreeBytes, mbTotalBytes) / 10.0;
		if (perDisk > console["SystemAlarmDisk"] && (!isAlarmDisk || perDisk > perLastDisk + 1)) {
			console.log("���棺" + GlobalMsg["strSelfName"] + "����ϵͳӲ��ռ�ô�" + toString(perDisk) + "%", 0b1000, printSTime(stNow));
			perLastDisk = perDisk;
			isAlarmDisk = true;
		}
		else if (perLastDisk > console["SystemAlarmDisk"] && perDisk < console["SystemAlarmDisk"]) {
			console.log("���ѣ�" + GlobalMsg["strSelfName"] + "����ϵͳӲ��ռ�ý���" + toString(perDisk) + "%", 0b10, printSTime(stNow));
			perLastDisk = perDisk;
			isAlarmDisk = false;
		}
	}
	if (isAlarmRAM || isAlarmCPU || isAlarmDisk) {
		sch.add_job_for(5 * 60, job);
	}
	else {
		sch.add_job_for(30 * 60, job);
	}
}

//�����õ�ͼƬ�б�
void clear_image(DiceJob& job) {
	if (!job.fromQQ) {
		if (sch.is_job_cold("clrimage"))return;
		if (console["AutoClearImage"] <= 0) {
			sch.add_job_for(60 * 60, job);
			return;
		}
	}
	scanImage(GlobalMsg, sReferencedImage);
	scanImage(HelpDoc, sReferencedImage);
	scanImage(CardDeck::mPublicDeck, sReferencedImage);
	scanImage(CardDeck::mReplyDeck, sReferencedImage);
	for (auto it : ChatList) {
		scanImage(it.second.strConf, sReferencedImage);
	}
	job.note("����" + GlobalMsg["strSelfName"] + "������ͼƬ" + to_string(sReferencedImage.size()) + "��", 0b0);
	int cnt = clrDir("data\\image\\", sReferencedImage);
	job.note("������image�ļ�"+ to_string(cnt) + "��", 1);
	if (console["AutoClearImage"] > 0) {
		sch.refresh_cold("clrimage", time(NULL) + console["AutoClearImage"]);
		sch.add_job_for(console["AutoClearImage"] * 60 * 60, "clrimage");
	}
}

void clear_group(DiceJob& job) {
	int intCnt = 0;
	ResList res;
	if (job.strVar["clear_mode"] == "unpower") {
		for (auto& [id, grp] : ChatList) {
			if (grp.isset("����") || grp.isset("����") || grp.isset("δ��") || grp.isset("����") || grp.isset("Э����Ч"))continue;
			if (grp.isGroup && !DD::isGroupAdmin(id, console.DiceMaid, true)) {
				res << printGroup(id);
				grp.leave(getMsg("strLeaveNoPower"));
				intCnt++;
				this_thread::sleep_for(3s);
			}
		}
		console.log(GlobalMsg["strSelfName"] + "ɸ����ȺȨ��Ⱥ��" + to_string(intCnt) + "��:" + res.show(), 0b10, printSTNow());
	}
	else if (isdigit(static_cast<unsigned char>(job.strVar["clear_mode"][0]))) {
		int intDayLim = stoi(job.strVar["clear_mode"]);
		string strDayLim = to_string(intDayLim);
		time_t tNow = time(NULL);
		for (auto& [id, grp] : ChatList) {
			if (grp.isset("����") || grp.isset("����") || grp.isset("δ��") || grp.isset("����") || grp.isset("Э����Ч"))continue;
			time_t tLast = grp.tUpdated;
			if (long long tLMT; grp.isGroup && ((tLMT = DD::getGroupLastMsg(id, console.DiceMaid)) > 0 && tLMT > tLast))tLast = tLMT;
			if (!tLast)continue;
			int intDay = (int)(tNow - tLast) / 86400;
			if (intDay > intDayLim) {
				job["day"] = to_string(intDay);
				res << printGroup(id) + ":" + to_string(intDay) + "��\n";
				grp.leave(getMsg("strLeaveUnused", job.strVar));
				intCnt++;
				this_thread::sleep_for(2s);
			}
		}
		console.log(GlobalMsg["strSelfName"] + "��ɸ��Ǳˮ" + strDayLim + "��Ⱥ��" + to_string(intCnt) + "����" + res.show(), 0b10, printSTNow());
	}
	else if (job.strVar["clear_mode"] == "black") {
		try {
			for (auto id : DD::getGroupIDList()) {
				Chat& grp = chat(id).group().name(DD::getGroupName(id));
				if (grp.isset("����") || grp.isset("����") || grp.isset("δ��") || grp.isset("����") || grp.isset("���") || grp.isset("Э����Ч"))continue;
				if (blacklist->get_group_danger(id)) {
					res << printGroup(id) + "��" + "������Ⱥ";
					if (console["LeaveBlackGroup"])grp.leave(getMsg("strBlackGroup"));
				}
				set<long long> MemberList{ DD::getGroupMemberList(id) };
				int authSelf{ DD::getGroupAuth(id, console.DiceMaid, 1) };
				for (auto eachQQ : MemberList) {
					if (blacklist->get_qq_danger(eachQQ) > 1) {
						if (auto authBlack{DD::getGroupAuth(id, eachQQ, 1)};authBlack < authSelf) {
							continue;
						}
						else if (authBlack > authSelf) {
							res << printChat(grp) + "��" + printQQ(eachQQ) + "�Է�ȺȨ�޽ϸ�";
							grp.leave("���ֺ���������Ա" + printQQ(eachQQ) + "\n" + GlobalMsg["strSelfName"] + "��Ԥ������Ⱥ");
							intCnt++;
							break;
						}
						else if (console["LeaveBlackQQ"]) {
							res << printChat(grp) + "��" + printQQ(eachQQ);
							grp.leave("���ֺ�������Ա" + printQQ(eachQQ) + "\n" + GlobalMsg["strSelfName"] + "��Ԥ������Ⱥ");
							intCnt++;
							break;
						}
					}
				}
			}
		}
		catch (...) {
			console.log("���ѣ�" + GlobalMsg["strSelfName"] + "��������Ⱥ��ʱ����", 0b10, printSTNow());
		}
		if (intCnt) {
			job.note("�Ѱ�" + getMsg("strSelfName") + "���������Ⱥ��" + to_string(intCnt) + "����" + res.show(), 0b10);
		}
		else if (job.fromQQ) {
			job.echo(getMsg("strSelfName") + "��������δ���ִ����Ⱥ��");
		}
	}
	else if (job["clear_mode"] == "preserve") {
		for (auto& [id, grp] : ChatList) {
			if (grp.isset("����") || grp.isset("����") || grp.isset("δ��") || grp.isset("ʹ�����") || grp.isset("����") || grp.isset("Э����Ч"))continue;
			if (grp.isGroup && DD::isGroupAdmin(id, console.master(), false)) {
				grp.set("ʹ�����");
				continue;
			}
			res << printChat(grp);
			grp.leave(getMsg("strPreserve"));
			intCnt++;
			this_thread::sleep_for(3s);
		}
		console.log(GlobalMsg["strSelfName"] + "ɸ�������Ⱥ��" + to_string(intCnt) + "����" + res.show(), 1, printSTNow());
	}
	else
		job.echo("�޷�ʶ��ɸѡ������");
}
void list_group(DiceJob& job) {
	if (job["list_mode"].empty()) {
		job.reply(fmt->get_help("groups_list"));
	}
	if (mChatConf.count(job["list_mode"])) {
		ResList res;
		for (auto& [id, grp] : ChatList) {
			if (grp.isset(job["list_mode"])) {
				res << printChat(grp);
			}
		}
		job.reply("{self}������" + job["list_mode"] + "Ⱥ��¼" + to_string(res.size()) + "��" + res.head(":").show());
	}
	else if (set<long long> grps(DD::getGroupIDList()); job["list_mode"] == "idle") {
		std::priority_queue<std::pair<time_t, string>> qDiver;
		time_t tNow = time(NULL);
		for (auto& [id, grp] : ChatList) {
			if (grp.isGroup && !grps.empty() && !grps.count(id))grp.set("����");
			if (grp.isset("����") || grp.isset("δ��"))continue;
			time_t tLast = grp.tUpdated;
			if (long long tLMT; grp.isGroup && (tLMT = DD::getGroupLastMsg(grp.ID, console.DiceMaid)) > 0 && tLMT > tLast)tLast = tLMT;
			if (!tLast)continue;
			int intDay = (int)(tNow - tLast) / 86400;
			qDiver.emplace(intDay, printGroup(id));
		}
		if (qDiver.empty()) {
			job.reply("{self}��Ⱥ�Ļ�Ⱥ��Ϣ����ʧ�ܣ�");
		}
		size_t intCnt(0);
		ResList res;
		while (!qDiver.empty()) {
			res << qDiver.top().second + to_string(qDiver.top().first) + "��";
			qDiver.pop();
			if (++intCnt > 32 || qDiver.top().first < 7)break;
		}
		job.reply("{self}��������Ⱥ�б�:" + res.show(1));
	}
	else if (job["list_mode"] == "size") {
		std::priority_queue<std::pair<time_t, string>> qSize;
		time_t tNow = time(NULL);
		for (auto& [id, grp] : ChatList) {
			if (grp.isGroup && !grps.empty() && !grps.count(id))grp.set("����");
			if (grp.isset("����") || grp.isset("δ��") || !grp.isGroup)continue;
			Size size(DD::getGroupSize(id));
			if (!size.siz)continue;
			qSize.emplace(size.siz, DD::printGroupInfo(id));
		}
		if (qSize.empty()) {
			job.reply("{self}��Ⱥ�Ļ�Ⱥ��Ϣ����ʧ�ܣ�");
		}
		size_t intCnt(0);
		ResList res;
		while (!qSize.empty()) {
			res << qSize.top().second;
			qSize.pop();
			if (++intCnt > 32 || qSize.top().first < 7)break;
		}
		job.reply("{self}���ڴ�Ⱥ�б�:" + res.show(1));
	}
}

//�������
void cloud_beat(DiceJob& job) {
	Cloud::heartbeat();
	sch.add_job_for(5 * 60, job);
}

void dice_update(DiceJob& job) {
	job.note("��ʼ����Dice\n�汾:" + job.strVar["ver"], 1);
	string ret;
	if (DD::updateDice(job.strVar["ver"], ret)) {
		job.note("����Dice!" + job.strVar["ver"] + "��ɹ���", 1);
	}
	else {
		job.echo("����ʧ��:" + ret);
	}
}

//��ȡ�Ʋ�����¼
void dice_cloudblack(DiceJob& job) {
	bool isSuccess(false);
	job.echo("��ʼ��ȡ�ƶ˼�¼"); 
	string strURL("https://shiki.stringempty.xyz/blacklist/checked.json?" + to_string(job.fromTime));
	switch (Cloud::DownloadFile(strURL.c_str(), (DiceDir + "/conf/CloudBlackList.json").c_str())) {
	case -1: {
		string des;
		if (Network::GET("shiki.stringempty.xyz", "/blacklist/checked.json", 80, des)) {
			ofstream fout(DiceDir + "/conf/CloudBlackList.json");
			fout << des << endl;
			isSuccess = true;
		}
		else
			job.echo("ͬ���Ʋ�����¼ͬ��ʧ��:" + des);
	}
		break;
	case -2:
		job.echo("ͬ���Ʋ�����¼ͬ��ʧ��!�ļ�δ�ҵ�");
		break;
	case 0:
	default:
		break;
	}
	if (isSuccess) {
		if (job.fromQQ)job.note("ͬ���Ʋ�����¼�ɹ���" + getMsg("self") + "��ʼ��ȡ", 1);
		blacklist->loadJson(DiceDir + "/conf/CloudBlackList.json", true);
	}
	if (console["CloudBlackShare"])
		sch.add_job_for(24 * 60 * 60, "cloudblack");
}

void log_put(DiceJob& job) {
	job["ret"] = put_s3_object("dicelogger",
							   job.strVar["log_file"],
							   job.strVar["log_path"],
							   "ap-southeast-1");
	if (job["ret"] == "SUCCESS") {
		job.echo(getMsg("strLogUpSuccess", job.strVar));
	}
	else if (job.cntExec++ > 1) {
		job.echo(getMsg("strLogUpFailureEnd",job.strVar));
	}
	else {
		job["retry"] = to_string(job.cntExec);
		job.echo(getMsg("strLogUpFailure", job.strVar));
		sch.add_job_for(2 * 60, job);
	}
}


string print_master() {
	if (!console.master())return "��������";
	return printQQ(console.master());
}

string list_deck() {
	return listKey(CardDeck::mPublicDeck);
}
string list_extern_deck() {
	return listKey(CardDeck::mExternPublicDeck);
}
string list_order_ex() {
	return fmt->list_order();
}
string list_dice_sister() {
	std::set<long long>list{ DD::getDiceSisters() };
	if (list.size() <= 1)return {};
	else {
		list.erase(console.DiceMaid);
		ResList li;
		li << printQQ(console.DiceMaid) + "�Ľ�����:";
		for (auto dice : list) {
			li << printQQ(dice);
		}
		return li.show();
	}
}