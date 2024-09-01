import random
import networkx as nx
from tsp_solver.greedy import solve_tsp
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import hashlib
from geopy.geocoders import Nominatim
from sklearn.metrics.pairwise import haversine_distances
from math import radians

geolocator = Nominatim(user_agent="rideshare_app")

def normalize_time(time_str):
    """Convert a time string to minutes past midnight."""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def calculate_distance(coord1, coord2):
    """Compute the Haversine distance between two points on the earth."""
    coord1 = (radians(coord1[0]), radians(coord1[1]))
    coord2 = (radians(coord2[0]), radians(coord2[1]))
    return haversine_distances([coord1, coord2])[0][1] * 6371000 / 1000  # in kilometers

def hash_sensitive_data(data):
    """Generate a hashed version of sensitive data for security purposes."""
    return hashlib.sha256(data.encode()).hexdigest()

def get_coordinates_from_landmark(landmark):
    """Retrieve geographical coordinates for a given landmark using geopy."""
    location = geolocator.geocode(landmark)
    return (location.latitude, location.longitude) if location else None

class RideMatcher:
    def __init__(self, rider_input, driver_inputs):
        self.rider = rider_input
        self.drivers = driver_inputs

    def match(self):
        rider_time = normalize_time(self.rider['time'])
        best_match = None
        best_score = float('inf')

        for driver in self.drivers:
            driver_time = normalize_time(driver['time'])
            distance = calculate_distance(self.rider['destination'], driver['destination'])
            time_diff = abs(rider_time - driver_time)
            score = distance + time_diff

            if score < best_score:
                best_score = score
                best_match = driver

        return best_match

class RouteOptimizer:
    def __init__(self, locations, traffic_data):
        self.locations = locations
        self.traffic_data = traffic_data

    def optimize_route(self):
        G = nx.Graph()
        for i, loc in enumerate(self.locations):
            G.add_node(i, pos=loc)

        for i in range(len(self.locations)):
            for j in range(i + 1, len(self.locations)):
                dist = calculate_distance(self.locations[i], self.locations[j])
                G.add_edge(i, j, weight=dist * (1 + random.random() * self.traffic_data['road_1']['congestion_level']))

        route = solve_tsp(nx.to_numpy_array(G))
        optimized_route = [self.locations[i] for i in route]
        return optimized_route

class PaymentCalculator:
    def __init__(self, distance, base_fare=50, rate_per_km=10):
        self.distance = distance
        self.base_fare = base_fare
        self.rate_per_km = rate_per_km

    def calculate_fare(self):
        total_fare = self.base_fare + self.rate_per_km * self.distance
        return total_fare

    def split_fare(self, total_fare, num_riders):
        return total_fare / num_riders

class Notifier:
    def __init__(self):
        self.notifications = {
            'ride_request': 'Your ride request has been received.',
            'ride_confirmation': 'Your ride has been confirmed.',
            'trip_start': 'Your trip has started.',
            'trip_end': 'Your trip has ended.',
            'feedback': 'Thank you for your feedback!'
        }

    def send_notification(self, event_type, user):
        message = self.notifications.get(event_type, 'Unknown event')
        print(f"Notification to {user}: {message}")

class FeedbackAnalyzer:
    def __init__(self, feedback_list):
        self.feedback_list = feedback_list
        self.sia = SentimentIntensityAnalyzer()

    def analyze(self):
        sentiments = [self.sia.polarity_scores(text) for text in self.feedback_list]
        for i, sentiment in enumerate(sentiments):
            print(f"Feedback: {self.feedback_list[i]}")
            print(f"Sentiment: {sentiment}\n")

class SecureUser:
    def __init__(self, username, password):
        self.username = username
        self.password = hash_sensitive_data(password)

    def authenticate(self, password):
        return self.password == hash_sensitive_data(password)

class RideShareApp:
    def __init__(self, rider_input, driver_inputs, locations, traffic_data, feedback_list):
        self.rider_input = rider_input
        self.driver_inputs = driver_inputs
        self.locations = locations
        self.traffic_data = traffic_data
        self.feedback_list = feedback_list

    def run(self):
        # Match Rider with Driver
        ride_matcher = RideMatcher(self.rider_input, self.driver_inputs)
        matched_driver = ride_matcher.match()
        if matched_driver:
            print(f"Best match: {matched_driver}")

            # Confirm with Driver
            driver_confirmation = input("Driver, do you accept the ride? (Y/N): ")
            if driver_confirmation.lower() == 'y':
                notifier = Notifier()
                notifier.send_notification('ride_confirmation', 'Rider')
                print("Driver has accepted the ride. Have a pleasant journey!")

                # Optimize Route
                route_optimizer = RouteOptimizer(self.locations, self.traffic_data)
                optimized_route = route_optimizer.optimize_route()
                print(f"Optimized route: {optimized_route}")

                # Calculate and Split Payment
                total_distance = calculate_distance(self.rider_input['start_location'], self.rider_input['destination'])
                payment_calculator = PaymentCalculator(total_distance)
                total_fare = payment_calculator.calculate_fare()
                fare_split = payment_calculator.split_fare(total_fare, 1)  # Assuming one rider
                print(f"Total fare (in INR): ₹{total_fare:.2f}")
                print(f"Fare split (in INR): ₹{fare_split:.2f}")

                # Send Notifications
                notifier.send_notification('trip_start', 'Rider')

                # Rider Status Check
                rider_reached = input("Rider, have you met the driver? (Y/N): ")
                if rider_reached.lower() == 'y':
                    destination_reached = input("Have you arrived at your destination? (Y/N): ")
                    if destination_reached.lower() == 'y':
                        notifier.send_notification('trip_end', 'Rider')
                        feedback = input("Please provide your feedback: ")
                        self.feedback_list.append(feedback)
                        feedback_analyzer = FeedbackAnalyzer(self.feedback_list)
                        feedback_analyzer.analyze()
                    else:
                        print("Continue your journey safely.")
                else:
                    print("Please wait for the driver; they may be on the way.")
            else:
                print("Driver has not accepted the ride.")
        else:
            print("No suitable driver available.")


rider_input = {
    'start_location': get_coordinates_from_landmark(input("Enter rider's starting location: ")),
    'destination': get_coordinates_from_landmark(input("Enter rider's destination: ")),
    'time': input("Enter time (HH:MM): "),
    'preferences': {'same_gender': True, 'non_smoking': True}
}

driver_inputs = [
    {
        'start_location': get_coordinates_from_landmark(input("Enter driver's starting location (e.g., Bangalore): ")),
        'destination': get_coordinates_from_landmark(input("Enter driver's destination (e.g., Chennai): ")),
        'route': [
            get_coordinates_from_landmark(input("Enter driver's route stop 1: ")),
            get_coordinates_from_landmark(input("Enter driver's route stop 2: "))
        ],
        'time': input("Enter driver's time (HH:MM): "),
        'available_seats': int(input("Enter number of available seats: "))
    }
]

locations = [get_coordinates_from_landmark(loc) for loc in ['Bangalore', 'Chennai', 'Coimbatore']]

traffic_data = {
    'road_1': {'congestion_level': 0.7},
}

feedback_list = [
    "The ride was great; the driver was on time.",
    "The vehicle was not clean, and the driver was late."
]

app = RideShareApp(rider_input, driver_inputs, locations, traffic_data, feedback_list)
app.run()
