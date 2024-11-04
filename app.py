from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from sklearn.metrics.pairwise import haversine_distances
from math import radians
import time
import ssl
import certifi
from geopy.distance import geodesic
from datetime import datetime, timedelta
from nltk.sentiment.vader import SentimentIntensityAnalyzer

app = Flask(__name__)
app.secret_key = "your_secret_key"
ssl_context = ssl.create_default_context(cafile=certifi.where())
geolocator = Nominatim(user_agent="rideServiceApp", ssl_context=ssl_context)
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'TQR'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def generate_password(length=10):
    if length < 8:
        length = 8
    elif length > 12:
        length = 12
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for _ in range(length))

def verify_login(email, password, role):
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to the database.")
        return None
    cursor = conn.cursor(dictionary=True)
    if role == 'admin':
        query = "SELECT * FROM admin WHERE email = %s"
    elif role == 'rider':
        query = "SELECT * FROM rider WHERE email = %s"
    elif role == 'driver':
        query = "SELECT * FROM driver WHERE email = %s"
    else:
        print("Invalid role provided.")
        return None
    cursor.execute(query, (email,))
    user = cursor.fetchone()
    conn.close()
    print(f"User fetched from database: {user}")
    if user and user['password'] == password:
        return user
    else:
        print("Password check failed or no user found.")
    return None

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/aboutus')
def about_us():
    return render_template('aboutus.html')

@app.route('/contactus')
def contact_us():
    return render_template('contactus.html')

@app.route('/affiliate')
def affiliate():
    return render_template('affiliate.html')

@app.route('/help_and_support')
def help_and_support():
    return render_template('help_and_support.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email_or_phone')
        password = request.form.get('password')
        print(f"Trying to log in with Email: {email}, Role: {role}")
        user = verify_login(email, password, role)
        if user:
            print(f"Login successful for user: {user}")
            session['user_id'] = user.get('admin_id') or user.get('rider_id') or user.get('driver_id')
            session['role'] = role
            if role == 'rider':
                return redirect(url_for('rider_search'))
            elif role == 'driver':
                return redirect(url_for('driver_ride_post'))
            elif role == 'admin':
                return redirect(url_for('admin_home'))
        else:
            print("Login failed: Invalid credentials.")
            flash('Login failed. Please check your credentials and try again.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/rider_home')
def rider_home():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM rider WHERE rider_id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return render_template('rider_home.html', user=user)
    else:
        return "User not found", 404
    
@app.route('/rider_search')
def rider_search():
    return render_template('rider_search.html')

def execute_query(query, params):
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to the database.")
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

def calculate_distance(coord1, coord2):
    coord1 = (radians(coord1[0]), radians(coord1[1]))
    coord2 = (radians(coord2[0]), radians(coord2[1]))
    return round(haversine_distances([coord1, coord2])[0][1] * 6371)

def store_ride_details(from_location, to_location, distance, fare):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ride_details (from_location, to_location, distance, fare)
        VALUES (%s, %s, %s, %s)
    """, (from_location, to_location, distance, fare))
    conn.commit()
    cursor.close()
    conn.close()

def get_coordinates_from_landmark(landmark, retries=3):
    for _ in range(retries):
        try:
            location = geolocator.geocode(landmark)
            if location:
                print(f"Coordinates for '{landmark}': ({location.latitude}, {location.longitude})")
                return (location.latitude, location.longitude)
        except GeocoderTimedOut:
            time.sleep(1)
    print(f"Could not retrieve coordinates for {landmark}")
    return None

def calculate_distance(coord1, coord2):
    if coord1 and coord2:
        return round(geodesic(coord1, coord2).kilometers, 2)
    else:
        print("Invalid coordinates provided for distance calculation.")
        return 0

def estimate_duration(distance):
    average_speed_kmh = 30
    duration = (distance / average_speed_kmh) * 60
    return round(duration)

class PaymentCalculator:
    def __init__(self, distance, duration, base_fare=10, rate_per_km=5, rate_per_minute=2, surge_multiplier=1.0):
        self.distance = distance  # in kilometers
        self.duration = duration  # in minutes
        self.base_fare = base_fare
        self.rate_per_km = rate_per_km
        self.rate_per_minute = rate_per_minute
        self.surge_multiplier = surge_multiplier
    def calculate_fare(self):
        distance_fare = self.rate_per_km * self.distance
        time_fare = self.rate_per_minute * self.duration
        total_fare = (self.base_fare + distance_fare + time_fare) * self.surge_multiplier
        return round(total_fare)

@app.route('/rider_search_ride', methods=['POST'])
def rider_search_ride():
    from_location = request.form.get('from').strip()
    to_location = request.form.get('to').strip()
    date = request.form.get('date').strip()
    time = request.form.get('time').strip()
    search_time = datetime.strptime(time, '%H:%M').time()
    
    # Define a ±30 minute window for AI-driven matching
    time_start = (datetime.combine(datetime.today(), search_time) - timedelta(minutes=30)).time()
    time_end = (datetime.combine(datetime.today(), search_time) + timedelta(minutes=30)).time()

    coord_from = get_coordinates_from_landmark(from_location)
    coord_to = get_coordinates_from_landmark(to_location)
    
    if not coord_from or not coord_to:
        return render_template('rider_ride_results.html', rides=[], message="Unable to find coordinates for your search.")

    rides_with_fare = []

    def calculate_fare_for_ride(ride):
        ride_coord_from = get_coordinates_from_landmark(ride['from_location'])
        ride_coord_to = get_coordinates_from_landmark(ride['to_location'])
        if ride_coord_from and ride_coord_to:
            distance = calculate_distance(ride_coord_from, ride_coord_to)
            duration = estimate_duration(distance)
            fare_calculator = PaymentCalculator(distance, duration)
            return fare_calculator.calculate_fare()
        return 0

    # 1. AI-Driven Exact Match Query
    exact_match_query = """
        SELECT dr.*, d.name AS driver_name, d.email AS driver_email, d.phone_number AS driver_contact,
               d.vehicle_type AS vehicle_details, d.vehicle_reg_number, d.license_number
        FROM driver_rides AS dr
        JOIN driver AS d ON dr.driver_id = d.driver_id
        WHERE 
            dr.from_location = %s AND 
            dr.to_location = %s AND 
            dr.date = %s AND 
            dr.status = 'not completed' AND 
            dr.time BETWEEN %s AND %s
    """
    exact_rides = execute_query(exact_match_query, (from_location, to_location, date, time_start, time_end))

    if exact_rides:
        for ride in exact_rides:
            fare = calculate_fare_for_ride(ride)
            rides_with_fare.append({**ride, 'fare': fare})
        print(f"Exact matches found: {len(rides_with_fare)}")
        return render_template('rider_ride_results.html', rides=rides_with_fare, message="Here are your exact search results!")

    # 2. AI-Driven Stop Match Query with ±30 Minute Flexibility
    stop_match_query = """
        SELECT dr.*, d.name AS driver_name, d.email AS driver_email, d.phone_number AS driver_contact,
               d.vehicle_type AS vehicle_details, d.vehicle_reg_number, d.license_number
        FROM driver_rides AS dr
        JOIN driver AS d ON dr.driver_id = d.driver_id
        WHERE 
            (dr.stop1 = %s OR dr.stop2 = %s) AND 
            (dr.from_location = %s OR dr.to_location = %s) AND 
            dr.date = %s AND 
            dr.status = 'not completed' AND 
            dr.time BETWEEN %s AND %s
    """
    stop_rides = execute_query(stop_match_query, (from_location, from_location, to_location, to_location, date, time_start, time_end))

    if stop_rides:
        for ride in stop_rides:
            fare = calculate_fare_for_ride(ride)
            rides_with_fare.append({**ride, 'fare': fare})
        print(f"Stop matches found: {len(rides_with_fare)}")
        return render_template('rider_ride_results.html', rides=rides_with_fare, message="Here are your stop search results!")

    # 3. AI-Driven Partial Match Query with ±30 Minute Flexibility
    partial_match_query = """
        SELECT dr.*, d.name AS driver_name, d.email AS driver_email, d.phone_number AS driver_contact,
               d.vehicle_type AS vehicle_details, d.vehicle_reg_number, d.license_number
        FROM driver_rides AS dr
        JOIN driver AS d ON dr.driver_id = d.driver_id
        WHERE 
            (dr.from_location LIKE %s OR dr.to_location LIKE %s OR dr.stop1 LIKE %s OR dr.stop2 LIKE %s) AND 
            dr.date = %s AND 
            dr.status = 'not completed' AND 
            dr.time BETWEEN %s AND %s
    """
    partial_rides = execute_query(partial_match_query, (f'%{from_location}%', f'%{to_location}%', f'%{from_location}%', f'%{to_location}%', date, time_start, time_end))

    if partial_rides:
        for ride in partial_rides:
            fare = calculate_fare_for_ride(ride)
            rides_with_fare.append({**ride, 'fare': fare})
        print(f"Partial matches found: {len(rides_with_fare)}")
        return render_template('rider_ride_results.html', rides=rides_with_fare, message="Here are your partial search results!")

    return render_template('rider_ride_results.html', rides=[], message="No rides found for your search criteria.")

@app.route('/rider_ride_details/<int:ride_id>')
def rider_ride_details(ride_id):
    query = """
    SELECT dr.ride_id, dr.from_location, dr.to_location, d.name AS driver_name, 
           d.vehicle_type, d.vehicle_reg_number, dr.seats_available, dr.date, dr.time 
    FROM driver_rides dr
    JOIN driver d ON dr.driver_id = d.driver_id
    WHERE dr.ride_id = %s
    """
    ride_details = execute_query(query, (ride_id,))
    print(ride_details)
    if not ride_details:
        return "Ride not found", 404
    return render_template('rider_ride_details.html', ride=ride_details[0])

@app.route('/rider_ride_history')
def rider_ride_history():
    rider_id = session.get('user_id')
    if not rider_id:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT rr.ride_id, rr.from_location, rr.to_location, rr.date, rr.time, 
               d.name AS driver_name, rr.status
        FROM rider_rides rr
        JOIN driver d ON rr.driver_id = d.driver_id
        WHERE rr.rider_id = %s
        ORDER BY rr.date DESC, rr.time DESC
    """, (rider_id,))
    rides = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('rider_ride_history.html', rides=rides)

@app.route('/rider_trip_details/<int:ride_id>')
def rider_trip_details(ride_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Fetch ride details
        cursor.execute('SELECT * FROM rider_rides WHERE ride_id = %s', (ride_id,))
        ride = cursor.fetchone()
        
        if ride is None:
            flash('Ride not found.', 'error')
            return redirect(url_for('rider_ride_history'))

        # Fetch driver info
        cursor.execute('''
            SELECT d.name AS driver_name, rd.fare
            FROM driver d
            JOIN ride_details rd ON rd.ride_id = %s
            WHERE d.driver_id = %s
        ''', (ride_id, ride['driver_id']))
        driver_info = cursor.fetchone()

        # Check if feedback has been submitted
        cursor.execute('SELECT comments FROM driver_feedback WHERE ride_id = %s AND driver_id = %s',
                       (ride_id, ride['driver_id']))
        feedback = cursor.fetchall()  # Use fetchall to consume all results
        feedback_submitted = len(feedback) > 0  # Determine if feedback has been submitted
        
        # Determine if payment has been made and if ride is completed
        payment_made = ride['status'] == 'completed'

        # Set ride status
        ride_status = 'Completed' if payment_made else ('Feedback Submitted' if feedback_submitted else 'Pending')

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('rider_ride_history'))
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'rider_trip_details.html',
        ride=ride,
        driver_info=driver_info,
        ride_status=ride_status,
        feedback_submitted=feedback_submitted,
        payment_made=payment_made
    )


@app.route('/request_ride', methods=['POST'])
def request_ride():
    ride_id = request.form.get('ride_id')
    rider_id = session.get('user_id')
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO driver_ride_requests (ride_id, rider_id, status)
            VALUES (%s, %s, 'pending')
        ''', (ride_id, rider_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Request sent successfully!', 'success')
    else:
        flash('Failed to send request. Please try again.', 'error')
    return redirect(url_for('rider_home'))

def get_current_rider_id():
    return session.get('rider_id')

@app.route('/rider_notifications')
def rider_notifications():
    rider_id = get_current_rider_id()
    if rider_id is None:
        flash('Please log in to view notifications.')
        return redirect('/login')
    notifications = get_notifications(rider_id, 'rider')
    return render_template('rider_notifications.html', notifications=notifications)

@app.route('/driver_notifications')
def driver_notifications():
    driver_id = get_current_driver_id()
    if driver_id:
        notifications = get_notifications(driver_id, 'driver')
        return render_template('driver_notifications.html', notifications=notifications)
    else:
        return redirect(url_for('index'))

def get_notifications(user_id, user_type):
    # Establish the database connection
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        query = "SELECT * FROM notifications WHERE user_id = %s AND user_type = %s ORDER BY created_at DESC"
        cursor.execute(query, (user_id, user_type))
        notifications = cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        notifications = []
    finally:
        cursor.close()
        connection.close()
    return notifications

@app.route('/driver_home')
def driver_home():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM driver WHERE driver_id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return render_template('driver_home.html', user=user)
    else:
        return "User not found", 404

@app.route('/post')
def driver_ride_post():
    return render_template("driver_ride_post.html")

@app.route('/driver_post_ride', methods=['POST'])
def driver_post_ride():
    driver_id = session['user_id']
    from_location = request.form['from']
    to_location = request.form['to']
    stop1 = request.form.get('stop1', None)
    stop2 = request.form.get('stop2', None)
    date = request.form['date']
    time = request.form['time']
    seats_available = request.form['seats_available']
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        INSERT INTO driver_rides (driver_id, from_location, to_location, stop1, stop2, date, time, seats_available)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (driver_id, from_location, to_location, stop1, stop2, date, time, seats_available))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('driver_ride_history'))

@app.route('/driver_ride_history')
def driver_ride_history():
    driver_id = session.get('user_id')
    if not driver_id:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT ride_id, from_location, to_location, stop1, stop2, date, time, seats_available, status 
        FROM driver_rides 
        WHERE driver_id = %s
        ORDER BY date DESC, time DESC
    """, (driver_id,))
    rides = cursor.fetchall()
    conn.close()
    return render_template('driver_ride_history.html', rides=rides)

@app.route('/driver_trip_details/<int:ride_id>', methods=['GET', 'POST'])
def driver_trip_details(ride_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch ride details
    cursor.execute('SELECT * FROM driver_rides WHERE ride_id = %s', (ride_id,))
    ride = cursor.fetchone()
    
    if ride is None:
        flash('Ride not found.', 'error')
        return redirect(url_for('driver_ride_history'))

    # Fetch accepted ride requests for the current ride and check feedback status
    cursor.execute('''
        SELECT drq.*, r.name AS rider_name, rd.fare,
            EXISTS(SELECT 1 FROM rider_feedback WHERE ride_id = %s AND rider_id = drq.rider_id) AS feedback_submitted
        FROM driver_ride_requests drq 
        JOIN rider r ON drq.rider_id = r.rider_id 
        LEFT JOIN ride_details rd ON drq.ride_id = rd.ride_id 
        WHERE drq.ride_id = %s AND drq.status = 'accepted'
    ''', (ride_id, ride_id))
    accepted_requests = cursor.fetchall()
    
    # Handle ride completion if the form is submitted
    if request.method == 'POST':
        if ride['status'] != 'completed':
            cursor.execute('UPDATE driver_rides SET status = %s WHERE ride_id = %s', ('completed', ride_id))
            conn.commit()
            flash('Ride marked as completed!', 'success')
            return redirect(url_for('driver_trip_details', ride_id=ride_id))

    ride_completed = ride['status'] == 'completed'
    cursor.close()
    conn.close()
    
    return render_template(
        'driver_trip_details.html',
        ride=ride,
        accepted_requests=accepted_requests,
        ride_completed=ride_completed
    )

@app.route('/submit_rider_feedback', methods=['POST'])
def submit_rider_feedback():
    ride_id = request.form['ride_id']
    rider_id = request.form['rider_id']
    rating = request.form['rating']
    comments = request.form['comments']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO rider_feedback (ride_id, rider_id, rating, comments) VALUES (%s, %s, %s, %s)', 
                   (ride_id, rider_id, rating, comments))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Rider feedback submitted successfully!', 'success')
    return redirect(url_for('driver_trip_details', ride_id=ride_id))

@app.route('/submit_driver_feedback', methods=['POST'])
def submit_driver_feedback():
    ride_id = request.form['ride_id']
    driver_id = request.form['driver_id']
    rating = request.form['rating']
    comments = request.form['comments']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insert feedback for the current rider
        cursor.execute(
            'INSERT INTO driver_feedback (ride_id, driver_id, rating, comments) VALUES (%s, %s, %s, %s)',
            (ride_id, driver_id, rating, comments)
        )

        # Update the status of the current rider's entry in rider_rides to 'feedback_submitted'
        cursor.execute('UPDATE rider_rides SET status = %s WHERE ride_id = %s AND rider_id = %s',
                       ('feedback_submitted', ride_id, request.form['rider_id']))

        # Check if all riders for this ride_id have submitted feedback
        cursor.execute('SELECT COUNT(*) FROM rider_rides WHERE ride_id = %s AND status != %s', (ride_id, 'feedback_submitted'))
        pending_count = cursor.fetchone()[0]

        # If no pending riders remain, mark the driver_rides entry as 'completed'
        if pending_count == 0:
            cursor.execute('UPDATE driver_rides SET status = %s WHERE ride_id = %s', ('completed', ride_id))

        conn.commit()
        flash('Driver feedback submitted successfully! Please proceed to payment.', 'success')
        
    except mysql.connector.Error as e:
        print(f"Database error occurred: {e}")
        flash('Failed to submit feedback. Please try again.', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('rider_trip_details', ride_id=ride_id))


@app.route('/driver_feedback/<int:ride_id>/<int:driver_id>', methods=['GET'])
def driver_feedback(ride_id, driver_id):
    return render_template('driver_feedback.html', ride_id=ride_id, driver_id=driver_id)

@app.route('/rider_feedback/<int:ride_id>/<int:rider_id>', methods=['GET'])
def rider_feedback(ride_id, rider_id):
    return render_template('rider_feedback.html', ride_id=ride_id, rider_id=rider_id)

@app.route('/process_payment', methods=['POST'])
def process_payment():
    # Get the ride_id from form data (assuming it's passed in the form)
    ride_id = request.form['ride_id']
    rider_id = session.get('user_id')

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()

            # Update the status of the ride to 'completed'
            cursor.execute("UPDATE rider_rides SET status = 'completed' WHERE ride_id = %s AND rider_id = %s", (ride_id, rider_id))
            connection.commit()

            return redirect(url_for('rider_trip_details', ride_id=ride_id, payment_status='paid'))
        except Error as e:
            print(f"Error processing payment: {e}")
            return render_template('error.html', message="Unable to process payment.")
        finally:
            cursor.close()
            connection.close()
    else:
        return render_template('error.html', message="Database connection failed.")


@app.route('/cancel_ride/<int:ride_id>', methods=['POST'])
def cancel_ride(ride_id):
    connection = get_db_connection()
    if connection is None:
        return "Error connecting to the database."
    try:
        cursor = connection.cursor()
        cursor.execute("UPDATE rider_rides SET status = 'cancelled' WHERE ride_id = %s", (ride_id,))
        cursor.execute("UPDATE driver_rides SET status = 'active' WHERE ride_id = %s", (ride_id,))
        connection.commit()
    except Error as e:
        print(f"Error updating ride status: {e}")
    finally:
        cursor.close()
        connection.close()
    return redirect('/rider_ride_history')

@app.route('/cancel_driver_ride/<int:ride_id>', methods=['POST'])
def cancel_driver_ride(ride_id):
    connection = get_db_connection()
    if connection is None:
        return "Error connecting to the database."
    try:
        cursor = connection.cursor()
        cursor.execute("UPDATE driver_rides SET status = 'cancelled' WHERE ride_id = %s", (ride_id,))
        cursor.execute("UPDATE rider_rides SET status = 'cancelled' WHERE ride_id = %s", (ride_id,))
        connection.commit()
    except Error as e:
        print(f"Error updating ride status: {e}")
    finally:
        cursor.close()
        connection.close()
    return redirect('/driver_ride_history')

def get_current_driver_id():
    return session.get('driver_id')

@app.route('/driver_ride_requests')
def driver_ride_requests():
    user_id = session.get('user_id')
    print("Current Driver ID:", user_id)
    requests = []
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT drr.request_id, r.name AS rider_name, r.email AS rider_email, r.phone_number AS rider_mobile, drr.status
                FROM driver_ride_requests AS drr
                JOIN rider AS r ON drr.rider_id = r.rider_id
                JOIN driver_rides AS dr ON drr.ride_id = dr.ride_id
                WHERE dr.driver_id = %s
                ORDER BY (drr.status = 'pending') DESC, drr.request_id DESC
            ''', (user_id,))
            requests = cursor.fetchall()
            print("Fetched Requests:", requests)
        except Error as e:
            print(f"Error fetching ride requests: {e}")
        finally:
            cursor.close()
            conn.close()
    else:
        print("Database connection could not be established.")
    return render_template('driver_ride_requests.html', requests=requests)

@app.route('/driver_request_details/<int:request_id>')
def driver_request_details(request_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT rr.request_id, r.from_location, r.to_location, u.name as rider_name, 
                       u.email as rider_email,u.phone_number as rider_mobile, rr.status
                FROM driver_ride_requests rr
                JOIN driver_rides r ON rr.ride_id = r.ride_id
                JOIN rider u ON rr.rider_id = u.rider_id
                WHERE rr.request_id = %s
            ''', (request_id,))
            request_details = cursor.fetchone()
            print(f"Request details: {request_details}")
        except Error as e:
            print(f"Error fetching request details: {e}")
            request_details = None
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Could not connect to the database. Please try again.', 'error')
        return redirect(url_for('driver_home'))
    return render_template('driver_request_details.html', request=request_details)

@app.route('/handle_request/<int:request_id>/<action>', methods=['POST'])
def handle_request(request_id, action):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            if action == 'accept':
                # Update the status of the ride request
                cursor.execute('''UPDATE driver_ride_requests
                                  SET status = 'accepted'
                                  WHERE request_id = %s''', (request_id,))
                cursor.execute('''SELECT ride_id, rider_id FROM driver_ride_requests WHERE request_id = %s''', (request_id,))
                request_details = cursor.fetchone()
                if request_details:
                    ride_id = request_details['ride_id']
                    rider_id = request_details['rider_id']
                    cursor.execute('''SELECT dr.ride_id, dr.from_location, dr.to_location, dr.stop1, dr.stop2, 
                                             dr.date, dr.time, dr.seats_available, dr.driver_id,
                                             d.name AS driver_name, d.email AS driver_email, 
                                             d.phone_number AS driver_mobile, d.vehicle_type AS vehicle_details 
                                      FROM driver_rides dr 
                                      JOIN driver d ON dr.driver_id = d.driver_id 
                                      WHERE dr.ride_id = %s''', (ride_id,))
                    ride_info = cursor.fetchone()
                    print(ride_info)
                    if ride_info:
                        from_coords = get_coordinates_from_landmark(ride_info['from_location'])
                        to_coords = get_coordinates_from_landmark(ride_info['to_location'])
                        if from_coords and to_coords:
                            distance = calculate_distance(from_coords, to_coords)
                            duration = estimate_duration(distance)
                            fare_calculator = PaymentCalculator(distance, duration)
                            fare = fare_calculator.calculate_fare()
                            cursor.execute('''INSERT INTO rider_rides 
                                (rider_id, driver_id, from_location, to_location, stop1, stop2, 
                                date, time, seats_available, driver_name, driver_email, driver_mobile, 
                                vehicle_details, status) 
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', (
                                    rider_id,
                                    ride_info['driver_id'],  # Ensure this key exists now
                                    ride_info['from_location'],
                                    ride_info['to_location'],
                                    ride_info['stop1'],
                                    ride_info['stop2'],
                                    ride_info['date'],
                                    ride_info['time'],
                                    ride_info['seats_available'],
                                    ride_info['driver_name'],
                                    ride_info['driver_email'],
                                    ride_info['driver_mobile'],
                                    ride_info['vehicle_details'],
                                    'accepted'
                                ))
                            cursor.execute('''INSERT INTO ride_details (from_location, to_location, distance, fare)
                                              VALUES (%s, %s, %s, %s)''', (
                                                  ride_info['from_location'],
                                                  ride_info['to_location'],
                                                  distance,
                                                  fare
                                              ))
                            cursor.execute('''UPDATE driver_rides 
                                              SET seats_available = seats_available - 1 
                                              WHERE ride_id = %s AND seats_available > 0''', (ride_id,))
                flash('Request accepted!', 'success')
            elif action == 'reject':
                cursor.execute('''UPDATE driver_ride_requests
                                  SET status = 'rejected'
                                  WHERE request_id = %s''', (request_id,))
                flash('Request rejected!', 'success')
            conn.commit()
        except Error as e:
            print(f"Error handling request: {e}")
            flash('Failed to handle the request. Please try again.', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Could not connect to the database. Please try again.', 'error')
    return redirect(url_for('driver_ride_requests'))

@app.route('/rider_payment/<int:ride_id>', methods=['GET'])
def rider_payment(ride_id):
    """Displays the payment page for a rider."""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            # Fetch fare and ride ID from the ride_details table
            cursor.execute("SELECT ride_id, fare FROM ride_details WHERE ride_id = %s", (ride_id,))
            ride_detail = cursor.fetchone()
            if ride_detail:
                fare = ride_detail['fare']
                # Pass the ride detail as well
                ride = ride_detail  # This can be used to pass the whole ride detail if needed
            else:
                fare = None
                ride = None  # Set ride to None if not found

            return render_template('rider_payment.html', fare=fare, ride=ride)
        except Error as e:
            print(f"Error fetching fare: {e}")
            return render_template('error.html', message="Unable to fetch ride details.")
        finally:
            cursor.close()
            connection.close()
    else:
        return render_template('error.html', message="Database connection failed.")


@app.route('/driver_payment/<int:ride_id>', methods=['GET'])
def driver_payment(ride_id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT fare FROM ride_details WHERE ride_id = %s", (ride_id,))
            ride_detail = cursor.fetchone()
            if ride_detail:
                fare = ride_detail['fare']
            else:
                fare = None
            return render_template('driver_payment.html', fare=fare, ride_id=ride_id)
        except Error as e:
            print(f"Error fetching fare: {e}")
            return render_template('error.html', message="Unable to fetch ride details.")
        finally:
            cursor.close()
            connection.close()
    else:
        return render_template('error.html', message="Database connection failed.")

@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    ride_id = request.form['ride_id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("UPDATE driver_rides SET status = 'completed' WHERE ride_id = %s", (ride_id,))
            connection.commit()
            return redirect(url_for('driver_ride_history'))
        except Error as e:
            print(f"Error confirming payment: {e}")
            return render_template('error.html', message="Unable to confirm payment.")
        finally:
            cursor.close()
            connection.close()
    else:
        return render_template('error.html', message="Database connection failed.")

@app.route('/admin_home')
def admin_home():
    page = request.args.get('page', 1, type=int)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT admin_id as user_id, name, email, phone_number, 'admin' as role FROM admin
        UNION ALL
        SELECT rider_id as user_id, name, email, phone_number, 'rider' as role FROM rider
        UNION ALL
        SELECT driver_id as user_id, name, email, phone_number, 'driver' as role FROM driver
        LIMIT %s OFFSET %s
    """
    cursor.execute(query, (10, (page - 1) * 10))
    users = cursor.fetchall()
    has_next_page = len(users) == 10
    conn.close()
    return render_template('admin_home.html', users=users, page=page, has_next_page=has_next_page)

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone_number = request.form['phone_number']
        dob = request.form['dob']
        role = request.form['role']
        if role == 'admin':
            cursor.execute("""
                UPDATE admin
                SET name = %s, email = %s, phone_number = %s, dob = %s
                WHERE admin_id = %s
            """, (name, email, phone_number, dob, user_id))
        elif role == 'rider':
            cursor.execute("""
                UPDATE rider
                SET name = %s, email = %s, phone_number = %s, dob = %s
                WHERE rider_id = %s
            """, (name, email, phone_number, dob, user_id))
        elif role == 'driver':
            vehicle_type = request.form['vehicle_type']
            vehicle_reg_number = request.form['vehicle_reg_number']
            license_number = request.form['license_number']
            cursor.execute("""
                UPDATE driver
                SET name = %s, email = %s, phone_number = %s, dob = %s, 
                    vehicle_type = %s, vehicle_reg_number = %s, 
                    license_number = %s
                WHERE driver_id = %s
            """, (name, email, phone_number, dob, vehicle_type, vehicle_reg_number, license_number, user_id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_home'))
    query = """
        SELECT 'admin' AS role, admin_id AS id, name, email, phone_number, dob, NULL AS vehicle_type, NULL AS vehicle_reg_number, NULL AS license_number
        FROM admin WHERE admin_id = %s
        UNION ALL
        SELECT 'rider' AS role, rider_id AS id, name, email, phone_number, dob, NULL AS vehicle_type, NULL AS vehicle_reg_number, NULL AS license_number
        FROM rider WHERE rider_id = %s
        UNION ALL
        SELECT 'driver' AS role, driver_id AS id, name, email, phone_number, dob, vehicle_type, vehicle_reg_number, license_number
        FROM driver WHERE driver_id = %s
    """
    cursor.execute(query, (user_id, user_id, user_id))
    user = cursor.fetchone()
    conn.close()
    if user is None:
        return "User not found", 404
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 'admin' AS role FROM admin WHERE admin_id = %s
            UNION ALL
            SELECT 'rider' AS role FROM rider WHERE rider_id = %s
            UNION ALL
            SELECT 'driver' AS role FROM driver WHERE driver_id = %s
        """, (user_id, user_id, user_id))
        users = cursor.fetchall()
        if users:
            role = users[0]['role']
            if role == 'admin':
                cursor.execute("DELETE FROM admin WHERE admin_id = %s", (user_id,))
            elif role == 'rider':
                cursor.execute("DELETE FROM rider WHERE rider_id = %s", (user_id,))
            elif role == 'driver':
                cursor.execute("DELETE FROM driver WHERE driver_id = %s", (user_id,))
            conn.commit()
            flash('User deleted successfully.', 'success')
        else:
            flash('User not found.', 'danger')
    except Exception as e:
        print(f"An error occurred: {e}")
        flash('An error occurred while trying to delete the user.', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_home'))

@app.route('/add_user')
def add_user():
    return render_template('add_user.html')

@app.route('/create_user', methods=['POST'])
def create_user():
    role = request.form.get('role')
    email = request.form.get('email')
    phone_number = request.form.get('phone_number')
    password = generate_password(random.randint(8, 12))
    name = request.form.get('name')
    dob = request.form.get('dob')
    vehicle_type = request.form.get('vehicle_type', None)
    vehicle_reg_number = request.form.get('vehicle_reg_number', None)
    license_number = request.form.get('license_number', None)
    conn = get_db_connection()
    cursor = conn.cursor()
    if role == 'admin':
        query = "SELECT * FROM admin WHERE email = %s"
    elif role == 'rider':
        query = "SELECT * FROM rider WHERE email = %s"
    elif role == 'driver':
        query = "SELECT * FROM driver WHERE email = %s"
    else:
        return render_template('add_user.html', message="Invalid role provided.")
    cursor.execute(query, (email,))
    existing_user = cursor.fetchone()
    if existing_user:
        message = f"User with email '{email}' already exists with role '{role}'."
        return render_template('add_user.html', message=message)
    if role == 'admin':
        query = "INSERT INTO admin (name, email, phone_number, dob, password) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (name, email, phone_number, dob, password))
    elif role == 'rider':
        query = "INSERT INTO rider (name, email, phone_number, dob, password) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (name, email, phone_number, dob, password))
    elif role == 'driver':
        query = """
            INSERT INTO driver (name, email, phone_number, dob, vehicle_type, vehicle_reg_number, license_number, password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (name, email, phone_number, dob, vehicle_type, vehicle_reg_number, license_number, password))
    conn.commit()
    cursor.close()
    conn.close()
    message = 'User created successfully!'
    return render_template('add_user.html', message=message, password=password)

@app.route('/ride_monitoring')
def admin_ride_monitoring():
    connection = get_db_connection()
    if connection is None:
        return "Error connecting to the database."
    active_rides = []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT ride_id, from_location, to_location, status FROM driver_rides")
        driver_rides = cursor.fetchall()
        for ride in driver_rides:
            ride_id = ride['ride_id']
            cursor.execute("SELECT status FROM rider_rides WHERE ride_id = %s", (ride_id,))
            rider_ride = cursor.fetchone()
            if rider_ride and rider_ride['status'] == 'completed' and ride['status'] == 'completed':
                status = 'completed'
            else:
                status = 'active'
            active_rides.append({
                'ride_id': ride_id,
                'status': status,
                'from_location': ride['from_location'],
                'to_location': ride['to_location']
            })
    except Error as e:
        print(f"Error fetching data: {e}")
    finally:
        cursor.close()
        connection.close()
    return render_template('admin_ride_monitoring_dashboard.html', active_rides=active_rides)

@app.route('/issue_management')
def issue_management():
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM issues")
        issues = cursor.fetchall()
        cursor.close()
        connection.close()
        return render_template('admin_issue_management.html', issues=issues)
    return "Database connection error."

@app.route('/admin_issue_raise')
def admin_issue_raise():
    return render_template('admin_issue_raise.html')

@app.route('/submit_issue', methods=['POST'])
def submit_issue():
    issue_name = request.form['issue_name']
    description = request.form['description']
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO issues (name, description, status) VALUES (%s, %s, 'Pending')",
            (issue_name, description)
        )
        connection.commit()
        cursor.close()
        connection.close()
    return redirect(url_for('issue_management'))

@app.route('/resolve_issue/<int:issue_id>')
def resolve_issue(issue_id):
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE issues SET status = 'Solved' WHERE id = %s", (issue_id,))
        connection.commit()
        cursor.close()
        connection.close()
    return redirect(url_for('issue_management'))

@app.route('/rider_change_password')
def rider_change_password():
    return render_template('rider_change_password.html')

@app.route('/driver_change_password')
def driver_change_password():
    return render_template('driver_change_password.html')

@app.route('/update_rider_password', methods=['POST'])
def update_rider_password():
    user_id = session['user_id']
    old_password = request.form['old_password']
    new_password = request.form['new_password']
    confirm_new_password = request.form['confirm_new_password']
    if new_password != confirm_new_password:
        flash('New password and confirm password do not match.', 'error')
        return redirect(url_for('rider_change_password'))
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT password FROM rider WHERE rider_id = %s', (user_id,))
            result = cursor.fetchone()
            if result and result[0] == old_password:
                cursor.execute('UPDATE rider SET password = %s WHERE rider_id = %s', (new_password, user_id))
                conn.commit()
                flash('Password changed successfully!', 'success')
            else:
                flash('Old password is incorrect.', 'error')
        except Error as e:
            print(f"Error updating password: {e}")
            flash('Failed to change password. Please try again.', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Could not connect to the database. Please try again.', 'error')
    return redirect(url_for('rider_home'))

@app.route('/update_driver_password', methods=['POST'])
def update_driver_password():
    user_id = session['user_id']
    old_password = request.form['old_password']
    new_password = request.form['new_password']
    confirm_new_password = request.form['confirm_new_password']
    if new_password != confirm_new_password:
        flash('New password and confirm password do not match.', 'error')
        return redirect(url_for('driver_change_password'))
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT password FROM driver WHERE driver_id = %s', (user_id,))
            result = cursor.fetchone()
            if result and result[0] == old_password:
                cursor.execute('UPDATE driver SET password = %s WHERE driver_id = %s', (new_password, user_id))
                conn.commit()
                flash('Password changed successfully!', 'success')
            else:
                flash('Old password is incorrect.', 'error')
        except Error as e:
            print(f"Error updating password: {e}")
            flash('Failed to change password. Please try again.', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Could not connect to the database. Please try again.', 'error')
    return redirect(url_for('driver_home'))

if __name__ == '__main__':
    app.run(debug=True)