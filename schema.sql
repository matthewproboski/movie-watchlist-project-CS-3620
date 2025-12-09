-- schema for movie & TV show watchlist app

-- drop the database if it already exists
DROP DATABASE IF EXISTS movie_app;

-- create the main database
CREATE DATABASE movie_app;

-- switch to using new database
USE movie_app;

-- `users` table: stores user authentication and basic info
CREATE TABLE users (
    user_id         INT AUTO_INCREMENT PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- `genres` table: a normalized reference table for all the content genres
CREATE TABLE genres (
    genre_id        INT AUTO_INCREMENT PRIMARY KEY,
    genre_name      VARCHAR(100) NOT NULL UNIQUE
);

-- `directors` table: a normalized reference table for the directors
CREATE TABLE directors (
    director_id     INT AUTO_INCREMENT PRIMARY KEY,
    director_name   VARCHAR(255) NOT NULL UNIQUE
);

-- `content` table: this is the central table that holds information about both movies and TV shows
CREATE TABLE content (
    content_id      INT AUTO_INCREMENT PRIMARY KEY,
    source_id       VARCHAR(50) NOT NULL UNIQUE, -- the ID from the original dataset (TMDB id or Netflix show_id)
    content_type    ENUM('Movie', 'TV Show') NOT NULL,
    title           VARCHAR(255) NOT NULL,
    release_year    YEAR,
    overview        TEXT,
    FULLTEXT(title, overview)
);


-- these tables are used to link core entities together
CREATE TABLE content_genres (
    content_id      INT NOT NULL,
    genre_id        INT NOT NULL,
    PRIMARY KEY (content_id, genre_id),
    FOREIGN KEY (content_id) REFERENCES content(content_id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES genres(genre_id) ON DELETE CASCADE
);

CREATE TABLE content_directors (
    content_id      INT NOT NULL,
    director_id     INT NOT NULL,
    PRIMARY KEY (content_id, director_id),
    FOREIGN KEY (content_id) REFERENCES content(content_id) ON DELETE CASCADE,
    FOREIGN KEY (director_id) REFERENCES directors(director_id) ON DELETE CASCADE
);

CREATE TABLE awards (
    award_id        INT AUTO_INCREMENT PRIMARY KEY,
    content_id      INT NOT NULL,
    year            INT NOT NULL,
    category        VARCHAR(255) NOT NULL,
    FOREIGN KEY (content_id) REFERENCES content(content_id) ON DELETE CASCADE
);

-- these tables hold all of the user related actions
CREATE TABLE sessions (
    session_id      VARCHAR(255) PRIMARY KEY,
    user_id         INT NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE user_watchlist (
    user_id         INT NOT NULL,
    content_id      INT NOT NULL,
    added_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, content_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (content_id) REFERENCES content(content_id) ON DELETE CASCADE
);

CREATE TABLE user_ratings (
    user_id         INT NOT NULL,
    content_id      INT NOT NULL,
    rating          DECIMAL(3, 1) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, content_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (content_id) REFERENCES content(content_id) ON DELETE CASCADE,
    CONSTRAINT chk_rating CHECK (rating >= 1.0 AND rating <= 5.0)
);

CREATE TABLE action_log (
    log_id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT NULL,
    action_type     VARCHAR(50) NOT NULL,
    target_id       INT NULL,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- `user_profiles` table: stores user profile data, is both optional and editable
CREATE TABLE user_profiles (
    user_id         INT PRIMARY KEY,
    display_name    VARCHAR(50),
    bio             TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- `search_history` table: logs user search history and analytics
CREATE TABLE search_history (
    history_id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT NOT NULL,
    search_query    VARCHAR(255) NOT NULL,
    searched_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);