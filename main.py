import os
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect, url_for, session, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'chuoi_bi_mat_sieu_cap_vip_123')

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'hosting.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ==========================================
# 1. CẤU HÌNH OAUTH DISCORD (Thay ID/Secret của bạn vào đây)
# ==========================================
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID', 'YOUR_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET', 'YOUR_CLIENT_SECRET')
ADMIN_DISCORD_ID = '1382388465597026429' # ID Admin của bạn

oauth = OAuth(app)
discord = oauth.register(
    name='discord',
    client_id=DISCORD_CLIENT_ID,
    client_secret=DISCORD_CLIENT_SECRET,
    access_token_url='https://discord.com/api/oauth2/token',
    authorize_url='https://discord.com/api/oauth2/authorize',
    api_base_url='https://discord.com/api/',
    client_kwargs={'scope': 'identify'},
)

# ==========================================
# 2. DATABASE MODELS
# ==========================================
class User(db.Model, UserMixin):
    id = db.Column(db.String(50), primary_key=True)
    username = db.Column(db.String(100))
    balance = db.Column(db.Integer, default=0)
    role = db.Column(db.String(20), default='user')

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'))
    name = db.Column(db.String(50))
    language = db.Column(db.String(20))
    plan = db.Column(db.String(50))
    status = db.Column(db.String(50), default='Đang chạy')
    expires_at = db.Column(db.DateTime)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'))
    action = db.Column(db.String(100))
    amount = db.Column(db.Integer)
    time = db.Column(db.DateTime, default=datetime.utcnow)

class GiftCode(db.Model):
    code = db.Column(db.String(50), primary_key=True)
    amount = db.Column(db.Integer)
    max_uses = db.Column(db.Integer)
    current_uses = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Tự động tạo Database và tài khoản Admin/Gift test khi khởi động
with app.app_context():
    db.create_all()
    if not GiftCode.query.get('HB-TEST01'):
        db.session.add(GiftCode(code='HB-TEST01', amount=100, max_uses=10))
    if not User.query.get(ADMIN_DISCORD_ID):
        db.session.add(User(id=ADMIN_DISCORD_ID, username="Admin Tong", role="admin", balance=9999))
    db.session.commit()

# ==========================================
# 3. CẤU HÌNH GÓI & NGÔN NGỮ
# ==========================================
PLANS = {
    'starter': {'name': 'Starter', 'ram': 256, 'cpu': 20, 'disk': 1024, 'price_week': 10, 'price_month': 40},
    'advanced': {'name': 'Advanced', 'ram': 1024, 'cpu': 50, 'disk': 3072, 'price_week': 50, 'price_month': 200},
    'ultimate': {'name': 'Ultimate (Tối Ưu)', 'ram': 100000000, 'cpu': 10000, 'disk': 999999, 'price_week': 8000, 'price_month': 30000}
}

LANGUAGES = ['Python', 'Node.js', 'Java', 'Lua', 'Deno', 'Nodemon']

# ==========================================
# 4. GIAO DIỆN HTML (Nhúng trực tiếp)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hosting Bui Van Minh</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #1a1a2e; color: white; font-family: sans-serif; }
        .bg-card { background-color: #24243e; }
        .bg-purple-grad { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .hidden { display: none !important; }
    </style>
</head>
<body class="min-h-screen flex flex-col">
    <div class="bg-black text-center py-1 text-xs text-green-400 font-mono">Đang chạy trên: {{ domain }}</div>
    
    <div class="p-4 max-w-md mx-auto w-full">
        <div class="flex justify-between items-center mb-6">
            <h1 class="text-xl font-bold text-blue-400">Hosting Bui Van Minh</h1>
            <div class="bg-gray-800 px-3 py-1 rounded-full text-yellow-400 font-bold text-sm" id="header-balance">0 xu</div>
        </div>

        <div class="bg-purple-grad rounded-xl p-5 mb-6 shadow-lg">
            <p class="text-sm opacity-80">Số dư của bạn</p>
            <h2 class="text-5xl font-bold mb-2"><span id="main-balance">0</span> <span class="text-2xl">xu</span></h2>
        </div>

        <div class="grid grid-cols-2 gap-3 mb-6">
            <button onclick="openGiftModal()" class="bg-card p-4 rounded-xl border border-gray-700">🎁 Nhập Gift</button>
            <button onclick="openStep1Modal()" class="bg-card p-4 rounded-xl border border-gray-700">➕ Tạo Tab</button>
        </div>

        <div id="admin-panel" class="hidden bg-card p-4 rounded-xl mb-6 border border-purple-500">
            <h3 class="font-bold text-purple-400 mb-2">👑 Khu Vực Admin</h3>
            <button onclick="createGift()" class="w-full bg-purple-600 py-2 rounded font-bold">Tạo Gift (Admin)</button>
            <p id="created-code" class="text-center text-green-400 font-mono mt-2 hidden"></p>
        </div>

        <div class="bg-card p-4 rounded-xl border border-gray-700">
            <h3 class="font-bold mb-3">Lịch sử giao dịch</h3>
            <div id="transaction-list" class="space-y-2 text-sm"><p class="text-gray-500">Đang tải...</p></div>
        </div>
    </div>

    <!-- Modal Gift -->
    <div id="gift-modal" class="fixed inset-0 bg-black bg-opacity-70 hidden flex items-center justify-center p-4">
        <div class="bg-card p-6 rounded-xl w-full max-w-sm">
            <h3 class="font-bold mb-4">Nhập Gift Code</h3>
            <input type="text" id="gift-code" placeholder="HB-XXXXXX" class="w-full bg-gray-800 p-3 mb-4 text-white rounded">
            <div class="flex justify-end gap-2">
                <button onclick="closeGiftModal()" class="px-4 py-2 bg-gray-600 rounded">Hủy</button>
                <button onclick="submitGift()" class="px-4 py-2 bg-blue-600 rounded font-bold">Nhận</button>
            </div>
        </div>
    </div>

    <!-- Modal Tạo Tab (Bước 1) -->
    <div id="step1-modal" class="fixed inset-0 bg-[#1a1a2e] hidden flex flex-col z-50">
        <div class="p-6 bg-[#24243e] mt-20 rounded-xl max-w-md mx-auto w-full">
            <h3 class="font-bold text-xl mb-4 text-center">CREATE SERVER</h3>
            <input type="text" id="step1-server-name" placeholder="Tên Server..." class="w-full bg-white text-black p-3 mb-4 rounded">
            <select id="step1-language" class="w-full bg-gray-800 text-white p-3 mb-4 rounded">
                {% for lang in languages %}<option value="{{ lang }}">{{ lang }}</option>{% endfor %}
            </select>
            <button onclick="goToStep2()" class="w-full bg-blue-600 py-3 rounded font-bold mb-2">Next (Tạo)</button>
            <button onclick="closeStep1Modal()" class="w-full text-gray-400 text-sm">Hủy bỏ</button>
        </div>
    </div>

    <script>
        let currentPlan = 'starter';
        async function loadData() {
            const res = await fetch('/api/user');
            if (res.status === 401) { window.location.href = '/login'; return; }
            const user = await res.json();
            document.getElementById('main-balance').innerText = user.balance;
            document.getElementById('header-balance').innerText = user.balance + ' xu';
            if(user.role === 'admin') document.getElementById('admin-panel').classList.remove('hidden');
            
            const txRes = await fetch('/api/transactions');
            const txs = await txRes.json();
            const list = document.getElementById('transaction-list');
            list.innerHTML = txs.length === 0 ? '<p class="text-gray-500">Chưa có giao dịch.</p>' : '';
            txs.forEach(tx => {
                const color = tx.amount > 0 ? 'text-green-400' : 'text-red-400';
                list.innerHTML += `<div class="flex justify-between border-b border-gray-700 pb-1"><span>${tx.action}</span><span class="${color} font-bold">${tx.amount > 0 ? '+' : ''}${tx.amount}</span></div>`;
            });
        }
        document.addEventListener('DOMContentLoaded', loadData);
        
        function openGiftModal() { document.getElementById('gift-modal').classList.remove('hidden'); }
        function closeGiftModal() { document.getElementById('gift-modal').classList.add('hidden'); }
        async function submitGift() {
            const code = document.getElementById('gift-code').value;
            const res = await fetch('/api/redeem-gift', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code}) });
            const data = await res.json(); alert(data.message);
            if (data.success) { closeGiftModal(); loadData(); }
        }
        
        async function createGift() {
            const res = await fetch('/api/admin/create-gift', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({amount: 100, maxUses: 10}) });
            const data = await res.json();
            if(data.success) { document.getElementById('created-code').innerText = `Mã: ${data.code}`; document.getElementById('created-code').classList.remove('hidden'); }
        }
        
        function openStep1Modal() { document.getElementById('step1-modal').classList.remove('hidden'); }
        function closeStep1Modal() { document.getElementById('step1-modal').classList.add('hidden'); }
        async function goToStep2() {
            const name = document.getElementById('step1-server-name').value;
            const lang = document.getElementById('step1-language').value;
            if(!name) return alert('Nhập tên!');
            const payload = { name, langId: lang, planId: currentPlan, duration: 'week' };
            const res = await fetch('/api/create-server', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json(); alert(data.message);
            if(data.success) { closeStep1Modal(); loadData(); }
        }
    </script>
</body>
</html>
"""

# ==========================================
# 5. ROUTES & APIS
# ==========================================
def get_domain():
    return f"https://{request.host}" if 'localhost' not in request.host else f"http://{request.host}"

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, domain=get_domain(), plans=PLANS, languages=LANGUAGES)

@app.route('/login')
def login():
    return discord.authorize_redirect(url_for('authorize', _external=True))

@app.route('/authorize')
def authorize():
    token = discord.authorize_access_token()
    resp = discord.get('users/@me')
    user_info = resp.json()
    user = User.query.get(user_info['id'])
    if not user:
        user = User(id=user_info['id'], username=user_info['username'], role='admin' if user_info['id'] == ADMIN_DISCORD_ID else 'user', balance=50)
        db.session.add(user); db.session.commit()
    login_user(user)
    return redirect(url_for('index'))

@app.route('/api/user')
@login_required
def get_user():
    return jsonify({"username": current_user.username, "balance": '∞' if current_user.role == 'admin' else current_user.balance, "role": current_user.role})

@app.route('/api/transactions')
@login_required
def get_transactions():
    txs = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.time.desc()).limit(10).all()
    return jsonify([{"action": t.action, "amount": t.amount} for t in txs])

@app.route('/api/create-server', methods=['POST'])
@login_required
def create_server():
    data = request.json
    is_admin = current_user.role == 'admin'
    if not is_admin:
        if current_user.balance < 10: return jsonify({"success": False, "message": "Không đủ xu!"})
        current_user.balance -= 10
        db.session.add(Transaction(user_id=current_user.id, action=f"Tạo tab {data['name']}", amount=-10))
    db.session.add(Server(user_id=current_user.id, name=data['name'], language=data['langId'], plan='starter', expires_at=datetime.utcnow() + timedelta(days=7)))
    db.session.commit()
    return jsonify({"success": True, "message": "Tạo thành công!"})

@app.route('/api/redeem-gift', methods=['POST'])
@login_required
def redeem_gift():
    gift = GiftCode.query.get(request.json.get('code'))
    if not gift or gift.current_uses >= gift.max_uses: return jsonify({"success": False, "message": "Mã sai hoặc hết lượt!"})
    current_user.balance += gift.amount
    gift.current_uses += 1
    db.session.commit()
    return jsonify({"success": True, "message": f"Nhận {gift.amount} xu!"})

@app.route('/api/admin/create-gift', methods=['POST'])
@login_required
def admin_create_gift():
    if current_user.role != 'admin': return jsonify({"success": False})
    code = f"HB-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
    db.session.add(GiftCode(code=code, amount=100, max_uses=10))
    db.session.commit()
    return jsonify({"success": True, "code": code})