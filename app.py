from flask import Flask, Request, json, request, render_template, redirect, session, send_from_directory, flash
import os
from datetime import datetime, timedelta
import mysql.connector
import hashlib
import time
import uuid
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify
from flask import request
from werkzeug.middleware.proxy_fix import ProxyFix
from pathlib import Path

app = Flask(__name__)
app.secret_key = "super_secret_key"

app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
app.wsgi_app = ProxyFix(app.wsgi_app)

class LargeRequest(Request):
    max_content_length = 500 * 1024 * 1024

app.request_class = LargeRequest

# Use pathlib for more robust path handling
APP_DIR = Path(__file__).parent.resolve()
UPLOAD_FOLDER = APP_DIR / "uploads"
BASELINE_FOLDER = UPLOAD_FOLDER / "baseline"

# Create folders on startup  
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
BASELINE_FOLDER.mkdir(parents=True, exist_ok=True)
print(f"✓ Upload folder ready: {UPLOAD_FOLDER}")
print(f"✓ Baseline folder ready: {BASELINE_FOLDER}")

# Convert to strings for Flask config
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="deena@1604",
    database="secure_file_sharing"
)


def ensure_metrics_table():
    cursor = db.cursor(buffered=True)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,
            file_id INT NULL,
            metric_name VARCHAR(64) NOT NULL,
            mode VARCHAR(32) NULL,
            status VARCHAR(32) NULL,
            duration_ms DECIMAL(12, 3) NULL,
            file_size_mb DECIMAL(12, 3) NULL,
            size_before_mb DECIMAL(12, 3) NULL,
            size_after_mb DECIMAL(12, 3) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    cursor.close()


def log_metric(metric_name, duration_ms, user_id=None, file_id=None, mode=None, status=None,
               file_size_mb=None, size_before_mb=None, size_after_mb=None):
    try:
        cursor = db.cursor(buffered=True)
        cursor.execute(
            """
            INSERT INTO performance_metrics
            (user_id, file_id, metric_name, mode, status, duration_ms, file_size_mb, size_before_mb, size_after_mb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, file_id, metric_name, mode, status, duration_ms, file_size_mb, size_before_mb, size_after_mb)
        )
        db.commit()
        cursor.close()
    except Exception as e:
        print("METRIC LOG ERROR:", e)


ensure_metrics_table()


@app.route("/")
def home():       
    return redirect("/login")


@app.route("/baseline-benchmark")
def baseline_benchmark_page():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("baseline_benchmark.html")


@app.route("/baseline/upload", methods=["POST"])
def baseline_upload():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file or uploaded_file.filename == "":
        return jsonify({"error": "Invalid file"}), 400

    try:
        # Ensure folders exist
        BASELINE_FOLDER.mkdir(parents=True, exist_ok=True)

        upload_start = time.perf_counter()
        safe_name = secure_filename(uploaded_file.filename)
        token = str(uuid.uuid4())
        # Keep stored filename short to avoid Windows path-length failures.
        suffix = Path(safe_name).suffix.lower() if safe_name else ""
        if not suffix:
            suffix = ".bin"
        temp_name = f"{token}{suffix}"
        temp_path = BASELINE_FOLDER / temp_name
        
        print(f"DEBUG: Saving file to {temp_path}")
        print(f"DEBUG: Original name length: {len(safe_name)}")
        print(f"DEBUG: Final path length: {len(str(temp_path))}")
        print(f"DEBUG: BASELINE_FOLDER exists: {BASELINE_FOLDER.exists()}")
        print(f"DEBUG: BASELINE_FOLDER = {BASELINE_FOLDER}")

        uploaded_file.save(str(temp_path))

        elapsed_ms = (time.perf_counter() - upload_start) * 1000
        size_bytes = temp_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)

        log_metric(
            metric_name="upload_server",
            duration_ms=elapsed_ms,
            user_id=session["user_id"],
            mode="non_encrypted",
            status="success",
            file_size_mb=size_mb,
            size_before_mb=size_mb,
            size_after_mb=size_mb
        )

        return jsonify({
            "success": True,
            "token": token,
            "stored_name": temp_name,
            "file_size_mb": size_mb,
            "filename": safe_name
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Baseline upload error: {e}")
        print(error_trace)
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/baseline/download/<token>")
def baseline_download(token):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    try:
        BASELINE_FOLDER.mkdir(parents=True, exist_ok=True)
        
        candidates = list(BASELINE_FOLDER.glob(f"{token}*"))
        if not candidates:
            return jsonify({"error": "File not found"}), 404

        filepath = candidates[0]
        return send_from_directory(str(BASELINE_FOLDER), filepath.name, as_attachment=True)
    except Exception as e:
        print(f"Baseline download error: {e}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500


@app.route("/metrics/client", methods=["POST"])
def metrics_client():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}

    metric_name = data.get("metric_name")
    mode = data.get("mode")
    duration_ms = data.get("duration_ms")
    file_size_mb = data.get("file_size_mb")
    file_id = data.get("file_id")

    allowed_metric_names = {"upload_total", "download_open_total", "approve_total"}
    allowed_modes = {"encrypted", "non_encrypted"}

    if metric_name not in allowed_metric_names:
        return jsonify({"error": "Invalid metric_name"}), 400

    if mode not in allowed_modes:
        return jsonify({"error": "Invalid mode"}), 400

    try:
        duration_ms = float(duration_ms)
        file_size_mb = float(file_size_mb) if file_size_mb is not None else None
        file_id = int(file_id) if file_id is not None else None
    except Exception:
        return jsonify({"error": "Invalid metric values"}), 400

    if duration_ms <= 0:
        return jsonify({"error": "duration_ms must be positive"}), 400

    log_metric(
        metric_name=metric_name,
        duration_ms=duration_ms,
        user_id=session["user_id"],
        file_id=file_id,
        mode=mode,
        status="success",
        file_size_mb=file_size_mb
    )

    return jsonify({"success": True})

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        public_key = request.form["public_key"]
        encrypted_private_key = request.form["encrypted_private_key"]
        private_key_iv = request.form["private_key_iv"]

        password_hash = generate_password_hash(password)

        cursor = db.cursor(buffered=True)

        cursor.execute("""
        INSERT INTO users
        (username, password_hash, public_key, encrypted_private_key, private_key_iv)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (username, password_hash, public_key, encrypted_private_key, private_key_iv)
        )

        db.commit()
        cursor.close()

        flash("Registration successful!", "success")

        return redirect("/login")

    return render_template("register.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password required", "error")
            return redirect("/login")

        cursor = db.cursor(buffered=True)

        # 🔹 GET USER WITH KEYS
        cursor.execute(
            "SELECT id, password_hash, encrypted_private_key, private_key_iv FROM users WHERE username = %s",
            (username,)
        )

        user = cursor.fetchone()

        if user is None:
            cursor.close()
            flash("Invalid username or password", "error")
            return redirect("/login")

        user_id = user[0]
        stored_hash = user[1]
        encrypted_private_key = user[2]
        private_key_iv = user[3]

        # 🔹 CHECK PASSWORD
        if not check_password_hash(stored_hash, password):
            cursor.close()
            flash("Invalid username or password", "error")
            return redirect("/login")

        # 🔹 LOGIN SUCCESS
        session["user_id"] = user_id
        session.permanent = True
        cursor.close()
        flash("Login successful!", "success")
        return redirect("/dashboard")
    
    # 🔹 GET REQUEST
    if "user_id" in session:
        return redirect("/dashboard")
    

    return render_template(
        "login.html",
        encrypted_private_key="",
        private_key_iv="",
        login_success=False
    )
# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please login to access the dashboard", "error")
        return redirect("/login")

    cursor = db.cursor(buffered=True)

    cursor.execute(
        "SELECT username, encrypted_private_key, private_key_iv "
        "FROM users WHERE id = %s",
        (session["user_id"],)
    )
    user = cursor.fetchone()

    if not user:
        cursor.close()
        flash("User not found. Please login again.", "error")
        session.clear()
        return redirect("/login")

    username, encrypted_private_key, private_key_iv = user

    # Handle case where keys are missing (e.g. old user without keys)
    if not encrypted_private_key or not private_key_iv:
        flash("No encryption keys found for your account. Some features may be limited.", "warning")

    cursor.close()

    return render_template(
        "dashboard.html",
        username=username,
        encrypted_private_key=encrypted_private_key or "",
        private_key_iv=private_key_iv or ""
    )

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect("/login")

# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["GET","POST"])
def upload():

    if "user_id" not in session:
        return redirect("/login")

    cursor = db.cursor(buffered=True)

    cursor.execute(
        "SELECT public_key FROM users WHERE id=%s",
        (session["user_id"],)
    )
    row = cursor.fetchone()

    if not row or not row[0]:
        cursor.close()
        flash("No public key found for your account", "error")
        return redirect("/dashboard")

    public_key = row[0]

    public_key = public_key.strip()
    public_key = public_key.replace('\r\n', '\n')
    public_key = '\n'.join(line.strip() for line in public_key.splitlines() if line.strip())

    if request.method == "POST":
        upload_start = time.perf_counter()

        data = request.get_json()

        encrypted_file_b64 = data.get("encrypted_file")
        encrypted_aes_key_b64 = data.get("encrypted_aes_key")
        duration_str = data.get("duration")
        original_filename = data.get("original_filename")
        original_size_bytes = data.get("original_size_bytes")

        try:
            original_size_bytes = int(original_size_bytes) if original_size_bytes is not None else None
        except Exception:
            original_size_bytes = None

        if not encrypted_file_b64 or not encrypted_aes_key_b64 or not duration_str:
            cursor.close()
            return jsonify({"error": "Missing data"})

        try:
            duration = float(duration_str)
            if duration not in [0.083, 12, 24, 48]:
                raise ValueError
        except:
            cursor.close()
            return jsonify({"error": "Invalid duration"})

        expiry = datetime.now() + timedelta(hours=duration)

        filename = secure_filename(
            f"encrypted_{int(datetime.now().timestamp())}.bin"
        )

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        import base64
        try:
            encrypted_bytes = base64.b64decode(encrypted_file_b64)
            with open(filepath, "wb") as f:
                f.write(encrypted_bytes)
        except Exception as e:
            print(e)

            # ❌ LOG UPLOAD FAILURE
            cursor.execute(
                "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
                (session["user_id"], None, "upload_failed")
            )
            db.commit()

            cursor.close()
            return jsonify({"error": "File save failed"})

        # ✅ INSERT FILE
        cursor.execute("""
            INSERT INTO files
            (owner_id, filename, original_filename, expiry_time)
            VALUES (%s, %s, %s, %s)
        """, (session["user_id"], filename, original_filename, expiry))

        file_id = cursor.lastrowid

        # ✅ INSERT AES KEY
        cursor.execute("""
            INSERT INTO file_keys
            (file_id, user_id, encrypted_aes_key)
            VALUES (%s, %s, %s)
        """, (file_id, session["user_id"], encrypted_aes_key_b64))

        db.commit()

        elapsed_ms = (time.perf_counter() - upload_start) * 1000
        encrypted_size_mb = len(encrypted_bytes) / (1024 * 1024)
        original_size_mb = (original_size_bytes / (1024 * 1024)) if original_size_bytes else None

        log_metric(
            metric_name="upload_server",
            duration_ms=elapsed_ms,
            user_id=session["user_id"],
            file_id=file_id,
            mode="encrypted",
            status="success",
            file_size_mb=encrypted_size_mb,
            size_before_mb=original_size_mb,
            size_after_mb=encrypted_size_mb
        )

        # ✅ LOG SUCCESS UPLOAD
        cursor.execute(
            "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
            (session["user_id"], file_id, "upload")
        )
        db.commit()

        cursor.close()
        return jsonify({"success": True})

    cursor.close()
    return render_template("upload.html", public_key=public_key)



# ---------------- MY FILES ----------------
@app.route("/files")
def list_files():

    if "user_id" not in session:
        return redirect("/login")

    cursor = db.cursor(buffered=True)

    # ✅ UPDATED QUERY (WITH REQUEST COUNT)
    cursor.execute("""
        SELECT f.id, f.filename, f.original_filename, f.expiry_time,
               (SELECT COUNT(*) FROM access_requests ar
                WHERE ar.file_id=f.id AND ar.status='pending') as request_count
        FROM files f
        WHERE f.owner_id=%s
        ORDER BY f.id DESC
    """, (session["user_id"],))

    files = cursor.fetchall()

    # keep this SAME (no change)
    cursor.execute("""
        SELECT id, username
        FROM users
        WHERE id != %s
    """, (session["user_id"],))

    users = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM access_requests WHERE status='pending'")
    request_count = cursor.fetchone()[0]

    cursor.close()

    return render_template("files.html", files=files, users=users, request_count=request_count)


# ---------------- SHARED WITH ME ----------------
@app.route("/shared")
def shared_files():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    cursor = db.cursor(buffered=True)

    cursor.execute("""
      SELECT 
        f.id,
        f.filename,
        f.original_filename,

        MAX(fa.expiry_time) as expiry_time,

        CASE 
            WHEN COUNT(n.id) > 0 THEN 1 
            ELSE 0 
        END AS notification_count,

        MAX(CASE WHEN n.type='rejected' THEN 1 ELSE 0 END) AS is_rejected

    FROM files f

    JOIN file_access fa 
        ON f.id = fa.file_id 
        AND fa.user_id = %s

    LEFT JOIN notifications n 
        ON n.file_id = f.id 
        AND n.user_id = %s

    WHERE fa.user_id = %s

    GROUP BY f.id, f.filename, f.original_filename
    ORDER BY f.id DESC
     """, (user_id, user_id, user_id))

    files = cursor.fetchall()

    cursor.close()

    return render_template(
        "shared.html",
        files=files,
        current_time=datetime.now()
    )

# ---------------- DOWNLOAD FILE ----------------
@app.route("/download/<int:file_id>")
def download(file_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    download_start = time.perf_counter()
    cursor = db.cursor(buffered=True)

    # 🔥 STEP 1: GET FILE (NO JOIN FIRST)
    cursor.execute("""
        SELECT id, filename, original_filename, owner_id
        FROM files
        WHERE id = %s
    """, (file_id,))

    file_row = cursor.fetchone()

    if not file_row:
        cursor.close()
        return jsonify({"error": "File not found"}), 404

    _, filename, original_filename, owner_id = file_row

    # 🔥 STEP 2: GET ACCESS + KEY SEPARATELY
    cursor.execute("""
        SELECT expiry_time
        FROM file_access
        WHERE file_id = %s AND user_id = %s
    """, (file_id, user_id))

    access_row = cursor.fetchone()

    cursor.execute("""
        SELECT encrypted_aes_key
        FROM file_keys
        WHERE file_id = %s AND user_id = %s
    """, (file_id, user_id))

    key_row = cursor.fetchone()

    expiry_time = access_row[0] if access_row else None
    # encrypted_key = key_row[0] if key_row else None
    encrypted_key = key_row[0] if key_row and key_row[0] else None

    # 🔥 OWNER ALWAYS ALLOWED
    
    if user_id == owner_id:
        pass  # no restriction

    else:
        if not access_row:
            elapsed_ms = (time.perf_counter() - download_start) * 1000
            log_metric(
                metric_name="download_unauthorized",
                duration_ms=elapsed_ms,
                user_id=user_id,
                file_id=file_id,
                mode="encrypted",
                status="denied_no_access"
            )
            cursor.execute(
                "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
                (user_id, file_id, "denied_no_access")
            )
            db.commit()
            return jsonify({"error": "Access not granted"}), 403

        # ❌ ONLY BLOCK IF NO KEY (NOT JUST EXPIRY)
        if not encrypted_key:
            elapsed_ms = (time.perf_counter() - download_start) * 1000
            log_metric(
                metric_name="download_unauthorized",
                duration_ms=elapsed_ms,
                user_id=user_id,
                file_id=file_id,
                mode="encrypted",
                status="denied_expired"
            )
            cursor.execute(
                "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
                (user_id, file_id, "denied_expired")
            )
            db.commit()
            return jsonify({"error": "Access expired"}), 403

        # optional: enforce expiry visually but NOT block if key exists
        # (since re-approval gives new key)

    # 🔥 STEP 3: READ FILE
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    if not os.path.exists(filepath):
        cursor.close()
        return jsonify({"error": "File not found on server"}), 404

    import base64
    with open(filepath, "rb") as f:
        encrypted_file = base64.b64encode(f.read()).decode()

    elapsed_ms = (time.perf_counter() - download_start) * 1000
    encrypted_size_mb = (len(encrypted_file) * 3 / 4) / (1024 * 1024)

    log_metric(
        metric_name="download_authorized",
        duration_ms=elapsed_ms,
        user_id=user_id,
        file_id=file_id,
        mode="encrypted",
        status="success",
        file_size_mb=encrypted_size_mb
    )


    # ✅ LOG DOWNLOAD SUCCESS
    cursor.execute(
        "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
        (user_id, file_id, "download")
    )
    db.commit()

    cursor.close()

    return jsonify({
        "encrypted_file": encrypted_file,
        "encrypted_aes_key": encrypted_key,
        "filename": original_filename
    })

# ---------------- SHARE MULTIPLE USERS ----------------
@app.route("/share/<int:file_id>", methods=["GET", "POST"])
def share_file(file_id):

    if "user_id" not in session:
        flash("Please login first", "error")
        return redirect("/login")

    cursor = db.cursor(dictionary=True, buffered=True)

    # ───────── FILE CHECK ─────────
    cursor.execute("""
        SELECT id, filename, original_filename, owner_id
        FROM files
        WHERE id = %s
    """, (file_id,))

    file = cursor.fetchone()

    if not file:
        flash("File not found", "error")
        cursor.close()
        return redirect("/files")

    if file["owner_id"] != session["user_id"]:
        flash("You are not the owner of this file", "error")
        cursor.close()
        return redirect("/files")

    # ───────── POST (E2EE SHARE) ─────────
    if request.method == "POST":

        recipient_id = request.form.get("recipient_id")
        encrypted_aes_key = request.form.get("encrypted_aes_key")

        if not recipient_id or not encrypted_aes_key:
            flash("Missing user or encryption data", "error")
            cursor.close()
            return redirect(f"/share/{file_id}")

        # prevent self share
        if int(recipient_id) == session["user_id"]:
            flash("Cannot share with yourself", "warning")
            cursor.close()
            return redirect(f"/share/{file_id}")

        # check user exists
        cursor.execute(
            "SELECT id FROM users WHERE id=%s",
            (recipient_id,)
        )

        if not cursor.fetchone():
            flash("User does not exist", "error")
            cursor.close()
            return redirect(f"/share/{file_id}")

        # check already shared
        cursor.execute("""
            SELECT id
            FROM file_access
            WHERE file_id=%s AND user_id=%s
        """, (file_id, recipient_id))

        if cursor.fetchone():
            flash("This user already has access", "info")
            cursor.close()
            return redirect("/files")

        # give access
        cursor.execute("""
            INSERT INTO file_access (file_id, user_id)
            VALUES (%s, %s)
        """, (file_id, recipient_id))

        # store encrypted AES key
        cursor.execute("""
            INSERT INTO file_keys (file_id, user_id, encrypted_aes_key)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                encrypted_aes_key = VALUES(encrypted_aes_key),
                created_at = CURRENT_TIMESTAMP
        """, (file_id, recipient_id, encrypted_aes_key))

        db.commit()

        # popup message
        flash("File shared successfully!", "success")

        cursor.close()
        return redirect("/files")

    # ───────── GET (SHOW SHARE PAGE) ─────────
    cursor.execute("""
        SELECT id, username, public_key
        FROM users
        WHERE id != %s
        ORDER BY username
    """, (session["user_id"],))

    users = cursor.fetchall()

    cursor.close()

    return render_template(
        "share_page.html",
        file=file,
        users=users,
        file_id=file_id
    )

# ---------------- DELETE FILES ----------------
@app.route("/delete/<int:file_id>", methods=["POST"])
def delete_file(file_id):
    if "user_id" not in session:
        return redirect("/")

    cursor = db.cursor(buffered=True)

    try:
        # First remove related child records (if foreign keys exist)
        cursor.execute("DELETE FROM file_access WHERE file_id=%s", (file_id,))
        cursor.execute("DELETE FROM file_keys WHERE file_id=%s", (file_id,))
        cursor.execute("DELETE FROM logs WHERE file_id=%s", (file_id,))

        # Now delete from files using owner_id
        cursor.execute(
            "DELETE FROM files WHERE id=%s AND owner_id=%s",
            (file_id, session["user_id"])
        )

        db.commit()
        flash("File deleted successfully", "success")

    except Exception as e:
        print("Delete Error:", e)
        flash("Error deleting file", "error")
    finally:
        cursor.close()

    return redirect("/files")

# ---------------- GET AES KEY ----------------
@app.route("/get_aes_key/<int:file_id>")
def get_aes_key(file_id):

    if "user_id" not in session:
        return {"error":"Not logged in"}

    cursor = db.cursor(buffered=True)

    cursor.execute("""
        SELECT encrypted_aes_key
        FROM file_keys
        WHERE file_id=%s AND user_id=%s
    """,(file_id, session["user_id"]))

    result = cursor.fetchone()

    if not result:
        cursor.close()
        return {"error":"Key not found"}

    cursor.close()
    return {"encrypted_aes_key": result[0]}


# ---------------- SAVE SHARED KEYS ----------------
@app.route("/save_shared_keys/<int:file_id>", methods=["POST"])
def save_shared_keys(file_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    cursor = db.cursor(buffered=True)

    try:
        # ✅ Verify owner
        cursor.execute("SELECT owner_id, expiry_time FROM files WHERE id = %s", (file_id,))
        row = cursor.fetchone()

        if not row or row[0] != session["user_id"]:
            cursor.close()
            return jsonify({"error": "Not the file owner"}), 403

        # ✅ 🔥 IMPORTANT: GET ORIGINAL EXPIRY (OWNER SELECTED)
        file_expiry = row[1]

        try:
            data = request.get_json()
        except:
            data = json.loads(request.data)

        if not data or "shares" not in data:
            cursor.close()
            return jsonify({"error": "No shares data"}), 400

        shares = data["shares"]

        if not shares:
            cursor.close()
            return jsonify({"error": "Select at least one user"}), 400

        shared_count = 0
        duplicate_count = 0

        print("DEBUG SHARES:", shares)

        for share in shares:

            raw_user_id = share.get("user_id")
            enc_key = share.get("encrypted_aes_key")

            if raw_user_id is None or enc_key is None:
                print("Invalid share data:", share)
                continue

            try:
                user_id = int(raw_user_id)
            except:
                print("Invalid user_id:", raw_user_id)
                continue

            # ✅ Check if already shared
            cursor.execute("""
                SELECT id FROM file_access
                WHERE file_id=%s AND user_id=%s
            """, (file_id, user_id))

            if cursor.fetchone():
                duplicate_count += 1
                print(f"User {user_id} already has access")
                continue

            # ✅ 🔥 FIX: USE SAME EXPIRY AS OWNER (NOT 24 HOURS)
            cursor.execute("""
                INSERT INTO file_access (file_id, user_id, expiry_time)
                VALUES (%s, %s, %s)
            """, (file_id, user_id, file_expiry))

            # ✅ Store encrypted AES key
            cursor.execute("""
                INSERT INTO file_keys (file_id, user_id, encrypted_aes_key)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE encrypted_aes_key = VALUES(encrypted_aes_key)
            """, (file_id, user_id, enc_key))

            shared_count += 1

        db.commit()
        cursor.close()

        # ✅ Response message
        if shared_count > 0 and duplicate_count == 0:
            message = "File shared successfully"

        elif shared_count > 0 and duplicate_count > 0:
            message = f"{shared_count} user(s) received file. {duplicate_count} already had access"

        else:
            message = "Selected users already have access"

        return jsonify({
            "success": True,
            "message": message
        })

    except Exception as e:
        db.rollback()
        cursor.close()

        print("❌ Error saving shares:", str(e))

        return jsonify({"error": "Database error"}), 500

# ---------------- REQUEST ACCESS ----------------
@app.route("/request_access/<int:file_id>", methods=["POST"])
def request_access(file_id):

    # 🔒 Check login
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    cursor = db.cursor(buffered=True)

    # ❌ Prevent duplicate pending requests
    cursor.execute("""
        SELECT id FROM access_requests
        WHERE file_id = %s AND user_id = %s AND status = 'pending'
    """, (file_id, user_id))

    if cursor.fetchone():
        cursor.close()
        return jsonify({"error": "Already requested access."}), 400

    # ✅ Insert request
    cursor.execute("""
        INSERT INTO access_requests (file_id, user_id)
        VALUES (%s, %s)
    """, (file_id, user_id))


    # ✅ LOG ACCESS REQUEST
    cursor.execute(
        "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
        (user_id, file_id, "access requested")
    )

    # ✅ Get owner of file
    cursor.execute("""
        SELECT owner_id FROM files WHERE id = %s
    """, (file_id,))
    
    owner_row = cursor.fetchone()

    if not owner_row:
        cursor.close()
        return jsonify({"error": "File not found"}), 404

    owner_id = owner_row[0]

    # ✅ OPTIONAL (Recommended): Remove old notifications for this file (clean UI)
    cursor.execute("""
        DELETE FROM notifications
        WHERE user_id = %s AND file_id = %s
    """, (owner_id, file_id))

    # ✅ Add notification ONLY for owner
    cursor.execute("""
        INSERT INTO notifications (user_id, message, type, file_id)
        VALUES (%s, %s, %s, %s)
    """, (
        owner_id,
        "New access request received",
        "request",
        file_id
    ))

    db.commit()
    cursor.close()

    return jsonify({"success": True})

# ---------------- REENABLE FILE ----------------
@app.route("/reenable/<int:file_id>", methods=["POST"])
def reenable(file_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    cursor = db.cursor(buffered=True)

    cursor.execute("SELECT owner_id FROM files WHERE id=%s", (file_id,))
    row = cursor.fetchone()

    if not row or row[0] != session["user_id"]:
        cursor.close()
        return jsonify({"error": "Unauthorized"}), 403

    cursor.execute("""
        SELECT user_id FROM file_access WHERE file_id=%s
    """, (file_id,))

    users = [u[0] for u in cursor.fetchall()]
    users.append(session["user_id"])

    cursor.close()

    return jsonify({
        "success": True,
        "users": users,
        "file_id": file_id
    })

# ---------------- GET PUBLIC KEY ----------------
@app.route("/get_public_key/<int:user_id>")
def get_public_key(user_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    cursor = db.cursor(buffered=True)

    cursor.execute("SELECT public_key FROM users WHERE id=%s", (user_id,))
    row = cursor.fetchone()

    cursor.close()

    if not row:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"public_key": row[0]})

# ---------------- VIEW ACCESS REQUESTS ----------------
@app.route("/requests")
def requests_page():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    file_id = request.args.get("file_id")   # 👈 NEW

    cursor = db.cursor(buffered=True)

    if file_id:
        cursor.execute("""
            SELECT r.id, u.username, f.original_filename,r.file_id
            FROM access_requests r
            JOIN users u ON r.user_id = u.id
            JOIN files f ON r.file_id = f.id
            WHERE f.owner_id = %s 
              AND r.status='pending'
              AND f.id = %s
            ORDER BY r.id DESC
        """, (user_id, file_id))
    else:
        cursor.execute("""
            SELECT r.id, u.username, f.original_filename, r.file_id
            FROM access_requests r
            JOIN users u ON r.user_id = u.id
            JOIN files f ON r.file_id = f.id
            WHERE f.owner_id = %s AND r.status='pending'
            ORDER BY r.id DESC
        """, (user_id,))

    requests = cursor.fetchall()

    cursor.close()

    return render_template("requests.html", requests=requests)


# ---------------- APPROVE ACCESS REQUEST ----------------
@app.route("/approve_request/<int:req_id>", methods=["POST"])
def approve_request(req_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    cursor = db.cursor(buffered=True)

    try:
        # 1. GET REQUEST
        cursor.execute("""
            SELECT file_id, user_id
            FROM access_requests
            WHERE id=%s AND status='pending'
        """, (req_id,))
        req = cursor.fetchone()

        if not req:
            return jsonify({"error": "Request not found"}), 404

        file_id, requester_id = req

        # 2. VERIFY OWNER
        cursor.execute("""
            SELECT owner_id
            FROM files
            WHERE id=%s
        """, (file_id,))
        file = cursor.fetchone()

        if not file:
            return jsonify({"error": "File not found"}), 404

        owner_id = file[0]

        if owner_id != session["user_id"]:
            return jsonify({"error": "Unauthorized"}), 403

        # 3. GET OWNER AES KEY
        cursor.execute("""
            SELECT encrypted_aes_key
            FROM file_keys
            WHERE file_id=%s AND user_id=%s
        """, (file_id, owner_id))

        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Owner key missing"}), 500

        owner_encrypted_key = row[0].strip()

        # 4. GET REQUESTER PUBLIC KEY
        cursor.execute("""
            SELECT public_key
            FROM users
            WHERE id=%s
        """, (requester_id,))

        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Requester not found"}), 404

        requester_public_key = row[0]

        return jsonify({
            "success": True,
            "encrypted_aes_key": owner_encrypted_key,
            "public_key": requester_public_key,
            "file_id": file_id,
            "requester_id": requester_id,
            "req_id": req_id
        })

    except Exception as e:
        print("APPROVE ERROR:", e)
        return jsonify({"error": "Approve failed"}), 500

    finally:
        cursor.close()


# ---------------- SAVE RE-ENCRYPTED AES KEY ----------------
@app.route("/save_reaccess/<int:req_id>", methods=["POST"])
def save_reaccess(req_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()

    encrypted_key = data.get("encrypted_key")

    cursor = db.cursor(buffered=True)

    try:
        # ==========================================================
        # GET REQUEST DETAILS
        # ==========================================================
        cursor.execute("""
            SELECT file_id, user_id
            FROM access_requests
            WHERE id=%s
        """, (req_id,))

        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Invalid request"}), 404

        file_id, requester_id = row

        # ==========================================================
        # SAVE NEW AES KEY (RE-ENCRYPTED)
        # ==========================================================
        cursor.execute("""
            INSERT INTO file_keys (file_id, user_id, encrypted_aes_key)
            VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE encrypted_aes_key=%s
        """, (file_id, requester_id, encrypted_key, encrypted_key))

        # ==========================================================
        # GIVE 24 HOUR ACCESS
        # ==========================================================
        new_expiry = datetime.now() + timedelta(hours=24)

        cursor.execute("""
            INSERT INTO file_access (file_id, user_id, expiry_time)
            VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE expiry_time=%s
        """, (file_id, requester_id, new_expiry, new_expiry))

        # ==========================================================
        # UPDATE REQUEST STATUS
        # ==========================================================
        cursor.execute("""
            UPDATE access_requests
            SET status='approved'
            WHERE id=%s
        """, (req_id,))


        # ✅ LOG ACCESS REQUEST
        cursor.execute(
            "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
            (requester_id, file_id, "access_approved")
        )

        # ==========================================================
        # NOTIFICATION
        # ==========================================================
        cursor.execute("""
            DELETE FROM notifications
            WHERE user_id=%s AND file_id=%s
        """, (requester_id, file_id))

        cursor.execute("""
            INSERT INTO notifications (user_id, file_id, type, message)
            VALUES (%s,%s,'approved','Owner granted access')
        """, (requester_id, file_id))

        db.commit()

        return jsonify({"success": True})

    except Exception as e:
        db.rollback()
        print("SAVE REACCESS ERROR:", e)
        return jsonify({"error": "Save failed"}), 500

    finally:
        cursor.close()

# ---------------- REJECT ACCESS REQUEST ----------------

@app.route("/reject_request/<int:req_id>", methods=["POST"])
def reject_request(req_id):

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    cursor = db.cursor(buffered=True)
    reject_start = time.perf_counter()

    cursor.execute("""
        SELECT file_id, user_id 
        FROM access_requests 
        WHERE id=%s
    """, (req_id,))
    
    row = cursor.fetchone()

    if not row:
        cursor.close()
        return jsonify({"error": "Request not found"})

    file_id, requester_id = row

    # ❌ DO NOT DELETE file_access
    # ❌ DO NOT DELETE expiry

    # 🔥 ONLY REMOVE AES KEY → disables download
    cursor.execute("""
        DELETE FROM file_keys 
        WHERE file_id=%s AND user_id=%s
    """, (file_id, requester_id))

    # ✅ update request
    cursor.execute("""
        UPDATE access_requests 
        SET status='rejected' 
        WHERE id=%s
    """, (req_id,))

    # ✅ notifications
    cursor.execute("""
        DELETE FROM notifications 
        WHERE user_id=%s AND file_id=%s
    """, (requester_id, file_id))

    cursor.execute("""
        INSERT INTO notifications (user_id, file_id, type, message)
        VALUES (%s, %s, 'rejected', 'Owner denied access')
    """, (requester_id, file_id))

    # ✅ LOG ACCESS REJECTED
    cursor.execute(
        "INSERT INTO logs (user_id, file_id, action) VALUES (%s,%s,%s)",
        (requester_id, file_id, "access_rejected")
    )


    db.commit()

    elapsed_ms = (time.perf_counter() - reject_start) * 1000
    log_metric(
        metric_name="reject_request",
        duration_ms=elapsed_ms,
        user_id=session["user_id"],
        file_id=file_id,
        mode="encrypted",
        status="success"
    )

    cursor.close()

    return jsonify({"success": True})
    

# ---------------- VIEW NOTIFICATIONS ----------------
@app.route("/notifications")
def notifications_page():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    file_id = request.args.get("file_id")

    cursor = db.cursor(buffered=True)

    if file_id:
        cursor.execute("""
            SELECT n.message, n.type, f.original_filename, n.created_at, n.file_id
            FROM notifications n
            JOIN files f ON n.file_id = f.id
            WHERE n.user_id=%s AND n.file_id=%s
            ORDER BY n.id DESC
        """, (user_id, file_id))

        # ✅ FIX: fetch before next query
        notifications = cursor.fetchall()

    else:
        cursor.execute("""
            SELECT n.message, n.type, f.original_filename, n.created_at, n.file_id
            FROM notifications n
            JOIN files f ON n.file_id = f.id
            WHERE n.user_id=%s
            ORDER BY n.id DESC
        """, (user_id,))

        notifications = cursor.fetchall()

        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE user_id=%s
        """, (user_id,))

    db.commit()
    cursor.close()

    return render_template("notifications.html", notifications=notifications)

# ---------------- VIEW FILE LOGS ----------------
@app.route("/file_logs/<int:file_id>")
def file_logs(file_id):

    if "user_id" not in session:
        return redirect("/login")

    cursor = db.cursor(buffered=True)

    # ==========================================================
    # ✅ 1. VERIFY OWNER
    # ==========================================================
    cursor.execute("""
        SELECT owner_id, original_filename
        FROM files
        WHERE id=%s
    """, (file_id,))

    file = cursor.fetchone()

    if not file:
        cursor.close()
        flash("File not found", "error")
        return redirect("/files")

    owner_id, filename = file

    if owner_id != session["user_id"]:
        cursor.close()
        flash("Unauthorized access", "error")
        return redirect("/files")

    # ==========================================================
    # ✅ 2. GET ONLY SHARED USER LOGS (PRIVACY-AWARE)
    # ==========================================================
    cursor.execute("""
        SELECT u.username, l.action, l.timestamp
        FROM logs l
        JOIN users u ON l.user_id = u.id
        WHERE l.file_id=%s
        AND l.user_id != %s   -- 🔥 EXCLUDE OWNER LOGS
        ORDER BY l.timestamp DESC
    """, (file_id, owner_id))

    logs = cursor.fetchall()

    cursor.close()

    # ==========================================================
    # ✅ 3. RENDER PAGE
    # ==========================================================
    return render_template(
        "file_logs.html",
        logs=logs,
        filename=filename
    )

if __name__ == "__main__":
    app.run(debug=True)