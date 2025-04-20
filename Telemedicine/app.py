import streamlit as st
# Set page configuration
st.set_page_config(
    page_title="Telemedicine Appointment Scheduler",
    page_icon="👨‍⚕️",
    layout="wide",
    initial_sidebar_state="expanded"
)

import google.generativeai as genai
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
import uuid
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure
import time
from functools import lru_cache

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGODB_URI = os.getenv('MONGODB_URI')
MONGODB_DB = os.getenv('MONGODB_DB')

# Gemini API Configuration
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Configure Gemini
try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Failed to configure Gemini: {str(e)}")

# Cache MongoDB connection
@st.cache_resource
def get_mongodb_client():
    try:
        client = MongoClient(MONGODB_URI)
        return client
    except Exception as e:
        st.error(f"Failed to initialize MongoDB client: {str(e)}")
        return None

def test_mongodb_connection():
    try:
        if not MONGODB_URI or not MONGODB_DB:
            raise ValueError("MongoDB URI or Database name is missing in .env file")
            
        # Initialize MongoDB client
        client = get_mongodb_client()
        if client is None:
            return None, None
            
        db = client[MONGODB_DB]
        
        # Test connection by getting server info
        server_info = client.server_info()
        
        # Show connection toast only once when the app starts
        if 'db_connection_shown' not in st.session_state:
            st.toast("Database Connected", icon="✅")
            st.session_state.db_connection_shown = True
        
        return client, db
        
    except Exception as e:
        if 'db_connection_shown' not in st.session_state:
            st.toast(f"Database Connection Failed: {str(e)}", icon="❌")
            st.session_state.db_connection_shown = True
        return None, None

# Initialize MongoDB connection
mongo_client, db = test_mongodb_connection()

# Cache available slots for 5 minutes
@st.cache_data(ttl=300)
def get_available_slots():
    try:
        if mongo_client is None or db is None:
            return generate_static_slots()
            
        # Get all booked slots from database
        booked_slots = list(db.appointments.find(
            {"status": "confirmed"},
            {"appointment_slot": 1, "_id": 0}
        ))
        
        # Count bookings for each slot
        slot_counts = {}
        for slot in booked_slots:
            slot_time = slot['appointment_slot']
            slot_counts[slot_time] = slot_counts.get(slot_time, 0) + 1
        
        # Maximum slots per time period
        MAX_SLOTS = 10
        
        # Generate available slots for the next 7 days
        slots_info = []
        for i in range(7):
            date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
            possible_slots = [
                f"{date} 09:00 AM",
                f"{date} 10:00 AM",
                f"{date} 11:00 AM",
                f"{date} 02:00 PM",
                f"{date} 03:00 PM",
                f"{date} 04:00 PM"
            ]
            
            # Check availability for each slot
            for slot in possible_slots:
                booked_count = slot_counts.get(slot, 0)
                available_count = MAX_SLOTS - booked_count
                
                if available_count > 0:
                    slots_info.append({
                        "slot": slot,
                        "available": available_count,
                        "total": MAX_SLOTS
                    })
        
        if not slots_info:
            st.warning("No available slots found for the next 7 days")
            return []
            
        return slots_info
        
    except Exception as e:
        st.error(f"Error fetching available slots: {str(e)}")
        return generate_static_slots()

def generate_static_slots():
    slots_info = []
    MAX_SLOTS = 10
    
    for i in range(7):
        date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
        possible_slots = [
            f"{date} 09:00 AM",
            f"{date} 10:00 AM",
            f"{date} 11:00 AM",
            f"{date} 02:00 PM",
            f"{date} 03:00 PM",
            f"{date} 04:00 PM"
        ]
        for slot in possible_slots:
            slots_info.append({
                "slot": slot,
                "available": MAX_SLOTS,
                "total": MAX_SLOTS
            })
    return slots_info

def save_appointment_to_db(appointment_details):
    try:
        if mongo_client is None or db is None:
            raise ValueError("Database connection not established")
            
        with st.spinner('Saving your appointment...'):
            # Check if slot is still available
            slot_time = appointment_details['slot']
            booked_count = db.appointments.count_documents({
                "appointment_slot": slot_time,
                "status": "confirmed"
            })
            
            MAX_SLOTS = 10
            if booked_count >= MAX_SLOTS:
                st.error("Sorry, this time slot is no longer available. Please select another slot.")
                return None
            
            # Generate a unique booking ID
            booking_id = str(uuid.uuid4())
            current_time = datetime.now()
            
            # Prepare appointment data with data validation
            appointment_data = {
                'booking_id': booking_id,
                'name': str(appointment_details['name']).strip(),
                'age': int(appointment_details['age']),
                'gender': str(appointment_details['gender']).strip(),
                'phone': str(appointment_details['phone']).strip(),
                'email': str(appointment_details['email']).strip().lower(),
                'doctor': str(appointment_details['doctor']),
                'doctor_specialization': str(appointment_details['doctor_specialization']),
                'appointment_slot': slot_time,
                'symptoms': str(appointment_details['symptoms']).strip(),
                'status': 'confirmed',
                'created_at': current_time,
                'updated_at': current_time
            }
            
            # Insert into MongoDB with timeout
            result = db.appointments.insert_one(appointment_data)
            
            if result.inserted_id:
                # Clear the slots cache to refresh available slots
                get_available_slots.clear()
                return booking_id
            else:
                st.error("Failed to save appointment to database")
                return None
                
    except Exception as e:
        st.error(f"Error saving appointment: {str(e)}")
        return None

@st.cache_data(ttl=3600)  # Cache doctor info for 1 hour
def get_doctors_info():
    return {
        "Dr. John Smith": {
            "specialization": "General Physician",
            "experience": "15+ years",
            "fee": "$100",
            "availability": "Mon-Fri",
            "education": "MD, Internal Medicine",
            "image": "🧑‍⚕️"  # You can replace with actual image URLs
        },
        "Dr. Sarah Johnson": {
            "specialization": "Cardiologist",
            "experience": "12+ years",
            "fee": "$150",
            "availability": "Mon-Wed",
            "education": "MD, Cardiology",
            "image": "👩‍⚕️"
        },
        "Dr. Michael Chen": {
            "specialization": "Pediatrician",
            "experience": "10+ years",
            "fee": "$120",
            "availability": "Tue-Sat",
            "education": "MD, Pediatrics",
            "image": "👨‍⚕️"
        },
        "Dr. Emily Williams": {
            "specialization": "Dermatologist",
            "experience": "8+ years",
            "fee": "$130",
            "availability": "Wed-Fri",
            "education": "MD, Dermatology",
            "image": "👩‍⚕️"
        }
    }

def handle_appointment_booking():
    if st.session_state.appointment_stage is None:
        st.session_state.appointment_stage = 'collect_info'
        st.session_state.appointment_details = {}
        return "Please provide your details for the appointment booking."
    
    elif st.session_state.appointment_stage == 'collect_info':
        st.markdown("""
            <div class='appointment-form'>
                <h3 style='color: #4267B2; margin-bottom: 1.5rem;'>Appointment Booking Form</h3>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Full Name", help="Enter your full name as per official documents")
                age = st.number_input("Age", min_value=1, max_value=120, help="Enter your current age")
                gender = st.selectbox("Gender", ["Select", "Male", "Female", "Other"])
                
            with col2:
                phone = st.text_input("Phone Number", help="Enter your active contact number")
                email = st.text_input("Email", help="Enter your email for appointment confirmation")
            
            # Doctor Selection with images
            doctors = get_doctors_info()
            doctor_cols = st.columns(len(doctors))
            
            # Initialize selected_doctor in session state if not exists
            if 'selected_doctor' not in st.session_state:
                st.session_state.selected_doctor = None
            
            for i, (doctor_name, details) in enumerate(doctors.items()):
                with doctor_cols[i]:
                    st.markdown(f"""
                        <div style='text-align: center; padding: 1rem; border-radius: 10px; border: 1px solid #e0e0e0;'>
                            <h1>{details['image']}</h1>
                            <h4>{doctor_name}</h4>
                            <p>{details['specialization']}</p>
                        </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"Select {doctor_name.split()[1]}", key=f"doc_{i}"):
                        st.session_state.selected_doctor = doctor_name

            if st.session_state.selected_doctor:
                st.success(f"Selected Doctor: {st.session_state.selected_doctor}")
            
            # Time slot selection
            st.markdown("<h4 style='margin: 1.5rem 0 1rem 0; color: #4267B2;'>Select Appointment Time</h4>", unsafe_allow_html=True)
            
            # Get available slots
            available_slots = get_available_slots()
            
            # Group slots by date
            slots_by_date = {}
            for slot_info in available_slots:
                date = slot_info["slot"].split()[0]
                if date not in slots_by_date:
                    slots_by_date[date] = []
                slots_by_date[date].append(slot_info)
            
            # Create date and time selection
            selected_date = st.selectbox(
                "Select Date",
                options=list(slots_by_date.keys()),
                format_func=lambda x: datetime.strptime(x, '%Y-%m-%d').strftime('%A, %B %d, %Y')
            )
            
            if selected_date:
                # Filter time slots for selected date
                time_slots = slots_by_date[selected_date]
                time_slot_options = [
                    f"{slot_info['slot']} ({slot_info['available']} slots available)"
                    for slot_info in time_slots
                ]
                
                preferred_slot = st.selectbox(
                    "Select Time",
                    options=time_slot_options,
                    help="Select your preferred appointment time"
                )
                
                if preferred_slot:
                    # Extract actual slot time from the selection
                    slot_time = preferred_slot.split(" (")[0]
            
            symptoms = st.text_area("Brief description of symptoms",
                                  help="Please describe your symptoms briefly")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("Book Appointment", type="primary", use_container_width=True):
                    if name and age and gender != "Select" and phone and email and st.session_state.selected_doctor and preferred_slot and symptoms:
                        with st.spinner("Processing your appointment..."):
                            appointment_details = {
                                "name": name,
                                "age": age,
                                "gender": gender,
                                "phone": phone,
                                "email": email,
                                "doctor": st.session_state.selected_doctor,
                                "doctor_specialization": doctors[st.session_state.selected_doctor]["specialization"],
                                "slot": slot_time,
                                "symptoms": symptoms
                            }
                            
                            # Save to MongoDB
                            booking_id = save_appointment_to_db(appointment_details)
                            
                            if booking_id:
                                st.session_state.appointment_details = appointment_details
                                st.session_state.appointment_stage = 'confirmed'
                                
                                # Update available slots
                                st.session_state.available_slots = get_available_slots()
                                
                                # Show success message with animation
                                st.balloons()
                                st.markdown(f"""
                                    <div style='background: linear-gradient(135deg, #4CAF50, #45a049); color: white; padding: 1.5rem; border-radius: 10px; margin: 1rem 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
                                        <h4 style='margin:0 0 1rem 0;'>🎉 Appointment Booked Successfully!</h4>
                                        <p style='margin: 0.5rem 0;'><strong>Booking ID:</strong> {booking_id}</p>
                                        <p style='margin: 0.5rem 0;'><strong>Name:</strong> {name}</p>
                                        <p style='margin: 0.5rem 0;'><strong>Doctor:</strong> {st.session_state.selected_doctor}</p>
                                        <p style='margin: 0.5rem 0;'><strong>Specialization:</strong> {doctors[st.session_state.selected_doctor]['specialization']}</p>
                                        <p style='margin: 0.5rem 0;'><strong>Time Slot:</strong> {slot_time}</p>
                                        <p style='margin: 1rem 0 0 0; font-style: italic;'>✉️ A confirmation email has been sent to {email}</p>
                                        <p style='margin: 0.5rem 0 0 0; font-style: italic;'>⏰ Please arrive 15 minutes before your appointment time.</p>
                                    </div>
                                """, unsafe_allow_html=True)
                                
                                # Reset appointment stage for new bookings
                                st.session_state.appointment_stage = None
                                st.session_state.active_button = None
                                return "Your appointment has been booked successfully! Is there anything else I can help you with?"
                    else:
                        # Create a list of missing fields
                        missing_fields = []
                        if not name:
                            missing_fields.append("Full Name")
                        if not age:
                            missing_fields.append("Age")
                        if gender == "Select":
                            missing_fields.append("Gender")
                        if not phone:
                            missing_fields.append("Phone Number")
                        if not email:
                            missing_fields.append("Email")
                        if not st.session_state.selected_doctor:
                            missing_fields.append("Doctor Selection")
                        if not preferred_slot:
                            missing_fields.append("Time Slot")
                        if not symptoms:
                            missing_fields.append("Symptoms Description")
                        
                        st.error(f"Please fill in the following required fields: {', '.join(missing_fields)}")
                        return None
        
        return None

# Initialize session states
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'appointment_stage' not in st.session_state:
    st.session_state.appointment_stage = None
if 'appointment_details' not in st.session_state:
    st.session_state.appointment_details = {}
if 'available_slots' not in st.session_state:
    st.session_state.available_slots = get_available_slots()
if 'db_connection_shown' not in st.session_state:
    st.session_state.db_connection_shown = False
if 'active_button' not in st.session_state:
    st.session_state.active_button = None

# Function to display available slots
def display_available_slots():
    available_slots = get_available_slots()
    
    if available_slots:
        st.markdown("""
            <div style='background: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin: 1rem 0;'>
                <h4 style='margin:0 0 1rem 0; color: #4267B2;'>Available Time Slots</h4>
                <div style='background: #f8f9fa; padding: 1rem; border-radius: 8px;'>
        """, unsafe_allow_html=True)
        
        # Group slots by date
        slots_by_date = {}
        for slot_info in available_slots:
            date = slot_info["slot"].split()[0]
            if date not in slots_by_date:
                slots_by_date[date] = []
            slots_by_date[date].append(slot_info)
        
        # Display slots grouped by date
        for date, slots in slots_by_date.items():
            formatted_date = datetime.strptime(date, '%Y-%m-%d').strftime('%A, %B %d, %Y')
            st.markdown(f"<h5 style='margin: 1rem 0 0.5rem 0; color: #333;'>{formatted_date}</h5>", unsafe_allow_html=True)
            
            for slot_info in slots:
                time = slot_info["slot"].split()[-2:]
                available = slot_info["available"]
                total = slot_info["total"]
                
                # Color coding based on availability
                if available <= 2:
                    color = "#dc3545"  # Red for almost full
                elif available <= 5:
                    color = "#ffc107"  # Yellow for medium availability
                else:
                    color = "#28a745"  # Green for good availability
                
                st.markdown(f"""
                    <div style='display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; margin: 0.25rem 0; background: white; border-radius: 5px;'>
                        <span>🕒 {' '.join(time)}</span>
                        <span style='color: {color};'>{available}/{total} slots available</span>
                    </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div></div>", unsafe_allow_html=True)
    else:
        st.warning("No available slots found")

# Custom CSS
st.markdown("""
    <style>
    /* Main Layout */
    .main {
        background-color: #f8f9fa;
        padding: 0;
    }
    
    /* Header Styling */
    .chat-header {
        background: linear-gradient(135deg, #4267B2, #3b5998);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .chat-header h2 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 600;
    }
    
    /* Input Fields */
    .stTextInput>div>div>input {
        background-color: white;
        border-radius: 10px;
        padding: 0.75rem 1rem;
        border: 1px solid #e0e0e0;
        font-size: 1rem;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .stTextInput>div>div>input:focus {
        border-color: #4267B2;
        box-shadow: 0 0 0 2px rgba(66, 103, 178, 0.2);
    }
    
    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #4267B2, #3b5998);
        color: white;
        border-radius: 10px;
        padding: 0.75rem 1.5rem;
        border: none;
        font-weight: 600;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Chat Container */
    .chat-container {
        background-color: white;
        border-radius: 15px;
        padding: 2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
    }
    
    /* Messages */
    .user-message {
        background: linear-gradient(135deg, #e3f2fd, #bbdefb);
        padding: 1rem 1.5rem;
        border-radius: 15px 15px 0 15px;
        margin: 1rem 0;
        max-width: 80%;
        margin-left: auto;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .bot-message {
        background: linear-gradient(135deg, #f5f5f5, #eeeeee);
        padding: 1rem 1.5rem;
        border-radius: 15px 15px 15px 0;
        margin: 1rem 0;
        max-width: 80%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Appointment Form */
    .appointment-form {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .appointment-form .stTextInput>div>div>input,
    .appointment-form .stTextArea>div>div>textarea {
        background-color: #f8f9fa;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        padding: 2rem 1rem;
    }
    
    /* Doctor Cards */
    .doctor-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
        transition: all 0.3s ease;
    }
    
    .doctor-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    /* Quick Action Buttons */
    .quick-action {
        background: white;
        padding: 1rem;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    
    .quick-action:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    /* Success/Error Messages */
    .stSuccess, .stError {
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    
    /* Selectbox Styling */
    .stSelectbox {
        border-radius: 10px;
    }
    
    .stSelectbox > div > div > div {
        background-color: white;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
    }
    
    /* Toast Messages */
    .stToast {
        background: white;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar with Doctors' Information
with st.sidebar:
    st.markdown("""
        <div style='background: linear-gradient(135deg, #4267B2, #3b5998); padding: 1.5rem; border-radius: 15px; color: white; margin-bottom: 1.5rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
            <h3 style='margin:0; font-size: 1.5rem;'>Our Specialists</h3>
        </div>
    """, unsafe_allow_html=True)
    
    # Total Appointments Counter
    if mongo_client is not None and db is not None:
        appointments_count = db.appointments.count_documents({})
        st.markdown(f"""
            <div style='background: white; padding: 1rem; border-radius: 10px; margin-bottom: 1.5rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);'>
                <h4 style='margin:0; color: #4267B2;'>Total Appointments</h4>
                <p style='font-size: 1.5rem; margin:0.5rem 0 0 0; color: #333;'>{appointments_count}</p>
            </div>
        """, unsafe_allow_html=True)
    
    # Doctors Information
    doctors = get_doctors_info()
    
    for doctor_name, details in doctors.items():
        st.markdown(f"""
            <div class='doctor-card'>
                <h4 style='margin:0 0 0.5rem 0; color: #4267B2;'>{doctor_name}</h4>
                <p style='margin:0.2rem 0;'>🏥 <strong>Specialization:</strong> {details['specialization']}</p>
                <p style='margin:0.2rem 0;'>⏳ <strong>Experience:</strong> {details['experience']}</p>
                <p style='margin:0.2rem 0;'>💰 <strong>Fee:</strong> {details['fee']}</p>
                <p style='margin:0.2rem 0;'>📅 <strong>Availability:</strong> {details['availability']}</p>
                <p style='margin:0.2rem 0;'>🎓 <strong>Education:</strong> {details['education']}</p>
            </div>
        """, unsafe_allow_html=True)

# Header
st.markdown("""
    <div class='chat-header'>
        <h2>👨‍⚕️ Telemedicine Appointment Scheduler</h2>
        <p style='margin:0.5rem 0 0 0; font-size: 1rem; opacity: 0.9;'>Book your virtual consultation with our specialists</p>
    </div>
""", unsafe_allow_html=True)

# Quick action buttons with enhanced styling and toggle functionality
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📅 Book Appointment", key="book", 
                 type="primary" if st.session_state.active_button == "book" else "secondary"):
        if st.session_state.active_button == "book":
            st.session_state.active_button = None
            st.session_state.appointment_stage = None  # Reset appointment stage when deactivating
        else:
            st.session_state.active_button = "book"
            st.session_state.appointment_stage = 'collect_info'
        st.rerun()

with col2:
    if st.button("🕒 View Available Slots", key="slots",
                 type="primary" if st.session_state.active_button == "slots" else "secondary"):
        if st.session_state.active_button == "slots":
            st.session_state.active_button = None
        else:
            st.session_state.active_button = "slots"
            display_available_slots()

with col3:
    if st.button("🚨 Emergency Contact", key="emergency",
                 type="primary" if st.session_state.active_button == "emergency" else "secondary"):
        if st.session_state.active_button == "emergency":
            st.session_state.active_button = None
        else:
            st.session_state.active_button = "emergency"
            st.markdown("""
                <div style='background: #ff4444; color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 1rem 0;'>
                    <h4 style='margin:0 0 1rem 0;'>Emergency Contacts</h4>
                    <p style='margin:0.5rem 0;'>📞 911</p>
                    <p style='margin:0.5rem 0;'>☎️ +1-XXX-XXX-XXXX</p>
                </div>
            """, unsafe_allow_html=True)

# Chat interface
with st.container():
    # Initialize Gemini model
    @st.cache_resource
    def get_gemini_model():
        try:
            if not GOOGLE_API_KEY:
                raise ValueError("Google API Key is missing in .env file")
            
            # Initialize the model
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # Basic configuration
            model.generation_config = {
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
            
            return model
        except Exception as e:
            st.error(f"Failed to initialize Gemini model: {str(e)}")
            return None

    # Function to get response from Gemini
    def get_gemini_response(question):
        try:
            if not GOOGLE_API_KEY:
                st.error("Please configure your Google API Key in the .env file")
                return "I apologize, but I'm not properly configured yet. Please contact the administrator to set up the API key."

            model = get_gemini_model()
            if model is None:
                return "I apologize, but I'm having trouble connecting to the AI service. Please try again later."

            # Special handling for appointment-related queries
            if any(word in question.lower() for word in ["appointment", "book", "schedule"]):
                return "I'll help you book an appointment. Let me guide you through the process."
            
            # Add context to the question
            context = """You are a helpful medical assistant for a Telemedicine Appointment Scheduling system. 
            You help patients with:
            1. Scheduling appointments
            2. Providing information about doctors and services
            3. Answering medical queries
            4. Handling emergency situations appropriately
            
            Be professional, empathetic, and provide accurate information."""
            
            prompt = f"{context}\n\nQuestion: {question}\nResponse:"

            # Generate response
            response = model.generate_content(prompt)
            
            if response and hasattr(response, 'text'):
                return response.text.strip()
            else:
                return "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."

        except Exception as e:
            st.error(f"Chat Error: {str(e)}")
            return f"I apologize, but I encountered an error: {str(e)}"

    # Display chat history
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"<div class='user-message'>{message['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='bot-message'>{message['content']}</div>", unsafe_allow_html=True)

    # Handle appointment booking process
    if st.session_state.appointment_stage is not None and st.session_state.active_button == "book":
        booking_response = handle_appointment_booking()
        if booking_response:
            st.markdown(f"<div class='bot-message'>{booking_response}</div>", unsafe_allow_html=True)

    # User input
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_input("Type your message...", key="user_input")
        submit_button = st.form_submit_button("Send")

    if submit_button and user_input:
        # Show user message
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # Show typing indicator
        with st.spinner("Thinking..."):
            try:
                # Get bot response
                bot_response = get_gemini_response(user_input)
                
                # Add response to chat history
                if bot_response:
                    st.session_state.chat_history.append({"role": "bot", "content": bot_response})
                    
                    # If it's an appointment request, activate the booking form
                    if "help you book an appointment" in bot_response:
                        st.session_state.appointment_stage = 'collect_info'
                        st.session_state.active_button = "book"
            except Exception as e:
                st.error("Sorry, I encountered an error. Please try again.")
                st.error(f"Error details: {str(e)}")
        
        # Rerun to update the chat display
        st.rerun()