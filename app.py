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
    
# helper
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to perform this action.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# homepage route
@app.route('/')
def index():
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500
    cursor = conn.cursor(dictionary=True)

    # analytical view 2 -> top rated content leaderboard
    leaderboard_query = """
        SELECT 
            c.content_id,
            c.title,
            c.release_year,
            c.content_type,
            COALESCE(AVG(r.rating), 0) AS avg_rating,
            COUNT(r.rating) AS num_ratings
        FROM 
            content c
        LEFT JOIN 
            user_ratings r ON c.content_id = r.content_id
        GROUP BY 
            c.content_id, c.title, c.release_year, c.content_type
        HAVING 
            COUNT(r.rating) > 0
        ORDER BY 
            avg_rating DESC, num_ratings DESC
        LIMIT 10;
    """
    cursor.execute(leaderboard_query)
    top_content = cursor.fetchall()

    # analytical view 3: recent oscar winners
    awards_query = """
        SELECT 
            c.content_id,
            c.title,
            c.release_year,
            a.year AS award_year,
            a.category
        FROM 
            content c
        JOIN 
            awards a ON c.content_id = a.content_id
        ORDER BY 
            a.year DESC
        LIMIT 10;
    """
    cursor.execute(awards_query)
    award_winners = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('index.html', 
                           top_content=top_content, 
                           award_winners=award_winners)

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

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        display_name = request.form['display_name']
        bio = request.form['bio']
        
        query = """
            INSERT INTO user_profiles (user_id, display_name, bio)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                display_name = VALUES(display_name), 
                bio = VALUES(bio);
        """
        cursor.execute(query, (user_id, display_name, bio))
        conn.commit()
        
        flash("Profile updated successfully!", "success")
        return redirect(url_for('dashboard'))

    cursor.execute("SELECT display_name, bio FROM user_profiles WHERE user_id = %s", (user_id,))
    profile_data = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return render_template('profile.html', profile=profile_data)

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

@app.route('/report/<int:content_id>', methods=['POST'])
@login_required
def report_content(content_id):
    reason = request.form['reason']
    details = request.form.get('details', '')

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "error")
        return redirect(request.referrer or url_for('index'))
    
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO content_reports (user_id, content_id, reason, details)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (session['user_id'], content_id, reason, details))
        conn.commit()
        flash("Report submitted successfully. Thank you for the feedback!", "success")
    except mysql.connector.Error as err:
        flash(f"An error occurred while submitting your report: {err}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return redirect(request.referrer or url_for('index'))

@app.route('/notes/save/<int:content_id>', methods=['POST'])
@login_required
def save_note(content_id):
    note_text = request.form['note_text']
    user_id = session['user_id']

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "error")
        return redirect(url_for('dashboard'))
    
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO content_notes (user_id, content_id, note_text)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE note_text = VALUES(note_text)
        """
        cursor.execute(query, (user_id, content_id, note_text))
        conn.commit()
        flash("Note saved!", "success")
    except mysql.connector.Error as err:
        flash(f"An error occurred while saving your note: {err}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('dashboard'))

@app.route('/request', methods=['POST'])
@login_required
def request_content():
    title = request.form['title']
    user_id = session['user_id']

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "error")
        return redirect(url_for('search'))
    
    cursor = conn.cursor()
    try:
        query = "INSERT INTO content_requests (user_id, title) VALUES (%s, %s)"
        cursor.execute(query, (user_id, title))
        conn.commit()
        flash(f"Your request for '{title}' has been submitted!", "success")
    except mysql.connector.Error as err:
        flash(f"An error occurred: {err}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('search'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session['user_id']

    watchlist_query = """
        SELECT 
            c.*,
            n.note_text
        FROM 
            user_watchlist w
        JOIN 
            content c ON w.content_id = c.content_id
        LEFT JOIN
            content_notes n ON w.user_id = n.user_id AND w.content_id = n.content_id
        WHERE 
            w.user_id = %s
    """
    cursor.execute(watchlist_query, (user_id,))
    watchlist = cursor.fetchall()

    ratings_query = """
        SELECT c.title, r.rating, r.created_at
        FROM user_ratings r
        JOIN content c ON r.content_id = c.content_id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """
    cursor.execute(ratings_query, (user_id,))
    my_ratings = cursor.fetchall()
    
    stats_watchlist_query = "SELECT COUNT(*) as total_count FROM user_watchlist WHERE user_id = %s"
    cursor.execute(stats_watchlist_query, (user_id,))
    watchlist_count = cursor.fetchone()['total_count']
    
    stats_rating_query = "SELECT COALESCE(AVG(rating), 0) as average_rating FROM user_ratings WHERE user_id = %s"
    cursor.execute(stats_rating_query, (user_id,))
    avg_rating = cursor.fetchone()['average_rating']
    avg_rating = round(float(avg_rating), 1)

    # get profile data in order to display on the dashboard
    profile_query = "SELECT display_name, bio FROM user_profiles WHERE user_id = %s"
    cursor.execute(profile_query, (user_id,))
    user_profile = cursor.fetchone()

    search_history_query = """
        SELECT search_query 
        FROM search_history 
        WHERE user_id = %s 
        GROUP BY search_query
        ORDER BY MAX(searched_at) DESC 
        LIMIT 5;
    """
    cursor.execute(search_history_query, (user_id,))
    recent_searches = cursor.fetchall()

    # get the users reports
    reports_query = """
        SELECT r.reason, r.status, r.created_at, c.title
        FROM content_reports r
        JOIN content c ON r.content_id = c.content_id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
        LIMIT 5;
    """
    cursor.execute(reports_query, (user_id,))
    my_reports = cursor.fetchall()

    # content requests
    requests_query = """
        SELECT title, status, requested_at
        FROM content_requests
        WHERE user_id = %s
        ORDER BY requested_at DESC
        LIMIT 5;
    """
    cursor.execute(requests_query, (user_id,))
    my_requests = cursor.fetchall()

    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', 
                           watchlist=watchlist, 
                           my_ratings=my_ratings,
                           watchlist_count=watchlist_count,
                           avg_rating=avg_rating,
                           profile=user_profile,
                           recent_searches=recent_searches,
                           my_reports=my_reports,
                           my_requests=my_requests)

@app.route('/search')
def search():
    # get the search query
    search_query = request.args.get('query', '').strip()
    
    if search_query:
        conn = get_db_connection()
        if not conn:
            return "Database connection failed", 500
        cursor = conn.cursor(dictionary=True)

        # save the search query if the user is logged in
        if 'user_id' in session:
            log_query = "INSERT INTO search_history (user_id, search_query) VALUES (%s, %s)"
            cursor.execute(log_query, (session['user_id'], search_query))
            conn.commit()

        sql_query = """
            SELECT content_id, title, release_year, content_type
            FROM content 
            WHERE MATCH(title, overview) AGAINST(%s IN NATURAL LANGUAGE MODE)
            LIMIT 50;
        """
        cursor.execute(sql_query, (search_query,))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('search.html', results=results, search_query=search_query)

    return render_template('search.html')

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