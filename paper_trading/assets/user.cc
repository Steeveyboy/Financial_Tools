#include <iostream>
#include <string>
#include <sstream>
#include <cmath>
#include <sqlite3.h>
#include <vector>
#include <iomanip>
#include "user.h"

using namespace std;

User::User(const string& username, int userID, double balance, const string& registrationDate){
    this->username = username;
    this->userID = userID;
    this->balance = balance;
    this->registrationDate = registrationDate;
}