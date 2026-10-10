-- PS Focus friends: who has friends turned on, who is friends with whom, and requests waiting for an answer.
-- sub is the Google account's id; no email is kept

CREATE TABLE IF NOT EXISTS users (
  sub TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  stats TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);

-- Each friendship is kept both ways round, so a person's friends are one lookup
CREATE TABLE IF NOT EXISTS friends (
  user TEXT NOT NULL,
  friend TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user, friend)
);

CREATE TABLE IF NOT EXISTS requests (
  sender TEXT NOT NULL,
  recipient TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (sender, recipient)
);

CREATE INDEX IF NOT EXISTS requests_by_recipient ON requests (recipient);
