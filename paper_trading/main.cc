#include <iostream>
#include <string>
#include <sstream>
#include <cmath>
#include <sqlite3.h>
#include <vector>
#include <iomanip>
#include "assets/user.h"

using namespace std;


int main(int argc, char* argv[]){

    cout << "Hello World" << endl;

    User my_user("Jon", 1, 100.0, "1234");

    cout << "User: " << my_user.username << endl;
}
