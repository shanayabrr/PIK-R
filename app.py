from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
import os
import time
import re
import threading
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'pikr_tazkia_secret_key'

# --- DATA ACCESS LAYER (DAL) ---
DB_PATH = 'database/'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def load_data(filename):
    try:
        with open(os.path.join(DB_PATH, filename), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if filename == 'users.json':
            return {"admin": [], "anggota_remaja": [], "konselor": []}
        return []

def save_data(filename, data):
    with open(os.path.join(DB_PATH, filename), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- BUSINESS LOGIC LAYER (Service Layer) ---
def add_notification(username, message, link):
    notifications = load_data('notifications.json')
    if not isinstance(notifications, list): notifications = []
    new_id = max([n.get('id', 0) for n in notifications], default=0) + 1
    notifications.append({
        "id": new_id,
        "username": username,
        "message": message,
        "link": link,
        "is_read": False,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_data('notifications.json', notifications)
def validate_age(birth_date_str):
    try:
        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
        today = datetime.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return 10 <= age <= 24
    except ValueError:
        return False

def notify_role(role, message, link):
    """Mengirim notifikasi ke semua user dengan role tertentu"""
    all_users = load_data('users.json')
    if role in all_users:
        for u in all_users[role]:
            if u.get('username') != session.get('username'):
                add_notification(u['username'], message, link)

def notify_admins(message, link):
    """Mengirim notifikasi khusus ke semua Admin"""
    notify_role('admin_pikr', message, link)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Silakan login terlebih dahulu", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- PRESENTATION LAYER (Controller/Routes) ---

@app.route('/api/notifications')
@login_required
def get_notifications():
    notifications = load_data('notifications.json')
    if not isinstance(notifications, list): notifications = []
    user_notifs = [n for n in notifications if n.get('username') == session.get('username')]
    user_notifs.sort(key=lambda x: x.get('id', 0), reverse=True)
    return jsonify(user_notifs)

@app.route('/api/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def read_notification(notif_id):
    notifications = load_data('notifications.json')
    for n in notifications:
        if n.get('id') == notif_id and n.get('username') == session.get('username'):
            n['is_read'] = True
            break
    save_data('notifications.json', notifications)
    return jsonify({"success": True})

@app.route('/api/notifications/read_all', methods=['POST'])
@login_required
def read_all_notifications():
    notifications = load_data('notifications.json')
    for n in notifications:
        if n.get('username') == session.get('username'):
            n['is_read'] = True
    save_data('notifications.json', notifications)
    return jsonify({"success": True})

@app.route('/api/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    notifications = load_data('notifications.json')
    # Hapus hanya notifikasi milik user yang sedang login
    notifications = [n for n in notifications if n.get('username') != session.get('username')]
    save_data('notifications.json', notifications)
    return jsonify({"success": True})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        birth_date = request.form['birth_date']
        role = request.form['role']

        if not validate_age(birth_date):
            flash("Pendaftaran Gagal: Usia harus antara 10-24 tahun.", "danger")
            return redirect(url_for('register'))

        all_users = load_data('users.json')

        for r in all_users:
            if any(u['username'] == username for u in all_users[r]):
                flash("Username sudah digunakan!", "danger")
                return redirect(url_for('register'))

        new_id = len(all_users[role]) + 1
        new_user = {
            "id": new_id,
            "username": username,
            "password": password,
            "birth_date": birth_date
        }

        all_users[role].append(new_user)
        save_data('users.json', all_users)
        
        flash(f"Registrasi sebagai {role} berhasil!", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

def authenticate_user(username, password):
    users_data = load_data('users.json') 
    for role, user_list in users_data.items():
        if isinstance(user_list, list):
            for user in user_list:
                if user['username'] == username and user['password'] == password:
                    user['role'] = role
                    return user
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = authenticate_user(request.form['username'], request.form['password'])
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        flash("Login gagal!", "danger")
    return render_template('login.html')

def update_user_data(username, new_data):
    all_users = load_data('users.json')
    updated = False
    for role in all_users:
        for u in all_users[role]:
            if u['username'] == username:
                u.update(new_data)
                updated = True
                break
    if updated:
        save_data('users.json', all_users)
    return updated

def add_points(username, points):
    all_users = load_data('users.json')
    for role in all_users:
        for u in all_users[role]:
            if u['username'] == username:
                u['points'] = u.get('points', 0) + points
                save_data('users.json', all_users)
                return True
    return False

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    my_username = session.get('username')
    all_users = load_data('users.json')
    user = None
    for role in all_users:
        user = next((u for u in all_users[role] if u['username'] == my_username), None)
        if user: 
            user['role'] = role
            break
            
    if request.method == 'POST':
        new_bio = request.form.get('bio')
        new_password = request.form.get('password')
        
        updates = {"bio": new_bio}
        if new_password:
            updates["password"] = new_password
            
        # Handle Profile Picture
        file = request.files.get('profile_pic')
        if file and file.filename:
            filename = f"profile_{my_username}_{int(time.time())}.png"
            filepath = os.path.join('static/uploads/profiles', filename)
            os.makedirs('static/uploads/profiles', exist_ok=True)
            file.save(filepath)
            updates["profile_pic"] = filepath
            
        update_user_data(my_username, updates)
        flash('Profil berhasil diperbarui!', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html', user=user)

@app.route('/dashboard')
@login_required
def dashboard():
    all_users = load_data('users.json')
    chats = load_data('messages.json')
    sessions = load_data('sessions.json') 
    articles = load_data('education.json') 
    forum_posts = load_data('forum.json')
    
    my_username = session['username']
    
    total_users = 0
    total_konselor = 0
    total_remaja = 0
    recent_users = []
    if isinstance(all_users, dict):
        for role_name, user_list in all_users.items():
            total_users += len(user_list)
            if role_name == 'konselor':
                total_konselor = len(user_list)
            elif role_name == 'anggota_remaja':
                total_remaja = len(user_list)
            
            for u in user_list:
                u_copy = u.copy()
                u_copy['role'] = role_name
                recent_users.append(u_copy)

    # Sort recent users by ID (assuming higher ID = newer)
    recent_users.sort(key=lambda x: x.get('id', 0), reverse=True)
    recent_users = recent_users[:5]

    total_articles = len(articles)

    chat_partners = set()
    for c in chats:
        if c.get('receiver') == my_username:
            chat_partners.add(c.get('sender'))
        elif c.get('sender') == my_username:
            chat_partners.add(c.get('receiver'))

    # Data untuk chart konseling
    all_sessions = load_data('sessions.json')
    
    # Filter sessions based on user role
    my_sessions = []
    if session.get('role') == 'admin_pikr':
        my_sessions = all_sessions
    elif session.get('role') == 'konselor':
        my_sessions = [s for s in all_sessions if s.get('counselor_name') == my_username]
    elif session.get('role') == 'klinik_kesehatan':
        my_sessions = [s for s in all_sessions if s.get('priority') in ['emergency', 'high']]
    else: # anggota_remaja
        my_sessions = [s for s in all_sessions if s.get('member_name') == my_username]
        
    chart_data = [
        len([s for s in my_sessions if s.get('status', '').lower() == 'pending']),
        len([s for s in my_sessions if s.get('status', '').lower() == 'approved']),
        len([s for s in my_sessions if s.get('status', '').lower() == 'rejected'])
    ]

    # Emergency Data (Visible to Admin, Counselor, and Klinik Kesehatan)
    emergency_sessions = [s for s in all_sessions if s.get('priority') in ['emergency', 'high']]
    total_emergency = len(emergency_sessions)

    # Joined Events (For Remaja)
    joined_events = [e for e in load_data('events.json') if my_username in e.get('participants', [])]

    # User Points & Badges
    user_points = 0
    for r in all_users:
        u = next((usr for usr in all_users[r] if usr['username'] == my_username), None)
        if u:
            user_points = u.get('points', 0)
            break

    return render_template('dashboard.html', 
                           role=session['role'], 
                           chart_data=chart_data,
                           total_users=total_users,
                           total_remaja=total_remaja,
                           total_running_sessions=chart_data[1],
                           total_konselor=total_konselor,
                           total_articles=total_articles,
                           recent_users=recent_users,
                           recent_posts=forum_posts[:5],
                           konselor_data=all_users.get('konselor', []),
                           chat_partners=list(chat_partners),
                           emergency_sessions=emergency_sessions,
                           total_emergency=total_emergency,
                           joined_events=joined_events,
                           user_points=user_points)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- FORUM FITUR (DENGAN COCH BOX PENGUMUMAN) ---
@app.route('/forum', methods=['GET', 'POST'])
@login_required
def forum():
    if request.method == 'POST':
        content = request.form.get('content')
        is_announcement = request.form.get('is_announcement') == 'on' # Cek checklist
        
        if content and content.strip():
            posts = load_data('forum.json')
            new_id = max([p.get('id', 0) for p in posts], default=0) + 1
            new_post = {
                "id": new_id,
                "username": session.get('username'),
                "content": content,
                "role": session.get('role'),
                "is_announcement": is_announcement, # Disimpan ke JSON
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            # Jika pengumuman, taruh di paling atas list forum biar langsung kebaca
            if is_announcement:
                posts.insert(0, new_post)
                all_users = load_data('users.json')
                if isinstance(all_users, dict):
                    for role_name, user_list in all_users.items():
                        if isinstance(user_list, list):
                            for u in user_list:
                                if u['username'] != session.get('username'):
                                    add_notification(u['username'], f"📢 Pengumuman: {content[:30]}...", url_for('forum'))
            else:
                posts.append(new_post)
                # Notifikasi ke konselor & admin jika ada kiriman forum baru
                notify_role('konselor', f"📝 Kiriman forum baru dari {session['username']}", url_for('forum'))
                notify_admins(f"📝 Kiriman forum baru dari {session['username']}", url_for('forum'))
            
            # Cek mentions dan kirim notifikasi khusus (Support username dengan spasi)
            all_users = load_data('users.json')
            valid_users = set()
            if isinstance(all_users, dict):
                for role_name, user_list in all_users.items():
                    if isinstance(user_list, list):
                        for u in user_list:
                            valid_users.add(u['username'])
            
            for username in valid_users:
                # Cari "@username" case insensitive
                if f"@{username.lower()}" in content.lower() and username != session.get('username'):
                    add_notification(username, f"💬 Kamu di-tag oleh {session['username']} di forum", url_for('forum'))
                        
            save_data('forum.json', posts)
            flash('Berhasil mengirim ke forum!', 'success')
        return redirect(url_for('forum'))
        
    posts = load_data('forum.json')
    all_users = load_data('users.json')
    valid_usernames = []
    if isinstance(all_users, dict):
        for role_name, user_list in all_users.items():
            if isinstance(user_list, list):
                for u in user_list:
                    valid_usernames.append(u['username'])
                    
    return render_template('forum.html', posts=posts, valid_usernames=valid_usernames)

@app.route('/delete_post/<post_id>')
@login_required
def delete_post(post_id):
    posts = load_data('forum.json')
    new_posts = [p for p in posts if str(p['id']) != str(post_id)]
    save_data('forum.json', new_posts)
    flash('Postingan berhasil dihapus!', 'success')
    return redirect(url_for('forum'))

@app.route('/edit_post/<post_id>', methods=['POST'])
@login_required
def edit_post(post_id):
    posts = load_data('forum.json')
    new_content = request.form.get('content')
    for post in posts:
        if str(post['id']) == str(post_id):
            post['content'] = new_content
            break
    save_data('forum.json', posts)
    flash('Postingan berhasil diperbarui!', 'success')
    return redirect(url_for('forum'))

# --- KONSELING FITUR ---
@app.route('/konseling', methods=['GET', 'POST'])
@login_required
def counseling():
    if request.method == 'POST':
        counselor_name = request.form.get('counselor_name')
        topic = request.form.get('topic')
        date = request.form.get('date')
        time = request.form.get('time')
        
        sessions = load_data('sessions.json')
        
        # Cek jadwal bentrok
        is_conflict = False
        for s in sessions:
            if s.get('counselor_name') == counselor_name and s.get('date') == date and s.get('time') == time:
                if s.get('status') in ['PENDING', 'APPROVED']:
                    is_conflict = True
                    break
        
        if is_conflict:
            flash(f"Maaf, jadwal pada tanggal {date} jam {time} dengan konselor {counselor_name} sudah dibooking orang lain. Silakan pilih waktu lain.", "danger")
            return redirect(url_for('counseling'))
            
        new_id = max([s.get('id', 0) for s in sessions], default=0) + 1
        
        new_session = {
            "id": new_id,
            "session_id": new_id,
            "member_name": session.get('username'),
            "counselor_name": counselor_name,
            "topic": topic,
            "date": date,
            "time": time,
            "status": "PENDING"
        }
        sessions.append(new_session)
        save_data('sessions.json', sessions)
        add_notification(counselor_name, f"📅 Permintaan konseling baru dari {session.get('username')}", url_for('counseling'))
        notify_admins(f"📅 Permintaan konseling baru dari {session.get('username')} untuk {counselor_name}", url_for('counseling'))
        flash("Permintaan konseling berhasil dikirim!", "success")
        return redirect(url_for('counseling'))

    sessions = load_data('sessions.json')
    if session.get('role') == 'admin_pikr':
        user_sessions = sessions
    elif session.get('role') == 'klinik_kesehatan':
        user_sessions = [s for s in sessions if s.get('priority') in ['emergency', 'high']]
    else:
        user_sessions = [s for s in sessions if s.get('member_name') == session.get('username') or s.get('counselor_name') == session.get('username')]
    
    return render_template('counseling.html', 
                           sessions=user_sessions, 
                           konselor_data=load_data('users.json').get('konselor', []))

@app.route('/approve_session/<int:session_id>')
@login_required
def approve_session(session_id):
    if session.get('role') not in ['konselor', 'admin_pikr']:
        flash("Akses ditolak", "danger")
        return redirect(url_for('counseling'))
        
    sessions = load_data('sessions.json')
    for s in sessions:
        if s.get('id') == session_id or s.get('session_id') == session_id:
            s['status'] = 'APPROVED'
            add_notification(s['member_name'], "✅ Jadwal konseling Anda disetujui!", url_for('counseling'))
            notify_admins(f"✅ Konselor {session['username']} menyetujui sesi #{session_id}", url_for('counseling'))
            break
    save_data('sessions.json', sessions)
    flash("Sesi disetujui!", "success")
    return redirect(url_for('counseling'))

@app.route('/reject_session/<int:session_id>')
@login_required
def reject_session(session_id):
    if session.get('role') not in ['konselor', 'admin_pikr']:
        flash("Akses ditolak", "danger")
        return redirect(url_for('counseling'))
        
    sessions = load_data('sessions.json')
    for s in sessions:
        if s.get('id') == session_id or s.get('session_id') == session_id:
            s['status'] = 'REJECTED'
            add_notification(s['member_name'], "❌ Jadwal konseling Anda ditolak.", url_for('counseling'))
            notify_admins(f"❌ Konselor {session['username']} menolak sesi #{session_id}", url_for('counseling'))
            break
    save_data('sessions.json', sessions)
    flash("Sesi ditolak!", "warning")
    return redirect(url_for('counseling'))

@app.route('/delete_session/<int:session_id>')
@login_required
def delete_session(session_id):
    sessions = load_data('sessions.json')
    # Allow deletion if admin or if the user is part of the session
    new_sessions = []
    found = False
    for s in sessions:
        if s.get('id') == session_id or s.get('session_id') == session_id:
            if session.get('role') == 'admin_pikr' or s.get('member_name') == session['username'] or s.get('counselor_name') == session['username']:
                found = True
                continue
        new_sessions.append(s)
    
    if found:
        save_data('sessions.json', new_sessions)
        flash("Riwayat sesi dihapus", "success")
    else:
        flash("Gagal menghapus atau akses ditolak", "danger")
        
    return redirect(url_for('counseling'))

@app.route('/edit_session/<int:session_id>', methods=['POST'])
@login_required
def edit_session(session_id):
    sessions = load_data('sessions.json')
    found = False
    for s in sessions:
        if s.get('id') == session_id or s.get('session_id') == session_id:
            # Check permission: Admin, Counselor of the session, or Member of the session
            if session.get('role') == 'admin_pikr' or \
               s.get('counselor_name') == session['username'] or \
               s.get('member_name') == session['username']:
                
                s['date'] = request.form.get('date')
                s['time'] = request.form.get('time')
                
                # Only Admin/Counselor can change status
                if session.get('role') in ['admin_pikr', 'konselor']:
                    s['status'] = request.form.get('status', s['status'])
                
                found = True
                break
    
    if found:
        save_data('sessions.json', sessions)
        flash("Jadwal diperbarui!", "success")
    else:
        flash("Gagal memperbarui jadwal atau akses ditolak", "danger")
        
    return redirect(url_for('counseling'))

# --- EDUKASI & ARTIKEL FITUR ---
@app.route('/edukasi')
@login_required
def education():
    articles = load_data('education.json')
    updated = False
    for art in articles:
        for idx, c in enumerate(art.get('comments', [])):
            if 'id' not in c:
                c['id'] = idx + 1
                updated = True
    if updated:
        save_data('education.json', articles)
    return render_template('education.html', articles=articles)

@app.route('/edukasi/<int:article_id>')
@login_required
def education_detail(article_id):
    articles = load_data('education.json')
    article = next((a for a in articles if a.get('id') == article_id), None)
    if article:
        return render_template('education_detail.html', article=article)
    flash("Artikel tidak ditemukan", "warning")
    return redirect(url_for('education'))

@app.route('/upload_image', methods=['POST'])
@login_required
def upload_image():
    file_gambar = request.files.get('upload')
    if file_gambar:
        nama_gambar = secure_filename(file_gambar.filename)
        nama_gambar = f"{int(datetime.now().timestamp())}_{nama_gambar}"
        file_gambar.save(os.path.join(app.config['UPLOAD_FOLDER'], nama_gambar))
        
        url_gambar = url_for('static', filename=f'uploads/{nama_gambar}')
        return f"""
        <script type='text/javascript'>
            window.parent.CKEDITOR.tools.callFunction({request.args.get('CKEditorFuncNum')}, '{url_gambar}', 'Gambar berhasil disisipkan!');
        </script>
        """
    return ''

@app.route('/add_article', methods=['POST'])
@login_required
def add_article():
    if session.get('role') not in ['konselor', 'admin_pikr']:
        flash("Akses ditolak!", "danger")
        return redirect(url_for('education'))
    
    title = request.form.get('title')
    content = request.form.get('content', '')
    
    file_dokumen = request.files.get('dokumen')
    nama_dokumen = None
    
    if file_dokumen and file_dokumen.filename != '':
        nama_dokumen = secure_filename(file_dokumen.filename)
        nama_dokumen = f"{int(datetime.now().timestamp())}_{nama_dokumen}"
        file_dokumen.save(os.path.join(app.config['UPLOAD_FOLDER'], nama_dokumen))

    if (not content or content.strip() == '') and not nama_dokumen:
        flash("Gagal menerbitkan: Mohon isi teks materi atau pilih file dokumen PDF/DOCX untuk diupload!", "danger")
        return redirect(url_for('education'))

    articles = load_data('education.json')
    new_id = max([a.get('id', 0) for a in articles], default=0) + 1
    
    new_article = {
        "id": new_id,
        "title": title,
        "content": content,
        "author": session['username'],
        "author_id": session['user_id'],
        "dokumen": nama_dokumen,
        "comments": []
    }
    articles.append(new_article)
    save_data('education.json', articles)
    
    # Notifikasi ke semua remaja & admin
    notify_role('anggota_remaja', f"📚 Materi Baru: {title}", url_for('education'))
    notify_admins(f"📚 Materi Baru diterbitkan oleh {session['username']}: {title}", url_for('education'))
    
    flash("Materi edukasi berhasil diterbitkan!", "success")
    return redirect(url_for('education'))

@app.route('/admin/education/add', methods=['POST'])
@login_required
def add_education_admin():
    return add_article()

@app.route('/admin/education/delete/<int:edu_id>')
@login_required
def delete_education(edu_id):
    articles = load_data('education.json')
    article = next((a for a in articles if a['id'] == edu_id), None)
    if not article:
        flash('Materi tidak ditemukan!', 'warning')
        return redirect(url_for('education'))
        
    if session.get('role') == 'admin_pikr' or (session.get('role') == 'konselor' and article.get('author') == session.get('username')):
        articles = [e for e in articles if e['id'] != edu_id]
        save_data('education.json', articles)
        notify_admins(f"🗑️ Artikel '{article.get('title')}' dihapus oleh {session['username']}", url_for('education'))
        flash('Materi edukasi berhasil dihapus!', 'success')
    else:
        flash('Akses ditolak: Anda tidak berhak menghapus materi ini!', 'danger')
    return redirect(url_for('education'))

@app.route('/add_comment/<int:article_id>', methods=['POST'])
@login_required
def add_comment(article_id):
    comment_text = request.form.get('comment')
    rating = request.form.get('rating')

    articles = load_data('education.json')
    for article in articles:
        if article['id'] == article_id:
            new_comment_id = max([c.get('id', 0) for c in article.get('comments', [])], default=0) + 1
            article['comments'].append({
                "id": new_comment_id,
                "user": session['username'],
                "text": comment_text,
                "rating": int(rating)
            })
            break
    save_data('education.json', articles)
    add_points(session['username'], 10) # Reward 10 poin untuk partisipasi ulasan
    
    # Notifikasi ke penulis artikel & admin
    article = next((a for a in articles if a['id'] == article_id), None)
    if article and article.get('author') != session.get('username'):
        add_notification(article.get('author'), f"💬 Ada ulasan baru di artikel '{article['title']}'", url_for('education'))
    
    notify_admins(f"💬 Ulasan baru dari {session['username']} di artikel: {article['title'] if article else article_id}", url_for('education'))
        
    flash('Ulasan berhasil ditambahkan!', 'success')
    return redirect(url_for('education'))

@app.route('/edit_comment/<int:article_id>/<int:comment_id>', methods=['POST'])
@login_required
def edit_comment(article_id, comment_id):
    new_text = request.form.get('comment')
    articles = load_data('education.json')
    for art in articles:
        if art['id'] == article_id:
            for c in art.get('comments', []):
                if int(c.get('id', 0)) == int(comment_id):
                    if c.get('user') == session.get('username'):
                        c['text'] = new_text
                        flash('Ulasan berhasil diperbarui!', 'success')
                    else:
                        flash('Akses ditolak!', 'danger')
                    break
            break
    save_data('education.json', articles)
    return redirect(url_for('education'))

@app.route('/admin/education/delete_comment/<int:article_id>/<int:comment_id>')
@login_required
def delete_comment(article_id, comment_id):
    articles = load_data('education.json')
    for art in articles:
        if art['id'] == article_id:
            komentar_target = next((c for c in art.get('comments', []) if int(c.get('id', 0)) == int(comment_id)), None)
            if komentar_target:
                if session.get('role') == 'admin_pikr' or komentar_target.get('user') == session.get('username'):
                    art['comments'] = [c for c in art['comments'] if int(c.get('id', 0)) != int(comment_id)]
                    flash('Ulasan berhasil dihapus!', 'info')
                else:
                    flash('Akses ditolak!', 'danger')
            break
    save_data('education.json', articles)
    return redirect(url_for('education'))

# --- CHAT PRIVAT FITUR ---
def load_messages():
    return load_data('messages.json')

def send_message(sender, receiver, message_text, attachment=None, is_bot=False):
    messages = load_messages()
    new_message = {
        "id": len(messages) + 1,
        "sender": sender,
        "receiver": receiver,
        "message": message_text,
        "attachment": attachment,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "seen": False,
        "is_bot": is_bot
    }
    messages.append(new_message)
    save_data('messages.json', messages)
    
    if not is_bot:
        add_notification(receiver, f"💬 Pesan baru dari {sender}", url_for('chat', receiver_username=sender))

    # --- EMERGENCY DETECTION SYSTEM ---
    msg_lower = message_text.lower()
    
    # Kosa Kata Darurat (Merah)
    EMERGENCY_KEYWORDS = [
        "bunuh diri", "akhiri hidup", "pengen mati", "mati aja", "sayat", "potong urat", 
        "racun", "gantung diri", "loncat", "darah", "sekarat", "tolong cepat",
        "suicide", "kill myself", "end my life", "self harm"
    ]
    
    # Kosa Kata Prioritas (Kuning)
    PRIORITY_KEYWORDS = [
        "pembullyan", "bully", "dihina", "diejek", "dikucilkan", "diteror", "intimidasi", 
        "pelecehan", "depresi", "stress", "tekanan", "trauma", "skizofrenia", "bipolar", 
        "halusinasi", "delusi", "gangguan jiwa", "skizo", "odgj", "gangguan mental", 
        "serangan panik", "bullying", "harassment", "abused", "depressed", 
        "schizophrenia", "panic attack", "borderline", "bpd", "ocd"
    ]

    level = None
    if any(k in msg_lower for k in EMERGENCY_KEYWORDS):
        level = "emergency"
    elif any(k in msg_lower for k in PRIORITY_KEYWORDS):
        level = "high"

    if level:
        sessions = load_data('sessions.json')
        updated = False
        for s in sessions:
            # Temukan sesi yang sedang berjalan antara kedua user ini
            if (s.get('member_name') == sender and s.get('counselor_name') == receiver) or \
               (s.get('member_name') == receiver and s.get('counselor_name') == sender):
                
                # Jangan turunkan level jika sudah emergency
                if s.get('priority') == 'emergency' and level == 'high':
                    continue
                    
                s['priority'] = level
                updated = True
        
        if updated:
            save_data('sessions.json', sessions)
            if level == 'emergency':
                notify_role('klinik_kesehatan', f"🚨 DARURAT: Deteksi kosa kata kritis dari {sender}!", url_for('counseling'))
                notify_admins(f"🚨 DARURAT: {sender} membutuhkan bantuan segera!", url_for('counseling'))
            else:
                notify_role('klinik_kesehatan', f"⚠️ PRIORITAS: Deteksi topik berisiko (Misal: bully) dari {sender}!", url_for('counseling'))
                notify_admins(f"⚠️ PRIORITAS: {sender} membahas topik sensitif/berisiko.", url_for('counseling'))
                add_notification(receiver, f"⚠️ PRIORITAS: Pesan dari {sender} terdeteksi butuh perhatian khusus.", url_for('counseling'))

@app.route('/delete_message/<int:message_id>/<string:receiver_username>')
@login_required
def delete_message(message_id, receiver_username):
    messages = load_messages()
    new_messages = []
    found = False
    for m in messages:
        if m.get('id') == message_id:
            if m.get('sender') == session['username'] or session['role'] == 'admin_pikr':
                found = True
                continue
        new_messages.append(m)
    
    if found:
        save_data('messages.json', new_messages)
        flash("Pesan dihapus", "info")
    else:
        flash("Gagal menghapus pesan", "danger")
        
    return redirect(url_for('chat', receiver_username=receiver_username))

@app.route('/chat')
@app.route('/chat/<string:receiver_username>', methods=['GET', 'POST'])
@login_required
def chat(receiver_username=None):
    my_username = session.get('username')
    
    if receiver_username and my_username == receiver_username:
        flash("Anda tidak bisa mengirim pesan ke diri sendiri.", "warning")
        return redirect(url_for('chat'))

    if request.method == 'POST' and receiver_username:
        message_text = request.form.get('message', '')
        attachment_path = None
        
        # Handle Attachment
        file = request.files.get('attachment')
        if file and file.filename:
            filename = f"chat_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            filepath = os.path.join('static/uploads/chats', filename)
            os.makedirs('static/uploads/chats', exist_ok=True)
            file.save(filepath)
            attachment_path = filepath
            
        if message_text.strip() or attachment_path:
            send_message(my_username, receiver_username, message_text, attachment_path)
            
        return redirect(url_for('chat', receiver_username=receiver_username))
        
    all_messages = load_messages()
    
    # Calculate chat partners for the sidebar
    chat_partners = set()
    for m in all_messages:
        if m.get('sender') == my_username:
            chat_partners.add(m.get('receiver'))
        elif m.get('receiver') == my_username:
            chat_partners.add(m.get('sender'))
    
    filtered_messages = []
    if receiver_username:
        filtered_messages = [
            msg for msg in all_messages 
            if (msg['sender'] == my_username and msg['receiver'] == receiver_username) or 
               (msg['sender'] == receiver_username and msg['receiver'] == my_username)
        ]
        
    return render_template('chat.html', 
                           receiver_username=receiver_username, 
                           history=filtered_messages, 
                           chat_partners=sorted(list(chat_partners)))

@app.route('/clear_chat/<string:receiver_username>', methods=['POST'])
@login_required
def clear_chat(receiver_username):
    current_user = session.get('username')
    all_messages = load_messages()
    # Hanya hapus pesan antara current_user dan receiver_username
    new_messages = [
        msg for msg in all_messages 
        if not ((msg['sender'] == current_user and msg['receiver'] == receiver_username) or 
               (msg['sender'] == receiver_username and msg['receiver'] == current_user))
    ]
    save_data('messages.json', new_messages)
    flash(f"Riwayat chat dengan {receiver_username} telah dibersihkan.", "info")
    return redirect(url_for('chat', receiver_username=receiver_username))

@app.route('/transfer_to_clinic/<string:receiver_username>', methods=['POST'])
@login_required
def transfer_to_clinic(receiver_username):
    if session.get('role') != 'konselor':
        flash("Akses ditolak.", "danger")
        return redirect(url_for('chat'))
    
    sender = session.get('username')
    
    # Notify member to chat with clinic
    add_notification(receiver_username, f"🏥 Konselor {sender} merujukmu ke Klinik Kesehatan. Klik di sini untuk mulai obrolan.", url_for('chat', receiver_username='klinik'))
    
    # Notify clinic that a chat has been transferred
    notify_role('klinik_kesehatan', f"🏥 Konselor {sender} merujuk {receiver_username} ke Klinik. Segera tindak lanjuti.", url_for('chat', receiver_username=receiver_username))
    
    # Send bot message to the current chat
    bot_msg = f"Sesi ini telah dirujuk ke Klinik Kesehatan oleh Konselor. {receiver_username}, silakan hubungi akun 'klinik' untuk penanganan medis lebih lanjut."
    send_message(sender, receiver_username, bot_msg, is_bot=True)
    
    flash("Sesi berhasil dialihkan ke Klinik Kesehatan.", "success")
    return redirect(url_for('chat', receiver_username=receiver_username))

# --- EVENTS FITUR ---
@app.route('/events')
def events():
    all_events = load_data('events.json')
    return render_template('events.html', events=all_events)

@app.route('/admin/events/add', methods=['POST'])
@login_required
def add_event():
    if session.get('role') not in ['admin_pikr', 'konselor']:
        return redirect(url_for('events'))
    
    title = request.form.get('title')
    description = request.form.get('description')
    date = request.form.get('date')
    time = request.form.get('time')

    events = load_data('events.json')
    new_id = max([e['id'] for e in events], default=0) + 1
    new_entry = {
        "id": new_id,
        "title": title,
        "description": description,
        "date": date,
        "time": time,
        "author": session.get('username'), # Simpan author untuk notifikasi nanti
        "participants": []
    }
    events.append(new_entry)
    save_data('events.json', events)
    
    # Notifikasi ke semua remaja & admin
    notify_role('anggota_remaja', f"🎉 Event Baru: {title}", url_for('events'))
    notify_admins(f"🎉 Event Baru ditambahkan oleh {session['username']}: {title}", url_for('events'))
    
    flash('Kegiatan berhasil ditambahkan!', 'success')
    return redirect(url_for('events'))

@app.route('/admin/events/delete/<int:event_id>')
@login_required
def delete_event(event_id):
    if session.get('role') != 'admin_pikr':
        return redirect(url_for('events'))
    events = load_data('events.json')
    events = [e for e in events if e['id'] != event_id]
    save_data('events.json', events)
    flash('Kegiatan berhasil dihapus!', 'danger')
    return redirect(url_for('events'))

@app.route('/admin/events/edit/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    if session.get('role') != 'admin_pikr':
        return redirect(url_for('events'))
    events = load_data('events.json')
    for e in events:
        if e['id'] == event_id:
            e['title'] = request.form.get('title')
            e['description'] = request.form.get('description')
            e['date'] = request.form.get('date')
            e['time'] = request.form.get('time')
            break
    save_data('events.json', events)
    flash('Kegiatan berhasil diperbarui!', 'success')
    return redirect(url_for('events'))

@app.route('/join_event/<int:event_id>')
@login_required
def join_event(event_id):
    if session.get('role') != 'anggota_remaja':
        return redirect(url_for('events'))
    events = load_data('events.json')
    for event in events:
        if event['id'] == event_id:
            if session['username'] not in event['participants']:
                event['participants'].append(session['username'])
                add_points(session['username'], 50) # Reward 50 poin untuk ikut event
    save_data('events.json', events)
    
    target_event = next((e for e in events if e['id'] == event_id), None)
    if target_event:
        author = target_event.get('author')
        msg = f"👥 {session['username']} mendaftar ke event: {target_event['title']}"
        if author:
            add_notification(author, msg, url_for('events'))
        notify_admins(msg, url_for('events'))
        
    flash('Berhasil mendaftar ke kegiatan!', 'success')
    return redirect(url_for('events'))

@app.route('/leave_event/<int:event_id>')
@login_required
def leave_event(event_id):
    if session.get('role') != 'anggota_remaja':
        return redirect(url_for('events'))
    events = load_data('events.json')
    for event in events:
        if event['id'] == event_id:
            if session['username'] in event['participants']:
                event['participants'].remove(session['username'])
            break
    save_data('events.json', events)
    flash('Pendaftaran kegiatan berhasil dibatalkan.', 'info')
    return redirect(url_for('events'))

# --- ADMIN KELOLA USER ---
@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if session.get('role') != 'admin_pikr':
        return redirect(url_for('dashboard'))
    data_json = load_data('users.json') 

    if request.method == 'POST':
        new_username = request.form.get('username')
        new_password = request.form.get('password')
        new_role = request.form.get('role')
        birth_date = request.form.get('birth_date', '2005-01-01')

        role_list = data_json.get(new_role, [])
        new_id = max([u['id'] for u in role_list], default=0) + 1
        new_user = {
            "id": new_id,
            "username": new_username,
            "password": new_password,
            "birth_date": birth_date
        }
        data_json[new_role].append(new_user)
        save_data('users.json', data_json)
        return redirect(url_for('admin_users'))

    all_users = []
    for role, user_list in data_json.items():
        if isinstance(user_list, list):
            for user in user_list:
                u = user.copy()
                u['role'] = role
                all_users.append(u)
    return render_template('admin_users.html', users=all_users)

@app.route('/admin/delete_user/<role>/<int:user_id>')
@login_required
def delete_user(role, user_id):
    if session.get('role') != 'admin_pikr':
        return redirect(url_for('dashboard'))
    data_json = load_data('users.json')
    if role in data_json:
        data_json[role] = [u for u in data_json[role] if u['id'] != user_id]
        save_data('users.json', data_json)
        flash("User berhasil dihapus!", "danger")
    return redirect(url_for('admin_users'))

def reminder_bot():
    while True:
        try:
            now = datetime.now()
            current_date = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%H:%M")
            
            sessions = load_data('sessions.json')
            updated = False
            if isinstance(sessions, list):
                for s in sessions:
                    if s.get('status') == 'APPROVED' and not s.get('reminder_sent'):
                        if s.get('date') == current_date and s.get('time') == current_time:
                            member = s.get('member_name')
                            counselor = s.get('counselor_name')
                            
                            with app.app_context():
                                add_notification(member, f"⏰ Mengingatkan: Sesi konselingmu dengan {counselor} dijadwalkan sekarang!", url_for('counseling'))
                                add_notification(counselor, f"⏰ Mengingatkan: Kamu ada jadwal konseling dengan {member} sekarang!", url_for('counseling'))
                                bot_msg = f"Halo! Jadwal konselingmu dengan Konselor {counselor} telah tiba. Silakan tunggu balasan dari konselor. Jika konselor belum merespons dalam beberapa waktu, mohon bersabar."
                                send_message(sender=counselor, receiver=member, message_text=bot_msg, is_bot=True)
                            
                            s['reminder_sent'] = True
                            updated = True
                
                if updated:
                    save_data('sessions.json', sessions)
        except Exception as e:
            print("Reminder Bot Error:", e)
        time.sleep(60)

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)
    
    for db_file in ['users.json', 'messages.json', 'education.json', 'events.json', 'sessions.json', 'forum.json', 'notifications.json']:
        file_path = os.path.join(DB_PATH, db_file)
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                if db_file == 'users.json':
                    json.dump({"admin": [], "anggota_remaja": [], "konselor": []}, f, indent=4)
                else:
                    json.dump([], f, indent=4)

    # Start Background Thread
    threading.Thread(target=reminder_bot, daemon=True).start()

    app.run(debug=True)