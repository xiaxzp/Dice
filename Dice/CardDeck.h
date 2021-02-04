/*
 * �ƶѳ鿨����
 * ��Ϊ��չ������Dice�����������ϣ����Ը��»�ֹ����ĳ�̶ֳ�
 * Copyright (C) 2019 String.Empty
 */
#pragma once
#ifndef CARD_DECK
#define CARD_DECK
#include <string>
#include <vector>
#include <map>
#include "STLExtern.hpp"

namespace CardDeck
{
	extern std::map<std::string, std::vector<std::string>, less_ci> mPublicDeck;
	extern std::map<std::string, std::vector<std::string>, less_ci> mExternPublicDeck;
	extern std::map<std::string, std::vector<std::string>, less_ci> mReplyDeck;
	extern std::map<std::string, std::string> PublicComplexDeck;
	int findDeck(std::string strDeckName);
	std::string drawCard(std::vector<std::string>& TempDeck, bool boolBack = false);
	std::string draw(std::string strDeckName);
};
#endif /*CARD_DECK*/
