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
SECRET_KEY_FROM_ENV = os.getenv("SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask config
app = Flask(__name__)
CORS(app)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['SECRET_KEY'] = SECRET_KEY_FROM_ENV

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        unique_filename = timestamp + filename
        file_bytes = file.read()
        file.seek(0)

        try:
            supabase.storage.from_('photos').upload(
                file=file_bytes,
                path=f'public/{unique_filename}',
                file_options={"content-type": file.mimetype}
            )
            public_url_response = supabase.storage.from_('photos').get_public_url(f'public/{unique_filename}')
            public_url = public_url_response

            metadata = {
                'filename': unique_filename,
                'location': request.form.get('location', ''),
                'bio': request.form.get('bio', ''),
                'paragraph': request.form.get('paragraph', ''), # New field
                'upload_date': datetime.now().isoformat(),
                'uploaded_by': current_user.get('username', 'unknown'),
                'image_url': public_url
            }

            supabase.table("images").insert(metadata).execute()

            return jsonify({
                'message': 'File uploaded successfully',
                'metadata': metadata
            }), 200
        except Exception as e:
            return jsonify({'error': f'Storage upload failed: {str(e)}'}), 500

    return jsonify({'error': 'Invalid file type'}), 400

# Get images
@app.route('/api/images', methods=['GET'])
def get_images():
    location = request.args.get('location')
    query = supabase.table('images').select('*').order('upload_date', desc=True)

    if location:
        result = query.eq('location', location).execute()
    else:
        result = query.execute()

    return jsonify(result.data), 200

# --- NEW: Edit an image's metadata ---
@app.route('/api/edit/<int:image_id>', methods=['POST'])
@token_required
def edit_image(current_user, image_id):
    data = request.get_json()
    bio = data.get('bio')
    paragraph = data.get('paragraph')

    if not bio or not paragraph:
        return jsonify({'error': 'Bio and paragraph are required'}), 400

    try:
        supabase.table('images').update({
            'bio': bio,
            'paragraph': paragraph
        }).eq('id', image_id).execute()
        return jsonify({'message': 'Image updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- NEW: Delete an image and its metadata ---
@app.route('/api/delete/<int:image_id>', methods=['DELETE'])
@token_required
def delete_image(current_user, image_id):
    try:
        # First, get the filename to delete from storage
        image_to_delete = supabase.table('images').select('filename').eq('id', image_id).single().execute()
        filename = image_to_delete.data['filename']

        # Delete from Supabase Storage
        supabase.storage.from_('photos').remove([f'public/{filename}'])

        # Delete from Supabase database
        supabase.table('images').delete().eq('id', image_id).execute()
        
        return jsonify({'message': 'Image deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'message': 'Invalid username or password'}), 401

def create_app():
    return app

if __name__ == '__main__':
    app.run(port=int(os.environ.get("PORT", 5000)), debug=True)
