/*
 * ��Ϣ����
 * Copyright (C) 2019 String.Empty
 */
#ifndef DICE_EVENT
#define DICE_EVENT
#include <map>
#include <set>
#include <utility>
#include <string>
#include "MsgMonitor.h"
#include "DiceSchedule.h"
#include "DiceMsgSend.h"
#include "GlobalVar.h"

using std::string;

//�����������Ϣ
class FromMsg : public DiceJobDetail {
public:
	string strLowerMessage;
	long long fromGroup = 0;
	long long fromSession;
	Chat* pGrp = nullptr;
	string strReply;
	FromMsg(std::string message, long long qq) :DiceJobDetail(qq, { qq,msgtype::Private }, message){
		fromSession = ~fromQQ;
	}
	FromMsg(std::string message, long long fromGroup, msgtype msgType, long long qq) :DiceJobDetail(qq, { fromGroup,msgType }, message), fromGroup(fromGroup), fromSession(fromGroup){
		pGrp = &chat(fromGroup);
	}

	bool isBlock = false;

	void formatReply();

	void reply(const std::string& strReply, bool isFormat = true)override;

	FromMsg& initVar(const std::initializer_list<const std::string>& replace_str);
	void reply(const std::string& strReply, const std::initializer_list<const std::string>& replace_str);
	void replyHidden(const std::string& strReply);

	void reply(bool isFormat = true);

	void replyHidden();

	//֪ͨ
	void note(std::string strMsg, int note_lv = 0b1)
	{
		strMsg = format(strMsg, GlobalMsg, strVar);
		ofstream fout(string(DiceDir + "\\audit\\log") + to_string(console.DiceMaid) + "_" + printDate() + ".txt",
		              ios::out | ios::app);
		fout << printSTNow() << "\t" << note_lv << "\t" << printLine(strMsg) << std::endl;
		fout.close();
		reply(strMsg);
		const string note = getName(fromQQ) + strMsg;
		for (const auto& [ct,level] : console.NoticeList) 
		{
			if (!(level & note_lv) || pair(fromQQ, msgtype::Private) == ct || ct == fromChat)continue;
			AddMsgToQueue(note, ct);
		}
	}

	//��ӡ��Ϣ��Դ
	std::string printFrom()
	{
		std::string strFwd;
		if (fromChat.second == msgtype::Group)strFwd += "[Ⱥ:" + to_string(fromGroup) + "]";
		if (fromChat.second == msgtype::Discuss)strFwd += "[������:" + to_string(fromGroup) + "]";
		strFwd += getName(fromQQ, fromGroup) + "(" + to_string(fromQQ) + "):";
		return strFwd;
	}

	//ת����Ϣ
	void fwdMsg();
	int AdminEvent(const string& strOption);
	int MasterSet();
	int BasicOrder();
	int InnerOrder();
	//int CustomOrder();
	int CustomReply();
	//�ж��Ƿ���Ӧ
	bool DiceFilter();
	bool WordCensor();
	void operator()();
	short trusted = 0;

private:
	bool isVirtual = false;
	//�Ƿ���Ӧ
	bool isAns = false;
	bool isDisabled = false;
	bool isCalled = false;
	bool isAuth = false;

	int getGroupAuth(long long group = 0);
public:
	unsigned int intMsgCnt = 0;
	//�����ո�
	void readSkipSpace()
	{
		while (intMsgCnt < strMsg.length() && isspace(static_cast<unsigned char>(strLowerMessage[intMsgCnt])))intMsgCnt++;
	}

	void readSkipColon();

	string readUntilSpace()
	{
		string strPara;
		readSkipSpace(); 
		while (intMsgCnt < strMsg.length() && !isspace(static_cast<unsigned char>(strLowerMessage[intMsgCnt])))
		{
			strPara += strMsg[intMsgCnt];
			intMsgCnt++;
		}
		return strPara;
	}

	//��ȡ���ǿո�հ׷�
	string readUntilTab()
	{
		while (intMsgCnt < strMsg.length() && isspace(static_cast<unsigned char>(strMsg[intMsgCnt])))intMsgCnt++;
		const int intBegin = intMsgCnt;
		int intEnd = intBegin;
		const unsigned int len = strMsg.length();
		while (intMsgCnt < len && (!isspace(static_cast<unsigned char>(strMsg[intMsgCnt])) || strMsg[intMsgCnt] == ' '))
		{
			if (strMsg[intMsgCnt] != ' ' || strMsg[intEnd] != ' ')intEnd = intMsgCnt;
			if (intMsgCnt < len && strMsg[intMsgCnt] < 0)intMsgCnt += 2;
			else intMsgCnt++;
		}
		if (strMsg[intEnd] == ' ')intMsgCnt = intEnd;
		return strMsg.substr(intBegin, intMsgCnt - intBegin);
	}

	string readRest()
	{
		readSkipSpace();
		return strMsg.substr(intMsgCnt);
	}

	//��ȡ����(ͳһСд)
	string readPara()
	{
		string strPara;
		while (intMsgCnt < strMsg.length() && isspace(static_cast<unsigned char>(strLowerMessage[intMsgCnt])))intMsgCnt++;
		while (intMsgCnt < strMsg.length() && !isspace(static_cast<unsigned char>(strLowerMessage[intMsgCnt])) && !isdigit(static_cast<unsigned char>(strLowerMessage[intMsgCnt]))
			&& (strLowerMessage[intMsgCnt] != '-') && (strLowerMessage[intMsgCnt] != '+') 
			&& (strLowerMessage[intMsgCnt] != '[') && (strLowerMessage[intMsgCnt] != ']') 
			&& (strLowerMessage[intMsgCnt] != '=') && (strLowerMessage[intMsgCnt] != ':')
			&& intMsgCnt != strLowerMessage.length()) {
			strPara += strLowerMessage[intMsgCnt];
			intMsgCnt++;
		}
		return strPara;
	}

	//��ȡ����
	string readDigit(bool isForce = true)
	{
		string strMum;
		if (isForce)while (intMsgCnt < strMsg.length() && !isdigit(static_cast<unsigned char>(strMsg[intMsgCnt])))
		{
			if (strMsg[intMsgCnt] < 0)intMsgCnt++;
			intMsgCnt++;
		}
		else while(intMsgCnt < strMsg.length() && isspace(static_cast<unsigned char>(strMsg[intMsgCnt])))intMsgCnt++;
		while (intMsgCnt < strMsg.length() && isdigit(static_cast<unsigned char>(strMsg[intMsgCnt])))
		{
			strMum += strMsg[intMsgCnt];
			intMsgCnt++;
		}
		if (intMsgCnt < strMsg.length() && strMsg[intMsgCnt] == ']')intMsgCnt++;
		return strMum;
	}

	//��ȡ���ֲ���������
	int readNum(int&);
	//��ȡȺ��
	long long readID()
	{
		const string strGroup = readDigit();
		if (strGroup.empty() || strGroup.length() > 18) return 0;
		return stoll(strGroup);
	}

	//�Ƿ�ɿ����������ʽ
	bool isRollDice()
	{
		readSkipSpace();
		if (isdigit(static_cast<unsigned char>(strLowerMessage[intMsgCnt]))
			|| strLowerMessage[intMsgCnt] == 'd' || strLowerMessage[intMsgCnt] == 'k'
			|| strLowerMessage[intMsgCnt] == 'p' || strLowerMessage[intMsgCnt] == 'b'
			|| strLowerMessage[intMsgCnt] == 'f'
			|| strLowerMessage[intMsgCnt] == '+' || strLowerMessage[intMsgCnt] == '-'
			|| strLowerMessage[intMsgCnt] == 'a'
			|| strLowerMessage[intMsgCnt] == 'x' || strLowerMessage[intMsgCnt] == '*')
		{
			return true;
		}
		return false;
	}

	//��ȡ�������ʽ
	string readDice()
	{
		string strDice;
		while (isspace(static_cast<unsigned char>(strLowerMessage[intMsgCnt])) || strLowerMessage[intMsgCnt] == '=' ||
			strLowerMessage[intMsgCnt] == ':')intMsgCnt++;
		while (isdigit(static_cast<unsigned char>(strLowerMessage[intMsgCnt]))
			|| strLowerMessage[intMsgCnt] == 'd' || strLowerMessage[intMsgCnt] == 'k'
			|| strLowerMessage[intMsgCnt] == 'p' || strLowerMessage[intMsgCnt] == 'b'
			|| strLowerMessage[intMsgCnt] == 'f'
			|| strLowerMessage[intMsgCnt] == '+' || strLowerMessage[intMsgCnt] == '-'
			|| strLowerMessage[intMsgCnt] == 'a'
			|| strLowerMessage[intMsgCnt] == 'x' || strLowerMessage[intMsgCnt] == '*' || strMsg[intMsgCnt] == '/'
			|| strLowerMessage[intMsgCnt] == '#')
		{
			strDice += strMsg[intMsgCnt];
			intMsgCnt++;
		}
		return strDice;
	}

	//��ȡ��ת��ı��ʽ
	string readExp()
	{
		bool inBracket = false;
		while (isspace(static_cast<unsigned char>(strLowerMessage[intMsgCnt])) || strLowerMessage[intMsgCnt] == '=' ||
			strLowerMessage[intMsgCnt] == ':')intMsgCnt++;
		const int intBegin = intMsgCnt;
		while (intMsgCnt != strMsg.length())
		{
			if (inBracket)
			{
				if (strMsg[intMsgCnt] == ']')inBracket = false;
				intMsgCnt++;
				continue;
			}
			if (isdigit(static_cast<unsigned char>(strLowerMessage[intMsgCnt]))
				|| strLowerMessage[intMsgCnt] == 'd' || strLowerMessage[intMsgCnt] == 'k'
				|| strLowerMessage[intMsgCnt] == 'p' || strLowerMessage[intMsgCnt] == 'b'
				|| strLowerMessage[intMsgCnt] == 'f'
				|| strLowerMessage[intMsgCnt] == '+' || strLowerMessage[intMsgCnt] == '-'
				|| strLowerMessage[intMsgCnt] == 'a'
				|| strLowerMessage[intMsgCnt] == 'x' || strLowerMessage[intMsgCnt] == '*' || strLowerMessage[intMsgCnt]
				== '/')
			{
				intMsgCnt++;
			}
			else if (strMsg[intMsgCnt] == '[')
			{
				inBracket = true;
				intMsgCnt++;
			}
			else break;
		}
		while (isalpha(static_cast<unsigned char>(strLowerMessage[intMsgCnt])) && isalpha(
			static_cast<unsigned char>(strLowerMessage[intMsgCnt - 1]))) intMsgCnt--;
		return strMsg.substr(intBegin, intMsgCnt - intBegin);
	}

	//��ȡ��ð�Ż�Ⱥ�ֹͣ���ı�
	string readToColon()
	{
		while (isspace(static_cast<unsigned char>(strMsg[intMsgCnt])))intMsgCnt++;
		const int intBegin = intMsgCnt;
		int intEnd = intBegin;
		const unsigned int len = strMsg.length();
		while (intMsgCnt < len && strMsg[intMsgCnt] != '=' && strMsg[intMsgCnt] != ':')
		{
			if (!isspace(static_cast<unsigned char>(strMsg[intMsgCnt])) || (!isspace(
				static_cast<unsigned char>(strMsg[intEnd]))))intEnd = intMsgCnt;
			if (strMsg[intMsgCnt] < 0)intMsgCnt += 2;
			else intMsgCnt++;
		}
		if (isspace(static_cast<unsigned char>(strMsg[intEnd])))intMsgCnt = intEnd;
		return strMsg.substr(intBegin, intMsgCnt - intBegin);
	}

	//��ȡ��Сд�����еļ�����
	string readAttrName()
	{
		while (isspace(static_cast<unsigned char>(strMsg[intMsgCnt])))intMsgCnt++;
		const int intBegin = intMsgCnt;
		int intEnd = intBegin;
		const unsigned int len = strMsg.length();
		while (intMsgCnt < len && !isdigit(static_cast<unsigned char>(strMsg[intMsgCnt]))
			&& strMsg[intMsgCnt] != '=' && strMsg[intMsgCnt] != ':'
			&& strMsg[intMsgCnt] != '+' && strMsg[intMsgCnt] != '-' && strMsg[intMsgCnt] != '*' && strMsg[intMsgCnt] !=
			'/')
		{
			if (!isspace(static_cast<unsigned char>(strMsg[intMsgCnt])) || (!isspace(
				static_cast<unsigned char>(strMsg[intEnd]))))intEnd = intMsgCnt;
			if (strMsg[intMsgCnt] < 0)intMsgCnt += 2;
			else intMsgCnt++;
		}
		if (intMsgCnt == strLowerMessage.length() && strLowerMessage.find(' ', intBegin) != string::npos)
		{
			intMsgCnt = strLowerMessage.find(' ', intBegin);
		}
		else if (isspace(static_cast<unsigned char>(strMsg[intEnd])))intMsgCnt = intEnd;
		return strMsg.substr(intBegin, intMsgCnt - intBegin);
	}

	//
	int readChat(chatType& ct, bool isReroll = false);

	int readClock(Console::Clock& cc)
	{
		const string strHour = readDigit();
		if (strHour.empty())return -1;
		const unsigned short nHour = stoi(strHour);
		if (nHour > 23)return -2;
		cc.first = nHour;
		if (strMsg[intMsgCnt] == ':' || strMsg[intMsgCnt] == '.')intMsgCnt++;
		if (strMsg.substr(intMsgCnt, 2) == "��")intMsgCnt += 2;
		readSkipSpace();
		if (intMsgCnt >= strMsg.length() || !isdigit(static_cast<unsigned char>(strMsg[intMsgCnt])))
		{
			cc.second = 0;
			return 0;
		}
		const string strMin = readDigit();
		const unsigned short nMin = stoi(strMin);
		if (nMin > 59)return -2;
		cc.second = nMin;
		return 0;
	}

	//��ȡ����
	string readItem()
	{
		string strMum;
		while (isspace(static_cast<unsigned char>(strMsg[intMsgCnt])) || strMsg[intMsgCnt] == '|')intMsgCnt++;
		while (strMsg[intMsgCnt] != '|' && intMsgCnt != strMsg.length())
		{
			strMum += strMsg[intMsgCnt];
			intMsgCnt++;
		}
		return strMum;
	}
	void readItems(vector<string>&);
};

#endif /*DICE_EVENT*/
