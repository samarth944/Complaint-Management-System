# ============================
# 1️⃣ Imports
# ============================
from flask import Flask, render_template, request, redirect, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

# ============================
# 2️⃣ Flask App
# ============================
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Upload Configuration
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ============================
# 3️⃣ Database Functions
# ============================
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_db()

    # Users Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)

    # Complaints Table (with file + date)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            description TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT
        )
    """)

    conn.commit()
    conn.close()


# ============================
# 4️⃣ Routes
# ============================

@app.route("/")
def home():
    return redirect("/login")


# ----------------------------
# Register
# ----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)
        role = "admin" if email == "admin@gmail.com" else "user"

        conn = get_db()
        conn.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (name, email, hashed_password, role)
        )
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ----------------------------
# Login
# ----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect("/admin")

            return redirect("/dashboard")

        else:
            return "Invalid Email or Password"

    return render_template("login.html")


# ----------------------------
# Dashboard
# ----------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    total = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()[0]

    pending = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'Pending'",
        (session["user_id"],)
    ).fetchone()[0]

    resolved = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'Resolved'",
        (session["user_id"],)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        total=total,
        pending=pending,
        resolved=resolved
    )


# ----------------------------
# Submit Complaint (WITH FILE)
# ----------------------------
@app.route("/submit", methods=["GET", "POST"])
def submit():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        category = request.form["category"]
        description = request.form["description"]

        file = request.files.get("file")
        filename = None

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        conn = get_db()
        conn.execute(
            "INSERT INTO complaints (user_id, category, description, file_path) VALUES (?, ?, ?, ?)",
            (session["user_id"], category, description, filename)
        )
        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("submit.html")


# ----------------------------
# My Complaints
# ----------------------------
@app.route("/mycomplaints")
def mycomplaints():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    complaints = conn.execute(
        "SELECT * FROM complaints WHERE user_id = ?",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    return render_template("mycomplaints.html", complaints=complaints)


# ----------------------------
# Admin Panel (Search + Pagination)
# ----------------------------
@app.route("/admin")
def admin():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    page = request.args.get("page", 1, type=int)
    per_page = 5
    offset = (page - 1) * per_page
    search = request.args.get("search")

    conn = get_db()

    if search:
        total_count = conn.execute("""
            SELECT COUNT(*)
            FROM complaints
            JOIN users ON complaints.user_id = users.id
            WHERE category LIKE ? OR users.name LIKE ?
        """, (f"%{search}%", f"%{search}%")).fetchone()[0]

        complaints = conn.execute("""
            SELECT complaints.*, users.name
            FROM complaints
            JOIN users ON complaints.user_id = users.id
            WHERE category LIKE ? OR users.name LIKE ?
            LIMIT ? OFFSET ?
        """, (f"%{search}%", f"%{search}%", per_page, offset)).fetchall()
    else:
        total_count = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]

        complaints = conn.execute("""
            SELECT complaints.*, users.name
            FROM complaints
            JOIN users ON complaints.user_id = users.id
            LIMIT ? OFFSET ?
        """, (per_page, offset)).fetchall()

    conn.close()

    total_pages = (total_count + per_page - 1) // per_page

    return render_template(
        "admin.html",
        complaints=complaints,
        page=page,
        total_pages=total_pages,
        search=search
    )


# ----------------------------
# Resolve
# ----------------------------
@app.route("/resolve/<int:id>")
def resolve(id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    conn.execute("UPDATE complaints SET status = 'Resolved' WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


# ----------------------------
# Delete
# ----------------------------
@app.route("/delete/<int:id>")
def delete(id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    conn.execute("DELETE FROM complaints WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


# ----------------------------
# Logout
# ----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ============================
# Run App
# ============================
if __name__ == "__main__":
    create_tables()
    app.run(debug=True)