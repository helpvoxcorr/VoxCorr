from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import secrets


# ── Chargeur Flask-Login ───────────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Teacher, int(user_id))


# ─────────────────────────────────────────────────────────────────────────────
# TEACHER  (UserMixin apporte is_authenticated, is_active, get_id à Flask-Login)
# ─────────────────────────────────────────────────────────────────────────────
class Teacher(UserMixin, db.Model):
    __tablename__ = 'teachers'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name    = db.Column(db.String(80))
    last_name     = db.Column(db.String(80))
    school        = db.Column(db.String(200))
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Charte graphique personnalisée
    theme_primary   = db.Column(db.String(7),  default='#39FF14')
    theme_secondary = db.Column(db.String(7),  default='#0a0a0a')
    theme_bg        = db.Column(db.String(7),  default='#ffffff')

    classrooms = db.relationship('Classroom', back_populates='teacher',
                                 cascade='all, delete-orphan', lazy='select')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f'{self.first_name} {self.last_name}'
        return self.email


# ─────────────────────────────────────────────────────────────────────────────
# CLASSROOM  (ex : 3ème B · Mathématiques)
# ─────────────────────────────────────────────────────────────────────────────
class Classroom(db.Model):
    __tablename__ = 'classrooms'

    id          = db.Column(db.Integer, primary_key=True)
    teacher_id  = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    name        = db.Column(db.String(80),  nullable=False)   # ex: "3ème B"
    subject     = db.Column(db.String(100))                   # ex: "Mathématiques"
    school_year = db.Column(db.String(9),   default='2025-2026')
    created_at  = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))

    teacher     = db.relationship('Teacher',    back_populates='classrooms')
    students    = db.relationship('Student',    back_populates='classroom',
                                  cascade='all, delete-orphan', lazy='select')
    assignments = db.relationship('Assignment', back_populates='classroom',
                                  cascade='all, delete-orphan', lazy='select')


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT  (nom réel chiffré · alias RGPD)
# ─────────────────────────────────────────────────────────────────────────────
class Student(db.Model):
    __tablename__ = 'students'

    id                   = db.Column(db.Integer, primary_key=True)
    classroom_id         = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=False)
    alias                = db.Column(db.String(60),  nullable=False)   # ex: "Renard-07"
    student_number       = db.Column(db.Integer)                       # n° dans la classe
    encrypted_first_name = db.Column(db.Text)                          # Fernet chiffré
    encrypted_last_name  = db.Column(db.Text)
    created_at           = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    classroom   = db.relationship('Classroom',   back_populates='students')
    corrections = db.relationship('Correction',  back_populates='student',
                                  cascade='all, delete-orphan', lazy='select')


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGNMENT  (devoir)
# ─────────────────────────────────────────────────────────────────────────────
class Assignment(db.Model):
    __tablename__ = 'assignments'

    id           = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=False)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text)
    date         = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    total_points = db.Column(db.Float, default=20.0)
    class_appreciation = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    classroom   = db.relationship('Classroom',   back_populates='assignments')
    questions   = db.relationship('Question',    back_populates='assignment',
                                  cascade='all, delete-orphan',
                                  order_by='Question.order', lazy='select')
    corrections = db.relationship('Correction',  back_populates='assignment',
                                  cascade='all, delete-orphan', lazy='select')


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION  (une ligne du barème)
# ─────────────────────────────────────────────────────────────────────────────
class Question(db.Model):
    __tablename__ = 'questions'

    id            = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    label         = db.Column(db.String(200), nullable=False)   # ex: "Question 1a"
    max_points    = db.Column(db.Float,       nullable=False)
    competence    = db.Column(db.String(100))                   # ex: "Rédiger"
    order         = db.Column(db.Integer,     default=0)

    assignment = db.relationship('Assignment', back_populates='questions')
    scores     = db.relationship('QuestionScore', back_populates='question',
                                 cascade='all, delete-orphan', lazy='select')


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTION  (cœur du système)
# ─────────────────────────────────────────────────────────────────────────────
class Correction(db.Model):
    __tablename__ = 'corrections'

    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.Integer, db.ForeignKey('students.id'),    nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)

    # Token public unique → URL /c/<token>  (sans compte élève)
    public_token  = db.Column(db.String(16), unique=True, nullable=False, index=True,
                              default=lambda: secrets.token_urlsafe(8))

    raw_transcript   = db.Column(db.Text)    # dictée brute du prof
    structured_text  = db.Column(db.Text)    # synthèse Mistral pour l'élève
    audio_url        = db.Column(db.String(500))
    audio_duration   = db.Column(db.Float)   # secondes

    total_score      = db.Column(db.Float)

    # draft | processing | published
    status           = db.Column(db.String(20), default='draft', nullable=False)

    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    published_at     = db.Column(db.DateTime)

    student    = db.relationship('Student',    back_populates='corrections')
    assignment = db.relationship('Assignment', back_populates='corrections')
    scores     = db.relationship('QuestionScore', back_populates='correction',
                                 cascade='all, delete-orphan', lazy='select')
    access_logs = db.relationship('AccessLog', back_populates='correction',
                                  cascade='all, delete-orphan', lazy='select')

    def compute_total(self):
        self.total_score = sum(
            s.score for s in self.scores if s.score is not None
        )

    def publish(self):
        self.status       = 'published'
        self.published_at = datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION SCORE  (note par question pour une correction donnée)
# ─────────────────────────────────────────────────────────────────────────────
class QuestionScore(db.Model):
    __tablename__ = 'question_scores'

    id            = db.Column(db.Integer, primary_key=True)
    correction_id = db.Column(db.Integer, db.ForeignKey('corrections.id'),  nullable=False)
    question_id   = db.Column(db.Integer, db.ForeignKey('questions.id'),    nullable=False)
    score         = db.Column(db.Float)

    correction = db.relationship('Correction', back_populates='scores')
    question   = db.relationship('Question',   back_populates='scores')


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS LOG  (dashboard "qui a consulté quand")
# ─────────────────────────────────────────────────────────────────────────────
class AccessLog(db.Model):
    __tablename__ = 'access_logs'

    id            = db.Column(db.Integer, primary_key=True)
    correction_id = db.Column(db.Integer, db.ForeignKey('corrections.id'), nullable=False)
    accessed_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ip_hash       = db.Column(db.String(64))    # SHA-256 de l'IP — jamais l'IP brute
    user_agent    = db.Column(db.String(255))

    correction = db.relationship('Correction', back_populates='access_logs')
