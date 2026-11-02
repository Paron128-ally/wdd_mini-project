PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL COLLATE NOCASE UNIQUE,
  username TEXT NOT NULL COLLATE NOCASE UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  currency_preference TEXT NOT NULL DEFAULT 'USD' CHECK (length(currency_preference)=3)
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  type TEXT NOT NULL CHECK (type IN ('INCOME','EXPENSE')),
  is_system INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0,1)),
  UNIQUE (user_id,id),
  UNIQUE (user_id,name,type)
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INTEGER NOT NULL,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
  amount NUMERIC NOT NULL CHECK (amount >= 0),
  type TEXT NOT NULL CHECK (type IN ('INCOME','EXPENSE')),
  date TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '' CHECK (length(notes)<=1000),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id,category_id) REFERENCES categories(user_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS transaction_owner_date ON transactions(user_id,date);

CREATE TABLE IF NOT EXISTS budgets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INTEGER NOT NULL,
  month TEXT NOT NULL,
  amount NUMERIC NOT NULL CHECK (amount >= 0),
  UNIQUE (user_id,category_id,month),
  FOREIGN KEY (user_id,category_id) REFERENCES categories(user_id,id) ON DELETE CASCADE
);
