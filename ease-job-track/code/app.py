from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime
from calendar_integration import add_interview_to_calendar, add_reminder_to_calendar, delete_event_from_calendar 

app = Flask(__name__)

# Database initialization
def init_db():
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            application_status TEXT NOT NULL,
            applied_date TEXT,
            interview_date TEXT,
            reminder_date TEXT,
            comments_section TEXT,
            priority INTEGER,
            event_id_interview TEXT,  
            event_id_reminder TEXT   
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            feedback_text TEXT NOT NULL,
            status TEXT NOT NULL,
            language TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')
    conn.commit()
    conn.close()

# Home page
@app.route('/')
def index():
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM jobs") 
    jobs = cursor.fetchall()

    # Fetch data for the pie chart 
    cursor.execute("SELECT application_status, COUNT(*) FROM jobs GROUP BY application_status")
    status_data = cursor.fetchall()

    # Fetch data for the bar chart (applications per company)
    cursor.execute("SELECT company_name, COUNT(*) FROM jobs GROUP BY company_name")
    company_data = cursor.fetchall()

    conn.close()

    #Prepare data for the pie chart
    labels = [row[0] for row in status_data]  # Status labels (e.g., Applied, Interview Scheduled)
    counts = [row[1] for row in status_data]  # Count of applications for each status

    # Prepare data for the bar chart
    company_names = [row[0] for row in company_data]  # Company names
    company_counts = [row[1] for row in company_data]  # Count of applications per company

    return render_template('index.html', jobs=jobs, status_labels=labels, status_counts=counts, company_names=company_names, company_counts=company_counts)
    
# To search for application by company name, job title, status, interview and reminder date
@app.route('/search', methods=['GET'])
def search_jobs():
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()

    # Get search parameters from the request
    search_query = request.args.get('search_query', '')
    applied_date = request.args.get('applied_date', '')
    interview_date = request.args.get('interview_date', '')

    # Base query to fetch all jobs
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []

    # Add search filters if provided
    if search_query:
        query += " AND (company_name LIKE ? OR job_title LIKE ? OR application_status LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

    if applied_date:
        query += " AND applied_date = ?"
        params.append(applied_date)

    if interview_date:
        interview_date_only = interview_date.split('T')[0]
        query += " AND DATE(interview_date) = ?"
        params.append(interview_date_only)

    cursor.execute(query, params)
    jobs = cursor.fetchall()
    conn.close()

    # Render the search template with the job data
    return render_template('search.html', jobs=jobs)

# Add new job
@app.route('/add', methods=['GET', 'POST'])
def add_job():
    if request.method == 'POST':
        company_name = request.form['company_name']
        job_title = request.form['job_title']
        application_status = request.form['application_status']
        applied_date = request.form['applied_date']
        interview_date = request.form['interview_date']
        reminder_date = request.form['reminder_date']
        comments_section = request.form['comments_section']
        priority = int(request.form.get('priority'))
                                        
        event_id_interview = None
        event_id_reminder = None

        if interview_date:
            event_id_interview = add_interview_to_calendar(company_name, job_title, interview_date)

        # Add reminder event to Google Calendar
        if reminder_date:
            event_id_reminder = add_reminder_to_calendar(company_name, job_title, reminder_date)

        conn = sqlite3.connect('job_tracker.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO jobs (company_name, job_title, application_status, applied_date, interview_date, reminder_date, comments_section, priority, event_id_interview, event_id_reminder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (company_name, job_title, application_status,applied_date, interview_date, reminder_date, comments_section, priority, event_id_interview, event_id_reminder))
        conn.commit()
        conn.close()

        return redirect(url_for('index'))
    return render_template('add_job.html')

# Edit job details
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_job(id):
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        company_name = request.form['company_name']
        job_title = request.form['job_title']
        application_status = request.form['application_status']
        applied_date = request.form['applied_date']
        new_interview_date = request.form['interview_date']
        new_reminder_date = request.form['reminder_date']
        comments_section = request.form['comments_section']
        new_priority = request.form.get('priority')

        # Fetch existing event IDs
        cursor.execute("SELECT event_id_interview, event_id_reminder FROM jobs WHERE id = ?", (id,))
        event_ids = cursor.fetchone()
        event_id_interview, event_id_reminder = event_ids if event_ids else (None, None)

        # Delete old events if dates are changed
        if new_interview_date:
            if event_id_interview:
                delete_event_from_calendar(event_id_interview)
            event_id_interview = add_interview_to_calendar(company_name, job_title, new_interview_date)
        else:
            if event_id_interview:
                delete_event_from_calendar(event_id_interview)
            event_id_interview = None

        if new_reminder_date:
            if event_id_reminder:
                delete_event_from_calendar(event_id_reminder)
            event_id_reminder = add_reminder_to_calendar(company_name, job_title, new_reminder_date)
        else:
            if event_id_reminder:
                delete_event_from_calendar(event_id_reminder)
            event_id_reminder = None

        # Update the job in the database
        cursor.execute('''
            UPDATE jobs
            SET company_name = ?, job_title = ?, application_status = ?, applied_date = ?, interview_date = ?, reminder_date = ?, comments_section = ?, priority = ?, event_id_interview = ?, event_id_reminder = ?
            WHERE id = ?
        ''', (company_name, job_title, application_status, applied_date, new_interview_date, new_reminder_date, comments_section, new_priority, event_id_interview, event_id_reminder, id))

        # Check if the job status is changed to "Rejected" or "Offer Received"
        status = request.form.get('status')
        feedback_text = request.form.get('feedback')
        language = request.form.get('language')

        if status and feedback_text:
            cursor.execute('''
                INSERT INTO feedback (job_id, feedback_text, status, language)
                VALUES (?, ?, ?, ?)
            ''', (id, feedback_text, status, language))

        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    cursor.execute("SELECT * FROM jobs WHERE id = ?", (id,))
    job = cursor.fetchone()
    conn.close()

    return render_template('edit_job.html', job=job)
    
# Delete a job
@app.route('/delete/<int:id>')
def delete_job(id):
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()

    cursor.execute("SELECT event_id_interview, event_id_reminder FROM jobs WHERE id = ?", (id,))
    event_ids = cursor.fetchone()

    if event_ids:
        event_id_interview, event_id_reminder = event_ids

        # Delete events from Google Calendar
        if event_id_interview:
            delete_event_from_calendar(event_id_interview)
        if event_id_reminder:
            delete_event_from_calendar(event_id_reminder)

    # Delete the job from the database
    cursor.execute("DELETE FROM jobs WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

# Priority listing
@app.route('/sort_jobs')
def sort_jobs():
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY priority DESC")
    sorted_list = cursor.fetchall()
    conn.close()
    return jsonify(sorted_list)

# Feedback Form
@app.route('/feedback/<int:job_id>')
def feedback(job_id):
    conn = sqlite3.connect('job_tracker.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT feedback_text, language, status FROM feedback WHERE job_id = ?
    ''', (job_id,))
    feedback = cursor.fetchall()

    cursor.execute("SELECT company_name, job_title FROM jobs WHERE id = ?", (job_id,))
    job = cursor.fetchone()

    conn.close()

    return render_template('feedback.html', feedback=feedback, job=job)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
