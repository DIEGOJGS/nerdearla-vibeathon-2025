print("--- CARGADO app.py v.FINAL-DIAGNÓSTICO ---")

import os
from flask import Flask, redirect, request, session, render_template
from flask_sqlalchemy import SQLAlchemy
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = 'clave-secreta-para-hackaton'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:final123@127.0.0.1/hackaton?client_encoding=utf8'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class TeacherStudentLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String(200), nullable=False)
    student_email = db.Column(db.String(200), nullable=False)

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
CLIENT_SECRETS_FILE = 'client_secret.json'
REDIRECT_URI = 'http://127.0.0.1:5000/callback'

# UBICACIÓN: En tu archivo app.py, reemplaza la lista SCOPES completa

SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.students.readonly',
    'https://www.googleapis.com/auth/classroom.student-submissions.students.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/classroom.profile.emails' # <-- ¡AÑADE ESTE PERMISO FINAL!
]

flow = Flow.from_client_secrets_file(
    client_secrets_file=CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

@app.route('/')
def index():
    if 'credentials' not in session:
        return '<a href="/login">Login con Google</a>'
    return redirect('/dashboard')

@app.route('/login')
def login():
    authorization_url, state = flow.authorization_url()
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
    logging.info("\n--- EJECUTANDO FUNCIÓN DASHBOARD ---")
    if 'credentials' not in session:
        logging.warning("No hay credenciales en la sesión, redirigiendo a login.")
        return redirect('/login')

    creds = Credentials(**session['credentials'])
    
    user_info_service = build('oauth2', 'v2', credentials=creds)
    user_info = user_info_service.userinfo().get().execute()
    user_email = user_info.get('email')
    user_name = user_info.get('name')
    logging.info(f"Paso 1: Usuario logueado es '{user_name}' ({user_email})")
    
    links = db.session.execute(db.select(TeacherStudentLink).filter_by(teacher_email=user_email)).scalars().all()
    is_teacher = True if links else False
    logging.info(f"Paso 2: ¿Es profesor? -> {is_teacher}")

    students_data_with_progress = []
    if is_teacher:
        student_emails_to_find = {link.student_email for link in links}
        logging.info(f"Paso 3: Alumnos a buscar en nuestra DB -> {student_emails_to_find}")
        
        try:
            classroom_service = build('classroom', 'v1', credentials=creds)
            courses = classroom_service.courses().list().execute().get('courses', [])
            logging.info(f"Paso 4: Cursos encontrados en API -> {[c.get('name') for c in courses]}")

            if courses:
                for course in courses:
                    course_id = course.get('id')
                    logging.info(f"---> Procesando curso '{course.get('name')}' (ID: {course_id})")
                    students_in_course = classroom_service.courses().students().list(courseId=course_id).execute().get('students', [])
                    
                    if not students_in_course:
                        logging.warning(f"     -> El curso no tiene alumnos según la API.")
                        continue

                    for student_summary in students_in_course:
                        user_id = student_summary.get('userId')
                        logging.info(f"     -> Inspeccionando alumno con ID de API: {user_id}")
                        
                        full_profile = classroom_service.userProfiles().get(userId=user_id).execute()
                        student_email_from_profile = full_profile.get('emailAddress')
                        logging.info(f"     -> Obtenido perfil completo. Email: {student_email_from_profile}")

                        if student_email_from_profile in student_emails_to_find:
                            logging.info(f"     =======> ¡COINCIDENCIA ENCONTRADA!: {student_email_from_profile}")
                            students_data_with_progress.append({'profile': full_profile, 'submissions': []}) # Simplificado para prueba
                        else:
                            logging.info(f"     -> No es un alumno asignado.")
        except Exception as e:
            logging.error(f"!!!!!!!!!! OCURRIÓ UN ERROR EN LA API DE GOOGLE: {e}")
    
    logging.info(f"Paso Final: Renderizando plantilla con {len(students_data_with_progress)} alumnos.")
    return render_template('dashboard.html', user_name=user_name, students_data=students_data_with_progress, is_teacher=is_teacher)

if __name__ == '__main__':
    app.run(debug=True)