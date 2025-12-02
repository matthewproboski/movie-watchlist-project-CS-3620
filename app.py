from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError
from functools import wraps
import sys

# load environment variables from .env
load_dotenv()

# initialize the flask application
app = Flask(__name__)

# secret key for session management
app.secret_key = os.getenv('SECRET_KEY')

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

# helper
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to perform this action.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- interaction routes ---

@app.route('/watchlist/add/<int:content_id>', methods=['POST'])
@login_required
def add_to_watchlist(content_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # write action [AR-1]: insert into the watchlist
        query = "INSERT INTO user_watchlist (user_id, content_id) VALUES (%s, %s)"
        cursor.execute(query, (session['user_id'], content_id))
        conn.commit()
        flash("Added to watchlist!", "success")
    except IntegrityError:
        # error handling [AR-5]: duplicate entry
        flash("This item is already in your watchlist.", "info")
    finally:
        cursor.close()
        conn.close()

    return redirect(request.referrer or url_for('index'))

@app.route('/watchlist/remove/<int:content_id>', methods=['POST'])
@login_required
def remove_from_watchlist(content_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # write action: delete from watchlist
    query = "DELETE FROM user_watchlist WHERE user_id = %s AND content_id = %s"
    cursor.execute(query, (session['user_id'], content_id))
    conn.commit()
    
    cursor.close()
    conn.close()
    flash("Removed from watchlist.", "info")
    return redirect(request.referrer or url_for('index'))

@app.route('/rate/<int:content_id>', methods=['POST'])
@login_required
def rate_content(content_id):
    rating = request.form['rating']
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # write action [AR-1]: insert or update the rating
        rating_query = """
            INSERT INTO user_ratings (user_id, content_id, rating) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE rating = VALUES(rating)
        """
        cursor.execute(rating_query, (session['user_id'], content_id, rating))

        # audit logging [DS-5]: record the action
        log_query = """
            INSERT INTO action_log (user_id, action_type, target_id) 
            VALUES (%s, 'USER_RATED_CONTENT', %s)
        """
        cursor.execute(log_query, (session['user_id'], content_id))

        conn.commit()
        flash("Rating submitted!", "success")

    except mysql.connector.Error as err:
        # error handling [AR-5]: catch the CHECK constraint violations (like rating > 5)
        if err.errno == 3819: 
            flash("Invalid rating. Must be between 1.0 and 5.0.", "error")
        else:
            flash(f"An error occurred: {err}", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(request.referrer or url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    watchlist_query = """
        SELECT c.* 
        FROM content c
        JOIN user_watchlist w ON c.content_id = w.content_id
        WHERE w.user_id = %s
    """
    cursor.execute(watchlist_query, (session['user_id'],))
    watchlist = cursor.fetchall()

    ratings_query = """
        SELECT c.title, r.rating, r.created_at
        FROM user_ratings r
        JOIN content c ON r.content_id = c.content_id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """
    cursor.execute(ratings_query, (session['user_id'],))
    my_ratings = cursor.fetchall()

    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', watchlist=watchlist, my_ratings=my_ratings)

if __name__ == '__main__':
    # check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--drop':
        print("Dropping database...")
        try:
            # connect
            conn = mysql.connector.connect(
                host=os.getenv('DB_HOST'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD')
            )
            cursor = conn.cursor()
            
            cursor.execute(f"DROP DATABASE IF EXISTS {os.getenv('DB_NAME')}")
            
            print(f"Database '{os.getenv('DB_NAME')}' has been dropped successfully.")
            
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(f"Error: {err}")
    else:
        # run the web server as normal
        app.run(debug=True, port=5001)