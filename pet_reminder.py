import streamlit as st
import qrcode
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta
import io
import base64
from PIL import Image
import uuid
import os
import urllib.parse
import hashlib
import boto3

# Configure page with mobile optimization
st.set_page_config(
    page_title="Pet Medication Reminder",
    page_icon="🐾",
    layout="wide"
)

# AWS Configuration
AWS_REGION = 'us-east-1'
S3_BUCKET = 'pet-medication-reminders'

# Initialize AWS client
s3_client = boto3.client('s3', region_name=AWS_REGION)

# Global counter for generating sequential IDs
if 'pet_counter' not in st.session_state:
    st.session_state.pet_counter = 1

def get_next_sequence_number():
    """Get next sequence number from S3 or start from 1"""
    try:
        # Try to get current counter from S3
        response = s3_client.get_object(Bucket=S3_BUCKET, Key='system/counter.txt')
        current_count = int(response['Body'].read().decode('utf-8'))
    except:
        # If file doesn't exist, start from 1
        current_count = 0
    
    # Increment counter
    next_count = current_count + 1
    
    # Save updated counter back to S3
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key='system/counter.txt',
            Body=str(next_count).encode('utf-8'),
            ContentType='text/plain'
        )
    except Exception as e:
        st.warning(f"Could not save counter to S3: {e}")
        # Fall back to session state if S3 fails
        if 'pet_counter' not in st.session_state:
            st.session_state.pet_counter = 1
        next_count = st.session_state.pet_counter
        st.session_state.pet_counter += 1
    
    return next_count

def generate_meaningful_id(pet_name, product_name):
    """Generate meaningful ID with sequence number"""
    # Get next sequence number from S3 (persistent)
    current_count = get_next_sequence_number()
    
    # Clean names for URL (remove special characters, spaces)
    clean_pet = ''.join(c for c in pet_name if c.isalnum())[:10]
    clean_product = ''.join(c for c in product_name.split('(')[0] if c.isalnum())[:10]
    
    # Format: QR0001_PetName_ProductName
    meaningful_id = f"QR{current_count:04d}_{clean_pet}_{clean_product}"
    
    return meaningful_id

def create_calendar_reminder(pet_name, product_name, frequency, frequency_value, reminder_time, end_after_count=None, notes=""):
    """Create ICS calendar content for recurring reminder"""
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Pet Medication Reminder//Boehringer Ingelheim//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    
    # Create event
    event = Event()
    event.add('summary', f"{pet_name} - {product_name}")
    event.add('description', f"Medication reminder: {product_name}\nPet: {pet_name}\n{notes}")
    
    # Calculate start time
    now = datetime.now()
    start_time = datetime.combine(now.date(), datetime.strptime(reminder_time, "%H:%M").time())
    
    # If start time is in the past today, move to next occurrence
    if start_time < now:
        if frequency == "Daily":
            start_time += timedelta(days=1)
        elif frequency == "Weekly":
            start_time += timedelta(days=7)
        elif frequency == "Monthly":
            if start_time.month == 12:
                start_time = start_time.replace(year=start_time.year + 1, month=1)
            else:
                start_time = start_time.replace(month=start_time.month + 1)
        elif frequency == "Custom Days":
            start_time += timedelta(days=int(frequency_value))
    
    event.add('dtstart', start_time)
    event.add('dtend', start_time + timedelta(hours=1))
    event.add('dtstamp', datetime.now())
    event.add('uid', str(uuid.uuid4()))
    
    # Add recurrence rule with optional end count
    rrule = {}
    
    if frequency == "Daily":
        rrule['freq'] = 'daily'
    elif frequency == "Weekly":
        rrule['freq'] = 'weekly'
    elif frequency == "Monthly":
        rrule['freq'] = 'monthly'
    elif frequency == "Custom Days":
        rrule['freq'] = 'daily'
        rrule['interval'] = int(frequency_value)
    
    # Add count limit if specified
    if end_after_count and end_after_count > 0:
        rrule['count'] = int(end_after_count)
    
    event.add('rrule', rrule)
    
    # Add alarm (reminder notification)
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', f'Time to give {product_name} to {pet_name}!')
    alarm.add('trigger', timedelta(hours=-1))
    event.add_component(alarm)
    
    cal.add_component(event)
    
    return cal.to_ical().decode('utf-8')

def upload_to_s3(calendar_data, file_id):
    """Upload calendar file to S3 and return public URL"""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"calendars/{file_id}.ics",
            Body=calendar_data.encode('utf-8'),
            ContentType='text/calendar',
            ContentDisposition=f'attachment; filename="{file_id}.ics"'
        )
        
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/calendars/{file_id}.ics"
    except Exception as e:
        st.error(f"Error uploading to S3: {e}")
        return None

def create_web_page_html(pet_name, product_name, calendar_url, reminder_details):
    """Create HTML page that serves calendar with device detection"""
    # Base64 encode the web page specific logo
    logo_data_url = ""
    if os.path.exists("BI-Logo-2.png"):
        try:
            with open("BI-Logo-2.png", "rb") as f:
                logo_bytes = f.read()
                logo_b64 = base64.b64encode(logo_bytes).decode()
                logo_data_url = f"data:image/png;base64,{logo_b64}"
        except:
            pass
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐾 {pet_name.upper()} - Medication Reminder</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #08312a;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
        }}
        
        .container {{
            background: linear-gradient(135deg, #0a3d33, #08312a);
            border: 2px solid #00e47c;
            border-radius: 20px;
            padding: 30px;
            max-width: 420px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }}
        
        .header {{
            margin-bottom: 25px;
        }}
        
        .logo-container {{
            width: 100px;
            height: 100px;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .logo-img {{
            max-width: 100px;
            max-height: 100px;
            object-fit: contain;
        }}
        
        .logo-fallback {{
            font-size: 40px;
            color: #00e47c;
        }}
        
        .pet-name {{
            font-size: 32px;
            font-weight: bold;
            color: #00e47c;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        
        .medication {{
            font-size: 20px;
            color: #ffffff;
            margin-bottom: 25px;
            opacity: 0.9;
        }}
        
        .details {{
            background: rgba(0, 228, 124, 0.1);
            border: 1px solid #00e47c;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
            text-align: left;
        }}
        
        .detail-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 15px;
        }}
        
        .detail-label {{
            color: #00e47c;
            font-weight: 600;
        }}
        
        .detail-value {{
            color: #ffffff;
        }}
        
        .notes-section {{
            background: rgba(0, 228, 124, 0.05);
            border: 1px dashed #00e47c;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            text-align: left;
        }}
        
        .notes-title {{
            color: #00e47c;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 14px;
        }}
        
        .notes-text {{
            color: #ffffff;
            font-size: 14px;
            line-height: 1.4;
            opacity: 0.9;
        }}
        
        .btn {{
            display: block;
            width: 100%;
            padding: 18px;
            margin: 15px 0;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 228, 124, 0.3);
        }}
        
        .btn-primary {{
            background: linear-gradient(45deg, #00e47c, #00b85c);
            color: #08312a;
            font-weight: 700;
        }}
        
        .instructions {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
            font-size: 14px;
            color: #ffffff;
            line-height: 1.5;
        }}
        
        .instructions-title {{
            color: #00e47c;
            font-weight: 600;
            margin-bottom: 10px;
            font-size: 16px;
        }}
        
        .device-specific {{
            margin-top: 15px;
            padding: 15px;
            background: rgba(0, 228, 124, 0.1);
            border-radius: 8px;
            border-left: 4px solid #00e47c;
        }}
        
        @media (max-width: 480px) {{
            body {{
                padding: 15px;
            }}
            
            .container {{
                padding: 25px 20px;
            }}
            
            .pet-name {{
                font-size: 26px;
            }}
            
            .medication {{
                font-size: 18px;
            }}
            
            .btn {{
                padding: 16px;
                font-size: 15px;
            }}
            
            .logo-container {{
                width: 80px;
                height: 80px;
            }}
            
            .logo-img {{
                max-width: 80px;
                max-height: 80px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-container">
                {f'<img src="{logo_data_url}" alt="BI Logo" class="logo-img">' if logo_data_url else '<div class="logo-fallback">🐾</div>'}
            </div>
            <div class="pet-name">{pet_name.upper()}</div>
            <div class="medication">{product_name}</div>
        </div>
        
        <div class="details">
            <div class="detail-row">
                <span class="detail-label">Frequency:</span>
                <span class="detail-value">{reminder_details['frequency']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Time:</span>
                <span class="detail-value">{reminder_details['time']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Duration:</span>
                <span class="detail-value">{reminder_details['duration']}</span>
            </div>
            
            {f'''
            <div class="notes-section">
                <div class="notes-title">📝 Additional Notes:</div>
                <div class="notes-text">{reminder_details['notes']}</div>
            </div>
            ''' if reminder_details.get('notes') and reminder_details['notes'].strip() else ''}
        </div>
        
        <a href="{calendar_url}" class="btn btn-primary" download="{pet_name.upper()}_{product_name}_reminder.ics">
            📅 Add to My Calendar
        </a>
    </div>

    <script>
        // Auto-redirect to calendar download on mobile for better UX
        function handleMobileDownload() {{
            const userAgent = navigator.userAgent;
            const downloadBtn = document.querySelector('.btn-primary');
            
            if (/iPhone|iPad|iPod|Android/i.test(userAgent)) {{
                downloadBtn.addEventListener('click', function(e) {{
                    // Let the default download behavior work
                    setTimeout(function() {{
                        // Optional: Show a brief success message
                        downloadBtn.innerHTML = '✅ Calendar File Ready!';
                        downloadBtn.style.background = '#28a745';
                        
                        setTimeout(function() {{
                            downloadBtn.innerHTML = '📅 Add to My Calendar';
                            downloadBtn.style.background = 'linear-gradient(45deg, #00e47c, #00b85c)';
                        }}, 2000);
                    }}, 500);
                }});
            }}
        }}
        
        window.addEventListener('load', handleMobileDownload);
    </script>
</body>
</html>
"""
    return html_content

def upload_web_page_to_s3(html_content, page_id):
    """Upload HTML page to S3 and return public URL"""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"pages/{page_id}.html",
            Body=html_content.encode('utf-8'),
            ContentType='text/html'
        )
        
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/pages/{page_id}.html"
    except Exception as e:
        st.error(f"Error uploading page to S3: {e}")
        return None

def generate_qr_code(web_page_url):
    """Generate QR code that points to the web page"""
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=6,
    )
    
    qr.add_data(web_page_url)
    qr.make(fit=True)
    
    # Create QR code with green background
    qr_img = qr.make_image(fill_color="black", back_color="#00e47c")
    
    img_buffer = io.BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer.getvalue()

def main():
    # Add mobile-responsive CSS
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }
    
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        
        .stButton button {
            width: 100%;
            height: 3rem;
            font-size: 16px;
        }
        
        .stTextInput input, .stSelectbox select, .stTextArea textarea {
            font-size: 16px;
        }
    }
    
    /* Hide sidebar completely */
    .css-1d391kg {
        display: none;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header with logo and title in same line
    if os.path.exists("BI-Logo.png"):
        # Encode logo to base64 for HTML embedding
        with open("BI-Logo.png", "rb") as f:
            logo_bytes = f.read()
            logo_b64 = base64.b64encode(logo_bytes).decode()
            logo_data_url = f"data:image/png;base64,{logo_b64}"
        
        st.markdown(f"""
        <div style='display: flex; align-items: center; margin-bottom: 10px; height: 90px;'>
            <img src="{logo_data_url}" style='width: 80px; height: 80px; object-fit: contain; margin-right: 20px;'>
            <div style='flex: 1; text-align: center;'>
                <h4 style='margin: 0; font-weight: bold; color: #333;'>🐾 Pet Medication Reminder 🐾</h4>
            </div>
            <div style='width: 80px;'></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='display: flex; align-items: center; margin-bottom: 10px; height: 90px;'>
            <div style='width: 80px; height: 80px; display: flex; align-items: center; justify-content: center; background: #f0f0f0; border-radius: 10px; font-size: 35px; margin-right: 20px;'>🐾</div>
            <div style='flex: 1; text-align: center;'>
                <h4 style='margin: 0; font-weight: bold; color: #333;'>🐾 Pet Medication Reminder 🐾</h4>
            </div>
            <div style='width: 80px;'></div>
        </div>
        """, unsafe_allow_html=True)
    
    st.text(" ")
    
    # Main form
    col1, spacer, col2 = st.columns([1, 0.2, 1])
    
    with col1:
        st.markdown("<h5 style='text-align: left; font-weight: bold;'>📋 Reminder Details</h5>", unsafe_allow_html=True)
        
        pet_name = st.text_input("Pet Name", placeholder="e.g., Max, Luna, Charlie")
        
        products = [
            "NexGard (Flea & Tick)",
            "NexGard SPECTRA (Flea, Tick & Worm)",
            "Heartgard Plus (Heartworm)",
            "Metacam (Pain Relief)", 
            "Frontline Plus (Flea & Tick)",
            "Other"
        ]
        
        product_name = st.selectbox("Boehringer Ingelheim Product", products)
        
        if product_name == "Other":
            product_name = st.text_input("Custom Product Name", placeholder="Enter product name")
        
        frequency = st.selectbox("Reminder Frequency", ["Daily", "Weekly", "Monthly", "Custom Days"], index=2)
        
        frequency_value = None
        if frequency == "Custom Days":
            frequency_value = st.number_input("Every X days", min_value=1, max_value=365, value=30)
        
        end_type = st.radio("", ["Continue indefinitely", "Stop after N occurrences"])
        
        end_after_count = None
        if end_type == "Stop after N occurrences":
            end_after_count = st.number_input("Number of reminders", min_value=1, max_value=1000, value=12)
            
            if frequency == "Monthly" and end_after_count:
                months = end_after_count
                years = months // 12
                remaining_months = months % 12
                if years > 0:
                    duration_text = f"≈ {years} year{'s' if years > 1 else ''}"
                    if remaining_months > 0:
                        duration_text += f" and {remaining_months} month{'s' if remaining_months > 1 else ''}"
                else:
                    duration_text = f"≈ {remaining_months} month{'s' if remaining_months > 1 else ''}"
                st.info(f"💡 {end_after_count} monthly reminders = {duration_text}")
        
        reminder_time = st.time_input("Reminder Time", value=datetime.strptime("19:00", "%H:%M").time())
        
        notes = st.text_area("Additional Notes (Optional)", placeholder="e.g., Give with food, Check for side effects")
        
        generate_button = st.button("🔄 Generate QR Code", type="primary")
    
    with col2:
        st.markdown("<h5 style='text-align: left; font-weight: bold;'>📱 QR Code</h5>", unsafe_allow_html=True)
        
        if generate_button:
            if pet_name and product_name:
                with st.spinner("QR Code Generation in Progress...."):
                    try:
                        calendar_data = create_calendar_reminder(
                            pet_name=pet_name,
                            product_name=product_name,
                            frequency=frequency,
                            frequency_value=frequency_value,
                            reminder_time=reminder_time.strftime("%H:%M"),
                            end_after_count=end_after_count,
                            notes=notes
                        )
                        
                        meaningful_id = generate_meaningful_id(pet_name, product_name)
                        calendar_url = upload_to_s3(calendar_data, meaningful_id)
                        
                        if calendar_url:
                            reminder_details = {
                                'frequency': frequency,
                                'time': reminder_time.strftime('%H:%M'),
                                'duration': f"{end_after_count} occurrences" if end_after_count else "Continues indefinitely",
                                'notes': notes
                            }
                            
                            html_content = create_web_page_html(pet_name, product_name, calendar_url, reminder_details)
                            web_page_url = upload_web_page_to_s3(html_content, meaningful_id)
                            
                            if web_page_url:
                                qr_image_bytes = generate_qr_code(web_page_url)
                                
                                col_qr1, col_qr2, col_qr3 = st.columns([0.3, 1, 0.3])
                                with col_qr2:
                                    st.image(qr_image_bytes, width=250)
                                
                                st.success("✅ QR Code Generated Successfully!")
                                
                                
                                with st.expander("🔗 URLs"):
                                    st.write(f"**QR Web Page URL:** {web_page_url}")
                                    st.write(f"**Calendar File URL:** {calendar_url}")
                                    
                                
                                with st.expander("📋 Reminder Summary"):
                                    st.write(f"**Pet:** {pet_name}")
                                    st.write(f"**Product:** {product_name}")
                                    st.write(f"**Frequency:** {frequency}")
                                    if frequency_value:
                                        st.write(f"**Every:** {frequency_value} days")
                                    st.write(f"**Time:** {reminder_time.strftime('%H:%M')}")
                                    if end_after_count:
                                        st.write(f"**Total Reminders:** {end_after_count}")
                                        st.write(f"**Will Stop After:** {end_after_count} occurrences")
                                    else:
                                        st.write(f"**Duration:** Continues indefinitely")
                                    if notes:
                                        st.write(f"**Notes:** {notes}")
                                
                                with st.expander("📥 Download Options"):
                                    st.download_button(
                                        label="📥 Download QR Code",
                                        data=qr_image_bytes,
                                        file_name=f"{meaningful_id}_qr.png",
                                        mime="image/png"
                                    )
                                    
                                    st.download_button(
                                        label="📅 Download Calendar File", 
                                        data=calendar_data,
                                        file_name=f"{meaningful_id}.ics",
                                        mime="text/calendar"
                                    )
                            else:
                                st.error("❌ Failed to create web page - check S3 permissions")
                        else:
                            st.error("❌ Failed to upload calendar file - check S3 configuration")
                        
                    except Exception as e:
                        st.error(f"Error generating QR code: {str(e)}")
            else:
                st.warning("⚠️ Please fill in Pet Name and Product Name")
        else:
            st.info("👈 Fill the form and click 'Generate QR Code'")

if __name__ == "__main__":
    main()
