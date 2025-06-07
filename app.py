from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import jwt
from functools import wraps
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask config
app = Flask(__name__)
CORS(app)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'your-secret-key'

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Auth token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Invalid token format'}), 401

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data
        except:
            return jsonify({'message': 'Token is invalid'}), 401

        return f(current_user, *args, **kwargs)
    return decorated

# Upload image
@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file(current_user):
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        metadata = {
            'filename': filename,
            'location': request.form.get('location', ''),
            'bio': request.form.get('bio', ''),
            'upload_date': datetime.now().isoformat(),
            'uploaded_by': current_user.get('username', 'unknown')
        }

        supabase.table("images").insert(metadata).execute()

        return jsonify({
            'message': 'File uploaded successfully',
            'metadata': metadata
        }), 200

    return jsonify({'error': 'Invalid file type'}), 400

# Get images
@app.route('/api/images', methods=['GET'])
def get_images():
    location = request.args.get('location')
    if location:
        result = supabase.table('images').select('*').eq('location', location).execute()
    else:
        result = supabase.table('images').select('*').execute()
    return jsonify(result.data), 200

# Serve image file
@app.route('/api/image/<filename>', methods=['GET'])
def get_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Home
@app.route('/')
def index():
    return jsonify({'message': 'Server is running'}), 200

# Login with Supabase
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    response = supabase.table('admins').select("*").eq('username', username).eq('password', password).execute()

    if response.data:
        token = jwt.encode({'username': username}, app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({'token': token}), 200
    else:
        return jsonify({'message': 'اسم المستخدم أو كلمة المرور غير صحيحة'}), 401

def create_app():
    return app

if __name__ == '__main__':
    app.run(port=5000, debug=True)
