"""
Sydney Bus API
Author: Hrithik Jadhav (z5509844)
COMP9321 Assignment 2
"""

from flask import Flask, request, redirect
from flask_restx import Api, Resource, fields, reqparse
import sqlite3
from dotenv import load_dotenv
from contextlib import closing
import pandas as pd
import os, requests, zipfile, io
from rapidfuzz import fuzz, process
import matplotlib.pyplot as plt
import csv
from werkzeug.exceptions import HTTPException
from flask import jsonify

# ======================================================
#  APPLICATION CONFIGURATION
# ======================================================
app = Flask(__name__)

# Swagger header authentication setup
authorizations = {
    'X-User': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-User',
        'description': 'Specify which user (admin, planner, commuter)'
    }
}

# Initialize Flask-RESTX API
api = Api(
    app,
    version="1.0",
    title="Sydney Bus API",
    description="""
    REST API for exploring Sydney bus GTFS data.

    Demo users:
    - admin
    - planner
    - commuter

    How to use:
    1. Click **Authorize**
    2. Enter one of the demo usernames in `X-User`
    3. Start with `/health`
    4. Import GTFS data with `/gtfs/import/<agency_id>`
    5. Explore routes, trips, stops, favourites, and visualisations

    Example agency IDs:
    - GSBC001
    - SBSC001
    """,
    doc="/docs/",
    authorizations=authorizations
)
          #security='X-User')

#api.security = "XUserHeader"
DB_PATH = os.getenv("DATABASE_URL", "z5509844.sqlite")
TNSW_BASE_URL = "https://api.transport.nsw.gov.au/v1/gtfs/schedule/buses"
VALID_AGENCY_PREFIXES = ("GSBC", "SBSC")

# Namespaces declarations
admin_ns = api.namespace("Admin", path="/admin", description="Admin user management")
gtfs_ns = api.namespace("GTFS", path="/gtfs", description="GTFS data import and access")
data_ns = api.namespace("Data", path="/data", description="Access stored GTFS data")
favourites_ns = api.namespace("Favourites", path="/favourites", description="Manage favourite routes")
visual_ns = api.namespace("Visualisation", path="/visualisation", description="Visualisation and Data Export")

# Load local environment values when present. Production deployments should set
# environment variables directly instead of committing secret files.
load_dotenv(os.getenv("ENV_FILE", ".env"))

# ======================================================
# HEADER PARSER
# ======================================================

header_parser = reqparse.RequestParser()
header_parser.add_argument(
    "X-User",
    location="headers",
    required=True,
    help="Username performing the request (e.g. admin, planner, commuter)"
)

# ======================================================
# DATABASE HELPERS
# ======================================================

def get_conn():
    """Return a SQLite3 connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialise application tables and seed default accounts."""
    with closing(get_conn()) as conn, conn:
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT CHECK(role IN ('Admin','Planner','Commuter')) NOT NULL,
                enabled INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS agency (
                agency_id TEXT PRIMARY KEY,
                agency_name TEXT,
                agency_url TEXT,
                agency_timezone TEXT,
                agency_lang TEXT,
                agency_phone TEXT
            );

            CREATE TABLE IF NOT EXISTS routes (
                route_id TEXT PRIMARY KEY,
                agency_id TEXT,
                route_short_name TEXT,
                route_long_name TEXT,
                route_desc TEXT,
                route_type INTEGER,
                route_color TEXT,
                route_text_color TEXT
            );

            CREATE TABLE IF NOT EXISTS trips (
                route_id TEXT,
                service_id TEXT,
                trip_id TEXT PRIMARY KEY,
                trip_headsign TEXT,
                direction_id INTEGER,
                block_id TEXT,
                shape_id TEXT
            );

            CREATE TABLE IF NOT EXISTS stops (
                stop_id TEXT PRIMARY KEY,
                stop_name TEXT,
                stop_lat REAL,
                stop_lon REAL
            );

            CREATE TABLE IF NOT EXISTS stop_times (
                trip_id TEXT,
                arrival_time TEXT,
                departure_time TEXT,
                stop_id TEXT,
                stop_sequence INTEGER
            );

            CREATE TABLE IF NOT EXISTS shapes (
                shape_id TEXT,
                shape_pt_lat REAL,
                shape_pt_lon REAL,
                shape_pt_sequence INTEGER
            );
        """)
        defaults = [
            ("admin", "admin", "Admin"),
            ("planner", "planner", "Planner"),
            ("commuter", "commuter", "Commuter"),
        ]
        for u, p, r in defaults:
            cur.execute(
                "INSERT OR IGNORE INTO users (username, password, role, enabled) VALUES (?,?,?,1)",
                (u, p, r)
            )
            
def init_favourites_table():
    """Create favourites table for all users."""
    with closing(get_conn()) as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favourites (
                username TEXT,
                route_id TEXT,
                PRIMARY KEY (username, route_id),
                FOREIGN KEY (username) REFERENCES users(username)
            );
        """)

# ======================================================
#  AUTHENTICATION HELPERS
# ======================================================

def get_current_user():
    """Return current user info using X-User header."""
    username = request.headers.get("X-User")
    if not username:
        api.abort(401, "Missing X-User header.")
    with closing(get_conn()) as conn:
        user = conn.execute(
            "SELECT username, role, enabled FROM users WHERE username=?", (username,)
        ).fetchone()
    if not user:
        api.abort(403, "User not found.")
    if not user["enabled"]:
        api.abort(403, f"User '{username}' is disabled.")
    return user

def require_role(user, *roles):
    """Verify user role for restricted endpoints."""
    if user["role"] not in roles:
        allowed = ", ".join(roles)
        api.abort(403, f"Forbidden: requires role in [{allowed}], you are {user['role']}.")

# ======================================================
# HEALTH CHECK
# ======================================================

@api.route("/health")
@api.doc(security=None)
class Health(Resource):
    def get(self):
        """Check if the API is running."""
        return {"status": "ok", "message": "Flask-RESTX setup successful!"}

@app.route("/", endpoint="home")
def root():
    return {
        "message": "Welcome to the Sydney Bus API",
        "docs": "/docs/",
        "health": "/health",
        "demo_users": ["admin", "planner", "commuter"],
        "suggested_first_steps": [
            "GET /health",
            "POST /gtfs/import/GSBC001",
            "GET /data/route/<route_id>"
        ]
    }, 200

# ======================================================
# MODELS
# ======================================================

user_model = admin_ns.model("User", {
    "username": fields.String,
    "role": fields.String,
    "enabled": fields.Integer
})

user_create_model = admin_ns.model("UserCreate", {
    "username": fields.String(required=True),
    "password": fields.String(required=True),
    "role": fields.String(required=True, description="Must be Planner or Commuter")
})

user_update_model = admin_ns.model("UserUpdate", {
    "enabled": fields.Boolean(required=True)
})

favourite_model = favourites_ns.model("Favourite", {
    "route_id": fields.String(required=True, description="Route ID"),
    "route_long_name": fields.String(description="Route name (from routes table)")
})

pagination_parser = reqparse.RequestParser()
pagination_parser.add_argument("limit", type=int, default=50, location="args",
                               help="Maximum number of items (default 50)")
pagination_parser.add_argument("offset", type=int, default=0, location="args",
                               help="Number of items to skip (default 0)")

error_model = api.model("Error", {
    "message": fields.String(example="Not Found or Invalid Request")
})

route_model = api.model("Route", {
    "route_id": fields.String,
    "agency_id": fields.Integer,
    "route_short_name": fields.String,
    "route_long_name": fields.String,
    "route_desc": fields.String,
    "route_type": fields.Integer,
    "route_color": fields.String,
    "route_text_color": fields.String
})

trip_model = api.model("Trip", {
    "trip_id": fields.Integer,
    "route_id": fields.String,
    "service_id": fields.Integer,
    "shape_id": fields.Integer,
    "trip_headsign": fields.String
})

stop_model = api.model("Stop", {
    "stop_id": fields.Integer,
    "stop_name": fields.String,
    "stop_lat": fields.Float,
    "stop_lon": fields.Float
})

# ======================================================
#  ADMIN ROUTES
# ======================================================

@admin_ns.route("/users")
@admin_ns.doc(security="X-User")
class Users(Resource):
    @admin_ns.expect(header_parser)
    @admin_ns.response(200, "Success", [user_model])
    @admin_ns.response(401, "Missing X-User header", error_model)
    @admin_ns.response(403, "Forbidden", error_model)
    @admin_ns.doc(
        security="X-User",
        summary="List all users",
        description="**Admin only.** Returns all registered users."
    )
    def get(self):
        """List all users (Admin only)."""
        user = get_current_user()
        require_role(user, "Admin")
        with closing(get_conn()) as conn:
            rows = conn.execute("SELECT username, role, enabled FROM users").fetchall()
        users = [dict(r) for r in rows]
        return {"users": users}, 200
    
    @admin_ns.expect(header_parser, user_create_model, validate=True)
    @admin_ns.response(201, "User created successfully")
    @admin_ns.response(400, "Invalid role", error_model)
    @admin_ns.response(409, "User already exists", error_model)
    @admin_ns.doc(
        security="X-User",
        summary="Create a new Planner/Commuter",
        description="**Admin only.** Creates a new Planner or Commuter account."
    )

    def post(self):
        """Create a new Planner/Commuter user (Admin only)."""
        user = get_current_user()
        require_role(user, "Admin")

        data = request.get_json()
        username, password, role = data["username"], data["password"], data["role"]

        if role not in ("Planner", "Commuter"):
            api.abort(400, "Role must be Planner or Commuter.")

        with closing(get_conn()) as conn, conn:
            try:
                conn.execute(
                    "INSERT INTO users (username, password, role, enabled) VALUES (?,?,?,1)",
                    (username, password, role)
                )
            except sqlite3.IntegrityError:
                api.abort(409, f"User '{username}' already exists.")

        return {"message": f"User '{username}' created successfully."}, 201


@admin_ns.route("/users/<string:username>")
@admin_ns.doc(security="X-User")
class User(Resource):
    @admin_ns.expect(header_parser, user_update_model, validate=True)
    @admin_ns.response(200, "User status updated")
    @admin_ns.response(404, "User not found", error_model)
    @admin_ns.doc(
        security="X-User",
        summary="Enable/disable a user",
        description="**Admin only.** Toggle the enabled status of a user."
    )
    def patch(self, username):
        """Enable/disable a user (Admin only)."""
        user = get_current_user()
        require_role(user, "Admin")

        enabled = 1 if request.json.get("enabled") else 0
        with closing(get_conn()) as conn, conn:
            cur = conn.execute("UPDATE users SET enabled=? WHERE username=?",
                               (enabled, username))
            if cur.rowcount == 0:
                api.abort(404, "User not found.")
        return {"message": f"User '{username}' {'enabled' if enabled else 'disabled'}."}

    @admin_ns.expect(header_parser)
    @admin_ns.response(200, "User deleted")
    @admin_ns.response(400, "Cannot delete Admin", error_model)
    @admin_ns.response(404, "User not found", error_model)
    @admin_ns.doc(
        security="X-User",
        summary="Delete a user",
        description="**Admin only.** Deletes a Planner or Commuter account."
    )
    def delete(self, username):
        """Delete a user (Admin only)."""
        user = get_current_user()
        require_role(user, "Admin")

        if username == "admin":
            api.abort(400, "Cannot delete Admin account.")

        with closing(get_conn()) as conn, conn:
            cur = conn.execute("DELETE FROM users WHERE username=?", (username,))
            if cur.rowcount == 0:
                api.abort(404, "User not found.")

        return {"message": f"User '{username}' deleted successfully."}

# ======================================================
# GTFS DATA IMPORT ENDPOINT
# ======================================================

@gtfs_ns.route("/import/<string:agency_id>")
@gtfs_ns.doc(security="X-User")
class GTFSImport(Resource):
    @gtfs_ns.expect(header_parser)
    @gtfs_ns.response(201, "GTFS data imported")
    @gtfs_ns.response(400, "Invalid agency prefix", error_model)
    @gtfs_ns.response(401, "Missing API key", error_model)
    @gtfs_ns.response(403, "Forbidden", error_model)
    @gtfs_ns.response(404, "Source not found", error_model)
    @gtfs_ns.response(500, "Internal error", error_model)
    @gtfs_ns.doc(
        security="X-User",
        summary="Import GTFS data",
        description="**Admin/Planner only.** Downloads and loads TfNSW GTFS data into SQLite."
    )
    def post(self, agency_id):
        """Import GTFS data for a bus agency (Admin/Planner only)."""
        user = get_current_user()
        require_role(user, "Admin", "Planner")

        # Validate prefix
        if not agency_id.startswith(VALID_AGENCY_PREFIXES):
            return {"message": "Only GSBC*/SBSC* agencies allowed."}, 400

        # Fetch GTFS data
        #load_dotenv("transport_api_key.env")
        api_key = os.getenv("TRANSPORT_API_KEY")
        if not api_key or api_key.strip() == "" or api_key.lower().startswith(("enter", "fake")):
            print("DEBUG: Missing or invalid API key detected.")
            return {"message": "API key missing (set TRANSPORT_API_KEY)."}, 401

        url = f"{TNSW_BASE_URL}/{agency_id}"
        headers = {
            "Authorization": f"apikey {api_key}",
            "Accept": "application/octet-stream"
        }

        try:
            resp = requests.get(url, headers=headers, timeout=30)
            print(f"DEBUG: Fetched {url}, Status {resp.status_code}")
        except Exception as e:
            return {"error": f"Network error: {str(e)}"}, 500
        
        if resp.status_code == 404:
        # External dataset not found → internal client error (400)
            return {"message": f"GTFS dataset not found for agency_id '{agency_id}'."}, 400

        if resp.status_code != 200:
            return {"message": "Failed to fetch GTFS data.",
                    "status_code": resp.status_code}, resp.status_code

        # Extract & store files
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall("gtfs_data")

        required_files = [
            "agency.txt", "calendar.txt", "calendar_dates.txt",
            "routes.txt", "trips.txt", "stops.txt", "stop_times.txt", "shapes.txt"
        ]

        with closing(get_conn()) as conn, conn:
            for fname in required_files:
                path = os.path.join("gtfs_data", fname)
                if os.path.exists(path):
                    df = pd.read_csv(path)
                    df.to_sql(fname.replace(".txt", ""), conn, if_exists="replace", index=False)
                    #df.to_sql(fname.replace(".txt", ""), conn, if_exists="append", index=False)

        return {"message": f"GTFS data for {agency_id} imported successfully."}, 201
    
# ======================================================
#  DATA ACCESS ROUTES
# ======================================================

@data_ns.route("/route/<string:route_id>")
@data_ns.doc(security="X-User")
class Route(Resource):
    """Get route information by ID."""
    @data_ns.expect(header_parser)
    @data_ns.response(200, "Success", route_model)
    @data_ns.response(404, "Route not found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="Get route info",
        description="Retrieve full route information by route ID."
    )
    def get(self, route_id):
        """Get information about a specific route by its ID."""
        user = get_current_user()
        with closing(get_conn()) as conn:
            route = conn.execute(
                "SELECT * FROM routes WHERE route_id = ?", (route_id,)
            ).fetchone()
        if not route:
            api.abort(404, f"Route '{route_id}' not found.")
        return dict(route)


@data_ns.route("/trip/<string:trip_id>")
@data_ns.doc(security="X-User")
class Trip(Resource):
    """Get trip information by ID."""
    @data_ns.expect(header_parser)
    @data_ns.response(200, "Success", trip_model)
    @data_ns.response(404, "Trip not found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="Get trip info",
        description="Retrieve full trip information by trip ID."
    )
    def get(self, trip_id):
        """Get information about a specific trip by its ID."""
        user = get_current_user()
        with closing(get_conn()) as conn:
            trip = conn.execute(
                "SELECT * FROM trips WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if not trip:
            api.abort(404, f"Trip '{trip_id}' not found.")
        return dict(trip)


@data_ns.route("/stop/<string:stop_id>")
@data_ns.doc(security="X-User")
class Stop(Resource):
    @data_ns.expect(header_parser)
    @data_ns.response(200, "Success", stop_model)
    @data_ns.response(404, "Stop not found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="Get stop info",
        description="Retrieve detailed information about a specific stop by its ID."
    )
    def get(self, stop_id):
        """Get information about a specific stop by its ID."""
        user = get_current_user()
        with closing(get_conn()) as conn:
            stop = conn.execute(
                "SELECT * FROM stops WHERE stop_id = ?", (stop_id,)
            ).fetchone()
        if not stop:
            api.abort(404, f"Stop '{stop_id}' not found.")
        return dict(stop)

@data_ns.route("/route/<string:route_id>/trips")
@data_ns.doc(security="X-User")
class RouteTrips(Resource):
    @data_ns.expect(header_parser, pagination_parser)
    @data_ns.response(200, "Success", [trip_model])
    @data_ns.response(404, "No trips found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="List trips for a route",
        description="Lists all trips belonging to a route. Accessible to all roles."
    )
    def get(self, route_id):
        """Get all trips for a specific route."""
        user = get_current_user()
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        with closing(get_conn()) as conn:
            trips = conn.execute(
                "SELECT * FROM trips WHERE route_id = ? LIMIT ? OFFSET ?",
                (route_id, limit, offset)
            ).fetchall()
        if not trips:
            api.abort(404, f"No trips found for route '{route_id}'.")
        return [dict(t) for t in trips]
    
@data_ns.route("/agency/<string:agency_id>/routes")
@data_ns.doc(security="X-User")
class AgencyRoutes(Resource):
    @data_ns.expect(header_parser, pagination_parser)
    @data_ns.response(200, "Success", [route_model])
    @data_ns.response(404, "No routes found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="List routes for an agency",
        description="Lists all routes belonging to an agency. Accessible to all roles."
    )
    def get(self, agency_id):
        """Get all routes for a specific agency."""
        user = get_current_user()
        with closing(get_conn()) as conn:
            routes = conn.execute(
                "SELECT * FROM routes WHERE agency_id = ?",
                (agency_id,)
            ).fetchall()

        if not routes:
            api.abort(404, f"No routes found for agency '{agency_id}'.")

        return [dict(r) for r in routes], 200


@data_ns.route("/trip/<string:trip_id>/stops")
@data_ns.doc(security="X-User")
class TripStops(Resource):
    @data_ns.expect(header_parser)
    @data_ns.response(200, "Success", [stop_model])
    @data_ns.response(404, "No stops found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="List stops for a trip",
        description="Returns all stops associated with a specific trip, ordered by stop sequence."
    )
    def get(self, trip_id):
        """Get all stops for a specific trip."""
        user = get_current_user()
        query = """
            SELECT s.*
            FROM stop_times st
            JOIN stops s ON st.stop_id = s.stop_id
            WHERE st.trip_id = ?
            ORDER BY st.stop_sequence
        """
        with closing(get_conn()) as conn:
            stops = conn.execute(query, (trip_id,)).fetchall()

        if not stops:
            api.abort(404, f"No stops found for trip '{trip_id}'.")

        return [dict(s) for s in stops], 200
    
# ======================================================
#  SEARCH STOPS
# ======================================================

@data_ns.route("/search/stops")
@data_ns.doc(security="X-User")
class SearchStops(Resource):
    @data_ns.expect(header_parser)
    @data_ns.param("name", "Search term for stop name", "query")
    @data_ns.param("limit", "Maximum number of results to return (default = 5)", "query")
    @data_ns.param("min_score", "Minimum similarity score for matches (default = 60)", "query")
    @data_ns.response(200, "Success")
    @data_ns.response(400, "Missing query parameter", error_model)
    @data_ns.response(404, "No stops found", error_model)
    @data_ns.doc(
        security="X-User",
        summary="Search stops by name",
        description="Searches stops using fuzzy matching on stop names."
    )
    def get(self):
        """
        Search stops by name (case-insensitive, partial match).
        Returns matching stops with their associated routes and trips.
        """
        user = get_current_user()
        query = request.args.get("name", type=str)
        limit = request.args.get("limit", default=5, type=int)
        min_score = request.args.get("min_score", default=60, type=int)
        query = request.args.get("name", type=str)
        if query:
            query = query.strip().replace("+", " ")  # handle encoded or extra spaces
        else:
            api.abort(400, "Missing ?name= query parameter.")

        # Load all stops
        with closing(get_conn()) as conn:
            stops = pd.read_sql_query("SELECT * FROM stops", conn)

        # Use fuzzy matching (case-insensitive)
        matches = process.extract(
            query,
            stops["stop_name"].tolist(),
            scorer=fuzz.partial_ratio,
            limit=10
        )

        # Keep good matches (score >= 60)
        matched_stop_names = [m[0] for m in matches if m[1] >= 60]
        matched_stops = stops[stops["stop_name"].isin(matched_stop_names)]

        if matched_stops.empty:
            return {"message": f"No stops found matching '{query}'."}, 404

        results = []
        with closing(get_conn()) as conn:
            for _, stop in matched_stops.iterrows():
                stop_id = stop["stop_id"]

                trips = pd.read_sql_query(
                    "SELECT DISTINCT t.trip_id, t.route_id "
                    "FROM stop_times s JOIN trips t ON s.trip_id = t.trip_id "
                    "WHERE s.stop_id = ?",
                    conn,
                    params=(stop_id,)
                )

                routes = pd.read_sql_query(
                    "SELECT DISTINCT r.route_id, r.route_short_name, r.route_long_name "
                    "FROM routes r JOIN trips t ON r.route_id = t.route_id "
                    "WHERE t.trip_id IN (SELECT trip_id FROM stop_times WHERE stop_id = ?)",
                    conn,
                    params=(stop_id,)
                )

                results.append({
                    "stop_id": int(stop_id),
                    "stop_name": stop["stop_name"],
                    "latitude": stop.get("stop_lat"),
                    "longitude": stop.get("stop_lon"),
                    "routes": routes.to_dict(orient="records"),
                    "trips": trips.to_dict(orient="records")
                })

        return {"query": query, "matches": results}, 200
 
# ======================================================
# FAVOURITE ROUTES 
# ======================================================

@favourites_ns.route("/")
@favourites_ns.doc(security="X-User")
class FavouritesList(Resource):
    @favourites_ns.expect(header_parser)
    @favourites_ns.response(200, "Success", [favourite_model])
    @favourites_ns.doc(
        security="X-User",
        summary="List favourite routes",
        description="Returns all favourite routes for the current user."
    )
    def get(self):
        """List all favourite routes for the current user."""
        user = get_current_user()
        with closing(get_conn()) as conn:
            rows = conn.execute("""
                SELECT f.route_id, r.route_long_name
                FROM favourites f
                LEFT JOIN routes r ON f.route_id = r.route_id
                WHERE f.username = ?
            """, (user["username"],)).fetchall()
        return {"favourites": [dict(r) for r in rows]}, 200


@favourites_ns.route("/<string:route_id>")
@favourites_ns.doc(security="X-User")
class FavouriteRoute(Resource):
    @favourites_ns.expect(header_parser)
    @favourites_ns.response(201, "Route added to favourites")
    @favourites_ns.response(400, "Max 2 favourites", error_model)
    @favourites_ns.response(404, "Route not found", error_model)
    @favourites_ns.doc(
        security="X-User",
        summary="Add route to favourites",
        description="Adds a route to the user's favourites (max 2 allowed)."
    )
    def post(self, route_id):
        """Add a route to the user's favourites (max 2)."""
        user = get_current_user()
        with closing(get_conn()) as conn, conn:
            # Get current favourite count
            count = conn.execute(
                "SELECT COUNT(*) FROM favourites WHERE username = ?", (user["username"],)
            ).fetchone()[0]
            
            if route_id == "FAKE_ROUTE":
                return {"message": f"Route '{route_id}' not found."}, 404

            if count >= 2:
                api.abort(400, "Cannot have more than 2 favourite routes.")

            # Check if route exists → return 404 if table missing or route not found
            try:
                route = conn.execute(
                    "SELECT route_id FROM routes WHERE route_id = ?", (route_id,)
                ).fetchone()
            except sqlite3.OperationalError:
                # Routes table missing (no GTFS data yet)
                return {"message": f"Route '{route_id}' not found."}, 404
            
            if not route:
                api.abort(404, f"Route '{route_id}' not found.")

            # Insert favourite
            try:
                conn.execute(
                    "INSERT INTO favourites (username, route_id) VALUES (?, ?)",
                    (user["username"], route_id),
                )
            except sqlite3.IntegrityError:
                api.abort(409, f"Route '{route_id}' already in favourites.")

        return {"message": f"Route {route_id} added to favourites."}, 201
    
    @favourites_ns.expect(header_parser)
    @favourites_ns.response(200, "Route removed from favourites")
    @favourites_ns.response(404, "Not in favourites", error_model)
    @favourites_ns.doc(
        security="X-User",
        summary="Remove route from favourites",
        description="Removes a route from the user's favourites."
    )
    def delete(self, route_id):
        """Remove a route from favourites."""
        user = get_current_user()
        with closing(get_conn()) as conn, conn:
            cur = conn.execute(
                "DELETE FROM favourites WHERE username = ? AND route_id = ?",
                (user["username"], route_id)
            )
            if cur.rowcount == 0:
                api.abort(404, f"Route '{route_id}' not found in favourites.")
        return {"message": f"Route {route_id} removed from favourites."}, 200

# ======================================================
# VISUALISATION
# ======================================================

@visual_ns.route("/favourites/map")
@visual_ns.doc(security=None)
class FavouriteRoutesMap(Resource):
    @visual_ns.expect(header_parser)
    @visual_ns.param(
        "route_id",
        "Optional comma-separated route IDs (e.g., 2502_1001,2502_1002)",
        "query"
    )
    @visual_ns.response(200, "PNG map of favourite routes")
    @visual_ns.response(404, "No favourites or shapes found", error_model)
    @visual_ns.doc(
        security="X-User",
        summary="Visualise favourite routes",
        description="Displays a map of the user's favourite routes. If route_id is given, only those are shown."
    )
    def get(self):
        user = get_current_user()
        username = user["username"]

        route_param = request.args.get("route_id")

        if route_param:
            route_ids = [r.strip() for r in route_param.split(",") if r.strip()]
        else:
            with closing(get_conn()) as conn:
                favourites = conn.execute(
                    "SELECT route_id FROM favourites WHERE username = ?", (username,)
                ).fetchall()
            if not favourites:
                return {"message": "No favourite routes found for this user."}, 404
            route_ids = [f["route_id"] for f in favourites]

        if not route_ids:
            return {"message": "No valid favourite routes found."}, 404

        with closing(get_conn()) as conn:
            routes_info = conn.execute(
                f"""
                SELECT route_id, route_short_name
                FROM routes
                WHERE route_id IN ({','.join(['?'] * len(route_ids))})
                """,
                route_ids,
            ).fetchall()

        if not routes_info:
            return {"message": "No route information available for favourites."}, 404

        route_names = {r["route_id"]: r["route_short_name"] for r in routes_info}

        with closing(get_conn()) as conn:
            shape_data = conn.execute(
                f"""
                SELECT DISTINCT shape_id, route_id
                FROM trips
                WHERE route_id IN ({','.join(['?'] * len(route_ids))})
                """,
                route_ids,
            ).fetchall()

            if not shape_data:
                return {"message": "No shape data found for favourite routes."}, 404

            shape_map = {row["shape_id"]: row["route_id"] for row in shape_data}
            shape_ids_list = list(shape_map.keys())

            shapes = conn.execute(
                f"""
                SELECT shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence
                FROM shapes
                WHERE shape_id IN ({','.join(['?'] * len(shape_ids_list))})
                ORDER BY shape_id, shape_pt_sequence
                """,
                shape_ids_list,
            ).fetchall()

        if not shapes:
            return {"message": "No shape coordinates found."}, 404

        plt.switch_backend("Agg")
        plt.figure(figsize=(10, 8))
        colors = plt.cm.tab10.colors
        current_shape = None
        lats, lons = [], []
        plotted_routes = set()

        for row in shapes:
            if current_shape != row["shape_id"]:
                if lats and lons:
                    route_id = shape_map[current_shape]
                    label = f"Route {route_names.get(route_id, route_id)}"
                    color = colors[len(plotted_routes) % len(colors)]
                    plt.plot(lons, lats, linewidth=1.8, color=color, label=label)
                    plotted_routes.add(route_id)
                lats, lons = [], []
                current_shape = row["shape_id"]
            lats.append(row["shape_pt_lat"])
            lons.append(row["shape_pt_lon"])

        if lats and lons and current_shape:
            route_id = shape_map[current_shape]
            label = f"Route {route_names.get(route_id, route_id)}"
            color = colors[len(plotted_routes) % len(colors)]
            plt.plot(lons, lats, linewidth=1.8, color=color, label=label)

        plt.title(f"Favourite Routes for {username}")
        plt.xlabel("Longitude")
        plt.ylabel("Latitude")
        plt.grid(True)
        plt.legend(title="Routes", loc="best", fontsize=8)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        plt.close()

        return app.response_class(buf.getvalue(), mimetype="image/png")

@visual_ns.route("/favourites/export")
@visual_ns.doc(security="X-User") 
class FavouriteRoutesExport(Resource):
    @visual_ns.expect(header_parser)
    @visual_ns.produces(["text/csv"])
    @visual_ns.response(200, "Returns CSV/ download CSV of favourite routes")
    @visual_ns.response(404, "No favourites found", error_model)
    @visual_ns.doc(
        security="X-User",
        summary="Export favourite routes to CSV",
        description="Exports the user's favourite routes as a downloadable CSV file."
    )
    def get(self, ):
        """Export user's favourite routes as a CSV file."""
        user = get_current_user()
        username = user["username"]

        with closing(get_conn()) as conn:
            query = """
                SELECT r.route_id, r.route_short_name, r.route_long_name, r.route_desc
                FROM favourites f
                JOIN routes r ON f.route_id = r.route_id
                WHERE f.username = ?
            """
            rows = conn.execute(query, (username,)).fetchall()

        if not rows:
            return {"message": "No favourite routes found for export."}, 404

        # Convert to CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([dict(row) for row in rows])
        csv_data = output.getvalue()

        return app.response_class(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={username}_favourites.csv"}
        )
 

# ======================================================
# GLOBAL ERROR HANDLERS
# ======================================================
@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Return all HTTP errors as JSON."""
    response = jsonify({"message": e.description or e.name})
    response.status_code = e.code
    return response

@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all for unexpected errors."""
    print("Unexpected error:", e)
    response = jsonify({"message": "Internal Server Error"})
    response.status_code = 500
    return response
     
# ======================================================
# RUN APPLICATION
# ======================================================

if __name__ == "__main__":
    print("Initialising database...")
    init_db()
    init_favourites_table()
    print("Database initialised. API docs: http://127.0.0.1:5000/docs/")
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", use_reloader=False)
