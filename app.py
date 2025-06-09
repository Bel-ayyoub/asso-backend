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

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Create Flask app
app = Flask(__name__)
CORS(app)  # Allow cross-origin requests
app.config['SECRET_KEY'] = SECRET_KEY_FROM_ENV

# Allowed file types for upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def token_required(f):
    """Decorator to check if user has valid token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Format: "Bearer <token>"
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        # Verify token
        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return jsonify({'error': 'Token is invalid'}), 401
            
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    """Home route to check if server is running"""
    return jsonify({'message': 'Server is running successfully!'}), 200

@app.route('/api/login', methods=['POST'])
def login():
    """Login route for admin authentication"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Check credentials in database
        response = supabase.table('admins').select("*").eq('username', username).eq('password', password).execute()
        
        if response.data:
            # Create JWT token
            token = jwt.encode({'username': username}, app.config['SECRET_KEY'], algorithm='HS256')
            return jsonify({'token': token}), 200
        else:
            return jsonify({'error': 'Invalid username or password'}), 401
            
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_image():
    """Upload image with metadata"""
    try:
        # Check if image file is provided
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check if file type is allowed
        if not file or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please use PNG, JPG, JPEG, or GIF'}), 400
        
        # Create unique filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        unique_filename = timestamp + filename
        
        # Read file data
        file_bytes = file.read()
        
        # Upload to Supabase storage
        supabase.storage.from_('photos').upload(
            file=file_bytes, 
            path=f'public/{unique_filename}', 
            file_options={"content-type": file.mimetype}
        )
        
        # Get public URL
        public_url = supabase.storage.from_('photos').get_public_url(f'public/{unique_filename}')
        
        # Prepare metadata
        metadata = {
            'filename': unique_filename,
            'location': request.form.get('location', ''),
            'bio': request.form.get('bio', ''),
            'paragraph': request.form.get('paragraph', ''),
            'upload_date': datetime.now().isoformat(),
            'image_url': public_url
        }
        
        # Save metadata to database
        supabase.table("images").insert(metadata).execute()
        
        return jsonify({'message': 'Image uploaded successfully!'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/images', methods=['GET'])
def get_images():
    """Get all images or filter by location"""
    try:
        # Start with basic query
        query = supabase.table('images').select('*').order('upload_date', desc=True)
        
        # Filter by location if provided
        location = request.args.get('location')
        if location:
            result = query.eq('location', location).execute()
        else:
            result = query.execute()
            
        return jsonify(result.data), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch images: {str(e)}'}), 500

@app.route('/api/delete/<string:image_id>', methods=['DELETE'])
@token_required
def delete_image(image_id):
    """Delete image and its metadata"""
    try:
        # Find the image record
        image_record = supabase.table('images').select('filename').eq('id', image_id).execute()
        
        if not image_record.data:
            return jsonify({'error': 'Image not found'}), 404
        
        filename = image_record.data[0]['filename']
        
        # Delete from storage
        supabase.storage.from_('photos').remove([f'public/{filename}'])
        
        # Delete from database
        supabase.table('images').delete().eq('id', image_id).execute()
        
        return jsonify({'message': 'Image deleted successfully!'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(port=port, debug=True)
