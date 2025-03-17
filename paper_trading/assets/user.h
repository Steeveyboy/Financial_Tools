#ifndef USER_H
#define USER_H

#include <string>

using namespace std;

class User {

public:
    int userID;
    string registrationDate; // YYYY-MM-DD
    string username;
    double balance;
    User(const string& username, int userID, double balance, const string& registrationDate);
};

#endif // USER_H