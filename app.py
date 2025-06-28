#!/usr/bin/env python3
"""
Photo to KML Web App
Extracts EXIF GPS data from photos and generates KML files with photo links
"""

import os
import uuid
import base64
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, send_file, url_for
from werkzeug.utils import secure_filename
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import xml.etree.ElementTree as ET
from xml.dom import minidom

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['KML_FOLDER'] = 'kml_files'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create directories if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['KML_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'tiff', 'heic'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_exif_data(image_path):
    """Extract EXIF data from image including GPS coordinates"""
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()

        if not exif_data:
            return None

        extracted_data = {}

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)

            if tag == "GPSInfo":
                gps_data = {}
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_data[gps_tag] = gps_value
                extracted_data["GPSInfo"] = gps_data
            else:
                extracted_data[tag] = value

        return extracted_data
    except Exception as e:
        print(f"Error extracting EXIF: {e}")
        return None

def convert_to_degrees(value):
    """Convert GPS coordinates from DMS to decimal degrees"""
    d, m, s = value
    return float(d) + float(m)/60 + float(s)/3600

def get_gps_coordinates(exif_data):
    """Extract GPS coordinates from EXIF data"""
    if not exif_data or "GPSInfo" not in exif_data:
        return None

    gps_info = exif_data["GPSInfo"]

    try:
        # Get latitude
        if "GPSLatitude" in gps_info and "GPSLatitudeRef" in gps_info:
            lat = convert_to_degrees(gps_info["GPSLatitude"])
            if gps_info["GPSLatitudeRef"] == "S":
                lat = -lat

        # Get longitude
        if "GPSLongitude" in gps_info and "GPSLongitudeRef" in gps_info:
            lon = convert_to_degrees(gps_info["GPSLongitude"])
            if gps_info["GPSLongitudeRef"] == "W":
                lon = -lon

        # Get altitude if available
        altitude = None
        if "GPSAltitude" in gps_info:
            altitude = float(gps_info["GPSAltitude"])
            if gps_info.get("GPSAltitudeRef") == 1:  # Below sea level
                altitude = -altitude

        return {
            "latitude": lat,
            "longitude": lon,
            "altitude": altitude
        }
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error parsing GPS coordinates: {e}")
        return None

def create_kml(photo_filename, coordinates, photo_url, timestamp=None):
    """Create KML file with photo location and link to original photo"""

    # Create KML structure
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(kml, "Document")

    # Document info
    name = ET.SubElement(document, "name")
    name.text = f"Photo Location: {photo_filename}"

    description = ET.SubElement(document, "description")
    description.text = f"GPS location extracted from {photo_filename}"

    # Create placemark
    placemark = ET.SubElement(document, "Placemark")

    # Placemark name
    pm_name = ET.SubElement(placemark, "name")
    pm_name.text = photo_filename

    # Placemark description with photo
    pm_description = ET.SubElement(placemark, "description")
    pm_description.text = f"""
    <![CDATA[
    <h3>{photo_filename}</h3>
    <p>Captured: {timestamp or 'Unknown'}</p>
    <p>Coordinates: {coordinates['latitude']:.6f}, {coordinates['longitude']:.6f}</p>
    {f"<p>Altitude: {coordinates['altitude']:.2f}m</p>" if coordinates['altitude'] else ""}
    <img src="{photo_url}" width="300" alt="Photo"/><br/>
    <a href="{photo_url}" target="_blank">View Full Size</a>
    ]]>
    """

    # Point coordinates
    point = ET.SubElement(placemark, "Point")
    coords = ET.SubElement(point, "coordinates")

    if coordinates['altitude']:
        coords.text = f"{coordinates['longitude']},{coordinates['latitude']},{coordinates['altitude']}"
    else:
        coords.text = f"{coordinates['longitude']},{coordinates['latitude']}"

    # Pretty print XML
    rough_string = ET.tostring(kml, 'utf-8')
    reparsed = minidom.parseString(rough_string)

    return reparsed.toprettyxml(indent="  ")

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo file provided'}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        # Generate unique filename
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        # Save file
        file.save(filepath)

        # Extract EXIF data
        exif_data = get_exif_data(filepath)
        if not exif_data:
            return jsonify({'error': 'No EXIF data found in image'}), 400

        # Get GPS coordinates
        coordinates = get_gps_coordinates(exif_data)
        if not coordinates:
            return jsonify({'error': 'No GPS coordinates found in image EXIF data'}), 400

        # Get timestamp if available
        timestamp = exif_data.get('DateTime', exif_data.get('DateTimeOriginal'))

        # Create photo URL
        photo_url = url_for('uploaded_file', filename=unique_filename, _external=True)

        # Generate KML
        kml_content = create_kml(
            file.filename,
            coordinates,
            photo_url,
            timestamp
        )

        # Save KML file
        kml_filename = f"{uuid.uuid4().hex}.kml"
        kml_filepath = os.path.join(app.config['KML_FOLDER'], kml_filename)

        with open(kml_filepath, 'w', encoding='utf-8') as f:
            f.write(kml_content)

        return jsonify({
            'success': True,
            'photo_url': photo_url,
            'kml_url': url_for('download_kml', filename=kml_filename, _external=True),
            'coordinates': coordinates,
            'timestamp': timestamp,
            'original_filename': file.filename
        })

    return jsonify({'error': 'Invalid file type. Please upload JPG, PNG, TIFF, or HEIC files.'}), 400

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

@app.route('/kml/<filename>')
def download_kml(filename):
    return send_file(
        os.path.join(app.config['KML_FOLDER'], filename),
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.google-earth.kml+xml'
    )

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Photo to KML Converter</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(45deg, #2196F3, #21CBF3);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 24px;
            margin-bottom: 10px;
        }

        .header p {
            opacity: 0.9;
            font-size: 16px;
        }

        .upload-section {
            padding: 40px 30px;
        }

        .upload-area {
            border: 3px dashed #ddd;
            border-radius: 15px;
            padding: 40px 20px;
            text-align: center;
            background: #fafafa;
            transition: all 0.3s ease;
            cursor: pointer;
        }

        .upload-area:hover {
            border-color: #2196F3;
            background: #f0f8ff;
        }

        .upload-area.dragover {
            border-color: #2196F3;
            background: #e3f2fd;
            transform: scale(1.02);
        }

        .upload-icon {
            font-size: 48px;
            color: #666;
            margin-bottom: 20px;
        }

        .upload-text {
            font-size: 18px;
            color: #333;
            margin-bottom: 10px;
        }

        .upload-subtext {
            font-size: 14px;
            color: #666;
            margin-bottom: 20px;
        }

        input[type="file"] {
            display: none;
        }

        .btn {
            background: #2196F3;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-block;
            text-decoration: none;
        }

        .btn:hover {
            background: #1976D2;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(33, 150, 243, 0.3);
        }

        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }

        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #2196F3;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .result {
            display: none;
            padding: 30px;
            background: #f9f9f9;
            border-top: 1px solid #eee;
        }

        .result h3 {
            color: #333;
            margin-bottom: 20px;
            font-size: 20px;
        }

        .result-item {
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }

        .result-item h4 {
            color: #2196F3;
            margin-bottom: 10px;
        }

        .coordinates {
            font-family: 'Courier New', monospace;
            background: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            font-size: 14px;
        }

        .error {
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            display: none;
        }

        .preview-image {
            max-width: 100%;
            height: auto;
            border-radius: 10px;
            margin: 15px 0;
        }

        @media (max-width: 480px) {
            body {
                padding: 10px;
            }

            .header {
                padding: 20px;
            }

            .header h1 {
                font-size: 20px;
            }

            .upload-section {
                padding: 20px;
            }

            .upload-area {
                padding: 30px 15px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📸 Photo to KML Converter</h1>
            <p>Extract GPS location from photos and generate KML files</p>
        </div>

        <div class="upload-section">
            <div class="upload-area" id="uploadArea">
                <div class="upload-icon">📷</div>
                <div class="upload-text">Take or Select a Photo</div>
                <div class="upload-subtext">Photos must contain GPS location data</div>
                <label for="photoInput" class="btn">Choose Photo</label>
                <input type="file" id="photoInput" name="photo" accept="image/*" capture="environment">
            </div>

            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Processing photo and extracting GPS data...</p>
            </div>

            <div class="error" id="error"></div>

            <div class="result" id="result">
                <h3>✅ Conversion Complete!</h3>
                <div class="result-item">
                    <h4>📍 GPS Coordinates</h4>
                    <div class="coordinates" id="coordinates"></div>
                </div>
                <div class="result-item">
                    <h4>📁 Download Files</h4>
                    <p>
                        <a href="#" id="photoLink" class="btn" target="_blank">View Photo</a>
                        <a href="#" id="kmlLink" class="btn" download>Download KML</a>
                    </p>
                </div>
                <div class="result-item" id="previewSection">
                    <h4>🖼️ Photo Preview</h4>
                    <img id="previewImage" class="preview-image" alt="Photo preview">
                </div>
            </div>
        </div>
    </div>

    <script>
        const uploadArea = document.getElementById('uploadArea');
        const photoInput = document.getElementById('photoInput');
        const loading = document.getElementById('loading');
        const result = document.getElementById('result');
        const error = document.getElementById('error');

        // Handle drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });

        // Handle file input change
        photoInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });

        // Handle click on upload area
        uploadArea.addEventListener('click', (e) => {
            if (e.target !== photoInput) {
                photoInput.click();
            }
        });

        function showError(message) {
            error.textContent = message;
            error.style.display = 'block';
            loading.style.display = 'none';
            result.style.display = 'none';
        }

        function handleFile(file) {
            // Validate file type
            const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/tiff', 'image/heic'];
            if (!validTypes.includes(file.type)) {
                showError('Please select a valid image file (JPG, PNG, TIFF, or HEIC)');
                return;
            }

            // Show loading
            error.style.display = 'none';
            result.style.display = 'none';
            loading.style.display = 'block';

            // Create form data
            const formData = new FormData();
            formData.append('photo', file);

            // Upload file
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                loading.style.display = 'none';

                if (data.success) {
                    // Show results
                    const coords = data.coordinates;
                    document.getElementById('coordinates').innerHTML = `
                        Latitude: ${coords.latitude.toFixed(6)}°<br>
                        Longitude: ${coords.longitude.toFixed(6)}°
                        ${coords.altitude ? `<br>Altitude: ${coords.altitude.toFixed(2)}m` : ''}
                        ${data.timestamp ? `<br>Captured: ${data.timestamp}` : ''}
                    `;

                    document.getElementById('photoLink').href = data.photo_url;
                    document.getElementById('kmlLink').href = data.kml_url;
                    document.getElementById('kmlLink').download = `${data.original_filename.split('.')[0]}.kml`;

                    document.getElementById('previewImage').src = data.photo_url;

                    result.style.display = 'block';
                } else {
                    showError(data.error || 'An error occurred while processing the photo');
                }
            })
            .catch(err => {
                loading.style.display = 'none';
                showError('Network error: ' + err.message);
            });
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
