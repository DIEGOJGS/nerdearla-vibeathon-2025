import os
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

from flask import Flask, redirect, request, session, render_template
from flask_sqlalchemy import SQLAlchemy
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)
app.secret_key = 'tu-clave-super-secreta-cambiar-esto'

# UBICACIÓN: Dentro de tu archivo app.py
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:final123@127.0.0.1/hackaton?client_encoding=utf8'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class TeacherStudentLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String(200), nullable=False)
    student_email = db.Column(db.String(200), nullable=False)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
CLIENT_SECRETS_FILE = 'client_secret.json'
REDIRECT_URI = 'http://127.0.0.1:5000/callback'
# UBICACIÓN: En tu archivo app.py, reemplaza esta lista


SCOPES = [
    'https://www.googleapis.com/auth/classroom.coursework.students.readonly', # ESTE ES EL PERMISO CORRECTO
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.me.readonly',
    'https://www.googleapis.com/auth/classroom.student-submissions.me.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
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
    return redirect('/dashboard') # Redirige al dashboard si ya está logueado

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
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return redirect('/dashboard')

# --- NUEVA RUTA PRINCIPAL: EL DASHBOARD ---
# UBICACIÓN: En tu archivo app.py, reemplaza SOLO esta función

# UBICACIÓN: En tu archivo app.py, reemplaza SOLO esta función

# UBICACIÓN: En tu archivo app.py, reemplaza SOLO esta función

@app.route('/dashboard')
def dashboard():
    if 'credentials' not in session:
        return redirect('/login')

    creds = Credentials(**session['credentials'])
    
    user_info_service = build('oauth2', 'v2', credentials=creds)
    user_info = user_info_service.userinfo().get().execute()
    
    user_email = user_info.get('email')
    user_name = user_info.get('name')
    is_teacher = False

    links = db.session.execute(db.select(TeacherStudentLink).filter_by(teacher_email=user_email)).scalars().all()
    
    students_with_progress = []
    if links:
        is_teacher = True
        student_emails_to_find = {link.student_email for link in links} # Usamos un set para búsquedas más rápidas
        
        classroom_service = build('classroom', 'v1', credentials=creds)
        
        # Quitamos pageSize=1 para obtener TODOS los cursos
        courses = classroom_service.courses().list().execute().get('courses', [])
        
        # Diccionario para no duplicar alumnos si están en varios cursos
        found_students_data = {}

        if courses:
            for course in courses:
                course_id = course['id']
                
                # Obtenemos la lista de todos los alumnos en el curso
                students_in_course = classroom_service.courses().students().list(courseId=course_id).execute().get('students', [])
                
                if not students_in_course:
                    continue # Si el curso no tiene alumnos, pasamos al siguiente

                for student_profile in students_in_course:
                    # Verificamos si el alumno está en nuestra lista de "célula"
                    if 'profile' in student_profile and 'emailAddress' in student_profile['profile']:
                        student_email = student_profile['profile']['emailAddress']

                        if student_email in student_emails_to_find:
                            # Si no hemos procesado a este alumno, lo hacemos ahora
                            if student_email not in found_students_data:
                                found_students_data[student_email] = {
                                    'profile': student_profile['profile'],
                                    'submissions': []
                                }

                            # Obtenemos todas las tareas de este curso
                            courseworks = classroom_service.courses().courseWork().students().list(courseId=course_id).execute().get('courseWork', [])
                            if courseworks:
                                for coursework in courseworks:
                                    submissions = classroom_service.courses().courseWork().studentSubmissions().list(
                                        courseId=course_id,
                                        courseWorkId=coursework['id'],
                                        userId=student_profile['userId']
                                    ).execute().get('studentSubmissions', [])
                                    
                                    submission_status = "Asignado / Faltante" # Estado por defecto
                                    if submissions:
                                        state = submissions[0].get('state')
                                        if state == 'TURNED_IN':
                                            submission_status = 'Entregado'
                                        elif state == 'RETURNED':
                                            submission_status = 'Calificado'

                                    found_students_data[student_email]['submissions'].append({
                                        'courseName': course.get('name', 'Curso sin nombre'),
                                        'title': coursework.get('title', 'Tarea sin título'),
                                        'status': submission_status
                                    })
        
        students_with_progress = list(found_students_data.values())

    return render_template('dashboard.html', user_name=user_name, students_data=students_with_progress, is_teacher=is_teacher)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)