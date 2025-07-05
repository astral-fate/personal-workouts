import os
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import boto3
from werkzeug.utils import secure_filename
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,  # recycle connections every 5 minutes
}

db = SQLAlchemy(app)

# --- MODELS ---
class Routine(db.Model):
    __tablename__ = 'routines'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    exercises = db.relationship('Exercise', backref='routine', cascade="all, delete-orphan")

class Exercise(db.Model):
    __tablename__ = 'exercises'
    id = db.Column(db.Integer, primary_key=True)
    routine_id = db.Column(db.Integer, db.ForeignKey('routines.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    image_url = db.Column(db.String(512), nullable=False)
    type = db.Column(db.String(16), nullable=False)  # 'time' or 'reps'
    value = db.Column(db.Integer, nullable=False)

# --- AWS S3 SETUP ---
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_REGION = os.environ.get('S3_REGION')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')

s3 = boto3.client(
    's3',
    region_name=S3_REGION,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY
)

def upload_image_to_s3(file):
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1]
    key = f"workout-images/{uuid4().hex}.{ext}"
    s3.upload_fileobj(file, S3_BUCKET, key)
    url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    return url

# --- ROUTES ---

@app.route('/api/routines', methods=['GET'])
def get_routines():
    routines = Routine.query.all()
    result = []
    for r in routines:
        result.append({
            'id': r.id,
            'name': r.name,
            'exercises': [
                {
                    'id': e.id,
                    'name': e.name,
                    'image': e.image_url,
                    'type': e.type,
                    'value': e.value
                } for e in r.exercises
            ]
        })
    return jsonify(result)

@app.route('/api/routines', methods=['POST'])
def create_routine():
    data = request.json
    routine = Routine(name=data['name'])
    db.session.add(routine)
    db.session.commit()
    # Add exercises
    for ex in data.get('exercises', []):
        exercise = Exercise(
            routine_id=routine.id,
            name=ex['name'],
            image_url=ex['image'],
            type=ex['type'],
            value=ex['value']
        )
        db.session.add(exercise)
    db.session.commit()
    return jsonify({'id': routine.id}), 201

@app.route('/api/routines/<int:routine_id>', methods=['PUT'])
def update_routine(routine_id):
    data = request.json
    routine = Routine.query.get_or_404(routine_id)
    routine.name = data['name']
    # Remove old exercises
    Exercise.query.filter_by(routine_id=routine_id).delete()
    # Add new exercises
    for ex in data.get('exercises', []):
        exercise = Exercise(
            routine_id=routine.id,
            name=ex['name'],
            image_url=ex['image'],
            type=ex['type'],
            value=ex['value']
        )
        db.session.add(exercise)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/routines/<int:routine_id>', methods=['DELETE'])
def delete_routine(routine_id):
    routine = Routine.query.get_or_404(routine_id)
    db.session.delete(routine)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    url = upload_image_to_s3(file)
    return jsonify({'url': url})

@app.route('/')
def serve_index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('public', path)




@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# --- DB INIT ---
def create_tables():
    with app.app_context():
        db.create_all()
        print("Database initialized.")

@app.cli.command("init-db")
def init_db_command():
    """Initialize the database tables."""
    create_tables()

# if __name__ == '__main__':
#     # Only run the dev server locally
#     app.run(debug=True)
