import os
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'A2d@5!kL9$qW7#pZ*eR8&gY6'

# File upload configuration
UPLOAD_FOLDER = 'static/uploads/resumes'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '123venkatesh',  # Add your MySQL password here
    'database': 'job_portal11'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get featured jobs (latest 5)
    cursor.execute("SELECT * FROM jobs ORDER BY post_date DESC LIMIT 5")
    featured_jobs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('index.html', featured_jobs=featured_jobs)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'employer':
                return redirect(url_for('employer_dashboard'))
            else:
                return redirect(url_for('job_seeker_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        role = request.form['role']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO users (name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s)",
                (name, email, phone, password, role)
            )
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Email already exists!', 'danger')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/jobs')
def all_jobs():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get filter parameters from query string
    min_salary = request.args.get('min_salary', type=float)
    max_salary = request.args.get('max_salary', type=float)
    location = request.args.get('location', '').strip()
    keywords = request.args.get('keywords', '').strip()
    
    # Base query
    query = "SELECT * FROM jobs"
    conditions = []
    params = []
    
    # Build filter conditions
    if min_salary is not None:
        conditions.append("salary >= %s")
        params.append(min_salary)
    if max_salary is not None:
        conditions.append("salary <= %s")
        params.append(max_salary)
    if location:
        conditions.append("location LIKE %s")
        params.append(f"%{location}%")
    if keywords:
        conditions.append("(title LIKE %s OR description LIKE %s)")
        params.extend([f"%{keywords}%", f"%{keywords}%"])
    
    # Combine conditions
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Order by post_date
    query += " ORDER BY post_date DESC"
    
    # Execute query
    cursor.execute(query, params)
    jobs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # Pass filter values back to template to persist in form
    return render_template('jobs.html', jobs=jobs, filters={
        'min_salary': min_salary or '',
        'max_salary': max_salary or '',
        'location': location,
        'keywords': keywords
    })

@app.route('/post_job', methods=['GET', 'POST'])
def post_job():
    if 'user_id' not in session or session['role'] != 'employer':
        flash('You need to be logged in as an employer to post jobs', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        company = request.form['company']
        location = request.form['location']
        salary = request.form['salary']
        description = request.form['description']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO jobs (title, company, location, salary, description, posted_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (title, company, location, salary, description, session['user_id'])
        )
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash('Job posted successfully!', 'success')
        return redirect(url_for('employer_dashboard'))
    
    return render_template('post_job.html')

@app.route('/apply/<int:job_id>', methods=['GET', 'POST'])
def apply_job(job_id):
    if 'user_id' not in session or session['role'] != 'job_seeker':
        flash('You need to be logged in as a job seeker to apply', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check if already applied
    cursor.execute("SELECT * FROM applications WHERE job_id = %s AND user_id = %s", (job_id, session['user_id']))
    existing_application = cursor.fetchone()
    
    if existing_application:
        cursor.close()
        conn.close()
        flash('You have already applied for this job', 'warning')
        return redirect(url_for('all_jobs'))
    
    # Get job details
    cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
    job = cursor.fetchone()
    
    if not job:
        cursor.close()
        conn.close()
        flash('Job not found', 'danger')
        return redirect(url_for('all_jobs'))
    
    if request.method == 'POST':
        cover_letter = request.form.get('cover_letter')
        years_experience = request.form.get('years_experience')
        skills = request.form.get('skills')
        resume = request.files.get('resume')
        
        # Validate form fields
        errors = []
        if not cover_letter or len(cover_letter.strip()) < 10:
            errors.append('Cover letter must be at least 10 characters.')
        if not years_experience or not years_experience.isdigit() or int(years_experience) < 0:
            errors.append('Years of experience must be a non-negative number.')
        if not skills or len(skills.strip()) < 3:
            errors.append('Skills must be at least 3 characters.')
        if not resume or not allowed_file(resume.filename):
            errors.append('A valid PDF resume is required.')
        
        if errors:
            cursor.close()
            conn.close()
            for error in errors:
                flash(error, 'danger')
            # Persist form data in template
            return render_template('apply.html', job=job, form_data={
                'cover_letter': cover_letter,
                'years_experience': years_experience,
                'skills': skills
            })
        
        # Save resume file
        filename = secure_filename(resume.filename)
        unique_filename = f"{session['user_id']}_{job_id}_{int(time.time())}_{filename}"
        resume_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        resume.save(resume_path)
        
        # Insert application into database
        cursor.execute(
            """INSERT INTO applications (job_id, user_id, cover_letter, years_experience, skills, resume_path)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (job_id, session['user_id'], cover_letter, int(years_experience), skills, resume_path)
        )
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash('Application submitted successfully!', 'success')
        return redirect(url_for('job_seeker_dashboard'))
    
    cursor.close()
    conn.close()
    
    return render_template('apply.html', job=job, form_data={})

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get stats
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()['total_users']
    
    cursor.execute("SELECT COUNT(*) as total_jobs FROM jobs")
    total_jobs = cursor.fetchone()['total_jobs']
    
    cursor.execute("SELECT COUNT(*) as total_applications FROM applications")
    total_applications = cursor.fetchone()['total_applications']
    
    # Get recent activities
    cursor.execute("SELECT * FROM jobs ORDER BY post_date DESC LIMIT 5")
    recent_jobs = cursor.fetchall()
    
    cursor.execute("""
        SELECT a.*, u.name as user_name, j.title as job_title 
        FROM applications a
        JOIN users u ON a.user_id = u.id
        JOIN jobs j ON a.job_id = j.id
        ORDER BY a.application_date DESC LIMIT 5
    """)
    recent_applications = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', 
                         role='admin',
                         total_users=total_users,
                         total_jobs=total_jobs,
                         total_applications=total_applications,
                         recent_jobs=recent_jobs,
                         recent_applications=recent_applications)

@app.route('/employer/dashboard')
def employer_dashboard():
    if 'user_id' not in session or session['role'] != 'employer':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get employer's jobs
    cursor.execute("SELECT * FROM jobs WHERE posted_by = %s ORDER BY post_date DESC", (session['user_id'],))
    jobs = cursor.fetchall()
    
    # Get applications for employer's jobs
    job_ids = [job['id'] for job in jobs]
    applications = []
    
    if job_ids:
        placeholders = ', '.join(['%s'] * len(job_ids))
        cursor.execute(f"""
            SELECT a.*, u.name as applicant_name, j.title as job_title 
            FROM applications a
            JOIN users u ON a.user_id = u.id
            JOIN jobs j ON a.job_id = j.id
            WHERE a.job_id IN ({placeholders})
            ORDER BY a.application_date DESC
        """, tuple(job_ids))
        applications = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', role='employer', jobs=jobs, applications=applications)

@app.route('/job_seeker/dashboard')
def job_seeker_dashboard():
    if 'user_id' not in session or session['role'] != 'job_seeker':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get user's applications
    cursor.execute("""
        SELECT a.*, j.title, j.company, j.location 
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.user_id = %s
        ORDER BY a.application_date DESC
    """, (session['user_id'],))
    applications = cursor.fetchall()
    
    # Get recommended jobs (simple implementation - just latest jobs)
    cursor.execute("SELECT * FROM jobs ORDER BY post_date DESC LIMIT 5")
    recommended_jobs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', role='job_seeker', applications=applications, recommended_jobs=recommended_jobs)

@app.route('/update_application_status/<int:app_id>/<status>')
def update_application_status(app_id, status):
    if 'user_id' not in session or session['role'] != 'employer':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify that the application is for a job posted by this employer
    cursor.execute("""
        UPDATE applications a
        JOIN jobs j ON a.job_id = j.id
        SET a.status = %s
        WHERE a.id = %s AND j.posted_by = %s
    """, (status, app_id, session['user_id']))
    conn.commit()
    
    affected_rows = cursor.rowcount
    
    cursor.close()
    conn.close()
    
    if affected_rows == 0:
        flash('Application not found or not authorized to update', 'danger')
    else:
        flash('Application status updated successfully', 'success')
    
    return redirect(url_for('employer_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)