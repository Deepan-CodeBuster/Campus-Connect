from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
from supabase import create_client, Client
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cloudinary config (from .env)
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

# Admin credentials
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Check if admin
        if username == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["username"] = username
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))

        # Otherwise check normal user (Supabase)
        try:
            user = supabase.auth.sign_in_with_password({"email": username, "password": password})
            if user and user.user:
                session["username"] = username
                session["user_id"] = user.user.id
                session["is_admin"] = False
                return redirect(url_for("profile"))
            else:
                return render_template("login.html", error="Invalid credentials")
        except Exception as e:
            return render_template("login.html", error=str(e))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            user = supabase.auth.sign_up({"email": username, "password": password})
            if user and user.user:
                session["username"] = username
                session["user_id"] = user.user.id
                session["is_admin"] = False
                return redirect(url_for("profile"))
            else:
                return render_template("register.html", error="Registration failed")
        except Exception as e:
            return render_template("register.html", error=str(e))
    return render_template("register.html")

@app.route("/profile")
@login_required
def profile():
    # fetch all posts created by this user
    posts = supabase.table("posts").select("*").eq("user_id", session["user_id"]).order("created_at", desc=True).execute()
    return render_template("profile.html", username=session["username"], posts=posts.data)


@app.route("/admin-dashboard")
@admin_required
def admin_dashboard():
    # Fetch all users (Admin API)
    users = []
    try:
        users_response = supabase.auth.admin.list_users()
        users = users_response.users if users_response else []
    except Exception as e:
        print("Error fetching users:", e)

    # Fetch all posts
    posts = supabase.table("posts").select("*").order("created_at", desc=True).execute()

    return render_template("admin.html", username=session["username"], users=users, posts=posts.data)


@app.route("/admin/delete-user/<user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    try:
        supabase.auth.admin.delete_user(user_id)
        return redirect(url_for("admin_dashboard"))
    except Exception as e:
        return f"Error deleting user: {str(e)}"


@app.route("/admin/delete-post/<int:post_id>", methods=["POST"])
@admin_required
def delete_post(post_id):
    supabase.table("posts").delete().eq("id", post_id).execute()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_post(post_id):
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        crowd = request.form["crowd"]
        chips = request.form["chips"]
        queue_time = request.form["queue"]

        update_data = {
            "title": title,
            "description": description,
            "crowd": crowd,
            "chips": chips,
            "queue_time": queue_time
        }

        supabase.table("posts").update(update_data).eq("id", post_id).execute()
        return redirect(url_for("admin_dashboard"))

    post = supabase.table("posts").select("*").eq("id", post_id).single().execute()
    return render_template("admin_editpost.html", post=post.data)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/profile/post", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        crowd = request.form["crowd"]
        chips = request.form["chips"]
        queue_time = request.form["queue"]

        # Upload image to Cloudinary
        image = request.files["image"]
        image_url = None
        if image:
            upload_result = cloudinary.uploader.upload(image)
            image_url = upload_result["secure_url"]

        # Insert post into Supabase
        supabase.table("posts").insert({
            "user_id": session["user_id"],
            "title": title,
            "description": description,
            "image_url": image_url,
            "crowd": crowd,
            "chips": chips,
            "queue_time": queue_time
        }).execute()

        return redirect(url_for("profile"))

    return render_template("post.html")

@app.route("/profile/editpost/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        crowd = request.form["crowd"]
        chips = request.form["chips"]
        queue_time = request.form["queue"]

        image = request.files.get("image")
        image_url = None
        if image and image.filename:
            upload_result = cloudinary.uploader.upload(image)
            image_url = upload_result["secure_url"]

        update_data = {
            "title": title,
            "description": description,
            "crowd": crowd,
            "chips": chips,
            "queue_time": queue_time
        }
        if image_url:
            update_data["image_url"] = image_url

        supabase.table("posts").update(update_data).eq("id", post_id).execute()

        return redirect(url_for("profile"))

    # Fetch post data
    post = supabase.table("posts").select("*").eq("id", post_id).single().execute()
    return render_template("editpost.html", post=post.data)

@app.route("/posts")
def view_posts():
    posts = supabase.table("posts").select("*").order("created_at", desc=True).execute().data

    post_ids = [p["id"] for p in posts]

    # Fetch comments for all posts
    comments = {}
    if post_ids:
        comments_query = (
            supabase.table("comments")
            .select("*")
            .in_("post_id", post_ids)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        for c in comments_query:
            comments.setdefault(c["post_id"], []).append(c)

    # ✅ Correct way to count likes
    likes = {}
    if post_ids:
        likes_query = (
            supabase.table("likes")
            .select("post_id, count:id")
            .in_("post_id", post_ids)
            .execute()
            .data
        )
        for l in likes_query:
            likes[l["post_id"]] = l["count"]

    return render_template("posts.html", posts=posts, comments=comments, likes=likes)


@app.route("/posts/<int:post_id>/like", methods=["POST"])
def like_post(post_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    # Try to insert like
    try:
        supabase.table("likes").insert({"post_id": post_id, "user_id": user_id}).execute()
    except Exception as e:
        # If already liked, ignore
        print("Like error:", e)
    return redirect(url_for("view_posts"))


@app.route("/posts/<int:post_id>/comment", methods=["POST"])
def comment_post(post_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    content = request.form["content"]
    supabase.table("comments").insert({"post_id": post_id, "user_id": user_id, "content": content}).execute()
    return redirect(url_for("view_posts"))


if __name__ == '__main__':
    app.run(debug=True)
