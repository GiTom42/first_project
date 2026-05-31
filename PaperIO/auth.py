import hashlib
import os
import pickle

DB_FILE = 'users.pkl'
PEPPER = b'super_secret_pepper_paper_io'  # Server-side pepper


def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return {}


def save_db(db):
    with open(DB_FILE, 'wb') as f:
        pickle.dump(db, f)


def hash_password(password: str, salt: bytes) -> str:
    # Hash combining password, salt, and pepper just like the assignment
    pw_bytes = password.encode('utf-8')
    return hashlib.sha256(pw_bytes + salt + PEPPER).hexdigest()


def signup_user(username, password):
    if not username or not password:
        return False, "Fields cannot be empty."

    db = load_db()
    if username in db:
        return False, "Username already exists."

    salt = os.urandom(16)
    pw_hash = hash_password(password, salt)

    db[username] = {
        'salt': salt,
        'hash': pw_hash
    }
    save_db(db)
    return True, "Signup successful."


def login_user(username, password):
    if not username or not password:
        return False, "Fields cannot be empty."

    db = load_db()
    if username not in db:
        return False, "Username not found."

    user_data = db[username]
    salt = user_data['salt']
    stored_hash = user_data['hash']

    if hash_password(password, salt) == stored_hash:
        return True, "Login successful."
    else:
        return False, "Incorrect password."