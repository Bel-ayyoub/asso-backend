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

# --- Auth Decorator (No changes here) ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            token = token.split(" ")[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# --- API Routes ---

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file(current_user):
    # This now includes the 'paragraph' field
    metadata = {
        'location': request.form.get('location'),
        'bio': request.form.get('bio'),
        'paragraph': request.form.get('paragraph'), # Added paragraph
        'upload_date': datetime.now().isoformat(),
        'uploaded_by': current_user.get('username', 'unknown'),
    }
    
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    file = request.files['image']
    filename = secure_filename(file.filename)
    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_')}_{filename}"
    file_bytes = file.read()

    try:
        # Upload to Storage
        supabase.storage.from_('photos').upload(file=file_bytes, path=f'public/{unique_filename}', file_options={"content-type": file.mimetype})
        
        # Get public URL and add to metadata
        public_url = supabase.storage.from_('photos').get_public_url(f'public/{unique_filename}')
        metadata['image_url'] = public_url
        metadata['filename'] = unique_filename
        
        # Insert all metadata into the 'images' table
        supabase.table("images").insert(metadata).execute()
        
        return jsonify({'message': 'File uploaded successfully'}), 200
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

# --- EDIT ROUTE (FIXED) ---
@app.route('/api/edit/<int:image_id>', methods=['POST'])
@token_required
def edit_image(current_user, image_id):
    try:
        data = request.get_json()
        # Data to update
        update_data = {
            'bio': data.get('bio'),
            'paragraph': data.get('paragraph')
        }
        # Find the image by its ID and update it
        supabase.table('images').update(update_data).eq('id', image_id).execute()
        return jsonify({'message': 'Image updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- DELETE ROUTE (FIXED) ---
@app.route('/api/delete/<int:image_id>', methods=['DELETE'])
@token_required
def delete_image(current_user, image_id):
    try:
        # Step 1: Find the image record to get its filename
        image_record = supabase.table('images').select('filename').eq('id', image_id).single().execute()
        
        if not image_record.data:
            return jsonify({'error': 'Image not found'}), 404

        filename = image_record.data['filename']

        # Step 2: Delete the file from Supabase Storage
        supabase.storage.from_('photos').remove([f'public/{filename}'])

        # Step 3: Delete the record from the 'images' database table
        supabase.table('images').delete().eq('id', image_id).execute()
        
        return jsonify({'message': 'Image deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Other routes (no changes) ---
@app.route('/api/images', methods=['GET'])
def get_images():
    location = request.args.get('location')
    query = supabase.table('images').select('*').order('upload_date', desc=True)
    if location:
        result = query.eq('location', location).execute()
    else:
        result = query.execute()
    return jsonify(result.data), 200

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
