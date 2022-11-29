import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from collections import Counter

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/about")
def about():
    return render_template("about.html")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    cash = db.execute("""SELECT cash
                         FROM users
                         WHERE id=?""", session["user_id"])

    funds = cash[0]['cash']

    stocks = db.execute(""" SELECT symbol, name, shares, value
                            FROM purchases
                            WHERE user_id=?
                            GROUP BY symbol, user_id, name""", session["user_id"])
    total=0
    for row in stocks:
        symbol = row["symbol"]
        shares = row["shares"]
        quote = lookup(symbol)
        row["price"] = quote["price"]
        row["cost"] = row["price"] * shares
        total += row["cost"]

    grand_total = total+funds

    return render_template("index.html",stocks=stocks,funds=usd(funds),total=usd(total), grand_total=usd(grand_total))



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if lookup(symbol) == None:
            return apology("That stock doesn't exist")
        else:
            fullquote = lookup(symbol) #dictionary
            value = fullquote['price'] #dictionary['key']
            name = fullquote['name'] #dictionary['key']
            shares = request.form.get("shares")
            try:
                shares = int(shares)
            except ValueError:
                return apology("Shares must be a positive integer")
            if shares < 1:
                return apology("Shares must be a positive integer")
            cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
            cost = shares * value
            exists = db.execute("SELECT shares FROM purchases WHERE user_id=? AND symbol=?",session["user_id"],symbol)
            if cash[0]['cash'] < cost:
                return apology("Insufficient funds!")
            try:
                #if shares of stock exist, add it to the table rather than creating a new table of same stock
                #updated table can't be used to tell stock purchase histry, so add it to a copy of purchases table called "history"
                 if exists[0]["shares"] != 0:
                    db.execute("INSERT INTO transactions (status, user_id, symbol, name, value, shares) VALUES (?, ?, ?, ?, ?, ?)","BOUGHT", session["user_id"], symbol, name, cost, shares)
                    shares = exists[0]["shares"] + shares
                    db.execute("UPDATE purchases SET shares = ? WHERE user_id=? AND symbol=?",shares, session["user_id"],symbol)
                    cash = cash[0]['cash']- cost
            #index error occurs if user hasn't bought any shares of any stock yet
            except IndexError:
                db.execute("INSERT INTO purchases (status, user_id, symbol, name, value, shares) VALUES (?, ?, ?, ?, ?, ?)","BOUGHT", session["user_id"], symbol, name, value, shares)
                db.execute("INSERT INTO transactions (status, user_id, symbol, name, value, shares) VALUES (?, ?, ?, ?, ?, ?)","BOUGHT", session["user_id"], symbol, name, cost, shares)
                #new cash value is what they had minus what was just spent on stocks (shares times value)
                cash = cash[0]['cash'] - cost
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
            cash = usd(cash)
            numshares = request.form.get("shares")
            return redirect("/")


    if request.method == "GET":
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    transactions = db.execute("""SELECT status, transacted, symbol, name, value, shares
                                 FROM transactions
                                 WHERE user_id=?
                                 GROUP BY transacted""", session["user_id"])

    return render_template("history.html", transactions=transactions)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if lookup(symbol) == None:
            return apology("That stock doesn't exist")
        else:
            fullquote = lookup(symbol)
            value = fullquote['price']
            name = fullquote['name']
            value = usd(value)
            return render_template("quoted.html", value=value, name=name)
    elif request.method == "GET":
        return render_template("quote.html")





@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide a username")
        elif not request.form.get("password"):
            return apology("must provide a password")
        elif not request.form.get("confirmation"):
            return apology("must confirm your passowrd")

        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")
        if password != confirm_password:
            return apology("Your passwords need to match")

        username = request.form.get("username")
        # check if username already exists
        exists = db.execute("SELECT username FROM users WHERE username = ?",username)
        if len(exists) != 0:
            return apology("That username already exists")
        else:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method=="POST":
        if not request.form.get("symbol"):
            return apology("missing stock symbol")
        if not request.form.get("shares"):
            return apology("missing stock shares")
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        stk_shrs = db.execute("SELECT symbol, shares FROM purchases WHERE user_id=? AND symbol=?", session["user_id"], symbol)
        if len(stk_shrs) == 0:
            return apology("You do not have this stock")
        if stk_shrs[0]["shares"] == 0:
            return apology("You have no shares of this stock")
        try:
            shares = int(shares)
        except ValueError:
            return apology("Shares must be a positive integer")
        if shares < 0:
            return apology("Shares must be a positive integer")
        if shares > stk_shrs[0]["shares"]:
            return apology("You don't have that many shares of this stock!")
        cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        funds = cash[0]["cash"]
        value = lookup(symbol)
        price = value["price"]*shares
        name = value["name"]
        total = funds + price
                            #update users cash value in sql
        new_shares = stk_shrs[0]["shares"] - shares #new shares are the total shares = shares being sold
        db.execute("UPDATE purchases SET shares=? WHERE symbol = ? AND user_id=?", new_shares, symbol, session["user_id"])
        db.execute("UPDATE users SET cash=? WHERE id=?", total, session["user_id"])
        #enter sale information into a new sales table
        db.execute("INSERT INTO transactions (status, user_id, symbol, value, shares,name) VALUES (?,?,?,?,?,?)","SOLD",session["user_id"],symbol,price,shares,name)
                            #update users shares value for stocks they sell

        return redirect("/")
    else:
        symbols = db.execute("SELECT symbol FROM purchases WHERE user_id=? GROUP BY symbol",session["user_id"])
        return render_template("sell.html",symbols=symbols)
@app.route("/funds", methods=["GET", "POST"])
def Add_Funds():
    if request.method=="POST":
        try:
            add_funds = float(request.form.get("funds"))
            if add_funds < 0:
                return apology("Please enter a positive value")
        except TypeError and ValueError:
            return apology("Type only a positive number. No Dollar signs or commas!")
        og_funds = db.execute("SELECT cash FROM users WHERE id=?",session["user_id"])
        funds = add_funds + og_funds[0]["cash"]
        db.execute("UPDATE users SET cash=? WHERE id=?", funds,session["user_id"])
        db.execute("INSERT INTO transactions (status, symbol, name, shares, user_id, value) VALUES (?,?,?,?,?,?)", "Added Funds","N/A", "N/A", "N/A", session["user_id"], add_funds)
        return redirect("/")
    else:
        return render_template("funds.html")
