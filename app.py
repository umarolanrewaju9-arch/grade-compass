import csv
from io import TextIOWrapper
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pdfkit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'professional-secure-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cgpa_upgraded.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ======================
# MODELS
# ======================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    matric_no = db.Column(db.String(50), default='')
    level = db.Column(db.String(20), default='100L')

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    unit = db.Column(db.Integer, nullable=False)
    grade = db.Column(db.String(2), nullable=False)
    semester = db.Column(db.String(50), default='Semester 1')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    @property
    def points(self):
        grade_map = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1, 'F': 0}
        return self.unit * grade_map.get(self.grade.upper(), 0)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ======================
# ROUTES
# ======================

@app.route('/')
def home():
    return redirect(url_for('dashboard')) if current_user.is_authenticated else redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        matric_no = request.form.get('matric_no', '').strip()
        level = request.form.get('level', '100L')
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            matric_no=matric_no,
            level=level
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Login below.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            try:
                file = request.files['file']
                csv_file = TextIOWrapper(file, encoding='utf-8')
                reader = csv.DictReader(csv_file)
                for row in reader:
                    db.session.add(Course(
                        code=row['code'].upper(), unit=int(row['unit']),
                        grade=row['grade'].upper(), semester=row.get('semester', 'Semester 1'),
                        user_id=current_user.id
                    ))
                db.session.commit()
                flash('Bulk upload successful!', 'success')
            except:
                flash('CSV Error. Required columns: code, unit, grade', 'danger')
        else:
            code = request.form.get('code')
            unit = request.form.get('unit')
            grade = request.form.get('grade')
            sem = request.form.get('semester')
            if code and unit and grade:
                db.session.add(Course(
                    code=code.upper(), unit=int(unit),
                    grade=grade, semester=sem,
                    user_id=current_user.id
                ))
                db.session.commit()
                flash(f'Added {code.upper()}!', 'success')

    courses = Course.query.filter_by(user_id=current_user.id).all()
    semesters = {}
    t_pts, t_units = 0, 0
    for c in courses:
        if c.semester not in semesters:
            semesters[c.semester] = {'courses': [], 'pts': 0, 'units': 0}
        semesters[c.semester]['courses'].append(c)
        semesters[c.semester]['pts'] += c.points
        semesters[c.semester]['units'] += c.unit
        t_pts += c.points
        t_units += c.unit

    cgpa = round(t_pts / t_units, 2) if t_units > 0 else 0.00
    return render_template('dashboard.html', semesters=semesters, cgpa=cgpa)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    course = Course.query.get_or_404(id)
    if course.user_id == current_user.id:
        db.session.delete(course)
        db.session.commit()
        flash('Course removed.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_profile':
            current_user.matric_no = request.form.get('matric_no', '').strip()
            current_user.level = request.form.get('level', '100L')
            db.session.commit()
            flash('Profile updated!', 'success')

        elif action == 'change_password':
            old_pw = request.form.get('old_password')
            new_pw = request.form.get('new_password')
            confirm_pw = request.form.get('confirm_password')
            if not check_password_hash(current_user.password, old_pw):
                flash('Current password is incorrect.', 'danger')
            elif new_pw != confirm_pw:
                flash('New passwords do not match.', 'danger')
            elif len(new_pw) < 6:
                flash('Password must be at least 6 characters.', 'danger')
            else:
                current_user.password = generate_password_hash(new_pw)
                db.session.commit()
                flash('Password changed successfully!', 'success')

    return render_template('profile.html')

@app.route('/transcript')
@login_required
def transcript():
    courses = Course.query.filter_by(user_id=current_user.id).all()
    semesters = {}
    t_pts, t_units = 0, 0
    for c in courses:
        if c.semester not in semesters:
            semesters[c.semester] = {'courses': [], 'pts': 0, 'units': 0}
        semesters[c.semester]['courses'].append(c)
        semesters[c.semester]['pts'] += c.points
        semesters[c.semester]['units'] += c.unit
        t_pts += c.points
        t_units += c.unit
    cgpa = round(t_pts / t_units, 2) if t_units > 0 else 0.00
    now = datetime.now().strftime('%B %d, %Y %I:%M %p')
    return render_template('transcript.html', semesters=semesters, cgpa=cgpa, now=now)

@app.route('/download_pdf')
@login_required
def download_pdf():
    courses = Course.query.filter_by(user_id=current_user.id).all()
    semesters = {}
    t_pts, t_units = 0, 0
    for c in courses:
        if c.semester not in semesters:
            semesters[c.semester] = {'courses': [], 'pts': 0, 'units': 0}
        semesters[c.semester]['courses'].append(c)
        semesters[c.semester]['pts'] += c.points
        semesters[c.semester]['units'] += c.unit
        t_pts += c.points
        t_units += c.unit
    cgpa = round(t_pts / t_units, 2) if t_units > 0 else 0.00
    now = datetime.now().strftime('%B %d, %Y %I:%M %p')
    html = render_template('transcript.html', semesters=semesters, cgpa=cgpa, now=now)
    pdf = pdfkit.from_string(html, False)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=transcript_{current_user.username}.pdf'
    return response

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)