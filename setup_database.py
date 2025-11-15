import os
import re 
import csv
import json
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

def populate_genres(cursor):
    """
    Reads genre data from movies.csv, extracts a unique list of genres,
    and populates the 'genres' table.
    """
    print("--> Populating 'genres' table...")
    
    unique_genres = set()
    movies_file_path = os.path.join('data', 'movies.csv')
    
    try:
        with open(movies_file_path, 'r', encoding='utf-8') as file:
            # find the genres column index
            header = next(file).strip().split(',')
            try:
                genres_column_index = header.index('genres')
            except ValueError:
                print("[ERROR] 'genres' column not found in the header of movies.csv")
                return

            # process each data line
            for line in file:
                try:
                    # split the line by comma
                    columns = line.split(',')

                    json_start = line.find('"[{"') 
                    json_end = line.find('}]"')
                    
                    if json_start != -1 and json_end != -1:
                        # extract the whole JSON string
                        genres_field = line[json_start : json_end + 3]
                        
                        # remove outer quotes
                        clean_json_string = genres_field.strip('"').replace('""', '"')
                        
                        genres_list = json.loads(clean_json_string)
                        for genre_obj in genres_list:
                            genre_name = genre_obj.get('name')
                            if genre_name:
                                unique_genres.add(genre_name)
                except (json.JSONDecodeError, ValueError):
                    continue

        print(f"--> Found {len(unique_genres)} unique genres to insert.")
        
        if not unique_genres:
            print("[!!!] No genres found to insert. Skipping insertion.")
            return

        sql = "INSERT INTO genres (genre_name) VALUES (%s)"
        genre_data = [(genre,) for genre in sorted(list(unique_genres))]
        
        cursor.executemany(sql, genre_data)
        
        print("[SUCCESS] 'genres' table populated successfully.")
        
    except FileNotFoundError:
        print(f"[ERROR] Could not find the file at {movies_file_path}")
    except Exception as e:
        print(f"[ERROR] An error occurred during genre population: {e}")
        raise

def populate_directors(cursor):
    """
    Reads director data from netflix_shows.csv, extracts a unique list,
    and populates the 'directors' table.
    """
    print("--> Populating 'directors' table...")
    
    unique_directors = set()
    shows_file_path = os.path.join('data', 'netflix_shows.csv')
    
    try:
        with open(shows_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                directors_string = row.get('director')
                
                if directors_string:
                    director_list = [name.strip() for name in directors_string.split(',')]
                    unique_directors.update(director_list)

        print(f"--> Found {len(unique_directors)} unique directors to insert.")
        
        if not unique_directors:
            print("[!!!] No directors found to insert. Skipping insertion.")
            return

        sql = "INSERT INTO directors (director_name) VALUES (%s)"
        director_data = [(name,) for name in sorted(list(unique_directors))]
        
        cursor.executemany(sql, director_data)
        
        print("[SUCCESS] 'directors' table populated successfully.")
        
    except FileNotFoundError:
        print(f"[ERROR] Could not find the file at {shows_file_path}")
    except Exception as e:
        print(f"[ERROR] An error occurred during director population: {e}")
        raise

def populate_content_and_bridges(cursor):
    """
    Populates content and bridge tables. Returns a map of 
    {original_tmdb_id -> new_auto_incremented_content_id}.
    """
    print("--> Populating 'content' and bridge tables...")
    
    cursor.execute("SELECT genre_id, genre_name FROM genres")
    genre_map = {name: id for id, name in cursor.fetchall()}
    cursor.execute("SELECT director_id, director_name FROM directors")
    director_map = {name: id for id, name in cursor.fetchall()}
    
    content_to_insert = []
    movies_by_tmdb_id = {}
    
    csv_regex = re.compile(r',(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)')

    print("--> Processing movies.csv...")
    movies_file_path = os.path.join('data', 'movies.csv')
    with open(movies_file_path, 'r', encoding='utf-8') as file:
        header = next(file).strip().split(',')
        h = {name: i for i, name in enumerate(header)}

        for line in file:
            try:
                fields = csv_regex.split(line)
                tmdb_id = int(fields[h['id']])
                title = fields[h['title']].strip('"')
                overview = fields[h['overview']].strip('"')
                release_year_str = fields[h['release_date']][:4]

                movie_tuple = (
                    'Movie', title, overview, 
                    int(release_year_str) if release_year_str.isdigit() else None,
                    tmdb_id
                )
                movies_by_tmdb_id[tmdb_id] = movie_tuple
                
            except (ValueError, IndexError, json.JSONDecodeError):
                continue

    print(f"--> Inserting {len(movies_by_tmdb_id)} movie records into 'content' table...")
    tmdb_id_to_content_id_map = {}
    sql_content_movie = "INSERT INTO content (content_type, title, overview, release_year, source_id) VALUES (%s, %s, %s, %s, %s)"

    for tmdb_id, movie_tuple in movies_by_tmdb_id.items():
        cursor.execute(sql_content_movie, movie_tuple)
        new_content_id = cursor.lastrowid
        tmdb_id_to_content_id_map[tmdb_id] = new_content_id

    # handle genres using new map
    content_genres_to_insert = []
    with open(movies_file_path, 'r', encoding='utf-8') as file:
        header = next(file).strip().split(',')
        h = {name: i for i, name in enumerate(header)}
        for line in file:
             try:
                fields = csv_regex.split(line)
                tmdb_id = int(fields[h['id']])
                if tmdb_id in tmdb_id_to_content_id_map:
                    new_content_id = tmdb_id_to_content_id_map[tmdb_id]
                    genres_json_string = fields[h['genres']].strip('"').replace('""', '"')
                    if genres_json_string:
                        genres_list = json.loads(genres_json_string)
                        for genre_obj in genres_list:
                            genre_name = genre_obj.get('name')
                            if genre_name in genre_map:
                                genre_id = genre_map[genre_name]
                                content_genres_to_insert.append((new_content_id, genre_id))
             except (ValueError, IndexError, json.JSONDecodeError):
                continue
                
    # process netflix_shows.csv
    print("--> Processing netflix_shows.csv...")
    shows_file_path = os.path.join('data', 'netflix_shows.csv')
    content_directors_to_insert = []
    sql_content_show = "INSERT INTO content (content_type, title, overview, release_year, source_id) VALUES (%s, %s, %s, %s, %s)"
    with open(shows_file_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            source_id = row.get('show_id')
            title = row.get('title')
            release_year_str = row.get('release_year')
            
            show_tuple = (
                'TV Show', title, None,
                int(release_year_str) if release_year_str and release_year_str.isdigit() else None,
                source_id
            )
            cursor.execute(sql_content_show, show_tuple)
            new_content_id = cursor.lastrowid

            directors_string = row.get('director')
            if directors_string:
                director_list = [name.strip() for name in directors_string.split(',')]
                for director_name in director_list:
                    if director_name in director_map:
                        director_id = director_map[director_name]
                        content_directors_to_insert.append((new_content_id, director_id))

    # insert the bridge table data
    print(f"--> Inserting {len(content_genres_to_insert)} records into 'content_genres' table...")
    sql_genres = "INSERT INTO content_genres (content_id, genre_id) VALUES (%s, %s)"
    cursor.executemany(sql_genres, content_genres_to_insert)

    print(f"--> Inserting {len(content_directors_to_insert)} records into 'content_directors' table...")
    sql_directors = "INSERT INTO content_directors (content_id, director_id) VALUES (%s, %s)"
    cursor.executemany(sql_directors, content_directors_to_insert)

    print("[SUCCESS] 'content' and bridge tables populated successfully.")
    
    # return map
    return tmdb_id_to_content_id_map

def populate_awards(cursor, tmdb_id_map):
    """
    Reads cleaned Oscar data and populates the 'awards' table using the
    tmdb_id -> content_id map.
    """
    print("--> Populating 'awards' table...")
    
    awards_to_insert = []
    awards_file_path = os.path.join('data', 'oscars.csv')
    
    try:
        with open(awards_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    original_tmdb_id_str = row.get('tmdb_id')
                    year = row.get('Year')
                    category = row.get('Category')
                    
                    if original_tmdb_id_str and original_tmdb_id_str.strip():
                        original_tmdb_id = int(original_tmdb_id_str)
                        
                        if original_tmdb_id in tmdb_id_map:
                            new_content_id = tmdb_id_map[original_tmdb_id]
                            
                            awards_to_insert.append((
                                new_content_id,
                                int(year),
                                category
                            ))
                except (ValueError, TypeError):
                    continue

        print(f"--> Found {len(awards_to_insert)} award records to insert.")

        if not awards_to_insert:
            print("[!!!] No awards found to insert. Skipping insertion.")
            return

        sql = "INSERT INTO awards (content_id, year, category) VALUES (%s, %s, %s)"
        cursor.executemany(sql, awards_to_insert)
        
        print("[SUCCESS] 'awards' table populated successfully.")

    except FileNotFoundError:
        # ... (error handling is the same) ...
        print(f"[ERROR] Could not find the file at {awards_file_path}")
        raise
    except Exception as e:
        print(f"[ERROR] An error occurred during award population: {e}")
        raise

def create_and_populate_database():
    """
    Connects to MySQL, creates the database and tables by executing schema.sql.
    """
    load_dotenv()

    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    conn = None
    cursor = None
    try:
        # connect to the MySQL server
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password
        )
        if conn.is_connected():
            print("[SUCCESS] Successfully connected to MySQL server.")

        cursor = conn.cursor()
        
        schema_file_path = 'schema.sql'
        print(f"--> Reading schema from: {schema_file_path}")

        with open(schema_file_path, 'r', encoding='utf-8') as file:
            sql_script = file.read()

        print("--> Executing DDL script to create schema and tables...")
        
        # Split the script into individual commands
        sql_commands = sql_script.split(';')

        # Execute each command one by one
        for command in sql_commands:
            if command.strip():
                cursor.execute(command)
        
        conn.database = db_name
        print(f"--> Switched to database '{db_name}'.")

        print("--- [GENRES TABLE] ---")
        populate_genres(cursor)
        print("--- [DIRECTORS TABLE] ---")
        populate_directors(cursor)
        print("--- [CONTENT & BRIDGE TABLES] ---")
        id_map = populate_content_and_bridges(cursor)
        print("--- [AWARDS TABLE] ---")
        populate_awards(cursor, id_map)

        conn.commit()

        print("[SUCCESS] Database schema and tables created successfully.")
        print("[SUCCESS] All data populated successfully.")

    except Error as e:
        print(f"[ERROR] Error during database setup: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("--> MySQL connection closed.")

if __name__ == '__main__':
    create_and_populate_database()