"""
Vercel deployment for Route Optimizer - Full functionality matching local version
"""
from flask import Flask, request, jsonify, render_template_string
import pandas as pd
import os
import logging
import math
import requests
import time
import json

# Configure logging for Vercel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Get API key from environment
OPENROUTESERVICE_API_KEY = os.environ.get('OPENROUTESERVICE_API_KEY', None)
logger.info(f"Flask app startup: API key = {'*' * (len(OPENROUTESERVICE_API_KEY) - 8) + OPENROUTESERVICE_API_KEY[-8:] if OPENROUTESERVICE_API_KEY else 'None'}")
logger.info(f"API key length: {len(OPENROUTESERVICE_API_KEY) if OPENROUTESERVICE_API_KEY else 0} characters")

# Allowed file extensions
ALLOWED_EXTENSIONS = {'csv'}

# Embedded cache data for Vercel (from your local cache)
GEOCODING_CACHE = {
    "Hauptstr. 40, 85643, Steinhöring, Germany": (48.0828668, 12.0630946),
    "Am Römerbrunnen 10, 85609, Aschheim, Germany": (48.1699178, 11.7097772),
    "Högerstr. 16, 85646, Anzing, Germany": (48.1527125, 11.8533032),
    "Hauptstr. 11, 85664, Hohenlinden, Germany": (48.1574977, 11.9964956),
    "Kastanienweg 4, 85652, Pliening, Germany": (48.1958199, 11.7999328),
    "Hauptstr. 14, 85669, Pastetten, Germany": (48.1986485, 11.9428809),
    "Erdinger Str. 6, 85570, Ottenhofen, Germany": (48.2145308, 11.8807559),
    "Klausnerring 12, 85551, Kirchheim, Germany": (48.1534232, 11.744214),
    "Fellnerstr. 2, 85656, Buch am Buchrain, Germany": (48.2115834, 11.9946216),
    "Markt Schwabener Str. 8, 85464, Finsing, Germany": (48.2157185, 11.8250747),
    "Morsestr. 1, 85716, Unterschleissheim, Germany": (48.2913849, 11.5712303),
    "Hauptstr. 32, 85778, Haimhausen, Germany": (48.3164316, 11.5536462),
    "Schlesierstr. 4, 85386, Eching, Germany": (48.3023776, 11.6203083),
    "Kirchgasse 4, 85435, Erding, Germany": (48.3062432, 11.9062046),
    "Am Stutenanger 2, 85764, Oberschleissheim, Germany": (48.2562362, 11.5560171),
    "Schleissheimer Str. 4, 85748, Garching, Germany": (48.2494586, 11.6513853)
}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate haversine distance between two points"""
    R = 6371  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def geocode_address(street, postcode, city, country="Germany"):
    """Geocode address using cache first, then API if needed"""
    address_key = f"{street}, {postcode}, {city}, {country}"
    
    # Check cache first
    if address_key in GEOCODING_CACHE:
        logger.info(f"Cache hit: {address_key}... -> {GEOCODING_CACHE[address_key]}")
        return GEOCODING_CACHE[address_key]
    
    # If not in cache and we have API key, try to geocode
    if OPENROUTESERVICE_API_KEY:
        try:
            url = "https://api.openrouteservice.org/geocode/search"
            params = {
                'api_key': OPENROUTESERVICE_API_KEY,
                'text': f"{street}, {postcode} {city}, {country}",
                'boundary.country': 'DE' if country.lower() in ['germany', 'deutschland'] else None,
                'size': 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data['features']:
                    coords = data['features'][0]['geometry']['coordinates']
                    lat, lng = coords[1], coords[0]
                    logger.info(f"Geocoded: {address_key} -> ({lat}, {lng})")
                    return (lat, lng)
        except Exception as e:
            logger.warning(f"Geocoding failed for {address_key}: {str(e)}")
    
    # Return None if geocoding fails
    logger.warning(f"Could not geocode: {address_key}")
    return None

def optimize_route_2opt(stops_with_coords):
    """Optimize route using 2-opt algorithm"""
    n = len(stops_with_coords)
    if n < 3:
        return stops_with_coords, 0.0, 0.0
    
    # Create distance matrix
    distances = {}
    for i in range(n):
        for j in range(n):
            if i != j:
                lat1, lng1 = stops_with_coords[i]['coordinates']['lat'], stops_with_coords[i]['coordinates']['lng']
                lat2, lng2 = stops_with_coords[j]['coordinates']['lat'], stops_with_coords[j]['coordinates']['lng']
                distances[(i, j)] = haversine_distance(lat1, lng1, lat2, lng2)
    
    # Calculate initial route distance
    def calculate_route_distance(route_order):
        total_distance = 0
        for i in range(len(route_order)):
            current = route_order[i]
            next_stop = route_order[(i + 1) % len(route_order)]
            total_distance += distances[(current, next_stop)]
        return total_distance
    
    # Initial route (just the order we received)
    current_route = list(range(n))
    current_distance = calculate_route_distance(current_route)
    original_distance = current_distance
    
    # Prevent division by zero
    if original_distance == 0:
        return stops_with_coords, 0.0, 0.0
    
    improved = True
    iterations = 0
    max_iterations = 50  # Allow more iterations for better optimization
    
    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                # Try reversing the segment between i and j
                new_route = current_route[:]
                new_route[i:j+1] = reversed(new_route[i:j+1])
                
                new_distance = calculate_route_distance(new_route)
                
                if new_distance < current_distance:
                    current_route = new_route
                    current_distance = new_distance
                    improved = True
    
    # Reorder stops according to optimized route
    optimized_stops = [stops_with_coords[i] for i in current_route]
    distance_saved = original_distance - current_distance
    
    logger.info(f"2-Opt completed after {iterations} iterations, improved: {distance_saved > 0}")
    
    # Safe percentage calculation
    improvement_pct = (distance_saved/original_distance)*100 if original_distance > 0 else 0
    logger.info(f"Route optimization: {n} stops, {distance_saved:.2f}km saved ({improvement_pct:.1f}%)")
    
    return optimized_stops, distance_saved, current_distance

def validate_route_data(df):
    """Validate that the DataFrame contains required columns for route optimization"""
    validation_result = {
        'is_valid': True,
        'missing_columns': [],
        'suggestions': [],
        'route_column': None,
        'address_columns': {},
        'warnings': []
    }
    
    # Define required column patterns and their variations
    required_patterns = {
        'route': ['route', 'tour', 'trip', 'planned_trip', 'planned trip', 'vehicle', 'driver'],
        'customer': ['name', 'customer', 'consignee', 'company'],
        'street': ['street', 'address', 'addr', 'strasse', 'straße'],
        'postal_code': ['postal', 'post', 'zip', 'plz', 'postcode', 'post code'],
        'city': ['city', 'ort', 'town', 'place'],
        'tracking': ['tracking', 'shipment', 'number', 'id']
    }
    
    # Get actual column names (case-insensitive)
    actual_columns = [col.lower().strip() for col in df.columns]
    column_mapping = {col.lower().strip(): col for col in df.columns}
    
    # Find matching columns
    found_columns = {}
    for req_type, patterns in required_patterns.items():
        found_column = None
        for pattern in patterns:
            for actual_col in actual_columns:
                if pattern in actual_col or actual_col in pattern:
                    found_column = column_mapping[actual_col]
                    break
            if found_column:
                break
        found_columns[req_type] = found_column
    
    # Check for route column (most critical)
    if found_columns['route']:
        validation_result['route_column'] = found_columns['route']
        route_values = df[found_columns['route']].dropna()
        unique_routes = route_values.nunique()
        if unique_routes == 0:
            validation_result['warnings'].append("Route column found but contains no data")
        elif unique_routes == 1:
            validation_result['warnings'].append(f"Only 1 unique route found: '{route_values.iloc[0]}'")
        else:
            validation_result['suggestions'].append(f"✅ Found {unique_routes} unique routes in '{found_columns['route']}'")
    else:
        validation_result['is_valid'] = False
        validation_result['missing_columns'].append('route_identifier')
        validation_result['suggestions'].append("❌ No route/tour column found. Look for columns like 'Route', 'Tour', 'Trip', 'Planned trip'")
    
    # Check for address components
    address_components = ['street', 'postal_code', 'city']
    for component in address_components:
        if found_columns[component]:
            validation_result['address_columns'][component] = found_columns[component]
        else:
            validation_result['missing_columns'].append(component)
    
    # Check if we have enough address info for routing
    if len(validation_result['address_columns']) < 2:
        validation_result['is_valid'] = False
        validation_result['suggestions'].append("❌ Need at least 2 address components (street, postal code, city) for routing")
    else:
        validation_result['suggestions'].append(f"✅ Found address components: {', '.join(validation_result['address_columns'].keys())}")
    
    return validation_result

# Main HTML template (embedded version of the local template)
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Route Optimizer - Vercel Deployment</title>
    
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
    <!-- Leaflet JavaScript -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
    
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
            height: 100vh;
            overflow: hidden;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-width: 800px;
            margin: 50px auto;
        }
        .main-layout {
            display: flex;
            height: 100vh;
            background: white;
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .upload-area {
            border: 2px dashed #ccc;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            margin: 20px 0;
            background-color: #fafafa;
            cursor: pointer;
            transition: border-color 0.3s;
        }
        .upload-area:hover {
            border-color: #007bff;
        }
        .upload-area.drag-over {
            border-color: #007bff;
            background-color: #e7f3ff;
        }
        input[type="file"] {
            display: none;
        }
        button {
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #0056b3;
        }
        button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .results {
            margin-top: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 5px;
            display: none;
        }
        .error {
            color: #dc3545;
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .success {
            color: #155724;
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }
        .stat-item {
            background: white;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #dee2e6;
        }
        .stat-label {
            font-weight: bold;
            color: #666;
            font-size: 14px;
        }
        .stat-value {
            font-size: 18px;
            color: #333;
            margin-top: 5px;
        }
        .text-success {
            color: #28a745 !important;
            font-weight: bold;
        }
        .sidebar {
            width: 350px;
            background: #f8f9fa;
            border-right: 1px solid #dee2e6;
            overflow-y: auto;
            padding: 20px;
            box-sizing: border-box;
        }
        .map-container {
            flex: 1;
            position: relative;
        }
        #routeMap {
            height: 100vh;
            width: 100%;
        }
        .route-list {
            margin-top: 20px;
        }
        .route-item {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin: 10px 0;
            padding: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .route-item:hover {
            border-color: #007bff;
            box-shadow: 0 2px 8px rgba(0,123,255,0.15);
        }
        .route-item.selected {
            border-color: #007bff;
            background: #e7f3ff;
        }
        .route-title {
            font-weight: bold;
            color: #333;
            font-size: 16px;
            margin-bottom: 8px;
        }
        .route-improvement {
            background: #28a745;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            float: right;
        }
        .route-stats {
            color: #666;
            font-size: 14px;
        }
        .stop-list {
            margin-top: 10px;
            font-size: 13px;
        }
        .stop-item {
            background: #f8f9fa;
            padding: 5px 10px;
            margin: 2px 0;
            border-radius: 3px;
            border-left: 3px solid #007bff;
        }
        .cache-stats {
            background: #e9ecef;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-size: 12px;
        }
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #007bff;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .upload-section {
            padding: 20px;
        }
        .results-section {
            display: none;
        }
    </style>
</head>
<body>
    <div class="main-layout">
        <!-- Sidebar -->
        <div class="sidebar">
            <!-- Upload Section -->
            <div class="upload-section" id="uploadSection">
                <h1>🚀 Route Optimizer</h1>
                <div class="upload-area" onclick="document.getElementById('fileInput').click()">
                    <p>📁 Click here or drag and drop your CSV file</p>
                    <p style="font-size: 14px; color: #666;">Supports: .csv files up to 16MB</p>
                </div>
                <input type="file" id="fileInput" accept=".csv" onchange="handleFileUpload(event)">
                
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p>Processing your routes...</p>
                </div>
                
                <div id="results" class="results"></div>
            </div>

            <!-- Results Section -->
            <div class="results-section" id="resultsSection">
                <h2>📊 Optimization Results</h2>
                <div id="optimizationStats"></div>
                <div id="routeList" class="route-list"></div>
                <button onclick="resetApp()" style="margin-top: 20px; width: 100%;">Upload New File</button>
            </div>
        </div>

        <!-- Map Container -->
        <div class="map-container">
            <div id="routeMap"></div>
        </div>
    </div>

    <script>
        let map = null;
        let routeData = null;
        let markers = [];
        let routeLines = [];

        // Initialize map
        function initMap() {
            map = L.map('routeMap').setView([48.2206, 11.8041], 10); // Center on Munich area
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);
        }

        // Initialize map on page load
        document.addEventListener('DOMContentLoaded', function() {
            initMap();
        });

        // Handle file upload
        function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').innerHTML = '';

            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('loading').style.display = 'none';
                handleResponse(data);
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                console.error('Error:', error);
                showError('Upload failed: ' + error.message);
            });
        }

        // Handle API response
        function handleResponse(data) {
            if (data.success) {
                routeData = data;
                showResults(data);
                switchToResultsView();
                displayOnMap(data);
            } else {
                showError(data.error || 'Unknown error occurred');
            }
        }

        // Show results in sidebar
        function showResults(data) {
            const statsHtml = `
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-label">Routes Optimized</div>
                        <div class="stat-value">${data.stats?.optimization?.stops_optimized || 0}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Distance Saved</div>
                        <div class="stat-value text-success">${data.stats?.optimization?.distance_saved_km || 0} km</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Improvement</div>
                        <div class="stat-value text-success">${data.stats?.optimization?.improvement_percentage || '0%'}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Cache Hit Rate</div>
                        <div class="stat-value">${data.stats?.geocoding?.cache_hit_rate || '0%'}</div>
                    </div>
                </div>
            `;

            document.getElementById('optimizationStats').innerHTML = statsHtml;

            // Show route details
            let routeListHtml = '<h3>📍 Optimized Route</h3>';
            if (data.optimized_route) {
                data.optimized_route.forEach((stop, index) => {
                    routeListHtml += `
                        <div class="stop-item">
                            <strong>${stop.stop_number}.</strong> ${stop.name}<br>
                            <small>${stop.address}</small>
                        </div>
                    `;
                });
            }

            document.getElementById('routeList').innerHTML = routeListHtml;
        }

        // Display routes on map
        function displayOnMap(data) {
            // Clear existing markers and routes
            markers.forEach(marker => map.removeLayer(marker));
            routeLines.forEach(line => map.removeLayer(line));
            markers = [];
            routeLines = [];

            if (!data.optimized_route || data.optimized_route.length === 0) return;

            const bounds = L.latLngBounds();

            // Add markers for each stop
            data.optimized_route.forEach((stop, index) => {
                const lat = stop.coordinates.latitude;
                const lng = stop.coordinates.longitude;
                
                if (lat && lng) {
                    const marker = L.marker([lat, lng])
                        .bindPopup(`
                            <div>
                                <strong>Stop ${stop.stop_number}</strong><br>
                                ${stop.name}<br>
                                <small>${stop.address}</small>
                            </div>
                        `)
                        .addTo(map);
                    
                    markers.push(marker);
                    bounds.extend([lat, lng]);
                }
            });

            // Draw route line
            const routePoints = data.optimized_route
                .filter(stop => stop.coordinates.latitude && stop.coordinates.longitude)
                .map(stop => [stop.coordinates.latitude, stop.coordinates.longitude]);

            if (routePoints.length > 1) {
                // Close the route loop
                routePoints.push(routePoints[0]);
                
                const routeLine = L.polyline(routePoints, {
                    color: '#007bff',
                    weight: 3,
                    opacity: 0.7
                }).addTo(map);
                
                routeLines.push(routeLine);
            }

            // Fit map to show all markers
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [20, 20] });
            }
        }

        // Switch to results view
        function switchToResultsView() {
            document.getElementById('uploadSection').style.display = 'none';
            document.getElementById('resultsSection').style.display = 'block';
        }

        // Reset app to upload view
        function resetApp() {
            document.getElementById('uploadSection').style.display = 'block';
            document.getElementById('resultsSection').style.display = 'none';
            document.getElementById('fileInput').value = '';
            document.getElementById('results').innerHTML = '';
            
            // Clear map
            markers.forEach(marker => map.removeLayer(marker));
            routeLines.forEach(line => map.removeLayer(line));
            markers = [];
            routeLines = [];
            
            // Reset map view
            map.setView([48.2206, 11.8041], 10);
        }

        // Show error message
        function showError(message) {
            document.getElementById('results').innerHTML = `
                <div class="error">
                    <strong>Error:</strong> ${message}
                </div>
            `;
        }

        // Drag and drop functionality
        document.addEventListener('DOMContentLoaded', function() {
            const uploadArea = document.querySelector('.upload-area');
            
            uploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                uploadArea.classList.add('drag-over');
            });
            
            uploadArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('drag-over');
            });
            
            uploadArea.addEventListener('drop', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('drag-over');
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    document.getElementById('fileInput').files = files;
                    handleFileUpload({ target: { files: files } });
                }
            });
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page with full web interface"""
    return render_template_string(MAIN_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload and perform route optimization - matching local functionality"""
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        # Check if file is allowed
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only CSV files are allowed'}), 400
        
        # Read CSV directly from memory - try different separators and encodings
        separators_to_try = [',', ';', '\t']
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        df = None
        successful_config = None
        
        for separator in separators_to_try:
            for encoding in encodings_to_try:
                try:
                    file.seek(0)
                    content = file.read().decode(encoding)
                    from io import StringIO
                    csv_data = StringIO(content)
                    temp_df = pd.read_csv(csv_data, sep=separator)
                    
                    if len(temp_df.columns) > 1 and len(temp_df) > 0:
                        df = temp_df
                        successful_config = f"separator='{separator}', encoding='{encoding}'"
                        logger.info(f"Successfully read CSV with {successful_config}")
                        break
                except Exception as e:
                    continue
            if df is not None:
                break
        
        if df is None:
            raise Exception("Could not parse CSV file with any combination of separators and encodings")
        
        # Clean up the data
        df = df.dropna(how='all')
        logger.info(f"Loaded CSV: {file.filename}")
        logger.info(f"Shape after cleaning: {df.shape}")
        logger.info(f"Columns: {list(df.columns)}")
        
        # Validate the data
        validation = validate_route_data(df)
        
        # Initialize stats
        stats = {
            'file_info': {
                'filename': file.filename,
                'rows': len(df),
                'columns': len(df.columns),
                'successful_config': successful_config
            },
            'validation': validation,
            'geocoding': {
                'total_addresses': len(df),
                'geocoded_successfully': 0,
                'cache_hits': 0,
                'cache_hit_rate': '0%'
            }
        }
        
        # If validation passed, proceed with optimization
        if validation['is_valid']:
            try:
                start_time = time.time()
                
                # Extract address information using validation results
                stops_with_coords = []
                geocoded_count = 0
                cache_hits = 0
                
                address_columns = validation['address_columns']
                route_column = validation['route_column']
                
                # Group by route if route column exists
                routes = {}
                if route_column:
                    route_groups = df.groupby(route_column)
                    for route_id, route_df in route_groups:
                        routes[route_id] = route_df
                else:
                    # Treat all data as one route
                    routes['Default Route'] = df
                
                # Process the main route (first one or all data)
                main_route_data = list(routes.values())[0]
                
                for index, row in main_route_data.iterrows():
                    street = str(row[address_columns.get('street', '')]).strip() if address_columns.get('street') and pd.notna(row[address_columns.get('street', '')]) else None
                    postcode = str(row[address_columns.get('postal_code', '')]).strip() if address_columns.get('postal_code') and pd.notna(row[address_columns.get('postal_code', '')]) else None
                    city = str(row[address_columns.get('city', '')]).strip() if address_columns.get('city') and pd.notna(row[address_columns.get('city', '')]) else None
                    
                    # Get customer name
                    customer_col = None
                    for col in df.columns:
                        if 'name' in col.lower() and 'shipment' not in col.lower():
                            customer_col = col
                            break
                    
                    customer = str(row[customer_col]).strip() if customer_col and pd.notna(row[customer_col]) else f"Stop {len(stops_with_coords) + 1}"
                    
                    if street and postcode and city:
                        coords = geocode_address(street, postcode, city)
                        if coords:
                            stops_with_coords.append({
                                'stop_number': len(stops_with_coords) + 1,
                                'customer': customer,
                                'street': street,
                                'postal_code': postcode,
                                'city': city,
                                'coordinates': {'lat': coords[0], 'lng': coords[1]}
                            })
                            geocoded_count += 1
                            
                            # Check if it was a cache hit
                            address_key = f"{street}, {postcode}, {city}, Germany"
                            if address_key in GEOCODING_CACHE:
                                cache_hits += 1
                
                # Update geocoding stats
                cache_hit_rate = (cache_hits/geocoded_count*100) if geocoded_count > 0 else 0
                stats['geocoding'] = {
                    'total_addresses': len(main_route_data),
                    'geocoded_successfully': geocoded_count,
                    'cache_hits': cache_hits,
                    'cache_hit_rate': f"{cache_hit_rate:.1f}%"
                }
                
                logger.info(f"Geocoded {geocoded_count}/{len(main_route_data)} stops ({cache_hits} cache hits, {cache_hit_rate:.1f}% hit rate)")
                
                if len(stops_with_coords) >= 2:
                    # Perform route optimization
                    optimized_stops, distance_saved, total_distance = optimize_route_2opt(stops_with_coords)
                    optimization_time = time.time() - start_time
                    
                    # Calculate improvement percentage
                    total_original_distance = total_distance + distance_saved
                    improvement_pct = (distance_saved/total_original_distance*100) if total_original_distance > 0 else 0
                    
                    # Prepare optimized route for response
                    optimized_route = []
                    for i, stop in enumerate(optimized_stops):
                        optimized_route.append({
                            'stop_number': i + 1,
                            'name': stop['customer'],
                            'address': f"{stop['street']}, {stop['postal_code']} {stop['city']}",
                            'coordinates': {
                                'latitude': stop['coordinates']['lat'],
                                'longitude': stop['coordinates']['lng']
                            }
                        })
                    
                    stats['optimization'] = {
                        'stops_optimized': len(optimized_stops),
                        'total_distance_km': round(total_distance, 2),
                        'distance_saved_km': round(distance_saved, 2),
                        'improvement_percentage': f"{improvement_pct:.1f}%",
                        'optimization_time_seconds': round(optimization_time, 2)
                    }
                    
                    logger.info(f"Optimization complete: {distance_saved:.2f}km saved ({improvement_pct:.1f}% improvement)")
                    logger.info(f"Route optimization completed in {optimization_time:.2f} seconds")
                    
                    return jsonify({
                        'success': True,
                        'message': 'Route optimization completed successfully',
                        'stats': stats,
                        'optimized_route': optimized_route,
                        'github_repo': 'https://github.com/YDVW/POC-Route-Vercel.git'
                    })
                else:
                    return jsonify({
                        'error': 'Not enough geocoded addresses for route optimization',
                        'geocoded_count': geocoded_count,
                        'total_addresses': len(main_route_data),
                        'note': 'Need at least 2 valid addresses for optimization'
                    }), 400
                    
            except Exception as e:
                logger.error(f"Error during route optimization: {str(e)}")
                return jsonify({
                    'error': f'Optimization error: {str(e)}',
                    'stats': stats
                }), 500
        else:
            return jsonify({
                'error': 'CSV validation failed',
                'validation_errors': validation,
                'stats': stats
            }), 400
        
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'Route Optimizer - Full Vercel Deployment',
        'api_key_configured': bool(OPENROUTESERVICE_API_KEY),
        'cached_addresses': len(GEOCODING_CACHE),
        'version': 'vercel-full-functionality',
        'platform': 'vercel'
    })

# Vercel serverless handler
app = app 