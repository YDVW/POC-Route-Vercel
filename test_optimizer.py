#!/usr/bin/env python3
"""
Test script for RouteOptimizer class
Demonstrates both Nearest Neighbor and 2-Opt algorithms
"""

from route_optimizer import RouteOptimizer
import logging
import os

# Set up logging to see the optimization process
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_single_route_optimization():
    """Test optimization of a single route with sample data"""
    print("=" * 60)
    print("TESTING SINGLE ROUTE OPTIMIZATION")
    print("=" * 60)
    
    # Create sample stops (München area)
    sample_stops = [
        {'postal_code': '80331', 'city': 'München', 'customer': 'Customer A'},
        {'postal_code': '80539', 'city': 'München', 'customer': 'Customer B'},
        {'postal_code': '80797', 'city': 'München', 'customer': 'Customer C'},
        {'postal_code': '80469', 'city': 'München', 'customer': 'Customer D'},
        {'postal_code': '80636', 'city': 'München', 'customer': 'Customer E'},
        {'postal_code': '80992', 'city': 'München', 'customer': 'Customer F'}
    ]
    
    # Use API key from environment if available
    ors_api_key = os.environ.get('OPENROUTESERVICE_API_KEY', None)
    optimizer = RouteOptimizer(ors_api_key=ors_api_key)
    
    print(f"Testing route with {len(sample_stops)} stops")
    print("\nOriginal stops order:")
    for i, stop in enumerate(sample_stops):
        print(f"  {i+1}. {stop['customer']} - {stop['postal_code']} {stop['city']}")
    
    # Test all three algorithms
    algorithms = ['nearest_neighbor', '2_opt', 'both']
    
    for algorithm in algorithms:
        print(f"\n--- Testing {algorithm.upper().replace('_', ' ')} ---")
        result = optimizer.optimize_route(sample_stops, algorithm)
        
        print(f"Algorithm: {result['algorithm_used']}")
        print(f"Original distance: {result['original_distance']:.2f} km")
        print(f"Optimized distance: {result['optimized_distance']:.2f} km")
        print(f"Distance saved: {result['distance_saved']:.2f} km ({result['improvement_pct']:.1f}%)")
        print(f"Processing time: {result['processing_time']:.3f} seconds")
        
        print("Optimized stop order:")
        for new_pos, original_pos in enumerate(result['optimized_order']):
            stop = sample_stops[original_pos]
            print(f"  {new_pos+1}. {stop['customer']} - {stop['postal_code']} {stop['city']}")

def test_multi_route_optimization():
    """Test optimization of multiple routes using pandas DataFrame"""
    print("\n" + "=" * 60)
    print("TESTING MULTIPLE ROUTE OPTIMIZATION")
    print("=" * 60)
    
    import pandas as pd
    
    # Create sample data with multiple routes
    sample_data = [
        # Route 1
        {'Planned trip': 'Route_001', 'Name': 'Customer A', 'Street': 'Marienplatz 1', 'Post code': '80331', 'City': 'München'},
        {'Planned trip': 'Route_001', 'Name': 'Customer B', 'Street': 'Maximilianstr 10', 'Post code': '80539', 'City': 'München'},
        {'Planned trip': 'Route_001', 'Name': 'Customer C', 'Street': 'Schwabing Nord', 'Post code': '80797', 'City': 'München'},
        {'Planned trip': 'Route_001', 'Name': 'Customer D', 'Street': 'Lehel', 'Post code': '80469', 'City': 'München'},
        
        # Route 2
        {'Planned trip': 'Route_002', 'Name': 'Customer E', 'Street': 'Neuhausen', 'Post code': '80636', 'City': 'München'},
        {'Planned trip': 'Route_002', 'Name': 'Customer F', 'Street': 'Moosach', 'Post code': '80992', 'City': 'München'},
        {'Planned trip': 'Route_002', 'Name': 'Customer G', 'Street': 'Milbertshofen', 'Post code': '80809', 'City': 'München'},
        
        # Route 3 (Single stop - should not be optimized)
        {'Planned trip': 'Route_003', 'Name': 'Customer H', 'Street': 'Bogenhausen', 'Post code': '81675', 'City': 'München'},
    ]
    
    df = pd.DataFrame(sample_data)
    
    print("Sample data:")
    print(df.to_string(index=False))
    
    # Define column mappings
    address_columns = {
        'postal_code': 'Post code',
        'city': 'City',
        'street': 'Street',
        'customer': 'Name'
    }
    
    # Use API key from environment if available
    ors_api_key = os.environ.get('OPENROUTESERVICE_API_KEY', None)
    optimizer = RouteOptimizer(ors_api_key=ors_api_key)
    
    # Optimize all routes
    results = optimizer.optimize_multiple_routes(
        df=df,
        route_column='Planned trip',
        address_columns=address_columns,
        algorithm='both'
    )
    
    print(f"\n--- OPTIMIZATION RESULTS ---")
    print(f"Total routes processed: {results['summary']['total_routes']}")
    print(f"Routes optimized: {results['summary']['optimized_routes']}")
    print(f"Total stops: {results['summary']['total_stops']}")
    print(f"Total distance saved: {results['summary']['total_distance_saved']:.2f} km")
    print(f"Average improvement: {results['summary']['average_improvement_pct']:.1f}%")
    print(f"Processing time: {results['summary']['processing_time']:.2f} seconds")
    
    # Show detailed results for each route
    for route_id, route_result in results['routes'].items():
        print(f"\n--- {route_id} ---")
        print(f"Stops: {route_result['stops_count']}")
        print(f"Distance saved: {route_result['distance_saved']:.2f} km ({route_result['improvement_pct']:.1f}%)")
        print(f"Algorithm: {route_result['algorithm_used']}")
        
        if route_result['stops_count'] > 1:
            print("Optimized order:")
            for new_pos, original_pos in enumerate(route_result['optimized_order']):
                stop = route_result['stops'][original_pos]
                print(f"  {new_pos+1}. {stop['customer']} - {stop['postal_code']} {stop['city']}")

def test_coordinates_and_distances():
    """Test coordinate generation and distance calculation"""
    print("\n" + "=" * 60)
    print("TESTING COORDINATES AND DISTANCES")
    print("=" * 60)
    
    # Use API key from environment if available
    ors_api_key = os.environ.get('OPENROUTESERVICE_API_KEY', None)
    optimizer = RouteOptimizer(ors_api_key=ors_api_key)
    
    # Test coordinate generation for different postal codes
    test_postcodes = ['80331', '80539', '30159', '22767', '01067', '91054', '48143']
    
    print("Postal code to coordinates mapping:")
    coordinates = []
    for postcode in test_postcodes:
        # Use the correct method signature
        stop_data = {'postal_code': postcode, 'city': '', 'street': ''}
        coords = optimizer.get_coordinates(stop_data)
        coordinates.append((postcode, coords))
        print(f"  {postcode}: {coords[0]:.4f}, {coords[1]:.4f}")
    
    print(f"\nDistance calculations:")
    for i in range(len(coordinates) - 1):
        pc1, coord1 = coordinates[i]
        pc2, coord2 = coordinates[i + 1]
        distance = optimizer.calculate_distance(coord1[0], coord1[1], coord2[0], coord2[1])
        print(f"  {pc1} → {pc2}: {distance:.2f} km")

if __name__ == "__main__":
    print("RouteOptimizer Test Suite")
    print("=" * 60)
    
    # Run all tests
    test_coordinates_and_distances()
    test_single_route_optimization()
    test_multi_route_optimization()
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60) 