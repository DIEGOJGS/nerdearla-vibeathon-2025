print("--- CARGADO app.py v.ROLES ---")

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

# Para nuestro MVP, definimos al coordinador con su email.
# Usaremos tu cuenta de profesor como si fuera el coordinador para la prueba.
COORDINATOR_EMAIL = 'dgcodex2025@gmail.com'

class TeacherStudentLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String(200), nullable=False)
    student_email = db.Column(db.String(200), nullable=False)

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
CLIENT_SECRETS_FILE = 'client_secret.json'
REDIRECT_URI = 'http://127.0.0.1:5000/callback'

SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.students.readonly',
    'https://www.googleapis.com/auth/classroom.student-submissions.students.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/classroom.profile.emails'
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
    if 'credentials' not in session:
        return redirect('/login')

    creds = Credentials(**session['credentials'])
    user_info_service = build('oauth2', 'v2', credentials=creds)
    user_info = user_info_service.userinfo().get().execute()
    user_email = user_info.get('email')
    user_name = user_info.get('name')

    # --- LÓGICA DE ROLES ---

    # 1. ¿El usuario es el COORDINADOR?
    if user_email == COORDINATOR_EMAIL:
        logging.info(f"Usuario '{user_email}' identificado como COORDINADOR.")
        all_links = db.session.execute(db.select(TeacherStudentLink)).scalars().all()
        cells_data = {}
        for link in all_links:
            teacher = link.teacher_email
            if teacher not in cells_data:
                cells_data[teacher] = 0
            cells_data[teacher] += 1
        
        return render_template('coordinator_dashboard.html', user_name=user_name, cells_data=cells_data)

    # 2. Si no, ¿es un PROFESOR?
    teacher_links = db.session.execute(db.select(TeacherStudentLink).filter_by(teacher_email=user_email)).scalars().all()
    if teacher_links:
        logging.info(f"Usuario '{user_email}' identificado como PROFESOR.")
        # (Aquí está la lógica del dashboard del profesor que ya funcionaba)
        student_emails_to_find = {link.student_email for link in teacher_links}
        students_data_with_progress = []
        
        classroom_service = build('classroom', 'v1', credentials=creds)
        courses = classroom_service.courses().list().execute().get('courses', [])

        if courses:
            for course in courses:
                course_id = course['id']
                students_in_course = classroom_service.courses().students().list(courseId=course_id).execute().get('students', [])
                
                if not students_in_course:
                    continue

                for student_summary in students_in_course:
                    user_id = student_summary.get('userId')
                    full_profile = classroom_service.userProfiles().get(userId=user_id).execute()
                    student_email_from_profile = full_profile.get('emailAddress')

                    if student_email_from_profile in student_emails_to_find:
                        student_info = {'profile': full_profile, 'submissions': []}
                        
                        courseworks = classroom_service.courses().courseWork().list(courseId=course_id).execute().get('courseWork', [])
                        if courseworks:
                            for coursework in courseworks:
                                submissions = classroom_service.courses().courseWork().studentSubmissions().list(
                                    courseId=course_id,
                                    courseWorkId=coursework['id'],
                                    userId=user_id
                                ).execute().get('studentSubmissions', [])
                                
                                submission_status = "Asignado"
                                if submissions:
                                    state = submissions[0].get('state')
                                    if state == 'TURNED_IN':
                                        submission_status = 'Entregado'
                                    elif state == 'RETURNED':
                                        submission_status = 'Calificado'
                                
                                student_info['submissions'].append({
                                    'title': coursework.get('title', 'Tarea sin título'),
                                    'status': submission_status
                                })
                        
                        students_data_with_progress.append(student_info)
        
        return render_template('teacher_dashboard.html', user_name=user_name, students_data=students_data_with_progress)

    # 3. Si no es ninguno de los anteriores, es un ALUMNO
    else:
        logging.info(f"Usuario '{user_email}' identificado como ALUMNO.")
        return render_template('student_dashboard.html', user_name=user_name)

if __name__ == '__main__':
    app.run(debug=True)