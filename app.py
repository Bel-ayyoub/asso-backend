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
SECRET_KEY_FROM_ENV = os.getenv("SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask config
app = Flask(__name__)
CORS(app)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['SECRET_KEY'] = SECRET_KEY_FROM_ENV

# Auth token decorator
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
            # Just decode to validate. No need to pass the user data.
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        # Pass the original arguments without adding 'current_user'
        return f(*args, **kwargs)
    return decorated

# Upload image - REMOVED the 'current_user' argument that caused the crash
@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file():
    if 'image' not in request.files: return jsonify({'error': 'No image file provided'}), 400
    file = request.files['image']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = datetime.now().strftime('%Y%m%d_%H%M%S_') + filename
        file_bytes = file.read()
        file.seek(0)
        try:
            supabase.storage.from_('photos').upload(file=file_bytes, path=f'public/{unique_filename}', file_options={"content-type": file.mimetype})
            public_url = supabase.storage.from_('photos').get_public_url(f'public/{unique_filename}')
            
            metadata = {
                'filename': unique_filename,
                'location': request.form.get('location', ''),
                'bio': request.form.get('bio', ''),
                'paragraph': request.form.get('paragraph', ''),
                'upload_date': datetime.now().isoformat(),
                'image_url': public_url
                # Removed 'uploaded_by' to fix the crash and simplify
            }
            supabase.table("images").insert(metadata).execute()
            return jsonify({'message': 'File uploaded successfully'}), 200
        except Exception as e:
            # Return a proper JSON error if Supabase fails
            return jsonify({'error': f'Storage or DB upload failed: {str(e)}'}), 500
    return jsonify({'error': 'Invalid file type'}), 400

# Other routes (no changes needed for them)

@app.route('/api/images', methods=['GET'])
def get_images():
    query = supabase.table('images').select('*').order('upload_date', desc=True)
    location = request.args.get('location')
    if location:
        result = query.eq('location', location).execute()
    else:
        result = query.execute()
    return jsonify(result.data), 200

@app.route('/api/delete/<string:image_id>', methods=['DELETE'])
@token_required
def delete_file(image_id):
    try:
        image_record_response = supabase.table('images').select('filename').eq('id', image_id).execute()
        if not image_record_response.data: return jsonify({'error': 'Image record not found'}), 404
        filename = image_record_response.data[0]['filename']
        supabase.storage.from_('photos').remove([f'public/{filename}'])
        supabase.table('images').delete().eq('id', image_id).execute()
        return jsonify({'message': 'File deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': f'Deletion process failed: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    response = supabase.table('admins').select("*").eq('username', data.get('username')).eq('password', data.get('password')).execute()
    if response.data:
        token = jwt.encode({'username': data.get('username')}, app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({'token': token}), 200
    else:
        return jsonify({'message': 'Invalid username or password'}), 401

@app.route('/')
def index():
    return jsonify({'message': 'Server is running'}), 200

if __name__ == '__main__':
    app.run(port=int(os.environ.get("PORT", 5000)), debug=True)
