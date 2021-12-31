import os

# Task: https://cs50.harvard.edu/x/2021/psets/9/finance/

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get user id
    user_id = session["user_id"]

    # Select data (raw stocks) and cash
    data = db.execute(
        "SELECT symbol, name, price, SUM(shares) as totalShares, type FROM transactions WHERE user_id = ? GROUP BY symbol", user_id)
    cash = db.execute("SELECT cash from users WHERE id = ?", user_id)[
        0]["cash"]

    # Calculate TOTAL
    total = cash
    stocks = []
    for stock in data:
        if stock["totalShares"] > 0:
            stocks.append(stock)
            total += stock["price"] * stock["totalShares"]

    return render_template("index.html", stocks=stocks, cash=cash, total=total, usd=usd)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Look up stock
        stock = lookup(request.form.get("symbol"))

        # Check if stock is found
        if not stock:
            return apology("stock not found", 400)

        # Get cash from db
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[
            0]["cash"]

        # Calculate total price
        stock_shares = int(request.form.get("shares"))
        total_price = stock["price"] * stock_shares

        # Update db
        if total_price > cash:
            return apology("not enough cash", 403)
        else:
            db.execute("UPDATE users SET cash = ? WHERE id = ?",
                       cash - total_price, user_id)
            db.execute("INSERT INTO transactions (user_id, symbol, name, price, shares, type) VALUES (?, ?, ?, ?, ?, ?)",
                       user_id, stock["symbol"], stock["name"], stock["price"], stock_shares, "buy")

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get user id
    user_id = session["user_id"]

    # Select all transactions
    transactions = db.execute(
        "SELECT symbol, name, price, shares, type, time FROM transactions WHERE user_id = ?", user_id)

    return render_template("history.html", transactions=transactions, usd=usd)


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
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          request.form.get("username"))

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
    """Get stock quote."""
    if request.method == "POST":
        # Look up stock
        stock = lookup(request.form.get("symbol"))

        # Check if stock is found
        if not stock:
            return apology("stock not found", 400)

        # Redirect to stock informations
        return render_template("quoted.html", stock=stock, usd=usd)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Get data
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username, password and confirmaton was submitted
        if not username:
            return apology("must provide username", 400)
        elif not password:
            return apology("must provide password", 400)
        elif not confirmation:
            return apology("must confirm password", 400)

        # Check if passwords match
        if password != confirmation:
            return apology("passwords do not match", 400)

        # Insert the new user and hash his password
        try:
            # Insert net user & redirect user to home page
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username, generate_password_hash(password))
            return redirect("/")
        except:
            return apology("username already exists")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Get user id
    user_id = session["user_id"]

    if request.method == "POST":
        # Get data
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Check if symbol is selected
        if not symbol:
            return apology("no symbol selected")

        # Select shares from db
        shares_owned = db.execute(
            "SELECT SUM(shares) as totalShares FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol", user_id, symbol)[0]["totalShares"]

        # Update db
        if shares > shares_owned:
            return apology("not enough shares owned")
        else:
            # Look up stock and select cash
            stock = lookup(symbol)
            cash = db.execute("SELECT cash from users WHERE id = ?", user_id)[
                0]["cash"]

            # Calculate earnings
            earnings = stock["price"] * shares

            # Update db
            db.execute("UPDATE users SET cash = ? WHERE id = ?",
                       cash + earnings, user_id)
            db.execute("INSERT INTO transactions (user_id, symbol, name, price, shares, type) VALUES (?, ?, ?, ?, ?, ?)",
                       user_id, stock["symbol"], stock["name"], stock["price"], -shares, "sell")

            # Redirect user to home page
            return redirect("/")

    else:
        # Select user's symbols
        symbols = db.execute(
            "SELECT symbol from transactions WHERE user_id = ? GROUP BY symbol", user_id)

        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
