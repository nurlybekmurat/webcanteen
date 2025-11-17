import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
from datetime import timedelta
from datetime import datetime

# --- Конфигурация Flask и Расширений ---
app = Flask(__name__, static_folder='static', template_folder='templates')

app.config['SECRET_KEY'] = 'your_super_secret_key_change_this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'cantean.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class QueueEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="waiting")

login_manager = LoginManager(app)
login_manager.login_view = 'index'
login_manager.login_message = 'Пожалуйста, войдите, чтобы получить доступ к этой странице.'
login_manager.login_message_category = 'info'


# ----------------------------------------

# --- Декоратор для Администратора ---
def admin_required(f):
    """Декоратор для проверки прав администратора."""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("У вас нет прав администратора для доступа к этой странице.", 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


# --- Модели Базы Данных (SQLAlchemy) ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --- ФУНКЦИЯ ИНИЦИАЛИЗАЦИИ МЕНЮ И АДМИНА ---
def create_initial_data():
    """Создает начальные данные: администратора и меню."""
    # 1. Администратор: логин 'admin', пароль '1234'
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', email='admin@canteen.kz', is_admin=True)
        admin.set_password('1234')
        db.session.add(admin)
        print("Администратор 'admin' создан с паролем '1234'")

    # 2. Начальное меню (цены в тенге ₸)
    if not MenuItem.query.first():
        initial_menu = [
            {"name": "Борщ с говядиной", "price": 1500.00},
            {"name": "Плов 'Узбекский'", "price": 2800.00},
            {"name": "Салат Цезарь", "price": 1800.00},
            {"name": "Компот из сухофруктов", "price": 500.00},
            {"name": "Хлеб белый", "price": 100.00},
        ]
        for item_data in initial_menu:
            db.session.add(MenuItem(**item_data))
        print("Начальное меню добавлено в БД")

    db.session.commit()


# ----------------------------------------


# --- Маршруты (Routes) ---

@app.route("/")
def index():
    menu = MenuItem.query.all()

    queue = (
        QueueEntry.query
        .filter_by(status="waiting")
        .order_by(QueueEntry.created_at.asc())
        .all()
    )

    for q in queue:
        q.local_time = q.created_at + timedelta(hours=5)

    return render_template("index.html", menu=menu, queue=queue)


@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    """Добавление товара в корзину (с учетом количества)."""
    item = MenuItem.query.get(item_id)
    # Используем request.form.get, чтобы получить количество из формы index.html
    try:
        quantity_to_add = int(request.form.get('quantity', 1))
    except ValueError:
        flash('Неверное количество.', 'danger')
        return redirect(url_for('index'))

    if item and quantity_to_add > 0:
        cart = session.get('cart', {})
        # Используем ID как ключ и увеличиваем количество
        current_quantity = cart.get(str(item_id), 0)
        cart[str(item_id)] = current_quantity + quantity_to_add
        session['cart'] = cart
        flash(f'"{item.name}" ({quantity_to_add} шт.) добавлен в корзину!', 'success')
    else:
        flash('Невозможно добавить этот товар в корзину!', 'danger')

    return redirect(url_for('index'))

@app.route("/queue/<int:entry_id>/done", methods=["POST"])
def queue_done(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)
    entry.status = "done"
    db.session.commit()
    return redirect(url_for("admin_panel"))

@app.route('/cart')
def view_cart():
    """Просмотр корзины."""
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0

    for item_id_str, quantity in cart.items():
        item_id = int(item_id_str)
        item_data = MenuItem.query.get(item_id)

        if item_data:
            subtotal = item_data.price * quantity
            total_price += subtotal
            cart_items.append({
                'id': item_id,
                'name': item_data.name,
                'price': item_data.price,
                'quantity': quantity,
                'subtotal': subtotal
            })

    return render_template('cart.html', cart_items=cart_items, total_price=total_price)


@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    flash('Корзина очищена!', 'warning')
    return redirect(url_for('view_cart'))


# --- Аутентификация (через Модальные окна) ---

@app.route('/handle_register', methods=['POST'])
def handle_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')

    user_exists = User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first()

    if user_exists:
        flash('Пользователь с таким именем или Email уже существует.', 'danger')
    else:
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        flash('Регистрация прошла успешно! Вы вошли в систему.', 'success')

    return redirect(url_for('index'))


@app.route('/handle_login', methods=['POST'])
def handle_login():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    username = request.form.get('username')
    password = request.form.get('password')

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        login_user(user, remember=True)
        flash('Вы успешно вошли!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('profile'))
    else:
        flash('Неверное имя пользователя или пароль.', 'danger')
        return redirect(url_for('index'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'success')
    return redirect(url_for('index'))


# --- Личный Кабинет ---

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Обновление личной информации
        current_user.address = request.form.get('address')
        current_user.phone = request.form.get('phone')

        new_email = request.form.get('email')
        if new_email and new_email != current_user.email:
            if User.query.filter_by(email=new_email).first() and User.query.filter_by(
                    email=new_email).first().id != current_user.id:
                flash('Этот Email уже занят.', 'danger')
                return redirect(url_for('profile'))
            current_user.email = new_email

        db.session.commit()
        flash('Личная информация обновлена!', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html')


@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')

    if not current_user.check_password(old_password):
        flash('Неверный старый пароль.', 'danger')
    elif len(new_password) < 6:
        flash('Новый пароль должен содержать минимум 6 символов.', 'danger')
    else:
        current_user.set_password(new_password)
        db.session.commit()
        flash('Пароль успешно изменен!', 'success')

    return redirect(url_for('profile'))


@app.route('/profile/payment_methods', methods=['POST'])
@login_required
def payment_methods():
    card_number = request.form.get('card_number')
    expiry_date = request.form.get('expiry_date')

    if card_number and expiry_date:
        # В реальном приложении: НИКОГДА НЕ ХРАНИТЕ НОМЕРА КАРТ. Используйте токены.
        flash(f'Способ оплаты (карта заканчивается на **{card_number[-4:]}) добавлен!', 'success')
    else:
        flash('Пожалуйста, заполните данные карты.', 'danger')

    return redirect(url_for('profile'))

@app.route("/pay", methods=["POST"])
def pay():
    customer_name = request.form.get("name")

    payment_success = True

    if not payment_success:
        flash("Оплата не прошла, попробуйте ещё раз", "danger")
        return redirect(url_for("cart"))

    entry = QueueEntry(name=customer_name)
    db.session.add(entry)
    db.session.commit()

    position = (
        QueueEntry.query
        .filter(QueueEntry.status == "waiting", QueueEntry.id <= entry.id)
        .count()
    )

    session["cart"] = {}
    session.modified = True

    return redirect(url_for("payment_success", entry_id=entry.id, pos=position))

@app.route("/success")
def payment_success():
    entry_id = request.args.get("entry_id", type=int)
    pos = request.args.get("pos", type=int)

    entry = QueueEntry.query.get(entry_id)
    if entry is None:
        return render_template("success.html", entry=None, position=None)

    return render_template("success.html", entry=entry, position=pos)

# --- АДМИНИСТРИРОВАНИЕ МЕНЮ ---

@app.route('/admin')
@admin_required
def admin_panel():
    """Панель администратора: просмотр меню."""
    menu = MenuItem.query.all()
    queue_waiting = (
        QueueEntry.query
        .filter_by(status="waiting")
        .order_by(QueueEntry.created_at.asc())
        .all()
    )

    queue_done = (
        QueueEntry.query
        .filter_by(status="done")
        .order_by(QueueEntry.created_at.desc())
        .limit(20)   # последние 20 обслуженных
        .all()
    )

    return render_template(
        "admin_panel.html",
        menu=menu,
        queue_waiting=queue_waiting,
        queue_done=queue_done,
        timedelta=timedelta,
    )



@app.route('/admin/add', methods=['POST'])
@admin_required
def admin_add_item():
    """Добавление новой позиции в меню."""
    name = request.form.get('name')
    try:
        price = float(request.form.get('price'))
    except (TypeError, ValueError):
        flash('Неверный формат цены.', 'danger')
        return redirect(url_for('admin_panel'))

    if name and price > 0:
        new_item = MenuItem(name=name, price=price)
        db.session.add(new_item)
        db.session.commit()
        flash(f'Позиция "{name}" успешно добавлена!', 'success')
    else:
        flash('Название и цена должны быть указаны.', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/admin/delete/<int:item_id>', methods=['POST'])
@admin_required
def admin_delete_item(item_id):
    """Удаление позиции из меню."""
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash(f'Позиция "{item.name}" удалена.', 'warning')
    return redirect(url_for('admin_panel'))


@app.route('/admin/edit/<int:item_id>', methods=['POST'])
@admin_required
def admin_edit_item(item_id):
    """Редактирование существующей позиции меню."""
    item = MenuItem.query.get_or_404(item_id)
    name = request.form.get('name')
    try:
        price = float(request.form.get('price'))
    except (TypeError, ValueError):
        flash('Неверный формат цены.', 'danger')
        return redirect(url_for('admin_panel'))

    if name and price > 0:
        item.name = name
        item.price = price
        db.session.commit()
        flash(f'Позиция "{name}" обновлена.', 'success')
    else:
        flash('Название и цена не могут быть пустыми.', 'danger')

    return redirect(url_for('admin_panel'))

@app.route("/admin/queue/<int:entry_id>/done", methods=["POST"])
def queue_mark_done(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)
    entry.status = "done"
    db.session.commit()
    flash(f"Клиент #{entry.id} отмечен как обслуженный.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/queue/<int:entry_id>/restore", methods=["POST"])
def queue_restore(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)
    entry.status = "waiting"
    db.session.commit()
    flash(f"Клиент #{entry.id} возвращён в очередь.", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/queue/<int:entry_id>/delete", methods=["POST"])
def queue_delete(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash(f"Запись #{entry.id} удалена из очереди.", "warning")
    return redirect(url_for("admin_panel"))

# --- Запуск Приложения ---
if __name__ == '__main__':
    with app.app_context():
        # Создание таблиц и начальных данных (администратора и меню)
        db.create_all()
        create_initial_data()
    app.run(debug=True)