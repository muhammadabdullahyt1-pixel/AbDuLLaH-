"""
Pakistan E-Commerce Platform
============================
A fully functional e-commerce website for Pakistan with:
- Seller accounts with monthly subscription and commission
- Buyer accounts for purchasing products
- Admin panel for managing the platform
- Payment simulation for EasyPaisa and JazzCash

Author: AI Assistant
Date: 2026-03-05
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3
import hashlib
import os
import json
from datetime import datetime, timedelta
from decimal import Decimal

# Initialize Flask application
app = Flask(__name__)
app.secret_key = 'pakistan_ecommerce_secure_key_2026'

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Admin credentials (hardcoded for security)
ADMIN_EMAIL = 'muhammadabdullah.yt.1@gmail.com'
ADMIN_PASSWORD = 'Abdullah.0786'

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database path
DATABASE = 'database/ecommerce.db'

# ==================== DATABASE FUNCTIONS ====================

def get_db_connection():
    """Create a database connection with row factory"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize database with all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table (Sellers and Buyers)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT,
            user_type TEXT NOT NULL CHECK(user_type IN ('seller', 'buyer')),
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'blocked')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            monthly_subscription_paid BOOLEAN DEFAULT 0,
            subscription_due_date TIMESTAMP,
            commission_paid BOOLEAN DEFAULT 1,
            commission_due_amount DECIMAL(10,2) DEFAULT 0.00,
            total_sales DECIMAL(10,2) DEFAULT 0.00,
            total_earnings DECIMAL(10,2) DEFAULT 0.00
        )
    ''')
    
    # Payment accounts for sellers (EasyPaisa, JazzCash)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_type TEXT NOT NULL CHECK(account_type IN ('easypaisa', 'jazzcash')),
            account_number TEXT NOT NULL,
            account_name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Admin payment accounts (to receive commissions)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_payment_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL CHECK(account_type IN ('easypaisa', 'jazzcash')),
            account_number TEXT NOT NULL,
            account_name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price DECIMAL(10,2) NOT NULL,
            stock INTEGER DEFAULT 0,
            category TEXT,
            image_url TEXT,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'sold_out')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            total_amount DECIMAL(10,2) NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled')),
            payment_method TEXT,
            payment_status TEXT DEFAULT 'pending' CHECK(payment_status IN ('pending', 'completed', 'failed')),
            shipping_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES users(id),
            FOREIGN KEY (seller_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    # Transactions table (for payment tracking)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('subscription', 'commission', 'sale', 'refund')),
            amount DECIMAL(10,2) NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'failed')),
            payment_method TEXT,
            reference_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Website settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default settings
    default_settings = [
        ('monthly_subscription', '200'),
        ('commission_rate', '3'),
        ('website_title', 'Pakistan E-Commerce'),
        ('website_theme', 'default'),
        ('maintenance_mode', 'false')
    ]
    
    for key, value in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)
        ''', (key, value))
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_setting(key, default=None):
    """Get website setting by key"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT setting_value FROM settings WHERE setting_key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result['setting_value'] if result else default

def update_setting(key, value):
    """Update website setting"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(setting_key) DO UPDATE SET
        setting_value = excluded.setting_value,
        updated_at = excluded.updated_at
    ''', (key, value))
    conn.commit()
    conn.close()

def calculate_monthly_sales(seller_id):
    """Calculate total sales for current month for a seller"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get first day of current month
    first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    cursor.execute('''
        SELECT COALESCE(SUM(total_amount), 0) as total_sales
        FROM orders
        WHERE seller_id = ? AND status IN ('paid', 'shipped', 'delivered')
        AND created_at >= ?
    ''', (seller_id, first_day))
    
    result = cursor.fetchone()
    conn.close()
    return float(result['total_sales']) if result else 0.0

def check_seller_payment_status(seller_id):
    """Check if seller has pending payments"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT monthly_subscription_paid, subscription_due_date,
               commission_paid, commission_due_amount
        FROM users WHERE id = ? AND user_type = 'seller'
    ''', (seller_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return {'can_login': False, 'message': 'Seller not found'}
    
    issues = []
    
    # Check monthly subscription
    if not result['monthly_subscription_paid']:
        issues.append('Monthly subscription (PKR 200) is pending')
    
    # Check subscription due date
    if result['subscription_due_date']:
        due_date = datetime.fromisoformat(result['subscription_due_date'])
        if datetime.now() > due_date and not result['monthly_subscription_paid']:
            issues.append('Subscription payment is overdue')
    
    # Check commission
    if not result['commission_paid'] and result['commission_due_amount'] > 0:
        issues.append(f"Commission payment (PKR {result['commission_due_amount']:.2f}) is pending")
    
    return {
        'can_login': len(issues) == 0,
        'message': '; '.join(issues) if issues else 'All payments clear',
        'issues': issues
    }

def update_seller_commission(seller_id):
    """Update seller's commission based on monthly sales"""
    monthly_sales = calculate_monthly_sales(seller_id)
    commission_rate = float(get_setting('commission_rate', '3'))
    commission_amount = (monthly_sales * commission_rate) / 100
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users 
        SET commission_due_amount = ?,
            commission_paid = CASE WHEN ? = 0 THEN 1 ELSE 0 END,
            total_sales = ?
        WHERE id = ?
    ''', (commission_amount, commission_amount, monthly_sales, seller_id))
    
    conn.commit()
    conn.close()

# ==================== DECORATORS ====================

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            flash('Admin access required', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def seller_required(f):
    """Decorator to require seller login with payment check"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'seller':
            flash('Seller access required', 'danger')
            return redirect(url_for('login'))
        
        # Check payment status
        payment_status = check_seller_payment_status(session['user_id'])
        if not payment_status['can_login']:
            flash(f'Payment required: {payment_status["message"]}', 'danger')
            return redirect(url_for('seller_payments'))
        
        return f(*args, **kwargs)
    return decorated_function

def buyer_required(f):
    """Decorator to require buyer login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'buyer':
            flash('Buyer access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== ROUTES ====================

# ----- Home & Public Routes -----

@app.route('/')
def index():
    """Home page with featured products"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get active products with seller info
    cursor.execute('''
        SELECT p.*, u.full_name as seller_name
        FROM products p
        JOIN users u ON p.seller_id = u.id
        WHERE p.status = 'active' AND u.status = 'approved'
        ORDER BY p.created_at DESC
        LIMIT 12
    ''')
    products = cursor.fetchall()
    conn.close()
    
    return render_template('index.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, u.full_name as seller_name
        FROM products p
        JOIN users u ON p.seller_id = u.id
        WHERE p.id = ? AND p.status = 'active'
    ''', (product_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('index'))
    
    return render_template('product_detail.html', product=product)

@app.route('/search')
def search():
    """Search products"""
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = '''
        SELECT p.*, u.full_name as seller_name
        FROM products p
        JOIN users u ON p.seller_id = u.id
        WHERE p.status = 'active' AND u.status = 'approved'
    '''
    params = []
    
    if query:
        sql += ' AND (p.name LIKE ? OR p.description LIKE ?)'
        params.extend([f'%{query}%', f'%{query}%'])
    
    if category:
        sql += ' AND p.category = ?'
        params.append(category)
    
    sql += ' ORDER BY p.created_at DESC'
    
    cursor.execute(sql, params)
    products = cursor.fetchall()
    
    # Get categories for filter
    cursor.execute('SELECT DISTINCT category FROM products WHERE status = "active"')
    categories = cursor.fetchall()
    conn.close()
    
    return render_template('search.html', products=products, query=query, 
                         categories=categories, selected_category=category)

# ----- Authentication Routes -----

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration (Seller or Buyer)"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        user_type = request.form.get('user_type')
        
        # Validation
        if not all([email, password, confirm_password, full_name, phone, user_type]):
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        if user_type not in ['seller', 'buyer']:
            flash('Invalid user type', 'danger')
            return redirect(url_for('register'))
        
        # Check if email exists
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('Email already registered', 'danger')
            conn.close()
            return redirect(url_for('register'))
        
        # Hash password
        hashed_password = hash_password(password)
        
        # Set subscription due date (30 days from now)
        subscription_due = datetime.now() + timedelta(days=30)
        
        # Insert user
        cursor.execute('''
            INSERT INTO users (email, password, full_name, phone, address, user_type, 
                             status, subscription_due_date, monthly_subscription_paid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (email, hashed_password, full_name, phone, address, user_type,
              'pending' if user_type == 'seller' else 'approved',
              subscription_due.isoformat(), False if user_type == 'seller' else True))
        
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        if user_type == 'seller':
            flash('Your seller account is pending approval. Please pay PKR 200 monthly subscription.', 'info')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email and password are required', 'danger')
            return redirect(url_for('login'))
        
        # Hash password
        hashed_password = hash_password(password)
        
        # Check credentials
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users WHERE email = ? AND password = ?
        ''', (email, hashed_password))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            flash('Invalid email or password', 'danger')
            return redirect(url_for('login'))
        
        # Check if seller is blocked
        if user['user_type'] == 'seller' and user['status'] == 'blocked':
            flash('Your account has been blocked. Contact admin.', 'danger')
            return redirect(url_for('login'))
        
        # Check if seller is approved
        if user['user_type'] == 'seller' and user['status'] == 'pending':
            flash('Your account is pending approval. Please wait for admin approval.', 'warning')
            return redirect(url_for('login'))
        
        # For sellers, check payment status
        if user['user_type'] == 'seller':
            payment_status = check_seller_payment_status(user['id'])
            if not payment_status['can_login']:
                session['user_id'] = user['id']
                session['user_type'] = user['user_type']
                session['user_name'] = user['full_name']
                session['payment_pending'] = True
                flash(f'Payment required: {payment_status["message"]}', 'danger')
                return redirect(url_for('seller_payments'))
        
        # Set session
        session['user_id'] = user['id']
        session['user_type'] = user['user_type']
        session['user_name'] = user['full_name']
        
        flash(f'Welcome back, {user["full_name"]}!', 'success')
        
        # Redirect based on user type
        if user['user_type'] == 'seller':
            return redirect(url_for('seller_dashboard'))
        else:
            return redirect(url_for('buyer_dashboard'))
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# ----- Admin Routes -----

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['admin'] = True
            session['admin_email'] = email
            flash('Welcome, Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'danger')
    
    return render_template('auth/admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin', None)
    session.pop('admin_email', None)
    flash('Admin logged out', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Statistics
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE user_type = "seller"')
    total_sellers = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE user_type = "seller" AND status = "pending"')
    pending_sellers = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE user_type = "buyer"')
    total_buyers = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM products')
    total_products = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM orders')
    total_orders = cursor.fetchone()['count']
    
    cursor.execute('''
        SELECT COALESCE(SUM(total_amount), 0) as total FROM orders 
        WHERE payment_status = 'completed'
    ''')
    total_revenue = cursor.fetchone()['total']
    
    # Recent sellers pending approval
    cursor.execute('''
        SELECT * FROM users WHERE user_type = 'seller' AND status = 'pending'
        ORDER BY created_at DESC LIMIT 10
    ''')
    pending_sellers_list = cursor.fetchall()
    
    # Recent transactions
    cursor.execute('''
        SELECT t.*, u.full_name, u.email
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC LIMIT 10
    ''')
    recent_transactions = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin/dashboard.html',
                         total_sellers=total_sellers,
                         pending_sellers=pending_sellers,
                         total_buyers=total_buyers,
                         total_products=total_products,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         pending_sellers_list=pending_sellers_list,
                         recent_transactions=recent_transactions)

@app.route('/admin/sellers')
@admin_required
def admin_sellers():
    """Manage all sellers"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    status_filter = request.args.get('status', '')
    
    sql = 'SELECT * FROM users WHERE user_type = "seller"'
    params = []
    
    if status_filter:
        sql += ' AND status = ?'
        params.append(status_filter)
    
    sql += ' ORDER BY created_at DESC'
    
    cursor.execute(sql, params)
    sellers = cursor.fetchall()
    conn.close()
    
    return render_template('admin/sellers.html', sellers=sellers, status_filter=status_filter)

@app.route('/admin/seller/<int:seller_id>/<action>')
@admin_required
def admin_seller_action(seller_id, action):
    """Approve or block seller"""
    if action not in ['approve', 'block']:
        flash('Invalid action', 'danger')
        return redirect(url_for('admin_sellers'))
    
    new_status = 'approved' if action == 'approve' else 'blocked'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET status = ? WHERE id = ? AND user_type = "seller"',
                   (new_status, seller_id))
    conn.commit()
    conn.close()
    
    flash(f'Seller {action}d successfully', 'success')
    return redirect(url_for('admin_sellers'))

@app.route('/admin/payment-accounts', methods=['GET', 'POST'])
@admin_required
def admin_payment_accounts():
    """Manage admin payment accounts"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        account_type = request.form.get('account_type')
        account_number = request.form.get('account_number')
        account_name = request.form.get('account_name')
        
        cursor.execute('''
            INSERT INTO admin_payment_accounts (account_type, account_number, account_name)
            VALUES (?, ?, ?)
        ''', (account_type, account_number, account_name))
        conn.commit()
        flash('Payment account added successfully', 'success')
    
    cursor.execute('SELECT * FROM admin_payment_accounts ORDER BY created_at DESC')
    accounts = cursor.fetchall()
    conn.close()
    
    return render_template('admin/payment_accounts.html', accounts=accounts)

@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    """Website settings"""
    if request.method == 'POST':
        monthly_subscription = request.form.get('monthly_subscription')
        commission_rate = request.form.get('commission_rate')
        website_title = request.form.get('website_title')
        website_theme = request.form.get('website_theme')
        
        update_setting('monthly_subscription', monthly_subscription)
        update_setting('commission_rate', commission_rate)
        update_setting('website_title', website_title)
        update_setting('website_theme', website_theme)
        
        flash('Settings updated successfully', 'success')
        return redirect(url_for('admin_settings'))
    
    settings = {
        'monthly_subscription': get_setting('monthly_subscription', '200'),
        'commission_rate': get_setting('commission_rate', '3'),
        'website_title': get_setting('website_title', 'Pakistan E-Commerce'),
        'website_theme': get_setting('website_theme', 'default')
    }
    
    return render_template('admin/settings.html', settings=settings)

@app.route('/admin/transactions')
@admin_required
def admin_transactions():
    """View all transactions"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.*, u.full_name, u.email, u.user_type
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
    ''')
    transactions = cursor.fetchall()
    conn.close()
    
    return render_template('admin/transactions.html', transactions=transactions)

# ----- Seller Routes -----

@app.route('/seller/dashboard')
@login_required
def seller_dashboard():
    """Seller dashboard"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    # Check payment status
    payment_status = check_seller_payment_status(session['user_id'])
    if not payment_status['can_login']:
        flash(f'Payment required: {payment_status["message"]}', 'danger')
        return redirect(url_for('seller_payments'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get seller info
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    seller = cursor.fetchone()
    
    # Get products count
    cursor.execute('SELECT COUNT(*) as count FROM products WHERE seller_id = ?', 
                   (session['user_id'],))
    products_count = cursor.fetchone()['count']
    
    # Get orders
    cursor.execute('''
        SELECT COUNT(*) as count FROM orders WHERE seller_id = ?
    ''', (session['user_id'],))
    orders_count = cursor.fetchone()['count']
    
    # Get monthly sales
    monthly_sales = calculate_monthly_sales(session['user_id'])
    
    # Get recent orders
    cursor.execute('''
        SELECT o.*, p.name as product_name, u.full_name as buyer_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        JOIN users u ON o.buyer_id = u.id
        WHERE o.seller_id = ?
        ORDER BY o.created_at DESC LIMIT 5
    ''', (session['user_id'],))
    recent_orders = cursor.fetchall()
    
    conn.close()
    
    return render_template('seller/dashboard.html',
                         seller=seller,
                         products_count=products_count,
                         orders_count=orders_count,
                         monthly_sales=monthly_sales,
                         recent_orders=recent_orders,
                         payment_status=payment_status)

@app.route('/seller/products')
@login_required
def seller_products():
    """Seller products management"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products WHERE seller_id = ? ORDER BY created_at DESC
    ''', (session['user_id'],))
    products = cursor.fetchall()
    conn.close()
    
    return render_template('seller/products.html', products=products)

@app.route('/seller/product/add', methods=['GET', 'POST'])
@login_required
def seller_add_product():
    """Add new product"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock = request.form.get('stock', 0)
        category = request.form.get('category')
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f"uploads/{filename}"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (seller_id, name, description, price, stock, category, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], name, description, price, stock, category, image_url))
        conn.commit()
        conn.close()
        
        flash('Product added successfully', 'success')
        return redirect(url_for('seller_products'))
    
    return render_template('seller/add_product.html')

@app.route('/seller/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def seller_edit_product(product_id):
    """Edit product"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM products WHERE id = ? AND seller_id = ?',
                   (product_id, session['user_id']))
    product = cursor.fetchone()
    
    if not product:
        flash('Product not found', 'danger')
        conn.close()
        return redirect(url_for('seller_products'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock = request.form.get('stock')
        category = request.form.get('category')
        status = request.form.get('status')
        
        # Handle image upload
        image_url = product['image_url']
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f"uploads/{filename}"
        
        cursor.execute('''
            UPDATE products 
            SET name = ?, description = ?, price = ?, stock = ?, 
                category = ?, status = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, description, price, stock, category, status, image_url, product_id))
        conn.commit()
        flash('Product updated successfully', 'success')
        return redirect(url_for('seller_products'))
    
    conn.close()
    return render_template('seller/edit_product.html', product=product)

@app.route('/seller/product/delete/<int:product_id>')
@login_required
def seller_delete_product(product_id):
    """Delete product"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ? AND seller_id = ?',
                   (product_id, session['user_id']))
    conn.commit()
    conn.close()
    
    flash('Product deleted successfully', 'success')
    return redirect(url_for('seller_products'))

@app.route('/seller/payment-accounts', methods=['GET', 'POST'])
@login_required
def seller_payment_accounts():
    """Manage seller payment accounts"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        account_type = request.form.get('account_type')
        account_number = request.form.get('account_number')
        account_name = request.form.get('account_name')
        
        cursor.execute('''
            INSERT INTO payment_accounts (user_id, account_type, account_number, account_name)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], account_type, account_number, account_name))
        conn.commit()
        flash('Payment account added successfully', 'success')
    
    cursor.execute('''
        SELECT * FROM payment_accounts WHERE user_id = ? ORDER BY created_at DESC
    ''', (session['user_id'],))
    accounts = cursor.fetchall()
    conn.close()
    
    return render_template('seller/payment_accounts.html', accounts=accounts)

@app.route('/seller/payments')
@login_required
def seller_payments():
    """Seller payments page"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get seller info
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    seller = cursor.fetchone()
    
    # Get admin payment accounts
    cursor.execute('SELECT * FROM admin_payment_accounts WHERE is_active = 1')
    admin_accounts = cursor.fetchall()
    
    # Get payment history
    cursor.execute('''
        SELECT * FROM transactions 
        WHERE user_id = ? AND transaction_type IN ('subscription', 'commission')
        ORDER BY created_at DESC
    ''', (session['user_id'],))
    payment_history = cursor.fetchall()
    
    conn.close()
    
    # Calculate pending amounts
    monthly_subscription = float(get_setting('monthly_subscription', '200'))
    commission_due = seller['commission_due_amount'] if seller['commission_due_amount'] else 0
    
    payment_status = check_seller_payment_status(session['user_id'])
    
    return render_template('seller/payments.html',
                         seller=seller,
                         admin_accounts=admin_accounts,
                         payment_history=payment_history,
                         monthly_subscription=monthly_subscription,
                         commission_due=commission_due,
                         payment_status=payment_status)

@app.route('/seller/pay-subscription', methods=['POST'])
@login_required
def seller_pay_subscription():
    """Process subscription payment (simulated)"""
    if session.get('user_type') != 'seller':
        return jsonify({'success': False, 'message': 'Seller access required'})
    
    payment_method = request.form.get('payment_method')
    admin_account_id = request.form.get('admin_account_id')
    
    # Simulate payment processing
    conn = get_db_connection()
    cursor = conn.cursor()
    
    monthly_subscription = float(get_setting('monthly_subscription', '200'))
    
    # Create transaction record
    cursor.execute('''
        INSERT INTO transactions (user_id, transaction_type, amount, description, 
                                status, payment_method, reference_number)
        VALUES (?, 'subscription', ?, 'Monthly subscription payment', 
                'completed', ?, ?)
    ''', (session['user_id'], monthly_subscription, payment_method,
          f'SUB{datetime.now().strftime("%Y%m%d%H%M%S")}'))
    
    # Update seller subscription status
    new_due_date = datetime.now() + timedelta(days=30)
    cursor.execute('''
        UPDATE users 
        SET monthly_subscription_paid = 1,
            subscription_due_date = ?
        WHERE id = ?
    ''', (new_due_date.isoformat(), session['user_id']))
    
    conn.commit()
    conn.close()
    
    flash('Subscription payment successful!', 'success')
    return redirect(url_for('seller_payments'))

@app.route('/seller/pay-commission', methods=['POST'])
@login_required
def seller_pay_commission():
    """Process commission payment (simulated)"""
    if session.get('user_type') != 'seller':
        return jsonify({'success': False, 'message': 'Seller access required'})
    
    payment_method = request.form.get('payment_method')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT commission_due_amount FROM users WHERE id = ?',
                   (session['user_id'],))
    seller = cursor.fetchone()
    commission_amount = seller['commission_due_amount'] if seller else 0
    
    if commission_amount > 0:
        # Create transaction record
        cursor.execute('''
            INSERT INTO transactions (user_id, transaction_type, amount, description, 
                                    status, payment_method, reference_number)
            VALUES (?, 'commission', ?, 'Monthly commission payment', 
                    'completed', ?, ?)
        ''', (session['user_id'], commission_amount, payment_method,
              f'COM{datetime.now().strftime("%Y%m%d%H%M%S")}'))
        
        # Update seller commission status
        cursor.execute('''
            UPDATE users 
            SET commission_paid = 1,
                commission_due_amount = 0
            WHERE id = ?
        ''', (session['user_id'],))
        
        conn.commit()
        flash('Commission payment successful!', 'success')
    
    conn.close()
    return redirect(url_for('seller_payments'))

@app.route('/seller/orders')
@login_required
def seller_orders():
    """View seller orders"""
    if session.get('user_type') != 'seller':
        flash('Seller access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.*, p.name as product_name, p.image_url, u.full_name as buyer_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        JOIN users u ON o.buyer_id = u.id
        WHERE o.seller_id = ?
        ORDER BY o.created_at DESC
    ''', (session['user_id'],))
    orders = cursor.fetchall()
    conn.close()
    
    return render_template('seller/orders.html', orders=orders)

@app.route('/seller/order/update/<int:order_id>', methods=['POST'])
@login_required
def seller_update_order(order_id):
    """Update order status"""
    if session.get('user_type') != 'seller':
        return jsonify({'success': False, 'message': 'Seller access required'})
    
    new_status = request.form.get('status')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND seller_id = ?
    ''', (new_status, order_id, session['user_id']))
    
    conn.commit()
    conn.close()
    
    flash('Order status updated', 'success')
    return redirect(url_for('seller_orders'))

# ----- Buyer Routes -----

@app.route('/buyer/dashboard')
@login_required
def buyer_dashboard():
    """Buyer dashboard"""
    if session.get('user_type') != 'buyer':
        flash('Buyer access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get buyer orders
    cursor.execute('''
        SELECT o.*, p.name as product_name, p.image_url, u.full_name as seller_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        JOIN users u ON o.seller_id = u.id
        WHERE o.buyer_id = ?
        ORDER BY o.created_at DESC
    ''', (session['user_id'],))
    orders = cursor.fetchall()
    
    conn.close()
    
    return render_template('buyer/dashboard.html', orders=orders)

@app.route('/buyer/order/<int:product_id>', methods=['GET', 'POST'])
@login_required
def buyer_order(product_id):
    """Place order for a product"""
    if session.get('user_type') != 'buyer':
        flash('Buyer access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, u.full_name as seller_name
        FROM products p
        JOIN users u ON p.seller_id = u.id
        WHERE p.id = ? AND p.status = 'active'
    ''', (product_id,))
    product = cursor.fetchone()
    
    if not product:
        flash('Product not found', 'danger')
        conn.close()
        return redirect(url_for('index'))
    
    # Get seller payment accounts
    cursor.execute('''
        SELECT * FROM payment_accounts 
        WHERE user_id = ? AND is_active = 1
    ''', (product['seller_id'],))
    seller_accounts = cursor.fetchall()
    
    if request.method == 'POST':
        quantity = int(request.form.get('quantity', 1))
        shipping_address = request.form.get('shipping_address')
        payment_method = request.form.get('payment_method')
        
        total_amount = float(product['price']) * quantity
        
        # Create order
        cursor.execute('''
            INSERT INTO orders (buyer_id, seller_id, product_id, quantity, total_amount,
                              status, payment_method, shipping_address)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        ''', (session['user_id'], product['seller_id'], product_id, 
              quantity, total_amount, payment_method, shipping_address))
        
        order_id = cursor.lastrowid
        
        # Update product stock
        cursor.execute('''
            UPDATE products SET stock = stock - ? WHERE id = ?
        ''', (quantity, product_id))
        
        conn.commit()
        conn.close()
        
        flash('Order placed successfully! Please complete payment.', 'success')
        return redirect(url_for('buyer_order_payment', order_id=order_id))
    
    conn.close()
    return render_template('buyer/place_order.html', 
                         product=product, 
                         seller_accounts=seller_accounts)

@app.route('/buyer/order/payment/<int:order_id>')
@login_required
def buyer_order_payment(order_id):
    """Payment page for order"""
    if session.get('user_type') != 'buyer':
        flash('Buyer access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.*, p.name as product_name, p.image_url, u.full_name as seller_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        JOIN users u ON o.seller_id = u.id
        WHERE o.id = ? AND o.buyer_id = ?
    ''', (order_id, session['user_id']))
    order = cursor.fetchone()
    
    if not order:
        flash('Order not found', 'danger')
        conn.close()
        return redirect(url_for('buyer_dashboard'))
    
    # Get seller payment accounts
    cursor.execute('''
        SELECT * FROM payment_accounts 
        WHERE user_id = ? AND is_active = 1
    ''', (order['seller_id'],))
    seller_accounts = cursor.fetchall()
    
    conn.close()
    
    return render_template('buyer/payment.html', 
                         order=order, 
                         seller_accounts=seller_accounts)

@app.route('/buyer/order/complete-payment/<int:order_id>', methods=['POST'])
@login_required
def buyer_complete_payment(order_id):
    """Complete payment for order (simulated)"""
    if session.get('user_type') != 'buyer':
        return jsonify({'success': False, 'message': 'Buyer access required'})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM orders WHERE id = ? AND buyer_id = ?
    ''', (order_id, session['user_id']))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        flash('Order not found', 'danger')
        return redirect(url_for('buyer_dashboard'))
    
    # Simulate payment completion
    cursor.execute('''
        UPDATE orders 
        SET payment_status = 'completed', status = 'paid',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (order_id,))
    
    # Create transaction record for seller
    cursor.execute('''
        INSERT INTO transactions (user_id, transaction_type, amount, description, 
                                status, payment_method, reference_number)
        VALUES (?, 'sale', ?, 'Product sale', 'completed', ?, ?)
    ''', (order['seller_id'], order['total_amount'], order['payment_method'],
          f'SALE{datetime.now().strftime("%Y%m%d%H%M%S")}'))
    
    # Update seller earnings
    cursor.execute('''
        UPDATE users 
        SET total_earnings = total_earnings + ?
        WHERE id = ?
    ''', (order['total_amount'], order['seller_id']))
    
    # Update seller commission
    update_seller_commission(order['seller_id'])
    
    conn.commit()
    conn.close()
    
    flash('Payment completed successfully!', 'success')
    return redirect(url_for('buyer_dashboard'))

@app.route('/buyer/orders')
@login_required
def buyer_orders():
    """View all buyer orders"""
    if session.get('user_type') != 'buyer':
        flash('Buyer access required', 'danger')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.*, p.name as product_name, p.image_url, u.full_name as seller_name
        FROM orders o
        JOIN products p ON o.product_id = p.id
        JOIN users u ON o.seller_id = u.id
        WHERE o.buyer_id = ?
        ORDER BY o.created_at DESC
    ''', (session['user_id'],))
    orders = cursor.fetchall()
    conn.close()
    
    return render_template('buyer/orders.html', orders=orders)

# ----- API Routes -----

@app.route('/api/categories')
def api_categories():
    """Get all product categories"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT category FROM products WHERE status = "active"')
    categories = [row['category'] for row in cursor.fetchall() if row['category']]
    conn.close()
    return jsonify(categories)

@app.route('/api/products')
def api_products():
    """Get products API"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, u.full_name as seller_name
        FROM products p
        JOIN users u ON p.seller_id = u.id
        WHERE p.status = 'active' AND u.status = 'approved'
        ORDER BY p.created_at DESC
    ''')
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(products)

# ==================== MAIN ====================

if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Run the application
    print("=" * 60)
    print("Pakistan E-Commerce Platform")
    print("=" * 60)
    print("Access the website at: http://localhost:5000")
    print("Admin Login: http://localhost:5000/admin/login")
    print("Admin Email:", ADMIN_EMAIL)
    print("Admin Password:", ADMIN_PASSWORD)
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
