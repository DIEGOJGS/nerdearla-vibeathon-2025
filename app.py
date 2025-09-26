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

# ... (El modelo de la DB no cambia) ...
class TeacherStudentLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String(200), nullable=False)
    student_email = db.Column(db.String(200), nullable=False)

# ... (La configuración de Google no cambia) ...
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

@app.route('/')
def index():
    if 'credentials' not in session: return render_template('login.html')
    return redirect('/dashboard')

# --- RUTA DE LOGIN CORREGIDA ---
@app.route('/login')
def login():
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

# ... (Las rutas /callback y /logout no cambian) ...
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

    # --- BLOQUE DE SEGURIDAD A PRUEBA DE BALAS (NUEVO) ---
    try:
        creds = Credentials(**session['credentials'])
        # Verificamos explícitamente si falta el refresh_token
        if not creds.refresh_token:
            # Si falta, esta sesión es inválida. Forzamos un nuevo login.
            raise ValueError("Refresh token ausente en la sesión.")
    except Exception as e:
        # Si hay cualquier error al cargar las credenciales, limpiamos la sesión y re-autenticamos
        logging.error(f"Error en credenciales de sesión: {e}. Forzando logout.")
        return redirect('/logout')
    # --- FIN DEL BLOQUE DE SEGURIDAD ---
        
    user_info_service = build('oauth2', 'v2', credentials=creds)
    user_info = user_info_service.userinfo().get().execute()
    user_email = user_info.get('email')
    user_name = user_info.get('name')

    # ... (El resto de la lógica de roles (Coordinador, Profesor, Alumno) no cambia) ...
    # ...
    if user_email == COORDINATOR_EMAIL:
        # Lógica del Coordinador
        all_links = db.session.execute(db.select(TeacherStudentLink)).scalars().all()
        cells_data = {}
        student_emails_in_db = set(link.student_email for link in all_links)
        for link in all_links:
            teacher = link.teacher_email
            if teacher not in cells_data: cells_data[teacher] = 0
            cells_data[teacher] += 1
        course_tasks_data = {}
        classroom_service = build('classroom', 'v1', credentials=creds)
        courses = classroom_service.courses().list().execute().get('courses', [])
        if courses:
            for course in courses:
                course_name = course.get('name', 'Curso sin nombre')
                courseworks = classroom_service.courses().courseWork().list(courseId=course['id']).execute().get('courseWork', [])
                task_count = len(courseworks) if courseworks else 0
                course_tasks_data[course_name] = task_count
        return render_template('coordinator_dashboard.html', user_name=user_name, cells_data=cells_data, course_tasks_data=course_tasks_data)
    
    teacher_links = db.session.execute(db.select(TeacherStudentLink).filter_by(teacher_email=user_email)).scalars().all()
    if teacher_links:
        # Lógica del Profesor
        student_emails_to_find = {link.student_email for link in teacher_links}
        students_data_with_progress = []
        classroom_service = build('classroom', 'v1', credentials=creds)
        courses = classroom_service.courses().list().execute().get('courses', [])
        if courses:
            for course in courses:
                course_id = course['id']
                students_in_course = classroom_service.courses().students().list(courseId=course_id).execute().get('students', [])
                if not students_in_course: continue
                for student_summary in students_in_course:
                    user_id = student_summary.get('userId')
                    full_profile = classroom_service.userProfiles().get(userId=user_id).execute()
                    student_email_from_profile = full_profile.get('emailAddress')
                    if student_email_from_profile in student_emails_to_find:
                        student_info = {'profile': full_profile, 'submissions': []}
                        courseworks = classroom_service.courses().courseWork().list(courseId=course_id).execute().get('courseWork', [])
                        if courseworks:
                            for coursework in courseworks:
                                submissions = classroom_service.courses().courseWork().studentSubmissions().list(courseId=course_id, courseWorkId=coursework['id'], userId=user_id).execute().get('studentSubmissions', [])
                                submission_status = "Asignado"
                                if submissions:
                                    state = submissions[0].get('state')
                                    if state == 'TURNED_IN': submission_status = 'Entregado'
                                    elif state == 'RETURNED': submission_status = 'Calificado'
                                student_info['submissions'].append({'title': coursework.get('title', 'Tarea sin título'), 'status': submission_status})
                        
                        student_name = student_info['profile']['name']['givenName']
                        subject = f"Seguimiento de tu progreso - Semillero Digital"
                        body = f"Hola {student_name},\n\nSoy {user_name}, tu profesor en Semillero Digital.\n\nMe pongo en contacto contigo para conversar sobre tu progreso en el curso. ¿Hay algo en lo que te pueda ayudar?\n\n¡Espero tu respuesta!\n\nSaludos,"
                        subject_encoded = quote(subject)
                        body_encoded = quote(body)
                        gmail_link = f"https://mail.google.com/mail/?view=cm&fs=1&to={student_email_from_profile}&su={subject_encoded}&body={body_encoded}"
                        student_info['gmail_link'] = gmail_link

                        students_data_with_progress.append(student_info)
        
        teacher_turned_in = 0
        teacher_total_tasks = 0
        for student in students_data_with_progress:
            teacher_total_tasks += len(student['submissions'])
            for sub in student['submissions']:
                if sub['status'] in ['Entregado', 'Calificado']:
                    teacher_turned_in += 1
        
        teacher_progress_data = { "entregadas": teacher_turned_in, "asignadas": teacher_total_tasks - teacher_turned_in }
        
        return render_template('teacher_dashboard.html', user_name=user_name, students_data=students_data_with_progress, progress_data=teacher_progress_data)
    else:
        # Lógica del Alumno
        classroom_service = build('classroom', 'v1', credentials=creds)
        results = classroom_service.courses().list().execute()
        courses = results.get('courses', [])
        return render_template('student_dashboard.html', user_name=user_name, courses=courses)

# ... (La ruta /manage-students no cambia) ...
@app.route('/manage-students', methods=['GET', 'POST'])
def manage_students():
    if 'credentials' not in session: return redirect('/login')
    creds = Credentials(**session['credentials'])
    user_info_service = build('oauth2', 'v2', credentials=creds)
    user_info = user_info_service.userinfo().get().execute()
    teacher_email = user_info.get('email')
    if request.method == 'POST':
        TeacherStudentLink.query.filter_by(teacher_email=teacher_email).delete()
        emails_text = request.form.get('student_emails', '')
        email_list = [email.strip() for email in emails_text.splitlines() if email.strip()]
        for student_email in email_list:
            new_link = TeacherStudentLink(teacher_email=teacher_email, student_email=student_email)
            db.session.add(new_link)
        db.session.commit()
        return redirect('/dashboard')
    current_links = TeacherStudentLink.query.filter_by(teacher_email=teacher_email).all()
    current_emails_text = "\n".join([link.student_email for link in current_links])
    return render_template('manage_students.html', current_emails=current_emails_text)


if __name__ == '__main__':
    app.run(debug=True)