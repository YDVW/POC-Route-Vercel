import math
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import requests
import sqlite3
import os
import hashlib

# OpenRouteService will be imported conditionally when needed

logger = logging.getLogger(__name__)

class GeocodingCache:
    """Persistent geocoding cache using SQLite database"""
    
    def __init__(self, db_path: str = "geocoding_cache.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the geocoding cache database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS geocoding_cache (
                    address_hash TEXT PRIMARY KEY,
                    full_address TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    success_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create index for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_address_hash ON geocoding_cache(address_hash)
            ''')
            
            conn.commit()
            conn.close()
            
            # Log cache statistics
            cache_size = self.get_cache_size()
            logger.info(f"Geocoding cache initialized: {cache_size} addresses cached")
            
        except Exception as e:
            logger.error(f"Error initializing geocoding cache: {e}")
    
    def _hash_address(self, address: str) -> str:
        """Create a hash for the address to use as key"""
        return hashlib.md5(address.lower().strip().encode()).hexdigest()
    
    def get_coordinates(self, address: str) -> Optional[Tuple[float, float]]:
        """Get coordinates from cache"""
        try:
            address_hash = self._hash_address(address)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT latitude, longitude FROM geocoding_cache 
                WHERE address_hash = ?
            ''', (address_hash,))
            
            result = cursor.fetchone()
            
            if result:
                # Update last_used timestamp and success_count
                cursor.execute('''
                    UPDATE geocoding_cache 
                    SET last_used = CURRENT_TIMESTAMP, success_count = success_count + 1
                    WHERE address_hash = ?
                ''', (address_hash,))
                conn.commit()
                
                logger.debug(f"Cache hit for: {address[:50]}...")
                return (result[0], result[1])
            
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"Error reading from geocoding cache: {e}")
            return None
    
    def store_coordinates(self, address: str, lat: float, lng: float):
        """Store coordinates in cache"""
        try:
            address_hash = self._hash_address(address)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Insert or update
            cursor.execute('''
                INSERT OR REPLACE INTO geocoding_cache 
                (address_hash, full_address, latitude, longitude, created_at, last_used)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (address_hash, address, lat, lng))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Cached coordinates for: {address[:50]}...")
            
        except Exception as e:
            logger.error(f"Error storing in geocoding cache: {e}")
    
    def get_cache_size(self) -> int:
        """Get number of cached addresses"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM geocoding_cache')
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except:
            return 0
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get basic stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_addresses,
                    SUM(success_count) as total_hits,
                    AVG(success_count) as avg_hits_per_address,
                    MIN(created_at) as oldest_entry,
                    MAX(last_used) as most_recent_use
                FROM geocoding_cache
            ''')
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'total_addresses': result[0],
                    'total_cache_hits': result[1],
                    'avg_hits_per_address': round(result[2], 1) if result[2] else 0,
                    'oldest_entry': result[3],
                    'most_recent_use': result[4]
                }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
        
        return {'total_addresses': 0, 'total_cache_hits': 0}


class RoutingCache:
    """Persistent routing cache for road distances"""
    
    def __init__(self, db_path: str = "routing_cache.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the routing cache database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create table for routing cache
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS routing_cache (
                    route_hash TEXT PRIMARY KEY,
                    from_lat REAL NOT NULL,
                    from_lng REAL NOT NULL,
                    to_lat REAL NOT NULL,
                    to_lng REAL NOT NULL,
                    distance_km REAL NOT NULL,
                    duration_minutes REAL NOT NULL,
                    geometry TEXT,
                    profile TEXT DEFAULT 'driving-car',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Add geometry column to existing tables if it doesn't exist
            try:
                cursor.execute('ALTER TABLE routing_cache ADD COLUMN geometry TEXT')
            except sqlite3.OperationalError:
                # Column already exists
                pass
            
            # Create index for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_route_hash ON routing_cache(route_hash)
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error initializing routing cache: {e}")
    
    def _hash_route(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> str:
        """Create a hash for the route (always driving-car profile)"""
        route_string = f"{from_coords[0]:.6f},{from_coords[1]:.6f}-{to_coords[0]:.6f},{to_coords[1]:.6f}-driving-car"
        return hashlib.md5(route_string.encode()).hexdigest()
    
    def get_route(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> Optional[Dict]:
        """Get route from cache"""
        try:
            route_hash = self._hash_route(from_coords, to_coords)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT distance_km, duration_minutes, geometry FROM routing_cache 
                WHERE route_hash = ?
            ''', (route_hash,))
            
            result = cursor.fetchone()
            
            if result:
                # Update last_used timestamp
                cursor.execute('''
                    UPDATE routing_cache 
                    SET last_used = CURRENT_TIMESTAMP
                    WHERE route_hash = ?
                ''', (route_hash,))
                conn.commit()
                
                return {
                    'distance_km': result[0],
                    'duration_minutes': result[1],
                    'geometry': result[2] if len(result) > 2 else None
                }
            
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"Error reading from routing cache: {e}")
            return None
    
    def store_route(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float], 
                   distance_km: float, duration_minutes: float, geometry: str = None):
        """Store route in cache"""
        try:
            route_hash = self._hash_route(from_coords, to_coords)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO routing_cache 
                (route_hash, from_lat, from_lng, to_lat, to_lng, distance_km, duration_minutes, geometry, profile, created_at, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (route_hash, from_coords[0], from_coords[1], to_coords[0], to_coords[1], 
                  distance_km, duration_minutes, geometry, 'driving-car'))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing in routing cache: {e}")
    
    def get_cache_size(self) -> int:
        """Get number of cached routes"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM routing_cache')
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except:
            return 0

    def clear_cache(self):
        """Clear all cached routes"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM routing_cache')
            conn.commit()
            conn.close()
            logger.info("Routing cache cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing routing cache: {e}")
            raise

    def get_cache_stats(self) -> Dict:
        """Get routing cache statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get basic stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_routes,
                    MIN(created_at) as oldest_entry,
                    MAX(last_used) as most_recent_use,
                    AVG(distance_km) as avg_distance_km,
                    AVG(duration_minutes) as avg_duration_min
                FROM routing_cache
            ''')
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'total_routes': result[0],
                    'oldest_entry': result[1] if result[1] else None,
                    'most_recent_use': result[2] if result[2] else None,
                    'avg_distance_km': round(result[3], 2) if result[3] else 0,
                    'avg_duration_min': round(result[4], 1) if result[4] else 0
                }
            
        except Exception as e:
            logger.error(f"Error getting routing cache stats: {e}")
        
        return {'total_routes': 0}


class RouteOptimizer:
    """Route optimization using Nearest Neighbor and 2-Opt algorithms"""
    
    def __init__(self, ors_api_key: str = None):
        # Initialize geocoder
        self.geocoder = Nominatim(user_agent="route_optimizer_app")
        
        # Initialize persistent caches
        self.geocoding_cache = GeocodingCache()
        self.routing_cache = RoutingCache()
        
        # In-memory cache for current session (faster access)
        self.session_cache = {}
        
        # Routing setup with rate limiting for free tier
        self.ors_client = None
        self.last_api_call = 0  # Track last API call for rate limiting
        self.api_calls_this_minute = 0  # Track calls per minute
        self.minute_start = 0  # Track when current minute started
        
        try:
            import openrouteservice
            
            if ors_api_key:
                # Use provided API key
                self.ors_client = openrouteservice.Client(key=ors_api_key)
                logger.info("Road routing enabled with OpenRouteService API key (2000 requests/day, 40 requests/min)")
            else:
                # Try different approaches without API key
                try:
                    # Try with no API key (might work with public instances)
                    self.ors_client = openrouteservice.Client()
                    logger.info("Road routing enabled with OpenRouteService free tier (40 requests/min, with smart caching)")
                except ValueError as e:
                    if "API key" in str(e):
                        try:
                            # Try with empty API key
                            self.ors_client = openrouteservice.Client(key='')
                            logger.info("Road routing enabled with OpenRouteService (no API key)")
                        except:
                            # Try with public demo instance
                            self.ors_client = openrouteservice.Client(base_url='https://api.openrouteservice.org')
                            logger.info("Road routing enabled with OpenRouteService public API")
                    else:
                        raise e
        except ImportError:
            logger.info("OpenRouteService not available. Using air distance only.")
        except Exception as e:
            logger.warning(f"OpenRouteService initialization failed: {e}. Using air distance only.")
        
        # German postal code to coordinate mapping (fallback)
        self.postal_coordinates = {
            '80': [48.1351, 11.5820],  # München center
            '81': [48.1200, 11.5800],  # München south
            '82': [48.0500, 11.4500],  # München southwest  
            '85': [48.2500, 11.7500],  # München east/north
            '30': [52.3759, 9.7320],   # Hannover
            '48': [51.9607, 7.6261],   # Münster
            '49': [52.4069, 7.8687],   # Emsland
            '86': [48.3000, 10.9000],  # Augsburg area
            '91': [49.4521, 11.0767],  # Nürnberg area
            '60': [50.1109, 8.6821],   # Frankfurt
            '22': [53.5511, 9.9937],   # Hamburg
            '01': [51.0504, 13.7373],  # Dresden
        }
    
    def geocode_address(self, street: str, postal_code: str, city: str) -> Tuple[float, float]:
        """Geocode full address using Nominatim service with persistent caching"""
        # Create full address string
        address_parts = []
        if street and str(street).strip() and str(street).strip().lower() != 'nan':
            address_parts.append(str(street).strip())
        if postal_code and str(postal_code).strip():
            address_parts.append(str(postal_code).strip())
        if city and str(city).strip() and str(city).strip().lower() != 'nan':
            address_parts.append(str(city).strip())
        
        full_address = ', '.join(address_parts) + ', Germany'
        
        # Check session cache first (fastest)
        if full_address in self.session_cache:
            return self.session_cache[full_address]
        
        # Check persistent cache
        cached_coords = self.geocoding_cache.get_coordinates(full_address)
        if cached_coords:
            # Store in session cache for even faster access
            self.session_cache[full_address] = cached_coords
            logger.info(f"Cache hit: {full_address[:50]}... -> {cached_coords}")
            return cached_coords
        
        try:
            # Try geocoding with full address
            location = self.geocoder.geocode(full_address, timeout=10)
            if location:
                coords = (location.latitude, location.longitude)
                # Store in both caches
                self.session_cache[full_address] = coords
                self.geocoding_cache.store_coordinates(full_address, coords[0], coords[1])
                logger.info(f"Geocoded: {full_address} -> {coords}")
                return coords
            
            # Fallback: try with just postal code and city
            if postal_code and city:
                fallback_address = f"{postal_code} {city}, Germany"
                
                # Check if fallback is cached
                cached_fallback = self.geocoding_cache.get_coordinates(fallback_address)
                if cached_fallback:
                    self.session_cache[full_address] = cached_fallback
                    logger.info(f"Cache hit (fallback): {fallback_address} -> {cached_fallback}")
                    return cached_fallback
                
                location = self.geocoder.geocode(fallback_address, timeout=10)
                if location:
                    coords = (location.latitude, location.longitude)
                    # Store both original and fallback address
                    self.session_cache[full_address] = coords
                    self.geocoding_cache.store_coordinates(full_address, coords[0], coords[1])
                    self.geocoding_cache.store_coordinates(fallback_address, coords[0], coords[1])
                    logger.info(f"Geocoded (fallback): {fallback_address} -> {coords}")
                    return coords
            
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(f"Geocoding failed for {full_address}: {e}")
        except Exception as e:
            logger.error(f"Unexpected geocoding error for {full_address}: {e}")
        
        # Final fallback to postal code mapping
        return self.get_coordinates_from_postal(postal_code, city)
    
    def get_coordinates_from_postal(self, postal_code: str, city: str = '') -> Tuple[float, float]:
        """Get approximate coordinates from postal code (fallback method)"""
        try:
            # Clean postal code
            postal = str(postal_code).strip()
            if len(postal) >= 2:
                prefix = postal[:2]
                if prefix in self.postal_coordinates:
                    base_coords = self.postal_coordinates[prefix]
                    # Add some variation based on full postal code for more realistic distribution
                    if len(postal) >= 5:
                        variation = int(postal[2:5]) / 10000  # Small variation
                        return (
                            base_coords[0] + (variation - 0.05),
                            base_coords[1] + (variation - 0.05)
                        )
                    return tuple(base_coords)
            
            # Default to München if postal code not recognized
            logger.warning(f"Unknown postal code: {postal}, using default coordinates")
            return (48.1351, 11.5820)
            
        except Exception as e:
            logger.error(f"Error getting coordinates for {postal_code}: {e}")
            return (48.1351, 11.5820)
    
    def get_coordinates(self, stop_data: Dict) -> Tuple[float, float]:
        """Get coordinates for a stop, trying geocoding first, then postal code fallback"""
        street = stop_data.get('street', '')
        postal_code = stop_data.get('postal_code', '')
        city = stop_data.get('city', '')
        
        # Try full address geocoding first
        return self.geocode_address(street, postal_code, city)
    
    def get_cache_stats(self) -> Dict:
        """Get comprehensive caching statistics"""
        persistent_stats = self.geocoding_cache.get_cache_stats()
        
        stats = {
            'geocoding_cache': persistent_stats,
            'session_cache_size': len(self.session_cache),
            'total_unique_addresses': persistent_stats.get('total_addresses', 0) + len(self.session_cache),
            'routing_enabled': self.ors_client is not None,
            'routing_profile': 'driving-car' if self.ors_client else None
        }
        
        # Add routing cache stats if available
        if self.ors_client:
            stats['routing_cache_size'] = self.routing_cache.get_cache_size()
        
        return stats
    
    def clear_session_cache(self):
        """Clear the current session cache"""
        self.session_cache.clear()
        logger.info("Session cache cleared")

    def clear_routing_cache(self):
        """Clear the persistent routing cache"""
        try:
            self.routing_cache.clear_cache()
        except Exception as e:
            logger.error(f"Error clearing routing cache: {e}")
            raise

    def clear_all_caches(self):
        """Clear session and routing caches only (keeps geocoding cache)"""
        try:
            self.clear_session_cache()
            self.clear_routing_cache()
            logger.info("Session and routing caches cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing caches: {e}")
            raise
    
    def preload_cache_for_addresses(self, addresses: List[str]) -> Dict:
        """Preload cache for a list of addresses and return statistics"""
        cache_hits = 0
        cache_misses = 0
        
        for address in addresses:
            if self.geocoding_cache.get_coordinates(address):
                cache_hits += 1
            else:
                cache_misses += 1
        
        return {
            'total_addresses': len(addresses),
            'cache_hits': cache_hits,
            'cache_misses': cache_misses,
            'cache_hit_rate': (cache_hits / len(addresses) * 100) if addresses else 0
        }
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates - try road routing first, fallback to air distance"""
        # Try road routing if available
        if self.ors_client:
            road_distance = self.calculate_road_distance((lat1, lon1), (lat2, lon2))
            if road_distance is not None:
                return road_distance
        
        # Fallback to air distance
        return self.calculate_air_distance(lat1, lon1, lat2, lon2)
    
    def calculate_road_distance(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> Optional[float]:
        """Calculate actual road distance using OpenRouteService with rate limiting"""
        # Check cache first
        cached_route = self.routing_cache.get_route(from_coords, to_coords)
        if cached_route:
            return cached_route['distance_km']
        
        # If no ORS client available, return None to trigger air distance fallback
        if not self.ors_client:
            return None
        
        # Rate limiting for free tier (40 requests per minute)
        current_time = time.time()
        current_minute = int(current_time // 60)
        
        # Reset counter if we're in a new minute
        if current_minute != self.minute_start:
            self.minute_start = current_minute
            self.api_calls_this_minute = 0
        
        # Check if we've hit the rate limit
        if self.api_calls_this_minute >= 35:  # Keep some buffer below 40
            logger.debug(f"Rate limit reached ({self.api_calls_this_minute}/35 calls this minute), using air distance fallback")
            return None
        
        # Ensure minimum 1.5 seconds between calls (40/min = 1.5s/call)
        time_since_last_call = current_time - self.last_api_call
        if time_since_last_call < 1.6:  # 1.6 seconds to be safe
            sleep_time = 1.6 - time_since_last_call
            logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        
        try:
            # Call OpenRouteService API
            coordinates = [
                [from_coords[1], from_coords[0]],  # ORS uses [lng, lat] format
                [to_coords[1], to_coords[0]]
            ]
            
            self.last_api_call = time.time()
            self.api_calls_this_minute += 1
            
            routes = self.ors_client.directions(
                coordinates=coordinates,
                profile='driving-car',
                format='geojson'
            )
            
            if routes and 'features' in routes and len(routes['features']) > 0:
                # Extract distance in kilometers and duration in minutes
                properties = routes['features'][0]['properties']
                distance_km = properties['segments'][0]['distance'] / 1000.0  # Convert m to km
                duration_minutes = properties['segments'][0]['duration'] / 60.0  # Convert s to min
                
                # Extract geometry (route path coordinates)
                geometry = None
                if 'geometry' in routes['features'][0]:
                    import json
                    geometry = json.dumps(routes['features'][0]['geometry'])
                
                # Cache the result including geometry
                self.routing_cache.store_route(from_coords, to_coords, distance_km, duration_minutes, geometry)
                
                logger.debug(f"Road route: {distance_km:.2f}km, {duration_minutes:.1f}min (API call {self.api_calls_this_minute}/35)")
                return distance_km
            else:
                logger.debug(f"No road route found between {from_coords} and {to_coords}")
                return None
                
        except Exception as e:
            logger.debug(f"Road routing API call failed: {e}")
            return None
    
    def calculate_air_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates using Haversine formula (in km)"""
        R = 6371  # Earth's radius in km
        
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def get_route_segments(self, stops: List[Dict], route_order: List[int]) -> List[Dict]:
        """Get route segments with geometry for visualization"""
        segments = []
        
        if len(route_order) <= 1:
            return segments
        
        for i in range(len(route_order) - 1):
            from_stop = stops[route_order[i]]
            to_stop = stops[route_order[i + 1]]
            
            from_coords = from_stop['_coordinates']
            to_coords = to_stop['_coordinates']
            
            # Try to get cached route with geometry
            cached_route = self.routing_cache.get_route(from_coords, to_coords)
            
            segment = {
                'from': {
                    'customer': from_stop.get('customer', ''),
                    'coordinates': {'lat': from_coords[0], 'lng': from_coords[1]},
                    'stop_number': i + 1
                },
                'to': {
                    'customer': to_stop.get('customer', ''),
                    'coordinates': {'lat': to_coords[0], 'lng': to_coords[1]},
                    'stop_number': i + 2
                },
                'distance_km': 0,
                'geometry': None,
                'type': 'air'  # default to air distance
            }
            
            if cached_route and cached_route.get('geometry'):
                # Use actual road route geometry
                try:
                    import json
                    geometry_data = json.loads(cached_route['geometry'])
                    segment['geometry'] = geometry_data
                    segment['distance_km'] = cached_route['distance_km']
                    segment['type'] = 'road'
                except:
                    # Fall back to air distance if geometry parsing fails
                    pass
            
            if segment['geometry'] is None:
                # Use straight line for air distance
                segment['distance_km'] = self.calculate_air_distance(
                    from_coords[0], from_coords[1], to_coords[0], to_coords[1]
                )
                # Create simple line geometry for air distance
                segment['geometry'] = {
                    'type': 'LineString',
                    'coordinates': [
                        [from_coords[1], from_coords[0]],  # [lng, lat]
                        [to_coords[1], to_coords[0]]
                    ]
                }
            
            segments.append(segment)
        
        return segments
    
    def create_distance_matrix(self, stops: List[Dict]) -> List[List[float]]:
        """Create distance matrix between all stops"""
        n = len(stops)
        matrix = [[0.0] * n for _ in range(n)]
        
        # Pre-geocode all stops to show progress
        logger.info(f"Geocoding {n} stops...")
        
        # Check cache hit rate first
        cache_stats = self.get_cache_stats()
        logger.info(f"Starting with {cache_stats['geocoding_cache']['total_addresses']} addresses in persistent cache")
        
        geocoded_count = 0
        cache_hits = 0
        
        for i, stop in enumerate(stops):
            # Check if this address was already cached before geocoding
            street = stop.get('street', '')
            postal_code = stop.get('postal_code', '')
            city = stop.get('city', '')
            address_parts = [street, postal_code, city]
            full_address = ', '.join([part for part in address_parts if part and str(part).strip()]) + ', Germany'
            
            was_cached = self.geocoding_cache.get_coordinates(full_address) is not None
            
            coords = self.get_coordinates(stop)
            stop['_coordinates'] = coords  # Cache coordinates in stop data
            
            if was_cached:
                cache_hits += 1
            
            geocoded_count = i + 1
            
            if geocoded_count % 10 == 0 or geocoded_count == n:
                hit_rate = (cache_hits / geocoded_count) * 100
                logger.info(f"Geocoded {geocoded_count}/{n} stops ({cache_hits} cache hits, {hit_rate:.1f}% hit rate)")
        
        final_hit_rate = (cache_hits / n) * 100 if n > 0 else 0
        new_geocodes = n - cache_hits
        logger.info(f"Geocoding complete: {cache_hits} cache hits, {new_geocodes} new geocodes ({final_hit_rate:.1f}% cache hit rate)")
        
        # Create distance matrix
        routing_mode = "road routing (fallback to air distance)" if self.ors_client else "air distance"
        logger.info(f"Creating distance matrix using {routing_mode}...")
        
        total_pairs = n * (n - 1)  # n*(n-1) because we skip i==j
        completed_pairs = 0
        routing_cache_hits = 0
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    coords_i = stops[i]['_coordinates']
                    coords_j = stops[j]['_coordinates']
                    
                    # Check if this route was cached (for road routing)
                    if self.ors_client:
                        cached_route = self.routing_cache.get_route(coords_i, coords_j)
                        if cached_route:
                            routing_cache_hits += 1
                    
                    distance = self.calculate_distance(coords_i[0], coords_i[1], coords_j[0], coords_j[1])
                    matrix[i][j] = distance
                    
                    completed_pairs += 1
                    
                    # Progress logging for large matrices
                    if completed_pairs % 50 == 0 or completed_pairs == total_pairs:
                        if self.ors_client:
                            route_hit_rate = (routing_cache_hits / completed_pairs) * 100
                            logger.info(f"Distance matrix: {completed_pairs}/{total_pairs} routes calculated ({routing_cache_hits} cached, {route_hit_rate:.1f}% hit rate)")
                        else:
                            logger.info(f"Distance matrix: {completed_pairs}/{total_pairs} distances calculated")
        
        if self.ors_client:
            final_route_hit_rate = (routing_cache_hits / total_pairs) * 100 if total_pairs > 0 else 0
            new_routes = total_pairs - routing_cache_hits
            logger.info(f"Distance matrix complete: {routing_cache_hits} routing cache hits, {new_routes} new routes ({final_route_hit_rate:.1f}% routing cache hit rate)")
        else:
            logger.info(f"Distance matrix complete: {total_pairs} air distances calculated")
        
        return matrix
    
    def nearest_neighbor(self, distance_matrix: List[List[float]], start_index: int = 0) -> List[int]:
        """Nearest Neighbor algorithm to find initial route"""
        n = len(distance_matrix)
        if n <= 1:
            return list(range(n))
        
        unvisited = set(range(n))
        route = [start_index]
        unvisited.remove(start_index)
        current = start_index
        
        while unvisited:
            nearest = min(unvisited, key=lambda x: distance_matrix[current][x])
            route.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        
        return route
    
    def calculate_route_distance(self, route: List[int], distance_matrix: List[List[float]]) -> float:
        """Calculate total distance for a route"""
        if len(route) <= 1:
            return 0.0
        
        total_distance = 0.0
        for i in range(len(route) - 1):
            total_distance += distance_matrix[route[i]][route[i + 1]]
        
        return total_distance
    
    def two_opt(self, route: List[int], distance_matrix: List[List[float]], 
                max_iterations: int = 1000) -> Tuple[List[int], bool]:
        """2-Opt improvement algorithm"""
        if len(route) <= 3:
            return route, False
        
        best_route = route.copy()
        best_distance = self.calculate_route_distance(best_route, distance_matrix)
        improved = False
        iterations = 0
        
        while iterations < max_iterations:
            current_improved = False
            
            for i in range(1, len(route) - 2):
                for j in range(i + 1, len(route)):
                    if j - i == 1:
                        continue  # Skip adjacent edges
                    
                    # Create new route by reversing segment between i and j
                    new_route = route[:i] + route[i:j][::-1] + route[j:]
                    new_distance = self.calculate_route_distance(new_route, distance_matrix)
                    
                    if new_distance < best_distance:
                        best_route = new_route.copy()
                        best_distance = new_distance
                        route = new_route.copy()
                        improved = True
                        current_improved = True
                        break
                
                if current_improved:
                    break
            
            if not current_improved:
                break
            
            iterations += 1
        
        logger.info(f"2-Opt completed after {iterations} iterations, improved: {improved}")
        return best_route, improved
    
    def optimize_route(self, stops: List[Dict], algorithm: str = 'both') -> Dict:
        """
        Optimize a single route using specified algorithm(s)
        
        Args:
            stops: List of stop dictionaries with required keys: postal_code, city
            algorithm: 'nearest_neighbor', '2_opt', or 'both'
        
        Returns:
            Dictionary with optimization results
        """
        start_time = time.time()
        
        if len(stops) <= 1:
            return {
                'original_order': [0] if stops else [],
                'optimized_order': [0] if stops else [],
                'original_distance': 0.0,
                'optimized_distance': 0.0,
                'distance_saved': 0.0,
                'improvement_pct': 0.0,
                'algorithm_used': algorithm,
                'processing_time': time.time() - start_time,
                'stops_count': len(stops)
            }
        
        # Create distance matrix
        distance_matrix = self.create_distance_matrix(stops)
        
        # Original order (as provided)
        original_order = list(range(len(stops)))
        original_distance = self.calculate_route_distance(original_order, distance_matrix)
        
        # Apply optimization algorithm
        if algorithm == 'nearest_neighbor':
            optimized_order = self.nearest_neighbor(distance_matrix, 0)
            algorithm_used = 'Nearest Neighbor'
            
        elif algorithm == '2_opt':
            # Start with original order and apply 2-opt
            optimized_order, improved = self.two_opt(original_order, distance_matrix)
            algorithm_used = '2-Opt'
            
        elif algorithm == 'both':
            # First apply nearest neighbor, then 2-opt
            nn_order = self.nearest_neighbor(distance_matrix, 0)
            optimized_order, improved = self.two_opt(nn_order, distance_matrix)
            algorithm_used = 'Nearest Neighbor + 2-Opt'
            
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        
        # Calculate improvements
        optimized_distance = self.calculate_route_distance(optimized_order, distance_matrix)
        distance_saved = original_distance - optimized_distance
        improvement_pct = (distance_saved / original_distance * 100) if original_distance > 0 else 0
        
        processing_time = time.time() - start_time
        
        logger.info(f"Route optimization: {len(stops)} stops, "
                   f"{distance_saved:.2f}km saved ({improvement_pct:.1f}%), "
                   f"{processing_time:.3f}s")
        
        # Get route segments with geometry for visualization
        original_segments = self.get_route_segments(stops, original_order)
        optimized_segments = self.get_route_segments(stops, optimized_order)
        
        return {
            'original_order': original_order,
            'optimized_order': optimized_order,
            'original_distance': round(original_distance, 2),
            'optimized_distance': round(optimized_distance, 2),
            'distance_saved': round(distance_saved, 2),
            'improvement_pct': round(improvement_pct, 1),
            'algorithm_used': algorithm_used,
            'processing_time': round(processing_time, 3),
            'stops_count': len(stops),
            'original_segments': original_segments,
            'optimized_segments': optimized_segments
        }
    
    def optimize_multiple_routes(self, df: pd.DataFrame, route_column: str, 
                               address_columns: Dict[str, str], 
                               algorithm: str = 'both') -> Dict:
        """
        Optimize multiple routes from a DataFrame
        
        Args:
            df: DataFrame with route data
            route_column: Name of column containing route identifiers
            address_columns: Dict mapping 'postal_code', 'city', etc. to column names
            algorithm: Optimization algorithm to use
        
        Returns:
            Dictionary with results for all routes
        """
        start_time = time.time()
        
        # Group by route
        routes = df.groupby(route_column)
        results = {}
        total_distance_saved = 0
        total_stops = 0
        
        logger.info(f"Optimizing {len(routes)} routes with {algorithm} algorithm")
        
        for route_id, route_data in routes:
            # Prepare stops data
            stops = []
            for _, row in route_data.iterrows():
                stop = {
                    'postal_code': str(row[address_columns['postal_code']]) if 'postal_code' in address_columns else '',
                    'city': str(row[address_columns['city']]) if 'city' in address_columns else '',
                    'street': str(row[address_columns['street']]) if 'street' in address_columns else '',
                    'customer': str(row[address_columns.get('customer', route_data.columns[0])]) if len(route_data.columns) > 0 else '',
                    'original_index': row.name
                }
                stops.append(stop)
            
            # Optimize this route
            if len(stops) > 1:  # Only optimize routes with multiple stops
                route_result = self.optimize_route(stops, algorithm)
                route_result['route_id'] = route_id
                route_result['stops'] = stops
                results[route_id] = route_result
                
                total_distance_saved += route_result['distance_saved']
                total_stops += route_result['stops_count']
            else:
                # Single stop route - no optimization needed
                results[route_id] = {
                    'route_id': route_id,
                    'stops': stops,
                    'original_order': [0],
                    'optimized_order': [0],
                    'original_distance': 0.0,
                    'optimized_distance': 0.0,
                    'distance_saved': 0.0,
                    'improvement_pct': 0.0,
                    'algorithm_used': 'No optimization needed',
                    'processing_time': 0.0,
                    'stops_count': 1
                }
        
        processing_time = time.time() - start_time
        
        # Calculate overall statistics
        optimized_routes = [r for r in results.values() if r['stops_count'] > 1]
        avg_improvement = sum(r['improvement_pct'] for r in optimized_routes) / len(optimized_routes) if optimized_routes else 0
        
        summary = {
            'total_routes': len(results),
            'optimized_routes': len(optimized_routes),
            'total_stops': total_stops,
            'total_distance_saved': round(total_distance_saved, 2),
            'average_improvement_pct': round(avg_improvement, 1),
            'processing_time': round(processing_time, 2),
            'algorithm_used': algorithm
        }
        
        logger.info(f"Optimization complete: {summary['total_distance_saved']}km saved "
                   f"({summary['average_improvement_pct']}% avg improvement)")
        
        return {
            'summary': summary,
            'routes': results
        }

    def create_optimized_dataframe(self, original_df: pd.DataFrame, optimization_results: Dict,
                                 route_column: str) -> pd.DataFrame:
        """Create a new DataFrame with optimized stop order"""
        optimized_rows = []
        
        for route_id, route_result in optimization_results['routes'].items():
            route_data = original_df[original_df[route_column] == route_id].copy()
            optimized_order = route_result['optimized_order']
            stops = route_result['stops']
            
            # Reorder according to optimization
            for new_position, original_position in enumerate(optimized_order):
                original_index = stops[original_position]['original_index']
                row = route_data.loc[original_index].copy()
                
                # Add optimization metadata
                row['Original_Stop_Number'] = original_position + 1
                row['Optimized_Stop_Number'] = new_position + 1
                row['Distance_To_Next_km'] = 0.0  # Will be calculated separately
                
                optimized_rows.append(row)
        
        return pd.DataFrame(optimized_rows) 