from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError

# load environment variables from .env
load_dotenv()

# initialize the flask application
app = Flask(__name__)

# secret key for session management
app.secret_key = 'secret_key_for_development_only'

# database connection helper function, for a fresh connection in each route
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

# homepage route
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # just a test query
    query = "SELECT * FROM content WHERE content_type = 'Movie' LIMIT 5;"
    cursor.execute(query)
    movies = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('index.html', movies=movies)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # get data from form
        email = request.form['email']
        password = request.form['password']
        
        # hash password
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # create a user [AR-1]
            query = "INSERT INTO users (email, password_hash) VALUES (%s, %s)"
            cursor.execute(query, (email, hashed_password))
            conn.commit()
            
            flash("Account created! Please log in.", "success")
            return redirect(url_for('login'))
            
        except IntegrityError:
            # catch any duplicate emails [AR-5]
            flash("That email is already taken.", "error")
            return redirect(url_for('signup'))
        finally:
            cursor.close()
            conn.close()

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) 
        
        query = "SELECT * FROM users WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()

        # check passwork hash
        if user and check_password_hash(user['password_hash'], password):
            # create session, log the user in [AR-4]
            session['user_id'] = user['user_id']
            session['email'] = user['email']
            flash("Logged in successfully!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid email or password.", "error")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)