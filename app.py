import os
from flask import Flask, redirect, request, session, render_template
from flask_sqlalchemy import SQLAlchemy
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from urllib.parse import quote
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = 'clave-secreta-para-hackaton-final'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:final123@127.0.0.1/hackaton?client_encoding=utf8'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

COORDINATOR_EMAIL = 'pemartdro7@gmail.com'

class TeacherStudentLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String(200), nullable=False)
    student_email = db.Column(db.String(200), nullable=False)

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
CLIENT_SECRETS_FILE = 'client_secret.json'
REDIRECT_URI = 'http://127.0.0.1:5000/callback'
SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly','https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.students.readonly','https://www.googleapis.com/auth/classroom.student-submissions.students.readonly',
    'https://www.googleapis.com/auth/userinfo.email','https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/classroom.profile.emails'
]
flow = Flow.from_client_secrets_file(client_secrets_file=CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)

# --- MODO DEMO: DATOS FALSOS ---
DEMO_COORDINATOR_DATA = {
    "user_name": "Coordinador (Modo Demo)",
    "cells_data": { "profesor.uno@semillero.digital": 8, "profesor.dos@semillero.digital": 6 },
    "course_tasks_data": { "Curso de E-commerce": 12, "Curso de Data Analytics": 8 }
}
DEMO_TEACHER_DATA = {
    "user_name": "Profesor (Modo Demo)",
    "students_data": [
        {
            "profile": {"name": {"fullName": "Lucía Gómez"}, "emailAddress": "lucia.gomez@example.com"},
            "submissions": [{"title": "Tarea 1: Plan de Negocio", "status": "Entregado"}, {"title": "Tarea 2: Estudio de Mercado", "status": "Calificado"}],
            "gmail_link": "#"
        },
        {
            "profile": {"name": {"fullName": "Carlos Vidal"}, "emailAddress": "carlos.vidal@example.com"},
            "submissions": [{"title": "Tarea 1: Plan de Negocio", "status": "Entregado"}, {"title": "Tarea 2: Estudio de Mercado", "status": "Asignado"}],
            "gmail_link": "#"
        }
    ],
    "progress_data": {"entregadas": 3, "asignadas": 1}
}
DEMO_STUDENT_DATA = {
    "user_name": "Alumno (Modo Demo)",
    "courses": [{"name": "Curso de E-commerce"}, {"name": "Curso de Data Analytics"}]
}
# --- FIN MODO DEMO ---


@app.route('/')
def index():
    if 'credentials' not in session: return render_template('login.html')
    return redirect('/dashboard')

@app.route('/login')
def login():
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token, 'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
        'client_secret': credentials.client_secret, 'scopes': credentials.scopes
    }
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'credentials' not in session:
        return redirect('/login')

    try:
        creds = Credentials(**session['credentials'])
    except Exception as e:
        logging.error(f"Error en credenciales de sesión: {e}. Forzando logout.")
        return redirect('/logout')
        
    user_info_service = build('oauth2', 'v2', credentials=creds)
    user_info = user_info_service.userinfo().get().execute()
    user_email = user_info.get('email')
    user_name = user_info.get('name')

    if user_email == COORDINATOR_EMAIL:
        # Lógica del Coordinador real
        # ... (código que ya funciona)
        return render_template('coordinator_dashboard.html', user_name=user_name, cells_data=cells_data, course_tasks_data=course_tasks_data)
    
    teacher_links = db.session.execute(db.select(TeacherStudentLink).filter_by(teacher_email=user_email)).scalars().all()
    if teacher_links:
        # Lógica del Profesor real
        # ... (código que ya funciona)
        return render_template('teacher_dashboard.html', user_name=user_name, students_data=students_data_with_progress, progress_data=teacher_progress_data)
    else:
        # Lógica del Alumno real
        # ... (código que ya funciona)
        return render_template('student_dashboard.html', user_name=user_name, courses=courses)

# --- NUEVAS RUTAS PARA EL MODO DEMO ---
@app.route('/demo-coordinator')
def demo_coordinator():
    return render_template('coordinator_dashboard.html', **DEMO_COORDINATOR_DATA)

@app.route('/demo-teacher')
def demo_teacher():
    return render_template('teacher_dashboard.html', **DEMO_TEACHER_DATA)

@app.route('/demo-student')
def demo_student():
    return render_template('student_dashboard.html', **DEMO_STUDENT_DATA)

@app.route('/manage-students', methods=['GET', 'POST'])
def manage_students():
    # ... (tu código de manage_students no cambia) ...

if __name__ == '__main__':
    app.run(debug=True)