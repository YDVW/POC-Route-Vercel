import os
import sys
import logging

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')

print("Testing environment variable...")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")

# Check if the environment variable is set
api_key = os.environ.get('OPENROUTESERVICE_API_KEY', None)
print(f"OPENROUTESERVICE_API_KEY = '{api_key}'")

if api_key:
    print(f"✅ API key found! Length: {len(api_key)} characters")
    print(f"First 10 chars: {api_key[:10]}...")
    print(f"Last 10 chars: ...{api_key[-10:]}")
else:
    print("❌ No API key found in environment variables")

# Print all environment variables containing 'ROUTE' or 'OPEN'
print("\nEnvironment variables containing 'ROUTE' or 'OPEN':")
found_vars = False
for key, value in os.environ.items():
    if 'ROUTE' in key.upper() or 'OPEN' in key.upper():
        print(f"  {key} = {value}")
        found_vars = True
if not found_vars:
    print("  No relevant environment variables found")

# Test OpenRouteService import
print("\nTesting OpenRouteService import...")
try:
    import openrouteservice
    print("✅ OpenRouteService imported successfully")
    
    # Try to create client with API key
    if api_key:
        print(f"Creating ORS client with API key: {api_key[:10]}...")
        try:
            client = openrouteservice.Client(key=api_key)
            print("✅ OpenRouteService client created with API key")
        except Exception as e:
            print(f"❌ Error creating ORS client with API key: {e}")
            
            # Try without API key
            try:
                client = openrouteservice.Client()
                print("✅ OpenRouteService client created without API key")
            except Exception as e2:
                print(f"❌ Error creating ORS client without API key: {e2}")
    else:
        print("No API key to test with")
        
except ImportError as e:
    print(f"❌ OpenRouteService import failed: {e}")

# Test RouteOptimizer initialization
print("\nTesting RouteOptimizer initialization...")
try:
    from route_optimizer import RouteOptimizer
    print(f"Creating RouteOptimizer with API key: {api_key}")
    optimizer = RouteOptimizer(ors_api_key=api_key)
    print("✅ RouteOptimizer created successfully")
    
    # Check if ORS client was created
    if hasattr(optimizer, 'ors_client') and optimizer.ors_client:
        print("✅ OpenRouteService client is available")
        print(f"ORS client type: {type(optimizer.ors_client)}")
    else:
        print("❌ OpenRouteService client is None")
        
    # Check rate limiting attributes
    print(f"Last API call: {optimizer.last_api_call}")
    print(f"API calls this minute: {optimizer.api_calls_this_minute}")
        
except Exception as e:
    print(f"❌ Error creating RouteOptimizer: {e}")
    import traceback
    traceback.print_exc() 