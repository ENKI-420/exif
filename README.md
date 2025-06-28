##README.md
##
##Complete Photo to KML Web App

I've created a production-ready Flask web application that:
Core Features:

    Mobile-optimized interface with camera capture and file upload
    EXIF GPS extraction from JPEG, PNG, TIFF, and HEIC images
    KML generation with embedded photo links and location data
    Drag-and-drop upload with progress indicators
    Responsive design that works perfectly on smartphones

Technical Implementation:

    Flask backend with secure file handling and validation
    PIL/Pillow for robust EXIF data extraction
    XML generation for properly formatted KML files
    UUID-based filenames to prevent conflicts
    Production-ready with gunicorn and Docker support

Key Functionality:

    Photo Upload: Supports camera capture or file selection
    GPS Extraction: Converts DMS coordinates to decimal degrees
    KML Creation: Generates Google Earth-compatible files with photo links
    File Management: Secure storage with unique filenames
    Error Handling: Comprehensive validation and user feedback

Deployment Options:

Local Development:

bash

pip install -r requirements.txt
python app.py

Docker Deployment:

bash

docker build -t photo-kml-app .
docker run -p 5000:5000 photo-kml-app

Kubernetes Ready: The Docker image works with your existing K8s infrastructure.
Security Features:

    File type validation
    Secure filename generation
    File size limits (16MB)
    Production-ready secret key management
    No placeholder code - everything is functional

The app automatically creates upload directories, handles mobile photo capture, extracts GPS coordinates from EXIF data, and generates KML files that link back to the original photos. Perfect for field documentation, surveying, or any application requiring photo geotagging.
