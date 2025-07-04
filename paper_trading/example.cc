#include <iostream>
#include <string>
#include <sstream>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <sqlite3.h>
#include <vector>
// #include <algorithm>
// #include <map>
// #include <cstdlib>

using namespace std;

int linearFunction(int n){
    int numEvens = 0;
    for(int i=0; i<n; i++){
        if(i % 2 == 0){
            numEvens++;
        }
    }
    return numEvens;
}

int main(int argc, char* argv[]){
    sqlite3 *db;
    char *zErrMsg = 0;
    int rc;
    string sql;

    rc = sqlite3_open("test.db", &db);
    if(rc){
        cout << "Can't open database: " << endl;
        return 0;
    }
    else{
        cout << "Opened database successfully" << endl;
    }

    // if(argc < 2){
    //     cout << "Please provide a number" << endl;
    //     return 1;
    // }

    // int n;
    // n = stoi(argv[1]);
    // cout << "Number is " << n << endl;

    // int numEvens = 0;
    // long long int functionInput;


    return 1;
}
