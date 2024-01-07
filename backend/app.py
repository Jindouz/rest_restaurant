# Import necessary modules
from flask import Flask, request, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
import os
import time
import uuid

# Create Flask app
app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key'
bcrypt = Bcrypt(app)

# Configure Flask-Uploads
app.config['UPLOAD_FOLDER'] = 'static/img'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Configure Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Define User model
class Users(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    @classmethod
    def register(cls, username, password):
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = cls(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        return user


# Define Recipe model
class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    ingredients = db.Column(db.Text, nullable=False)
    prep_time = db.Column(db.String(50), nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_recipe_user'), nullable=False)
    user = db.relationship('Users', backref=db.backref('recipes', lazy=True))


#===========

@login_manager.user_loader
def load_user(user_id_or_username):
    user = Users.query.filter((Users.id == int(user_id_or_username)) | (Users.username == user_id_or_username)).first()
    return user


@app.route('/login', methods=['POST'])
def login():
    identifier = request.form.get('identifier')  # This can be either username or user ID
    password = request.form.get('password')

    user = Users.query.filter((Users.id == int(identifier)) | (Users.username == identifier)).first()

    if user and bcrypt.check_password_hash(user.password, password):
        login_user(user)
        return jsonify({'message': 'Login successful'})
    else:
        return jsonify({'error': 'Invalid username or password'}), 401



@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')

    if Users.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    Users.register(username, password)
    return jsonify({'message': 'Registration successful'})


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logout successful'})



#=============

# REST API endpoints
@app.route('/api/recipes', methods=['GET'])
@login_required
def get_recipes():
    recipes = Recipe.query.all()
    recipe_list = [{'id': recipe.id, 'name': recipe.name, 'ingredients': recipe.ingredients,
                    'prep_time': recipe.prep_time, 'image_path': recipe.image_path} for recipe in recipes]
    return jsonify(recipe_list)

@app.route('/api/recipes/<int:id>', methods=['GET'])
@login_required
def get_recipe_by_id(id):
    recipe = Recipe.query.get_or_404(id)
    return jsonify({'id': recipe.id, 'name': recipe.name, 'ingredients': recipe.ingredients,
                    'prep_time': recipe.prep_time, 'image_path': recipe.image_path})

@app.route('/api/recipes', methods=['POST'])
@login_required
def add_recipe():
    name = request.form.get('name')
    ingredients = request.form.get('ingredients')
    prep_time = request.form.get('prep_time')

    if 'photo' in request.files:
        photo = request.files['photo']
        if photo.filename != '' and allowed_file(photo.filename):
            timestamp = str(int(time.time()))
            filename = f'{timestamp}.jpg'  # Save as JPEG with timestamp
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f'static/img/{filename}'
        else:
            image_path = None
    else:
        image_path = None

    new_recipe = Recipe(name=name, ingredients=ingredients, prep_time=prep_time, image_path=image_path, user=current_user)
    db.session.add(new_recipe)

    try:
        db.session.commit()
        return jsonify({'id': new_recipe.id, 'name': new_recipe.name, 'ingredients': new_recipe.ingredients,
                        'prep_time': new_recipe.prep_time, 'image_path': new_recipe.image_path})
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    


@app.route('/api/recipes/<int:id>', methods=['PUT'])
@login_required
def update_recipe(id):
    recipe = Recipe.query.get_or_404(id)
    recipe.user = current_user

    if recipe.user != current_user:
        return jsonify({'error': 'You do not have permission to update this recipe'}), 403


    name = request.form.get('name')
    ingredients = request.form.get('ingredients')
    prep_time = request.form.get('prep_time')

    # Check if a new photo is provided
    if 'photo' in request.files:
        photo = request.files['photo']
        if photo.filename != '' and allowed_file(photo.filename):
            timestamp = str(int(time.time()))
            filename = f'{timestamp}.jpg'  # Save as JPEG with timestamp
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f'static/img/{filename}'
        else:
            image_path = None
    else:
        # No new photo provided, keep the existing image
        image_path = recipe.image_path

    recipe.name = name
    recipe.ingredients = ingredients
    recipe.prep_time = prep_time
    recipe.image_path = image_path

    try:
        db.session.commit()
        return jsonify({'id': recipe.id, 'name': recipe.name, 'ingredients': recipe.ingredients,
                        'prep_time': recipe.prep_time, 'image_path': recipe.image_path})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/recipes/<int:id>', methods=['DELETE'])
@login_required
def delete_recipe(id):
    recipe = Recipe.query.get_or_404(id)

    if recipe.user != current_user:
        return jsonify({'error': 'You do not have permission to delete this recipe'}), 403

    db.session.delete(recipe)
    db.session.commit()

    return jsonify({'message': 'Recipe deleted successfully'})

# Function to check if a file has an allowed extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Function to generate a unique filename
def generate_unique_filename():
    timestamp = str(int(time.time()))
    return f'{timestamp}.jpg'  # Save as JPEG with timestamp


# Function to create tables
def create_tables():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
