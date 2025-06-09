from flask import Flask, request, jsonify, render_template
import pandas as pd
import os
from werkzeug.utils import secure_filename
import logging
from route_optimizer import RouteOptimizer
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# OpenRouteService API Key configuration
# You can set this via environment variable: set OPENROUTESERVICE_API_KEY=your_api_key_here
OPENROUTESERVICE_API_KEY = os.environ.get('OPENROUTESERVICE_API_KEY', None)
logger.info(f"Flask app startup: API key = {repr(OPENROUTESERVICE_API_KEY)}")
if OPENROUTESERVICE_API_KEY:
    logger.info(f"API key length: {len(OPENROUTESERVICE_API_KEY)} characters")
else:
    logger.info("No API key found in environment")

# Allowed file extensions
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    
    # Check for customer/tracking info
    if found_columns['customer']:
        validation_result['suggestions'].append(f"✅ Customer info found in '{found_columns['customer']}'")
    else:
        validation_result['warnings'].append("No customer name column found")
        
    if found_columns['tracking']:
        validation_result['suggestions'].append(f"✅ Tracking info found in '{found_columns['tracking']}'")
    else:
        validation_result['warnings'].append("No tracking/shipment number column found")
    
    # Data quality checks
    if validation_result['is_valid']:
        # Check for empty values in critical columns
        critical_cols = [validation_result['route_column']] + list(validation_result['address_columns'].values())
        for col in critical_cols:
            if col and df[col].isna().sum() > 0:
                empty_count = df[col].isna().sum()
                empty_pct = (empty_count / len(df)) * 100
                validation_result['warnings'].append(f"Column '{col}' has {empty_count} empty values ({empty_pct:.1f}%)")
    
    return validation_result

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload and process with pandas"""
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
        
        # Save file securely
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Read CSV with pandas - try different separators and encodings
        separators_to_try = [',', ';', '\t']
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        df = None
        successful_config = None
        
        for separator in separators_to_try:
            for encoding in encodings_to_try:
                try:
                    temp_df = pd.read_csv(filepath, encoding=encoding, sep=separator)
                    # Check if we got reasonable data (more than 1 column and some non-empty rows)
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
            raise Exception("Could not parse CSV file with any combination of separators (comma, semicolon, tab) and encodings")
        
        # Clean up the data - remove empty rows and fix headers
        # Check if first row might be a description row
        if len(df) > 0:
            # Remove rows where all values are empty or NaN
            df = df.dropna(how='all')
            
            # Check if we need to skip description rows (common in German CSV exports)
            # Look for rows that might be actual headers
            potential_header_indices = []
            for idx, row in df.iterrows():
                row_str = ' '.join(str(val) for val in row.values if pd.notna(val)).lower()
                if any(keyword in row_str for keyword in ['shipment', 'tracking', 'transport', 'planned', 'street', 'post', 'city']):
                    potential_header_indices.append(idx)
            
            # If we found a better header row, use it
            if potential_header_indices:
                header_idx = potential_header_indices[0]
                if header_idx > 0:
                    # Use the row as new header and drop previous rows
                    df.columns = df.iloc[header_idx].values
                    df = df.iloc[header_idx + 1:].reset_index(drop=True)
                    logger.info(f"Detected and used header row at index {header_idx}")
            
            # Clean column names - remove empty/unnamed columns
            df.columns = [col if not (pd.isna(col) or str(col).startswith('Unnamed')) else f'Column_{i}' 
                         for i, col in enumerate(df.columns)]
            
            # Remove completely empty columns
            df = df.dropna(axis=1, how='all')
        
        # Log basic info
        logger.info(f"Loaded CSV: {filename}")
        logger.info(f"Shape after cleaning: {df.shape}")
        logger.info(f"Columns: {list(df.columns)}")
        
        # Basic data analysis
        stats = {
            'filename': filename,
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': list(df.columns),
            'memory_usage': f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB"
        }
        
        # Check for route-related columns
        route_columns = []
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['route', 'tour', 'trip']):
                route_columns.append(col)
        
        if route_columns:
            stats['route_columns'] = route_columns
            # Count unique routes
            for route_col in route_columns:
                unique_routes = df[route_col].nunique()
                stats[f'unique_{route_col}'] = unique_routes
        
        # Sample data (first 5 rows) - replace NaN with None for JSON serialization
        sample_df = df.head().fillna('')  # Replace NaN with empty strings
        stats['sample_data'] = sample_df.to_dict('records')
        
        # Validate route data
        validation = validate_route_data(df)
        stats['validation'] = validation
        
        # Route optimization (if validation passes)
        optimization_results = None
        if validation['is_valid']:
            try:
                # Get algorithm from request (default to 'both')
                algorithm = request.form.get('algorithm', 'both')
                if algorithm not in ['nearest_neighbor', '2_opt', 'both']:
                    algorithm = 'both'
                
                logger.info(f"Starting route optimization with {algorithm} algorithm")
                start_time = time.time()
                
                # Initialize optimizer
                try:
                    optimizer = RouteOptimizer(ors_api_key=OPENROUTESERVICE_API_KEY)
                    logger.info("RouteOptimizer initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to initialize RouteOptimizer: {e}")
                    raise e
                
                # Count total stops for progress tracking
                total_stops = len(df)
                routing_mode = "road routing (with air distance fallback)" if optimizer.ors_client else "air distance only"
                logger.info(f"Will geocode {total_stops} addresses and calculate distances using {routing_mode}")
                
                # Optimize routes
                logger.info("Starting optimize_multiple_routes...")
                try:
                    optimization_results = optimizer.optimize_multiple_routes(
                        df=df,
                        route_column=validation['route_column'],
                        address_columns=validation['address_columns'],
                        algorithm=algorithm
                    )
                    logger.info("Route optimization completed successfully")
                except Exception as e:
                    logger.error(f"Route optimization failed: {e}")
                    raise e
                
                # Create optimized dataframe
                optimized_df = optimizer.create_optimized_dataframe(
                    original_df=df,
                    optimization_results=optimization_results,
                    route_column=validation['route_column']
                )
                
                # Prepare detailed route comparison
                route_comparisons = []
                for route_id, route_result in optimization_results['routes'].items():
                    # Get original route data
                    original_route = df[df[validation['route_column']] == route_id].copy()
                    
                    # Create route comparison
                    comparison = {
                        'route_id': route_id,
                        'stops_count': route_result['stops_count'],
                        'algorithm_used': route_result['algorithm_used'],
                        'original_distance_km': route_result['original_distance'],
                        'optimized_distance_km': route_result['optimized_distance'],
                        'distance_saved_km': route_result['distance_saved'],
                        'improvement_percentage': route_result['improvement_pct'],
                        'processing_time_seconds': route_result['processing_time'],
                        'original_stops': [],
                        'optimized_stops': [],
                        'original_segments': route_result.get('original_segments', []),
                        'optimized_segments': route_result.get('optimized_segments', [])
                    }
                    
                    # Add stop details for routes with multiple stops
                    if route_result['stops_count'] > 1:
                        # Original order
                        for i, (_, row) in enumerate(original_route.iterrows()):
                            stop_info = {
                                'stop_number': i + 1,
                                'customer': str(row.get(validation['address_columns'].get('customer', ''), 'Unknown')),
                                'street': str(row.get(validation['address_columns'].get('street', ''), '')),
                                'postal_code': str(row.get(validation['address_columns'].get('postal_code', ''), '')),
                                'city': str(row.get(validation['address_columns'].get('city', ''), '')),
                            }
                            # Add coordinates using the new method
                            coords = optimizer.get_coordinates(stop_info)
                            stop_info['coordinates'] = {'lat': coords[0], 'lng': coords[1]}
                            comparison['original_stops'].append(stop_info)
                        
                        # Optimized order
                        stops = route_result['stops']
                        for new_pos, original_pos in enumerate(route_result['optimized_order']):
                            stop = stops[original_pos]
                            stop_info = {
                                'stop_number': new_pos + 1,
                                'original_position': original_pos + 1,
                                'customer': stop['customer'],
                                'street': stop['street'],
                                'postal_code': stop['postal_code'],
                                'city': stop['city'],
                            }
                            # Use cached coordinates from optimization if available
                            if '_coordinates' in stop:
                                coords = stop['_coordinates']
                            else:
                                coords = optimizer.get_coordinates(stop_info)
                            stop_info['coordinates'] = {'lat': coords[0], 'lng': coords[1]}
                            comparison['optimized_stops'].append(stop_info)
                    else:
                        # Single stop route
                        stop_info = {
                            'stop_number': 1,
                            'customer': route_result['stops'][0]['customer'] if route_result['stops'] else 'Unknown',
                            'street': route_result['stops'][0]['street'] if route_result['stops'] else '',
                            'postal_code': route_result['stops'][0]['postal_code'] if route_result['stops'] else '',
                            'city': route_result['stops'][0]['city'] if route_result['stops'] else '',
                        }
                        coords = optimizer.get_coordinates(stop_info)
                        stop_info['coordinates'] = {'lat': coords[0], 'lng': coords[1]}
                        comparison['original_stops'] = [stop_info]
                        comparison['optimized_stops'] = [stop_info]
                    
                    route_comparisons.append(comparison)
                
                optimization_time = time.time() - start_time
                logger.info(f"Route optimization completed in {optimization_time:.2f} seconds")
                
                # Add optimization results to stats - clean NaN values
                clean_optimized_df = optimized_df.fillna('')
                stats['optimization'] = {
                    'completed': True,
                    'summary': optimization_results['summary'],
                    'route_comparisons': route_comparisons,
                    'optimized_data': clean_optimized_df.to_dict('records'),
                    'total_processing_time': round(optimization_time, 2)
                }
                
            except Exception as e:
                logger.error(f"Error during route optimization: {str(e)}")
                stats['optimization'] = {
                    'completed': False,
                    'error': str(e),
                    'message': 'Route optimization failed but file validation was successful'
                }
        else:
            stats['optimization'] = {
                'completed': False,
                'message': 'Route optimization skipped due to validation issues',
                'validation_errors': validation
            }
        
        # Clean up - remove uploaded file after processing
        os.remove(filepath)
        
        # Clean data for JSON serialization - replace NaN with empty strings
        clean_df = df.fillna('')
        
        return jsonify({
            'success': True,
            'message': 'CSV file processed successfully',
            'stats': stats,
            'data': clean_df.to_dict('records')  # Full original data for reference
        })
        
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/optimize', methods=['POST'])
def optimize_routes():
    """Standalone route optimization endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'data' not in data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Convert data back to DataFrame
        df = pd.DataFrame(data['data'])
        
        # Get parameters
        algorithm = data.get('algorithm', 'both')
        route_column = data.get('route_column')
        address_columns = data.get('address_columns', {})
        
        if not route_column:
            return jsonify({'error': 'Route column not specified'}), 400
        
        if not address_columns:
            return jsonify({'error': 'Address columns not specified'}), 400
        
        logger.info(f"Optimizing routes with {algorithm} algorithm")
        
        # Initialize optimizer and run optimization
        optimizer = RouteOptimizer(ors_api_key=OPENROUTESERVICE_API_KEY)
        optimization_results = optimizer.optimize_multiple_routes(
            df=df,
            route_column=route_column,
            address_columns=address_columns,
            algorithm=algorithm
        )
        
        # Create optimized dataframe
        optimized_df = optimizer.create_optimized_dataframe(
            original_df=df,
            optimization_results=optimization_results,
            route_column=route_column
        )
        
        # Clean optimized data for JSON serialization
        clean_optimized_df = optimized_df.fillna('')
        
        return jsonify({
            'success': True,
            'message': 'Route optimization completed',
            'summary': optimization_results['summary'],
            'optimized_data': clean_optimized_df.to_dict('records'),
            'route_details': {route_id: {
                'route_id': result['route_id'],
                'stops_count': result['stops_count'],
                'distance_saved_km': result['distance_saved'],
                'improvement_pct': result['improvement_pct'],
                'algorithm_used': result['algorithm_used']
            } for route_id, result in optimization_results['routes'].items()}
        })
        
    except Exception as e:
        logger.error(f"Error in route optimization: {str(e)}")
        return jsonify({'error': f'Optimization error: {str(e)}'}), 500

@app.route('/cache/stats', methods=['GET'])
def get_cache_stats():
    """Get geocoding cache statistics"""
    try:
        optimizer = RouteOptimizer(ors_api_key=OPENROUTESERVICE_API_KEY)
        stats = optimizer.get_cache_stats()
        
        return jsonify({
            'success': True,
            'cache_stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cache/clear', methods=['POST'])
def clear_cache():
    """Clear session cache (persistent cache remains)"""
    try:
        optimizer = RouteOptimizer(ors_api_key=OPENROUTESERVICE_API_KEY)
        optimizer.clear_session_cache()
        
        return jsonify({
            'success': True,
            'message': 'Session cache cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cache/clear/routing', methods=['POST'])
def clear_routing_cache():
    """Clear routing cache only"""
    try:
        optimizer = RouteOptimizer(ors_api_key=OPENROUTESERVICE_API_KEY)
        optimizer.clear_routing_cache()
        
        return jsonify({
            'success': True,
            'message': 'Routing cache cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing routing cache: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cache/clear/all', methods=['POST'])
def clear_all_caches():
    """Clear session and routing caches (keeps geocoding cache)"""
    try:
        optimizer = RouteOptimizer(ors_api_key=OPENROUTESERVICE_API_KEY)
        optimizer.clear_all_caches()
        
        return jsonify({
            'success': True,
            'message': 'Session and routing caches cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing caches: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 