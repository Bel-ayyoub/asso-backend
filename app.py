from flask import Flask, request, jsonify
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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

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

# Upload image to Supabase storage bucket 'photos'
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
        final_filename = f"{timestamp}{filename}"
        path_in_bucket = f"images/{final_filename}"
        file_bytes = file.read()

        upload_response = supabase.storage.from_('photos').upload(
            path=path_in_bucket,
            file=file_bytes,
            file_options={
                "content-type": file.mimetype,
                "upsert": True
            }
        )

        if upload_response.get('error'):
            return jsonify({'error': 'Upload to Supabase failed'}), 500

        public_url = supabase.storage.from_('photos').get_public_url(path_in_bucket)

        metadata = {
            'filename': final_filename,
            'url': public_url,
            'location': request.form.get('location', ''),
            'bio': request.form.get('bio', ''),
            'upload_date': datetime.now().isoformat(),
            'uploaded_by': current_user.get('username', 'unknown')
        }

        supabase.table("images").insert(metadata).execute()

        return jsonify({'message': 'Upload successful', 'metadata': metadata}), 200

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

# Login endpoint
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

# Root
@app.route('/')
def index():
    return jsonify({'message': 'Server is running'}), 200

if __name__ == '__main__':
    app.run(port=5000, debug=True)
