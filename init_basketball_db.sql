USE basketball_db;

-- Таблица игроков с HSV цветом майки
CREATE TABLE players (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    team_name VARCHAR(100) NOT NULL,
    jersey_h INT NOT NULL,
    jersey_s INT NOT NULL,
    jersey_v INT NOT NULL
);

CREATE TABLE teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    hsv_h INT,
    hsv_s INT,
    hsv_v INT
);

-- Таблица матчей
CREATE TABLE matches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team1 VARCHAR(100),
    team2 VARCHAR(100),
    match_time DATETIME,
    video_path VARCHAR(255) DEFAULT NULL
);

-- Вставка матчей
INSERT INTO matches (team1, team2, match_time, video_path) VALUES
('Pacers', 'Bulls', '2025-04-20 15:00:00', 'model/video_test_1.mp4'),
('CSKA', 'FEFU', '2025-04-20 18:00:00', 'model/video_test_2.mp4'),
('Spurs', 'Warriors', '2025-05-01 14:30:00', 'model/video_test_3.mp4'),
('Barcelona', 'RealMadrid', '2025-05-20 18:00:00', 'model/video_test_4.mp4'),
('Miami', 'Lakers', '2025-06-01 18:30:00', 'model/video_test_5.mp4');

-- Таблица статистики
CREATE TABLE stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id INT NOT NULL,
    team1_points INT DEFAULT 0,
    team2_points INT DEFAULT 0,
    team1_fouls INT DEFAULT 0,
    team2_fouls INT DEFAULT 0,
    team1_twos INT DEFAULT 0,
    team2_twos INT DEFAULT 0,
    team1_threes INT DEFAULT 0,
    team2_threes INT DEFAULT 0,
    team1_freethrows INT DEFAULT 0,
    team2_freethrows INT DEFAULT 0,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

-- Вставка тестовой статистики
INSERT INTO stats (match_id, team1_points, team2_points, team1_fouls, team2_fouls, team1_twos, team2_twos, team1_threes, team2_threes, team1_freethrows, team2_freethrows) VALUES
(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
(2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
(3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
(5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);

-- Таблица пользователей
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('user', 'admin') DEFAULT 'user'
);


-- Таблица статистики игроков
CREATE TABLE player_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT,
    match_id INT,
    points INT,
    shot_time DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team_id INT,
    match_id INT NOT NULL,
    event_type ENUM('shot', 'foul') NOT NULL,
    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    points INT DEFAULT NULL,  -- для бросков
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

-- Примеры игроков
INSERT INTO players (name, team_name, jersey_h, jersey_s, jersey_v)
VALUES ('Example Player', 'CSKA', 260, 32, 73);

INSERT INTO players (name, team_name, jersey_h, jersey_s, jersey_v)
VALUES ('NoName', 'Pacers', 110, 92, 65);

INSERT INTO players (name, team_name, jersey_h, jersey_s, jersey_v)
VALUES ('Evgeniy', 'Bulls', 14, 168, 121);


SELECT * FROM matches;
SELECT * FROM players;
SELECT * FROM teams;
SELECT * FROM stats;
SELECT * FROM events;