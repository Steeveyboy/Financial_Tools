class User {
    - int userID
    - string username
    - double balance
    - string registrationDate
    + User(int userID, string username, double balance, string registrationDate)
    + getUserID() int
    + getUsername() string
    + getBalance() double
    + getRegistrationDate() string
    + setBalance(double balance) void
}

class Stock {
    - string symbol
    - string name
    - double currentPrice
    + Stock(string symbol, string name, double currentPrice)
    + getSymbol() string
    + getName() string
    + getCurrentPrice() double
    + setCurrentPrice(double currentPrice) void
}

class Portfolio {
    - int userID
    - vector<Holding> holdings
    + Portfolio(int userID)
    + addHolding(Holding holding) void
    + removeHolding(string symbol) void
    + getHoldings() vector<Holding>
}

class Holding {
    - string symbol
    - int quantity
    - double averagePrice
    + Holding(string symbol, int quantity, double averagePrice)
    + getSymbol() string
    + getQuantity() int
    + getAveragePrice() double
    + setQuantity(int quantity) void
    + setAveragePrice(double averagePrice) void
}

class Order {
    - int orderID
    - int userID
    - string symbol
    - int quantity
    - double price
    - string orderType
    + Order(int orderID, int userID, string symbol, int quantity, double price, string orderType)
    + getOrderID() int
    + getUserID() int
    + getSymbol() string
    + getQuantity() int
    + getPrice() double
    + getOrderType() string
}

class Trade {
    - int tradeID
    - int orderID
    - string executionTime
    - double executionPrice
    + Trade(int tradeID, int orderID, string executionTime, double executionPrice)
    + getTradeID() int
    + getOrderID() int
    + getExecutionTime() string
    + getExecutionPrice() double
}

User "1" -- "0..*" Portfolio : manages
Portfolio "1" -- "0..*" Holding : contains
Order "1" -- "1" Trade : executed
User "1" -- "0..*" Order : creates
Stock "1" -- "0..*" Order : symbol
Stock "1" -- "0..*" Holding : symbol
