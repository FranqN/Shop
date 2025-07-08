from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime, date
from sqlalchemy import func
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///duka_yetu.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/images'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='cashier')  # admin, owner, cashier

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=0)
    buying_price = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    barcode = db.Column(db.String(100), unique=True)
    image = db.Column(db.String(100))
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity_sold = db.Column(db.Integer)
    total_price = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def role_required(*roles):
    def wrapper(fn):
        @login_required
        def decorated_view(*args, **kwargs):
            if current_user.role not in roles:
                flash("Access denied.")
                return redirect(url_for('dashboard'))
            return fn(*args, **kwargs)
        decorated_view.__name__ = fn.__name__
        return decorated_view
    return wrapper

@app.route('/')
@login_required
def dashboard():
    today = date.today()
    start_of_month = today.replace(day=1)

    daily_sales = db.session.query(func.sum(Sale.total_price)).filter(func.date(Sale.timestamp) == today).scalar() or 0
    monthly_sales = db.session.query(func.sum(Sale.total_price)).filter(Sale.timestamp >= start_of_month).scalar() or 0

    top_products = db.session.query(
        Product.name, func.sum(Sale.quantity_sold).label('total_sold')
    ).join(Sale.product).group_by(Product.name).order_by(func.sum(Sale.quantity_sold).desc()).limit(5).all()

    bottom_products = db.session.query(
        Product.name, func.sum(Sale.quantity_sold).label('total_sold')
    ).join(Sale.product).group_by(Product.name).order_by(func.sum(Sale.quantity_sold).asc()).limit(5).all()

    return render_template('dashboard.html',
                           daily_sales=daily_sales,
                           monthly_sales=monthly_sales,
                           top_products=top_products,
                           bottom_products=bottom_products)

@app.route('/sales_summary')
@login_required
def sales_summary():
    today = date.today()
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)
    quarter = (today.month - 1) // 3 + 1
    start_of_quarter = date(today.year, (quarter - 1) * 3 + 1, 1)

    sales_today = db.session.query(func.sum(Sale.total_price)).filter(func.date(Sale.timestamp) == today).scalar() or 0
    sales_month = db.session.query(func.sum(Sale.total_price)).filter(Sale.timestamp >= start_of_month).scalar() or 0
    sales_quarter = db.session.query(func.sum(Sale.total_price)).filter(Sale.timestamp >= start_of_quarter).scalar() or 0
    sales_year = db.session.query(func.sum(Sale.total_price)).filter(Sale.timestamp >= start_of_year).scalar() or 0

    recent_sales = Sale.query.order_by(Sale.timestamp.desc()).limit(20).all()

    return render_template('sales_summary.html',
                           sales_today=sales_today,
                           sales_month=sales_month,
                           sales_quarter=sales_quarter,
                           sales_year=sales_year,
                           recent_sales=recent_sales,
                           now=datetime.now)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            flash(f"Welcome {user.username} ({user.role})")
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        confirm = request.form['confirm_password']
        if password != confirm:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        new_user = User(username=username, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_product', methods=['GET', 'POST'])
@role_required('admin', 'owner')
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        quantity = int(request.form['quantity'])
        buying_price = float(request.form['buying_price'])
        selling_price = float(request.form['selling_price'])
        barcode = request.form['barcode']
        image = request.files['image']

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
        image.save(image_path)

        product = Product(name=name, category=category, quantity=quantity,
                          buying_price=buying_price, selling_price=selling_price,
                          barcode=barcode, image=image.filename)
        db.session.add(product)
        db.session.commit()
        flash('Product added')
        return redirect(url_for('all_products'))
    return render_template('add_product.html')

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@role_required('admin', 'owner')
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.category = request.form['category']
        product.quantity = int(request.form['quantity'])
        product.buying_price = float(request.form['buying_price'])
        product.selling_price = float(request.form['selling_price'])
        product.barcode = request.form['barcode']

        image = request.files.get('image')
        if image:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            image.save(image_path)
            product.image = image.filename

        db.session.commit()
        flash('Product updated successfully.')
        return redirect(url_for('all_products'))

    return render_template('edit_product.html', product=product)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@role_required('admin', 'owner')
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully.')
    return redirect(url_for('all_products'))

@app.route('/products')
@login_required
def all_products():
    products = Product.query.order_by(Product.name).all()
    return render_template('all_products.html', products=products)

@app.route('/register_sale', methods=['GET', 'POST'])
@login_required
def register_sale():
    if request.method == 'POST':
        barcode = request.form['barcode']
        quantity = int(request.form['quantity'])
        product = Product.query.filter_by(barcode=barcode).first()
        if product and product.quantity >= quantity:
            total = product.selling_price * quantity
            sale = Sale(product_id=product.id, quantity_sold=quantity, total_price=total)
            product.quantity -= quantity
            db.session.add(sale)
            db.session.commit()
            flash(f"✅ Sale registered for {product.name} - {quantity} item(s) sold.")
            return redirect(url_for('register_sale'))
        elif product:
            flash(f"❌ Only {product.quantity} item(s) left in stock for {product.name}.")
        else:
            flash("❌ Product with the given barcode not found.")

    products = Product.query.filter(Product.quantity > 0).order_by(Product.name).all()
    return render_template('register_sale.html', products=products)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')