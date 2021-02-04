/*
 * ��������
 * Copyright (C) 2019 String.Empty
 */
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <WinInet.h>
#include <urlmon.h>
#include "json.hpp"
#include "DiceCloud.h"
#include "GlobalVar.h"
#include "EncodingConvert.h"
#include "DiceNetwork.h"
#include "DiceConsole.h"
#include "DiceMsgSend.h"
#include "DiceEvent.h"
#include "DDAPI.h"

#pragma comment(lib, "urlmon.lib")

using namespace std;
using namespace nlohmann;

namespace Cloud
{
	void heartbeat()
	{
		const string strVer = GBKtoUTF8(string(Dice_Ver));
		const string data = "&masterQQ=" + to_string(console.master()) + "&Ver=" +
			strVer + "&isGlobalOn=" + to_string(!console["DisabledGlobal"]) + "&isPublic=" +
			to_string(!console["Private"]) + "&isVisible=" + to_string(console["CloudVisible"]);
		DD::heartbeat(data);
	}

	int checkWarning(const char* warning)
	{
		char* frmdata = new char[strlen(warning) + 1];
		strcpy_s(frmdata, strlen(warning) + 1, warning);
		string temp;
		Network::POST("shiki.stringempty.xyz", "/DiceCloud/warning_check.php", 80, frmdata, temp);
		delete[] frmdata;
		if (temp == "exist")
		{
			return 1;
		}
		if (temp == "erased")
		{
			return -1;
		}
		return 0;
	}

	int DownloadFile(const char* url, const char* downloadPath)
	{
		DeleteUrlCacheEntryA(url);
		if (URLDownloadToFileA(nullptr, url, downloadPath, 0, nullptr) != S_OK) return -1;
		if (_access(downloadPath, 0))return -2;
		return 0;
	}

	int checkUpdate(FromMsg* msg)
	{
		std::string strVerInfo;
		if (!Network::GET("shiki.stringempty.xyz", "/DiceVer/update", 80, strVerInfo))
		{
			msg->reply("{self}��ȡ�汾��Ϣʱ��������: \n" + strVerInfo);
			return -1;
		}
		try
		{
			json jInfo(json::parse(strVerInfo, nullptr, false));
			unsigned short nBuild = jInfo["release"]["build"];
			if (nBuild > Dice_Build)
			{
				msg->note(
					"����Dice!�ķ��������:" + jInfo["release"]["ver"].get<string>() + "(" + to_string(nBuild) + ")\n����˵����" +
					UTF8toGBK(jInfo["release"]["changelog"].get<string>()), 1);
				return 1;
			}
			if (nBuild = jInfo["dev"]["build"]; nBuild > Dice_Build)
			{
				msg->note(
					"����Dice!�Ŀ��������:" + jInfo["dev"]["ver"].get<string>() + "(" + to_string(nBuild) + ")\n����˵����" +
					UTF8toGBK(jInfo["dev"]["changelog"].get<string>()), 1);
				return 2;
			}
			msg->reply("δ���ְ汾���¡�");
			return 0;
		}
		catch (...)
		{
			msg->reply("{self}����jsonʧ�ܣ�");
			return -2;
		}
		return 0;
	}
}
