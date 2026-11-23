from flask import (
    Flask, Response, jsonify, render_template, request,
    redirect, url_for, session, flash
)

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from functools import lru_cache, wraps
from datetime import datetime, timedelta
import json
import os
import random
import smtplib
import urllib.error
import urllib.request
import csv
import io
from email.mime.text import MIMEText

load_dotenv()

app = Flask(__name__)

init_db()

app.secret_key = os.environ.get(
    "SECRET_KEY", "change-this-secret-before-deployment"
)
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower()
    in {"1", "true", "yes", "y"}
)

OTP_EXPIRY_MINUTES = 10


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, otp):
    smtp_server = os.environ.get("MAIL_SERVER") or os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    smtp_port = int(os.environ.get("MAIL_PORT") or os.environ.get("SMTP_PORT") or 587)
    smtp_username = os.environ.get("MAIL_USERNAME") or os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("MAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes", "y"}
    sender_name = os.environ.get("MAIL_FROM_NAME", "InterviewMate AI")
    sender_email = os.environ.get("MAIL_FROM") or smtp_username

    if not smtp_username or not smtp_password:
        app.logger.error("OTP email is not configured; cannot send password reset email.")
        return False

    message = MIMEText(
        f"Your InterviewMate AI password reset OTP is: {otp}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.",
        "plain",
        "utf-8"
    )
    message["Subject"] = "InterviewMate AI Password Reset OTP"
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(sender_email, email, message.as_string())
        server.quit()
        return True
    except Exception as exc:
        print(f"[OTP ERROR] Could not send email: {exc}")
        return False


@lru_cache(maxsize=90)
def synthesize_question_audio(question):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    payload = json.dumps({
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "input": question,
        "instructions": (
            "Speak clearly and naturally as a friendly professional interviewer "
            "asking a candidate this interview question."
        ),
        "response_format": "mp3"
    }).encode("utf-8")
    api_request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(api_request, timeout=30) as response:
        return response.read()


QUESTIONS = {
    "Python Developer": {
        "Beginner": [
            "What are some key features of Python?",
            "How are lists and tuples different, and when would you use each?",
            "What is the difference between a mutable and an immutable object?",
            "How do you handle exceptions in Python?",
            "What is a Python dictionary, and how do you look up a value?",
            "What is the purpose of a virtual environment?",
            "How does a for loop differ from a while loop?",
            "What is the difference between a module and a package?",
            "How would you read a file safely in Python?",
            "How would you sort a list of dictionaries by one of their values?"
        ],
        "Intermediate": [
            "What are decorators, and where have you used one?",
            "Explain generators and how they differ from returning a list.",
            "How does Python manage memory and garbage collection?",
            "What is the difference between threading and multiprocessing in Python?",
            "How do context managers work, and how would you create one?",
            "What are *args and **kwargs used for?",
            "How would you write and test a reusable API client?",
            "What is the Global Interpreter Lock, and when does it matter?",
            "How do you structure a medium-sized Python application?",
            "How would you design a cache with expiration and invalidation?"
        ],
        "Advanced": [
            "How would you profile and optimize a Python service with high latency?",
            "Describe a robust strategy for managing concurrent tasks in Python.",
            "How would you design a plugin architecture using Python?",
            "What trade-offs would you consider when choosing between async I/O and threads?",
            "How do Python descriptors and the method resolution order work?",
            "How would you make a data-processing pipeline memory efficient?",
            "How do you design backward-compatible Python library APIs?",
            "What are common causes of memory leaks in long-running Python processes?",
            "How would you investigate and resolve contention in a high-throughput service?",
            "How would you ensure a Python service shuts down gracefully while cleaning up resources?"
        ]
    },
    "Web Developer": {
        "Beginner": [
            "What is semantic HTML, and why is it useful?",
            "How do the CSS box model and box-sizing property work?",
            "What is the difference between a class and an ID in CSS?",
            "What happens when a browser loads a web page?",
            "What is the difference between GET and POST requests?",
            "How do you make a web page responsive?",
            "What is the purpose of HTML forms and their labels?",
            "How do CSS Flexbox and Grid help with layouts?",
            "What is an API, and how does a web page use one?",
            "How do alt text and descriptive link labels help people use a website?"
        ],
        "Intermediate": [
            "How do you manage client-side state in a complex web application?",
            "What is the difference between authentication and authorization?",
            "How would you improve the performance of a slow-loading page?",
            "How do promises and async/await help manage asynchronous JavaScript?",
            "What are common causes of cross-browser layout differences?",
            "How would you design and validate a REST API endpoint?",
            "How do you make interactive components accessible?",
            "What is the purpose of content security policy headers?",
            "How do you test a web interface across different screen sizes?",
            "How would you reduce unnecessary re-renders in a component-based interface?"
        ],
        "Advanced": [
            "How would you diagnose a production web performance regression?",
            "How would you design a frontend architecture for a large team?",
            "What trade-offs do server-side rendering and client-side rendering introduce?",
            "How would you plan a safe migration from a legacy frontend?",
            "How do caching strategies affect consistency and freshness in web applications?",
            "How would you prevent a slow third-party script from blocking the user experience?",
            "How would you design resilient frontend behavior for unreliable networks?",
            "What metrics would you use to assess real-user web performance?",
            "How would you approach accessibility in a large existing product?",
            "How would you safely roll out a major frontend change to users?"
        ]
    },
    "Java Developer": {
        "Beginner": [
            "What is the difference between the JDK, JRE, and JVM?",
            "How do classes and objects relate in Java?",
            "What is inheritance, and when is it useful?",
            "How do primitive types differ from reference types?",
            "What is the difference between an interface and a class?",
            "How do you handle exceptions in Java?",
            "What are the main access modifiers in Java?",
            "How does an ArrayList differ from an array?",
            "What is method overloading?",
            "How do String, StringBuilder, and StringBuffer differ?"
        ],
        "Intermediate": [
            "How do equals() and hashCode() work together?",
            "When would you use a Java Stream instead of a loop?",
            "How does the Java garbage collector affect application performance?",
            "What is dependency injection, and what problem does it solve?",
            "How do checked and unchecked exceptions differ?",
            "How would you make a Java class immutable?",
            "What are the benefits and risks of using CompletableFuture?",
            "How do HashMap and ConcurrentHashMap differ?",
            "How do you organize tests for a Spring service?",
            "When is Optional useful, and when should you avoid using it?"
        ],
        "Advanced": [
            "How would you investigate long garbage-collection pauses in production?",
            "How would you design a high-throughput Java service?",
            "What trade-offs do different JVM garbage collectors offer?",
            "How do Java memory-model guarantees affect concurrent code?",
            "How would you evolve a Java API without breaking existing clients?",
            "How would you diagnose thread-pool saturation in a production service?",
            "What design considerations matter when building a distributed Java system?",
            "How would you reduce allocation pressure in a latency-sensitive application?",
            "How would you structure observability for a large Java platform?",
            "How would you plan a safe Java runtime upgrade across multiple services?"
        ]
    }
}

DIFFICULTIES = ("Beginner", "Intermediate", "Advanced")
QUESTIONS_PER_INTERVIEW = 5


ROLE_KEYWORDS = {
    "Python Developer": (
        "python", "function", "class", "list", "tuple", "dictionary", "api",
        "test", "exception", "async", "thread", "process", "memory", "data",
    ),
    "Web Developer": (
        "html", "css", "javascript", "browser", "api", "state", "component",
        "responsive", "accessibility", "test", "performance", "cache",
    ),
    "Java Developer": (
        "java", "class", "object", "interface", "thread", "spring", "stream",
        "exception", "garbage", "jvm", "memory", "test", "api",
    ),
}


def evaluate_answer(answer, role):
    words = answer.split()
    word_count = len(words)
    normalized = answer.lower()
    sentences = [
        part.strip()
        for part in normalized.replace("!", ".").replace("?", ".").split(".")
        if part.strip()
    ]

    if word_count >= 55:
        completeness = 100
    elif word_count >= 40:
        completeness = 90
    elif word_count >= 25:
        completeness = 75
    elif word_count >= 12:
        completeness = 55
    else:
        completeness = 35

    average_sentence_length = word_count / max(len(sentences), 1)
    if 8 <= average_sentence_length <= 28:
        clarity = 90
    elif 5 <= average_sentence_length <= 35:
        clarity = 75
    else:
        clarity = 55

    keywords = ROLE_KEYWORDS.get(role, ())
    relevance_matches = sum(
        1 for keyword in keywords
        if keyword in normalized
    )
    if relevance_matches >= 4:
        relevance = 100
    elif relevance_matches >= 2:
        relevance = 80
    elif relevance_matches == 1:
        relevance = 65
    else:
        relevance = 45

    example_markers = (
        "for example", "for instance", "in my", "when i", "i used",
        "we used", "in a project", "this resulted", "as a result",
    )
    if any(marker in normalized for marker in example_markers):
        evidence = 100
    elif word_count >= 35:
        evidence = 70
    else:
        evidence = 45

    structure_markers = (
        "first", "then", "next", "finally", "because", "so that",
        "however", "trade-off", "approach", "result",
    )
    structure_hits = sum(
        1 for marker in structure_markers
        if marker in normalized
    )
    structure = min(100, 50 + (structure_hits * 10))

    dimensions = {
        "Completeness": completeness,
        "Clarity": clarity,
        "Relevance": relevance,
        "Evidence": evidence,
        "Structure": structure,
    }
    score = round(
        (completeness * 0.30)
        + (clarity * 0.20)
        + (relevance * 0.20)
        + (evidence * 0.15)
        + (structure * 0.15)
    )

    strengths = [
        name for name, value in dimensions.items()
        if value >= 80
    ]
    weak_dimensions = [
        name for name, value in dimensions.items()
        if value < 70
    ]

    suggestions = []
    if "Completeness" in weak_dimensions:
        suggestions.append("Add more detail about the reasoning, trade-offs, and expected outcome.")
    if "Clarity" in weak_dimensions:
        suggestions.append("Use shorter sentences and explain one idea at a time.")
    if "Relevance" in weak_dimensions:
        suggestions.append("Connect the answer directly to {} concepts and terminology.".format(role))
    if "Evidence" in weak_dimensions:
        suggestions.append("Include a concrete project example or describe how you verified the result.")
    if "Structure" in weak_dimensions:
        suggestions.append("Organize the response with a brief approach, key steps, and conclusion.")

    if score >= 85:
        summary = "Strong, well-rounded answer."
    elif score >= 70:
        summary = "Good foundation with clear room to sharpen the response."
    elif score >= 55:
        summary = "Partially developed answer; expand and organize the explanation."
    else:
        summary = "Early-stage answer; add detail, role-specific terms, and a concrete example."

    feedback = summary
    if strengths:
        feedback += " Strengths: {}.".format(", ".join(strengths[:2]))
    if suggestions:
        feedback += " Improve: {}".format(" ".join(suggestions[:2]))

    return score, feedback, dimensions, strengths, weak_dimensions, suggestions


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 8:
            flash("Enter your details and a password of at least 8 characters.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        connection = get_db()

        try:
            connection.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            connection.commit()
            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))

        except Exception:
            flash("This email may already be registered.")

        finally:
            connection.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        connection.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.")
            return redirect(url_for("forgot_password"))

        connection = get_db()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            flash("No account found with that email address.")
            connection.close()
            return redirect(url_for("forgot_password"))

        otp = generate_otp()
        expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

        connection.execute(
            "DELETE FROM password_reset_requests WHERE user_id = ?",
            (user["id"],)
        )
        connection.execute(
            "INSERT INTO password_reset_requests (user_id, otp, expires_at) VALUES (?, ?, ?)",
            (user["id"], otp, expires_at)
        )
        connection.commit()
        connection.close()

        if send_otp_email(email, otp):
            session["reset_email"] = email
            flash("An OTP has been sent to your email address.")
            return redirect(url_for("verify_otp"))

        flash("OTP could not be sent because email is not configured. Please contact support.")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        otp = request.form.get("otp", "").strip()

        if not email or not otp:
            flash("Please provide both email and OTP.")
            return redirect(url_for("verify_otp"))

        connection = get_db()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            flash("No account found with that email address.")
            connection.close()
            return redirect(url_for("verify_otp"))

        reset_request = connection.execute(
            """
            SELECT * FROM password_reset_requests
            WHERE user_id = ? AND otp = ? AND used = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (user["id"], otp)
        ).fetchone()

        if not reset_request:
            flash("Invalid or expired OTP.")
            connection.close()
            return redirect(url_for("verify_otp"))

        expires_at = datetime.strptime(reset_request["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            flash("Your OTP has expired. Please request a new one.")
            connection.close()
            return redirect(url_for("forgot_password"))

        connection.execute(
            "UPDATE password_reset_requests SET used = 1 WHERE id = ?",
            (reset_request["id"],)
        )
        connection.commit()
        connection.close()

        session["password_reset_user_id"] = user["id"]
        session["reset_email"] = email
        flash("OTP verified successfully.")
        return redirect(url_for("reset_password"))

    return render_template("verify_otp.html", email=session.get("reset_email"))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("password_reset_user_id")
    if not user_id:
        flash("Please verify your OTP first.")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.")
            return redirect(url_for("reset_password"))

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("reset_password"))

        hashed_password = generate_password_hash(password)
        connection = get_db()
        connection.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hashed_password, user_id)
        )
        connection.execute(
            "DELETE FROM password_reset_requests WHERE user_id = ?",
            (user_id,)
        )
        connection.commit()
        connection.close()

        session.pop("password_reset_user_id", None)
        session.pop("reset_email", None)
        flash("Password reset successfully. Please log in.")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/dashboard")
@login_required
def dashboard():
    connection = get_db()

    history = connection.execute(
        """SELECT * FROM interviews
           WHERE user_id = ?
           ORDER BY id DESC LIMIT 5""",
        (session["user_id"],)
    ).fetchall()

    stats = connection.execute(
        """SELECT
               COUNT(*) AS answer_count,
               ROUND(AVG(score), 1) AS average_score,
               MAX(score) AS best_score
           FROM interviews
           WHERE user_id = ?""",
        (session["user_id"],)
    ).fetchone()

    weekly = connection.execute(
        """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS answers,
                  ROUND(AVG(score), 1) AS score
           FROM interviews
           WHERE user_id = ? AND created_at >= datetime('now', '-7 days')
           GROUP BY substr(created_at, 1, 10)
           ORDER BY day""",
        (session["user_id"],)
    ).fetchall()

    role_counts = connection.execute(
        """SELECT role, COUNT(*) AS count, ROUND(AVG(score), 1) AS avg_score
           FROM interviews WHERE user_id = ?
           GROUP BY role ORDER BY count DESC LIMIT 3""",
        (session["user_id"],)
    ).fetchall()

    practice_days = connection.execute(
        """SELECT DISTINCT substr(created_at, 1, 10) AS day
           FROM interviews WHERE user_id = ?
           ORDER BY day DESC""",
        (session["user_id"],)
    ).fetchall()
    preferences = connection.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()

    connection.close()

    answer_count = stats["answer_count"] or 0
    average_score = stats["average_score"] or 0
    practice_hours = round(answer_count * 3 / 60, 1)
    interview_count = max(1, (answer_count + 4) // 5) if answer_count else 0
    xp = answer_count * 20 + int((average_score or 0) * 2)
    streak = 0
    streak_cursor = datetime.now().date()
    active_days = {row["day"] for row in practice_days}
    while streak_cursor.strftime("%Y-%m-%d") in active_days:
        streak += 1
        streak_cursor -= timedelta(days=1)
    weekly_labels = [row["day"][-5:] for row in weekly]
    weekly_values = [row["score"] or 0 for row in weekly]

    return render_template(
        "dashboard.html",
        name=session["name"],
        roles=QUESTIONS.keys(),
        difficulties=DIFFICULTIES,
        history=history,
        stats=stats,
        interview_count=interview_count,
        practice_hours=practice_hours,
        streak=streak,
        xp=xp,
        level=(xp // 500) + 1,
        weekly_labels=json.dumps(weekly_labels),
        weekly_values=json.dumps(weekly_values),
        role_counts=role_counts,
        preferences=preferences
    )


@app.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    if request.method == "POST":
        role = request.form.get("role")
        difficulty = request.form.get("difficulty")
        answer_time = request.form.get("answer_time", "120")

        if role not in QUESTIONS:
            flash("Please select a valid job role.")
            return redirect(url_for("dashboard"))

        if difficulty not in DIFFICULTIES:
            flash("Please select a valid difficulty level.")
            return redirect(url_for("dashboard"))

        try:
            answer_time = int(answer_time)
        except (TypeError, ValueError):
            answer_time = 120
        if answer_time not in (60, 90, 120, 180, 300):
            answer_time = 120

        connection = get_db()
        completed_questions = {
            row["question"] for row in connection.execute(
                """SELECT question FROM interviews
                   WHERE user_id = ? AND role = ? AND difficulty = ?""",
                (session["user_id"], role, difficulty)
            ).fetchall()
        }
        connection.close()

        question_pool = QUESTIONS[role][difficulty]
        unseen_questions = [
            question for question in question_pool
            if question not in completed_questions
        ]
        question_count = min(QUESTIONS_PER_INTERVIEW, len(question_pool))
        if len(unseen_questions) >= question_count:
            interview_questions = random.sample(unseen_questions, question_count)
        else:
            previously_seen = [
                question for question in question_pool
                if question in completed_questions
            ]
            interview_questions = unseen_questions + random.sample(
                previously_seen, question_count - len(unseen_questions)
            )
            random.shuffle(interview_questions)

        session["role"] = role
        session["difficulty"] = difficulty
        session["interview_questions"] = interview_questions
        session["question_index"] = 0
        session["answers"] = []
        session["answer_time"] = answer_time
        session["started_at"] = datetime.now().isoformat()

        return redirect(url_for("interview"))

    role = session.get("role")
    difficulty = session.get("difficulty")
    questions = session.get("interview_questions", [])

    if role not in QUESTIONS or difficulty not in DIFFICULTIES or not questions:
        return redirect(url_for("dashboard"))

    index = session.get("question_index", 0)

    if index >= len(questions):
        return redirect(url_for("result"))

    return render_template(
        "interview.html",
        role=role,
        difficulty=difficulty,
        question=questions[index],
        number=index + 1,
        total=len(questions),
        progress=round(index / len(questions) * 100),
        answer_time=session.get("answer_time", 120),
        voice_enabled=bool(os.environ.get("OPENAI_API_KEY"))
    )


@app.route("/api/question-audio", methods=["POST"])
def question_audio():
    if "user_id" not in session:
        return jsonify(error="Please log in to hear interview questions."), 401

    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify(error="Invalid request."), 400

    if not os.environ.get("OPENAI_API_KEY"):
        return jsonify(error="Voice is not configured. Add OPENAI_API_KEY to the server environment."), 503

    role = session.get("role")
    difficulty = session.get("difficulty")
    questions = session.get("interview_questions", [])
    index = session.get("question_index", 0)
    if (
        role not in QUESTIONS or difficulty not in DIFFICULTIES
        or not isinstance(index, int) or index < 0
        or index >= len(questions)
    ):
        return jsonify(error="There is no active interview question to read."), 409

    question = questions[index]
    if question not in QUESTIONS[role][difficulty]:
        return jsonify(error="The current interview question is invalid."), 409

    try:
        audio = synthesize_question_audio(question)
    except urllib.error.HTTPError as error:
        app.logger.error("OpenAI text-to-speech returned HTTP %s.", error.code)
        error.close()
        return jsonify(error="Voice generation failed. Please try again later."), 502
    except (urllib.error.URLError, TimeoutError) as error:
        app.logger.error("Could not reach OpenAI text-to-speech: %s", error)
        return jsonify(error="Voice service could not be reached. Please try again."), 502

    return Response(
        audio,
        mimetype="audio/mpeg",
        headers={"Cache-Control": "private, no-store"}
    )


@app.route("/submit-answer", methods=["POST"])
@login_required
def submit_answer():
    role = session.get("role")
    difficulty = session.get("difficulty")
    index = session.get("question_index", 0)
    questions = session.get("interview_questions", [])

    if (
        role not in QUESTIONS or difficulty not in DIFFICULTIES
        or not questions or index >= len(questions)
    ):
        return redirect(url_for("dashboard"))

    answer = request.form.get("answer", "").strip()

    if not answer:
        flash("Please enter your answer.")
        return redirect(url_for("interview"))

    session["answers"] = session.get("answers", []) + [answer]
    session["question_index"] = index + 1

    return redirect(url_for("interview"))


@app.route("/result")
@login_required
def result():
    role = session.get("role")
    difficulty = session.get("difficulty")
    answers = session.get("answers", [])
    questions = session.get("interview_questions", [])

    if (
        role not in QUESTIONS or difficulty not in DIFFICULTIES
        or not questions or len(answers) != len(questions)
    ):
        return redirect(url_for("dashboard"))

    scores = []
    feedback_list = []
    dimension_scores = []
    strength_lists = []
    suggestion_lists = []

    for answer in answers:
        score, feedback, dimensions, strengths, weak_dimensions, suggestions = evaluate_answer(
            answer, role
        )
        scores.append(score)
        feedback_list.append(feedback)
        dimension_scores.append(dimensions)
        strength_lists.append(strengths)
        suggestion_lists.append(suggestions)

    overall_score = round(sum(scores) / len(scores))

    connection = get_db()

    for question, answer, score, feedback in zip(
        questions, answers, scores, feedback_list
    ):
        connection.execute(
            """INSERT INTO interviews
               (user_id, role, difficulty, question, answer, score, feedback)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session["user_id"], role, difficulty, question,
                answer, score, feedback
            )
        )

    connection.commit()
    connection.close()

    session.pop("role", None)
    session.pop("difficulty", None)
    session.pop("interview_questions", None)
    session.pop("question_index", None)
    session.pop("answers", None)

    return render_template(
        "result.html",
        score=overall_score,
        role=role,
        difficulty=difficulty,
        feedback_list=feedback_list,
        answers=answers,
        questions=questions,
        scores=scores,
        dimension_scores=dimension_scores,
        strength_lists=strength_lists,
        suggestion_lists=suggestion_lists
    )


QUESTION_LIBRARY = [
    {"question": "Tell me about yourself.", "category": "HR", "difficulty": "Beginner", "answer": "Use a concise 60-second summary: present role, relevant strengths, and a goal connected to the position."},
    {"question": "Describe a situation where you resolved a disagreement.", "category": "Behavioral", "difficulty": "Intermediate", "answer": "Apply STAR: describe the situation, your responsibility, the constructive action, and the measurable or observable result."},
    {"question": "Explain the time complexity of binary search.", "category": "Algorithms", "difficulty": "Beginner", "answer": "Binary search halves the remaining sorted search space each iteration, giving O(log n) time and O(1) iterative space."},
    {"question": "What is the difference between a process and a thread?", "category": "Java", "difficulty": "Intermediate", "answer": "Processes have separate address spaces; threads within a process share memory and resources. Threads require careful synchronization."},
    {"question": "How would you optimize a slow SQL query?", "category": "SQL", "difficulty": "Intermediate", "answer": "Inspect the execution plan, validate indexes, reduce unnecessary columns and scans, improve predicates, and measure before and after."},
    {"question": "Explain the bias-variance tradeoff.", "category": "AI & Machine Learning", "difficulty": "Advanced", "answer": "Bias is error from oversimplified assumptions; variance is sensitivity to training data. Tune model flexibility and validation strategy to balance them."},
]


@app.route("/history")
@login_required
def history_page():
    connection = get_db()
    history = connection.execute(
        "SELECT * FROM interviews WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    connection.close()
    return render_template("workspace.html", name=session["name"], active="history",
                           title="Interview History", subtitle="Review sessions and track your progress",
                           history=history)


@app.route("/history/export")
@login_required
def export_history():
    connection = get_db()
    history = connection.execute(
        """SELECT role, difficulty, question, answer, score, feedback, created_at
           FROM interviews WHERE user_id = ? ORDER BY id DESC""",
        (session["user_id"],)
    ).fetchall()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Role", "Difficulty", "Question", "Answer", "Score", "Feedback", "Date"])
    for item in history:
        writer.writerow([
            item["role"], item["difficulty"], item["question"], item["answer"],
            item["score"], item["feedback"], item["created_at"],
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=interviewmate-history.csv"},
    )


@app.route("/studio")
@login_required
def studio():
    return render_template("workspace.html", name=session["name"], active="studio",
                           title="AI Mock Interview Studio",
                           subtitle="Configure a focused, role-specific interview",
                           roles=list(QUESTIONS.keys()), difficulties=DIFFICULTIES)


@app.route("/resume-lab", methods=["GET", "POST"])
@login_required
def resume_lab():
    analysis = None
    if request.method == "POST":
        resume_text = request.form.get("resume_text", "").strip()
        if len(resume_text) < 30:
            flash("Paste at least a short resume summary or add detailed resume text.")
        else:
            text = resume_text.lower()
            skills = [s for s in ("Python", "Java", "JavaScript", "SQL", "React", "Spring", "AWS", "Docker", "Git", "Machine Learning")
                      if s.lower() in text]
            analysis = {
                "skills": skills or ["Add specific technical skills"],
                "strength": "The resume identifies work or study experience that can be expanded with measurable outcomes.",
                "missing": ["Quantified achievements", "Relevant tools and technologies", "Concise project impact"],
                "questions": [
                    "Describe the most technically challenging project in this resume.",
                    "What measurable impact did your work create?",
                    "Which tool or technology in your resume would you improve first?",
                ],
            }
    return render_template("workspace.html", name=session["name"], active="resume",
                           title="Resume Lab", subtitle="Turn your resume into an interview preparation plan",
                           analysis=analysis)


@app.route("/job-analyzer", methods=["GET", "POST"])
@login_required
def job_analyzer():
    analysis = None
    if request.method == "POST":
        job_text = request.form.get("job_text", "").strip()
        resume_text = request.form.get("resume_text", "").strip()
        if len(job_text) < 30:
            flash("Paste a more detailed job description.")
        else:
            skill_catalog = ("Python", "Java", "JavaScript", "SQL", "React", "Spring", "AWS", "Docker", "Git", "Machine Learning")
            required = [skill for skill in skill_catalog if skill.lower() in job_text.lower()]
            resume_skills = [skill for skill in skill_catalog if resume_text and skill.lower() in resume_text.lower()]
            gaps = [skill for skill in required if skill not in resume_skills]
            shared = [skill for skill in required if skill in resume_skills]
            compatibility = round((len(shared) / len(required) * 100) if required else 0)
            analysis = {
                "required": required or ["Add technical requirements from the job description"],
                "gaps": gaps,
                "shared": shared,
                "compatibility": compatibility,
                "roadmap": ["Prioritize the largest skill gaps", "Practice two role-specific scenarios", "Prepare evidence-based resume examples"],
                "questions": [
                    "How would you use {} in this role?".format(required[0] if required else "the required technologies"),
                    "Tell me about a project that demonstrates your strongest relevant skill.",
                    "How would you close the gaps in this job description?",
                ],
            }
    return render_template("workspace.html", name=session["name"], active="jobs",
                           title="Job Description Analyzer", subtitle="Find skill gaps and prepare a focused roadmap",
                           analysis=analysis)


@app.route("/coding")
@login_required
def coding_arena():
    problems = [
        {"title": "Two Sum", "difficulty": "Easy", "topic": "Arrays", "language": "Python",
         "prompt": "Given nums and target, return indices of two values that add to target.",
         "starter": "def two_sum(nums, target):\n    # Write your solution here\n    return []",
         "solution_hint": "Use a dictionary to remember each value and its index."},
        {"title": "Valid Parentheses", "difficulty": "Easy", "topic": "Stacks", "language": "Python",
         "prompt": "Return True when every opening bracket is closed by the matching bracket.",
         "starter": "def is_valid_parentheses(text):\n    # Write your solution here\n    return False",
         "solution_hint": "Push opening brackets onto a stack and validate each closing bracket."},
        {"title": "Longest Unique Substring", "difficulty": "Medium", "topic": "Strings", "language": "Python",
         "prompt": "Return the length of the longest substring without repeating characters.",
         "starter": "def length_of_longest_unique(text):\n    # Write your solution here\n    return 0",
         "solution_hint": "Maintain a sliding window and the last position of each character."},
        {"title": "Fibonacci Number", "difficulty": "Medium", "topic": "Dynamic Programming", "language": "Python",
         "prompt": "Return the nth Fibonacci number using an efficient iterative algorithm.",
         "starter": "def fibonacci(n):\n    # Write your solution here\n    return 0",
         "solution_hint": "Keep only the previous two values while iterating from zero to n."},
    ]
    result = None
    selected = problems[0]
    if request.method == "POST":
        title = request.form.get("problem", "")
        selected = next((item for item in problems if item["title"] == title), selected)
        if request.form.get("select_problem"):
            return render_template("workspace.html", name=session["name"], active="coding",
                                   title="Coding Interview Arena",
                                   subtitle="Practice problems without executing code on the app server",
                                   problems=problems, selected=selected, coding_result=None)
        code = request.form.get("code", "").strip()
        explanation = request.form.get("explanation", "").strip()
        if len(code) < 20:
            flash("Add more of your Python solution before submitting.")
        elif "return" not in code:
            flash("Your solution should include a return value.")
        else:
            score = 60
            if len(code) >= 120:
                score += 15
            if "for " in code or "while " in code:
                score += 10
            if "dict" in code or "{" in code or "set(" in code:
                score += 10
            if len(explanation.split()) >= 15:
                score += 5
            result = {
                "score": min(score, 100),
                "feedback": "Good implementation attempt. Verify edge cases and explain your time/space complexity.",
                "hint": selected["solution_hint"],
            }
    return render_template("workspace.html", name=session["name"], active="coding",
                           title="Coding Interview Arena", subtitle="Practice problems without executing code on the app server",
                           problems=problems, selected=selected, coding_result=result)


@app.route("/questions")
@login_required
def question_library():
    query = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    items = QUESTION_LIBRARY
    if query:
        items = [i for i in items if query in i["question"].lower() or query in i["category"].lower()]
    if category:
        items = [i for i in items if i["category"] == category]
    if difficulty:
        items = [i for i in items if i["difficulty"] == difficulty]
    categories = sorted(set(i["category"] for i in QUESTION_LIBRARY))
    connection = get_db()
    saved = {
        row["question"] for row in connection.execute(
            "SELECT question FROM saved_questions WHERE user_id = ?",
            (session["user_id"],)
        ).fetchall()
    }
    connection.close()
    return render_template("workspace.html", name=session["name"], active="questions",
                           title="Question Library", subtitle="Search, filter, and practice interview questions",
                           questions=items, categories=categories, saved_questions=saved)


@app.route("/questions/save", methods=["POST"])
@login_required
def save_question():
    question = request.form.get("question", "").strip()
    category = request.form.get("category", "").strip()
    difficulty = request.form.get("difficulty", "").strip()
    if not question:
        return jsonify(error="Question is required."), 400
    connection = get_db()
    existing = connection.execute(
        "SELECT id FROM saved_questions WHERE user_id = ? AND question = ?",
        (session["user_id"], question)
    ).fetchone()
    if existing:
        connection.execute("DELETE FROM saved_questions WHERE id = ?", (existing["id"],))
        saved = False
    else:
        connection.execute(
            "INSERT INTO saved_questions (user_id, question, category, difficulty) VALUES (?, ?, ?, ?)",
            (session["user_id"], question, category, difficulty)
        )
        saved = True
    connection.commit()
    connection.close()
    return jsonify(saved=saved)


@app.route("/answer-studio", methods=["GET", "POST"])
@login_required
def answer_studio():
    result = None
    if request.method == "POST":
        answer = request.form.get("answer", "").strip()
        if len(answer) < 20:
            flash("Enter at least a few sentences to improve.")
        else:
            lowered = answer.lower()
            score = 50
            score += 15 if len(answer.split()) >= 40 else 5
            score += 10 if any(x in lowered for x in ("because", "for example", "for instance")) else 0
            score += 10 if any(x in lowered for x in ("result", "outcome", "completed")) else 0
            result = {
                "score": min(score, 100),
                "missing": ["A specific measurable result", "A concise explanation of your role"] if "result" not in lowered else ["One more concrete trade-off or lesson"],
                "sample": "SITUATION: Describe the context briefly. TASK: State your responsibility. ACTION: Explain the specific steps you took and why. RESULT: Share an honest, measurable outcome and lesson.",
            }
    return render_template("workspace.html", name=session["name"], active="answer",
                           title="Answer Improvement Studio", subtitle="Get practical, transparent feedback on your response",
                           result=result)


@app.route("/roadmap")
@login_required
def roadmap():
    tasks = [
        {"title": "Core concepts review", "detail": "Revisit 3 fundamentals in your target role", "done": False},
        {"title": "Timed practice", "detail": "Complete one 5-question mock interview", "done": False},
        {"title": "Answer practice", "detail": "Improve one behavioral answer with STAR", "done": False},
    ]
    return render_template("workspace.html", name=session["name"], active="roadmap",
                           title="Career Preparation Roadmap", subtitle="A realistic weekly plan built around consistent practice",
                           tasks=tasks)


@app.route("/challenge", methods=["GET", "POST"])
@login_required
def challenge():
    question = QUESTION_LIBRARY[(datetime.now().timetuple().tm_yday - 1) % len(QUESTION_LIBRARY)]
    result = None
    if request.method == "POST":
        answer = request.form.get("answer", "").strip()
        if len(answer.split()) < 12:
            flash("Write at least a few detailed sentences before submitting.")
        else:
            score, feedback, dimensions, strengths, weak_dimensions, suggestions = evaluate_answer(
                answer, "Web Developer"
            )
            connection = get_db()
            connection.execute(
                """INSERT INTO interviews
                   (user_id, role, difficulty, question, answer, score, feedback)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session["user_id"], "Daily Challenge", question["difficulty"],
                 question["question"], answer, score, feedback)
            )
            connection.commit()
            connection.close()
            result = {
                "score": score,
                "feedback": feedback,
                "strengths": strengths,
                "suggestions": suggestions,
            }
    return render_template("workspace.html", name=session["name"], active="challenge",
                           title="Daily Interview Challenge", subtitle="Today's focused practice",
                           challenge=question, challenge_result=result)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    connection = get_db()
    preferences = connection.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?", (session["user_id"],)
    ).fetchone()
    if request.method == "POST":
        target_role = request.form.get("target_role", "").strip()
        difficulty = request.form.get("difficulty", "Intermediate")
        theme = request.form.get("theme", "dark")
        connection.execute(
            """INSERT INTO user_preferences (user_id, target_role, difficulty, theme)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               target_role=excluded.target_role, difficulty=excluded.difficulty, theme=excluded.theme""",
            (session["user_id"], target_role, difficulty, theme)
        )
        connection.commit()
        flash("Your preferences have been saved.")
        preferences = connection.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?", (session["user_id"],)
        ).fetchone()
    connection.close()
    return render_template("workspace.html", name=session["name"], active="settings",
                           title="Settings", subtitle="Personalize your InterviewMate experience",
                           preferences=preferences, difficulties=DIFFICULTIES)


if __name__ == "__main__":
    init_db()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )