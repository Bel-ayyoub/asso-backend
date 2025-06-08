from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import jwt
from functools import wraps
from dotenv import load_dotenv
from supabase import create_client, Client

# --- Setup ---
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SECRET_KEY_FROM_ENV = os.getenv("SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = SECRET_KEY_FROM_ENV

# --- Auth Decorator (No changes needed) ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            try:
                token = request.headers['Authorization'].split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Invalid token format'}), 401
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data
        except Exception:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# --- API Routes ---

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file(current_user):
    # This route now expects a 'paragraph' field from the form
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        filename = secure_filename(file.filename)
        unique_filename = datetime.now().strftime('%Y%m%d_%H%M%S_') + filename
        file_bytes = file.read()

        # Upload to Supabase Storage
        supabase.storage.from_('photos').upload(
            file=file_bytes,
            path=f'public/{unique_filename}',
            file_options={"content-type": file.mimetype}
        )
        public_url = supabase.storage.from_('photos').get_public_url(f'public/{unique_filename}')

        # Prepare metadata for the database, including the new paragraph
        metadata = {
            'filename': unique_filename,
            'location': request.form.get('location', ''),
            'bio': request.form.get('bio', ''),
        'paragraph': request.form.get('paragraph', ''), # ADDED
            'upload_date': datetime.now().isoformat(),
            'uploaded_by': current_user.get('username', 'unknown'),
            'image_url': public_url
        }

        # Insert metadata into the 'images' table
        supabase.table("images").insert(metadata).execute()
        return jsonify({'message': 'File uploaded successfully'}), 200

    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/images', methods=['GET'])
def get_images():
    # No changes needed here
    location = request.args.get('location')
    query = supabase.table('images').select('*').order('upload_date', desc=True)
    if location:
        result = query.eq('location', location).execute()
    else:
        result = query.execute()
    return jsonify(result.data), 200

# --- FIX: Edit Route ---
@app.route('/api/edit/<int:image_id>', methods=['POST'])
@token_required
def edit_image(current_user, image_id):
    try:
        data = request.get_json()
        # Update the record in Supabase with the new bio and paragraph
        supabase.table('images').update({
            'bio': data.get('bio'),
            'paragraph': data.get('paragraph')
        }).eq('id', image_id).execute()
        return jsonify({'message': 'Image updated successfully'}), 200
    except Exception as e:
        # Return a clear error if something goes wrong
        return jsonify({'error': f'Update failed: {str(e)}'}), 500

# --- FIX: Delete Route ---
@app.route('/api/delete/<int:image_id>', methods=['DELETE'])
@token_required
def delete_image(current_user, image_id):
    try:
        # First, find the record to get the filename
        image_record = supabase.table('images').select('filename').eq('id', image_id).single().execute()
        
        # If record exists, delete file from storage
        if image_record.data:
            filename = image_record.data['filename']
            supabase.storage.from_('photos').remove([f'public/{filename}'])

        # Finally, delete the record from the database table
        supabase.table('images').delete().eq('id', image_id).execute()
        
        return jsonify({'message': 'Image deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

# --- Login and other routes (no changes) ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    response = supabase.table('admins').select("*").eq('username', data.get('username')).eq('password', data.get('password')).execute()
    if response.data:
        token = jwt.encode({'username': data.get('username')}, app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({'token': token}), 200
    else:
        return jsonify({'message': 'Invalid credentials'}), 401

if __name__ == '__main__':
    app.run(port=int(os.environ.get("PORT", 5000)), debug=True)
