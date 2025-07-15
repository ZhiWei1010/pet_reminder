import streamlit as st
import qrcode
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta, date
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import uuid
import os
import urllib.parse
import hashlib
import boto3
import math
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import re
import uuid

# Configure page with mobile optimization
st.set_page_config(
    page_title="Pet Reminder",
    page_icon="🐾",
    layout="wide"
)

# AWS Configuration - Use Streamlit secrets for cloud deployment
if "AWS_REGION" in st.secrets:
    # Production: Use Streamlit secrets
    AWS_REGION = st.secrets["AWS_REGION"]
    S3_BUCKET = st.secrets["S3_BUCKET_NAME"]
    aws_access_key_id = st.secrets["AWS_ACCESS_KEY_ID"]
    aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"]
    
    # Email Configuration from secrets
    SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(st.secrets.get("SMTP_PORT", "587"))
    EMAIL_USER = st.secrets.get("EMAIL_USER", "")
    EMAIL_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "")
else:
    # Development: Use environment variables
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'pet-reminder')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    # Email Configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    EMAIL_USER = os.getenv('EMAIL_USER', '')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')

# Initialize AWS client
try:
    s3_client = boto3.client(
        's3',
        region_name=AWS_REGION,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )
    # Test AWS connection
    s3_client.list_buckets()
    AWS_CONFIGURED = True
except Exception as e:
    AWS_CONFIGURED = False
    st.error(f"⚠️ AWS S3 not configured properly: {str(e)}")
    st.info("Some features may be limited without S3 configuration.")

# Initialize session state for persistence
def init_session_state():
    """Initialize all session state variables"""
    if 'pet_counter' not in st.session_state:
        st.session_state.pet_counter = 1
    
    # Form data persistence
    if 'form_data' not in st.session_state:
        st.session_state.form_data = {}
    
    # Generated content persistence
    if 'generated_content' not in st.session_state:
        st.session_state.generated_content = None
    
    # Generation status
    if 'content_generated' not in st.session_state:
        st.session_state.content_generated = False

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_qr_svg(web_page_url):
    """Generate QR code as SVG string for HTML embedding"""
    import qrcode.image.svg
    
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
        image_factory=factory
    )
    
    qr.add_data(web_page_url)
    qr.make(fit=True)
    
    # Generate SVG
    img = qr.make_image()
    svg_string = img.to_string().decode('utf-8')
    
    # Customize SVG colors to match theme
    svg_string = svg_string.replace('fill="black"', 'fill="#000000"')
    svg_string = svg_string.replace('fill="white"', 'fill="#00e47c"')
    
    return svg_string

def send_email_with_attachment(recipient_email, pet_name, product_name, reminder_image_bytes, calendar_data, reminder_details):
    """Send email with Gmail mobile optimized template"""
    try:
        if not EMAIL_USER or not EMAIL_PASSWORD:
            return False, "Email configuration not set. Please configure SMTP settings."
        
        # Get the web page URL and QR code from session state
        web_page_url = st.session_state.generated_content.get('web_page_url') if st.session_state.generated_content else None
        qr_image_bytes = st.session_state.generated_content.get('qr_image_bytes') if st.session_state.generated_content else None
        
        if not web_page_url:
            # Fallback URL if web page not available
            web_page_url = f"https://example.com/reminder/{pet_name}_{product_name}"
        
        # Create message with related multipart for embedded images
        msg = MIMEMultipart('related')
        msg['From'] = EMAIL_USER
        msg['To'] = recipient_email
        msg['Subject'] = f"🐾 Pet QR Reminder Card - {pet_name} ({product_name}) 🐾"
        
        # Generate unique CIDs for embedded images
        qr_cid = f"qr_code_{uuid.uuid4().hex}"
        logo_cid = f"logo_{uuid.uuid4().hex}"
        
        # Load BI Logo for embedding
        logo_image_bytes = None
        if os.path.exists("BI-Logo-2.png"):
            try:
                with open("BI-Logo-2.png", "rb") as f:
                    logo_image_bytes = f.read()
            except Exception as e:
                print(f"Error loading BI-Logo-2.png: {e}")
        elif os.path.exists("BI-Logo.png"):
            try:
                with open("BI-Logo.png", "rb") as f:
                    logo_image_bytes = f.read()
            except Exception as e:
                print(f"Error loading BI-Logo.png: {e}")
        
        # Gmail Mobile Optimized HTML - Simplified layout with tables
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        /* Reset styles for Gmail */
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        /* Main container - Use table for Gmail compatibility */
        .email-wrapper {{
            width: 100% !important;
            background-color: #f5f5f5;
            font-family: Arial, sans-serif;
            line-height: 1.4;
        }}
        
        .email-container {{
            width: 100%;
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
        }}
        
        /* Header styles */
        .header {{
            background-color: #08312a;
            padding: 20px;
            text-align: center;
        }}
        
        .header-content {{
            display: table;
            width: 100%;
            margin: 0 auto;
        }}
        
        .logo-section {{
            display: table-cell;
            vertical-align: middle;
            width: 80px;
            text-align: left;
        }}
        
        .logo-img {{
            width: 60px;
            height: 60px;
            object-fit: contain;
            display: block;
        }}
        
        .title-section {{
            display: table-cell;
            vertical-align: middle;
            text-align: center;
        }}
        
        .header h1 {{
            color: #00e47c;
            font-size: 24px;
            margin: 5px 0;
            font-weight: bold;
        }}
        
        .header p {{
            color: #ffffff;
            font-size: 16px;
            margin: 0;
        }}
        
        /* QR Code section - Simplified for mobile */
        .qr-section {{
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            border: 3px solid #00e47c;
        }}
        
        .qr-title {{
            color: #08312a;
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 15px;
        }}
        
        .qr-image {{
            width: 200px;
            height: 200px;
            margin: 10px auto;
            background-color: #ffffff;
            border: 2px solid #00e47c;
            padding: 10px;
            display: block;
        }}
        
        .qr-instructions {{
            color: #08312a;
            font-size: 16px;
            font-weight: bold;
            margin: 15px 0 10px 0;
        }}
        
        .qr-link {{
            margin: 10px 0;
        }}
        
        .qr-link a {{
            color: #007bff;
            text-decoration: underline;
            font-weight: bold;
            font-size: 14px;
        }}
        
        .scan-tip {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 10px;
            margin: 15px 0;
            border-radius: 5px;
            color: #856404;
            font-size: 13px;
        }}
        
        /* Details section - Using table for better Gmail support */
        .details-section {{
            padding: 20px;
            background-color: #ffffff;
        }}
        
        .details-title {{
            color: #08312a;
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            border-bottom: 2px solid #00e47c;
            padding-bottom: 5px;
        }}
        
        .details-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .details-table td {{
            padding: 8px 5px;
            border-bottom: 1px solid #e9ecef;
            vertical-align: top;
        }}
        
        .detail-label {{
            color: #08312a;
            font-weight: bold;
            width: 40%;
            font-size: 14px;
        }}
        
        .detail-value {{
            color: #333333;
            width: 60%;
            font-size: 14px;
        }}
        
        /* Times section */
        .times-section {{
            background-color: #e8f5e8;
            padding: 15px;
            margin: 15px 0;
            border-radius: 5px;
        }}
        
        .times-title {{
            color: #08312a;
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 16px;
        }}
        
        .time-item {{
            color: #333333;
            margin: 5px 0;
            font-size: 14px;
        }}
        
        /* Notes section */
        .notes-section {{
            background-color: #fff3cd;
            padding: 15px;
            margin: 15px 0;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
        }}
        
        .notes-title {{
            color: #856404;
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 16px;
        }}
        
        .notes-text {{
            color: #856404;
            font-size: 14px;
            line-height: 1.4;
        }}
        
        /* Instructions section */
        .instructions {{
            background-color: #e3f2fd;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #2196f3;
        }}
        
        .instructions-title {{
            color: #1976d2;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        .instruction-text {{
            color: #1976d2;
            font-size: 14px;
            line-height: 1.4;
        }}
        
        /* Attachment note */
        .attachment-note {{
            background-color: #d1ecf1;
            border: 1px solid #bee5eb;
            padding: 15px;
            margin: 15px 0;
            text-align: center;
            border-radius: 5px;
        }}
        
        .attachment-note strong {{
            color: #0c5460;
            font-size: 14px;
        }}
        
        /* Footer */
        .footer {{
            background-color: #08312a;
            color: #ffffff;
            text-align: center;
            padding: 20px;
            font-size: 12px;
        }}
        
        /* Mobile specific - Gmail Mobile overrides */
        @media only screen and (max-width: 480px) {{
            .email-container {{
                width: 100% !important;
            }}
            
            .header-content {{
                display: block !important;
            }}
            
            .logo-section,
            .title-section {{
                display: block !important;
                width: 100% !important;
                text-align: center !important;
            }}
            
            .logo-section {{
                margin-bottom: 10px;
            }}
            
            .logo-img {{
                margin: 0 auto !important;
            }}
            
            .header h1 {{
                font-size: 20px !important;
            }}
            
            .header p {{
                font-size: 14px !important;
            }}
            
            .qr-title {{
                font-size: 18px !important;
            }}
            
            .qr-image {{
                width: 150px !important;
                height: 150px !important;
            }}
            
            .qr-instructions {{
                font-size: 14px !important;
            }}
            
            .details-title {{
                font-size: 16px !important;
            }}
            
            .detail-label,
            .detail-value {{
                font-size: 13px !important;
            }}
            
            .times-title,
            .notes-title {{
                font-size: 14px !important;
            }}
            
            .time-item,
            .notes-text {{
                font-size: 13px !important;
            }}
        }}
        
        /* Force Gmail to respect our styles */
        .gmail-fix {{
            min-width: 1px;
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <table class="email-container" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td>
                    <!-- Header -->
                    <div class="header">
                        <div class="header-content">
                            <div class="title-section">
                                <h1>🐾 Pet QR Reminder Card 🐾</h1>
                                <p>Schedule for <strong>{pet_name} ({product_name})</strong></p>
                            </div>
                        </div>
                    </div>
                    
                    <!-- QR Code Section -->
                    <div class="qr-section">
                        <div class="qr-title">📱 Scan QR Code</div>
                        
                        {f'''
                        <div style="text-align: center; margin: 15px 0;">
                            <img src="cid:{qr_cid}" 
                                 alt="QR Code for Pet Reminder" 
                                 class="qr-image"
                                 style="width: 200px; height: 200px; display: block; margin: 0 auto; border: 2px solid #00e47c; padding: 10px; background-color: white;" />
                        </div>
                        ''' if qr_image_bytes else '''
                        <div style="text-align: center; margin: 15px 0;">
                            <div style="width: 200px; height: 200px; background: #f0f0f0; display: inline-block; border: 2px solid #00e47c; padding: 10px; color: #666; line-height: 180px; font-size: 14px;">QR Code Not Available</div>
                        </div>
                        '''}
                        
                        
                        
                        <div class="qr-link">
                            Can't scan? <a href="{web_page_url}">Click here instead</a>
                        </div>
                        
                        
                    </div>
                    
                    <!-- Details Section -->
                    <div class="details-section">
                        <div class="details-title">📋 Reminder Details</div>
                        
                        <table class="details-table">
                            <tr>
                                <td class="detail-label">Pet Name:</td>
                                <td class="detail-value">{pet_name}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">BI Product:</td>
                                <td class="detail-value">{product_name}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">Start Date:</td>
                                <td class="detail-value">{reminder_details['start_date']}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">End Date:</td>
                                <td class="detail-value">{reminder_details['end_date']}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">Frequency:</td>
                                <td class="detail-value">{reminder_details['frequency']}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">Duration:</td>
                                <td class="detail-value">{reminder_details['duration']}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">Total Reminders:</td>
                                <td class="detail-value">{reminder_details['total_reminders']}</td>
                            </tr>
                        </table>
                        
                        <div class="times-section">
                            <div class="times-title">⏰ Reminder Times:</div>
                            {"".join([f'<div class="time-item">• {time_info["time"]} - {time_info["label"]}</div>' for time_info in reminder_details['times']])}
                        </div>
                        
                        {f'''
                        <div class="notes-section">
                            <div class="notes-title">📝 Additional Notes:</div>
                            <div class="notes-text">{reminder_details['notes']}</div>
                        </div>
                        ''' if reminder_details.get('notes') and reminder_details['notes'].strip() else ''}
                    </div>
                    
                    
                </td>
            </tr>
        </table>
    </div>
</body>
</html>
        """
        
        # Create plain text version (important for Gmail)
        text_body = f"""
🐾 Pet Reminder Card - {pet_name} ({product_name})

🔗 Reminder Link: {web_page_url}

📋 Reminder Details:
• Pet Name: {pet_name}
• Product: {product_name}
• Start Date: {reminder_details['start_date']}
• End Date: {reminder_details['end_date']}
• Frequency: {reminder_details['frequency']}
• Duration: {reminder_details['duration']}
• Total Reminders: {reminder_details['total_reminders']}

⏰ Reminder Times:
"""
        for time_info in reminder_details['times']:
            text_body += f"• {time_info['time']} - {time_info['label']}\n"
        
        if reminder_details.get('notes'):
            text_body += f"\n📝 Additional Notes:\n{reminder_details['notes']}\n"
        
        text_body += """
📱 How to use:
1. Click the reminder link above to access the QR code page
2. Scan the QR code with your phone camera
3. Download the attached reminder card and calendar file
4. Add the calendar file (.ics) to your calendar app

📎 Attachments:
• Full Reminder Card (PNG image)
• Calendar File (.ics)

Best regards,
Pet Reminder System
        """
        
        # Create multipart structure
        msg_alternative = MIMEMultipart('alternative')
        
        part_text = MIMEText(text_body, 'plain')
        part_html = MIMEText(html_body, 'html')
        
        msg_alternative.attach(part_text)
        msg_alternative.attach(part_html)
        msg.attach(msg_alternative)
        
        # Embed QR code as related attachment (CID) - Gmail compatible
        if qr_image_bytes:
            qr_embedded = MIMEImage(qr_image_bytes)
            qr_embedded.add_header('Content-ID', f'<{qr_cid}>')
            qr_embedded.add_header('Content-Disposition', 'inline', filename=f"{pet_name}_qr_code.png")
            msg.attach(qr_embedded)
        
        # Embed BI Logo as related attachment (CID) - Gmail compatible
        #if logo_image_bytes:
            #logo_embedded = MIMEImage(logo_image_bytes)
            #logo_embedded.add_header('Content-ID', f'<{logo_cid}>')
            #logo_embedded.add_header('Content-Disposition', 'inline', filename="bi_logo.png")
            #msg.attach(logo_embedded)
        
        # Attach the full reminder card image as attachment
        reminder_card_attachment = MIMEImage(reminder_image_bytes)
        reminder_card_attachment.add_header('Content-Disposition', f'attachment; filename="{pet_name}_{product_name}_reminder_card.png"')
        msg.attach(reminder_card_attachment)
        
        # Attach calendar file
        calendar_attachment = MIMEText(calendar_data, 'calendar')
        calendar_attachment.add_header('Content-Disposition', f'attachment; filename="{pet_name}_{product_name}_calendar.ics"')
        msg.attach(calendar_attachment)
        
        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_USER, recipient_email, text)
        server.quit()
        
        return True, "Email sent successfully!"
        
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def save_form_data(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes):
    """Save current form data to session state"""
    st.session_state.form_data = {
        'pet_name': pet_name,
        'product_name': product_name,
        'start_date': start_date,
        'end_date': end_date,
        'frequency': frequency,
        'frequency_value': frequency_value,
        'selected_times': selected_times,
        'notes': notes
    }

def get_form_data(key, default=None):
    """Get form data from session state"""
    return st.session_state.form_data.get(key, default)

def calculate_reminder_count(start_date, end_date, frequency, frequency_value=None):
    """Calculate total number of reminders based on date range and frequency"""
    if end_date < start_date:
        return 0
    
    total_days = (end_date - start_date).days + 1  # Include both start and end dates
    
    if frequency == "Daily":
        return total_days
    elif frequency == "Weekly":
        return math.ceil(total_days / 7)
    elif frequency == "Monthly":
        # Calculate months between dates
        months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        # Add 1 if we haven't passed the start day in the end month
        if end_date.day >= start_date.day:
            months += 1
        return max(1, months)
    elif frequency == "Custom Days" and frequency_value:
        return math.ceil(total_days / frequency_value)
    
    return 0

def format_duration_text(start_date, end_date, reminder_count, frequency):
    """Format duration text for display"""
    total_days = (end_date - start_date).days + 1
    
    if total_days <= 7:
        return f"{total_days} day{'s' if total_days > 1 else ''}"
    elif total_days <= 31:
        weeks = math.ceil(total_days / 7)
        return f"≈ {weeks} week{'s' if weeks > 1 else ''}"
    elif total_days <= 365:
        months = math.ceil(total_days / 30)
        return f"≈ {months} month{'s' if months > 1 else ''}"
    else:
        years = total_days / 365
        if years >= 2:
            return f"≈ {years:.1f} years"
        else:
            months = math.ceil(total_days / 30)
            return f"≈ {months} months"

def get_fallback_font(size):
    """Get the best available font for the system"""
    font_paths = [
        # Common Windows fonts
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        # Common macOS fonts
        "/System/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Common Linux fonts
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/arial.ttf",
        # Streamlit Cloud / Ubuntu fonts
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    
    # If no fonts found, use default
    return ImageFont.load_default()

def get_next_sequence_number():
    """Get next sequence number from S3 or start from 1"""
    if not AWS_CONFIGURED:
        # Fallback to session state if S3 not available
        if 'pet_counter' not in st.session_state:
            st.session_state.pet_counter = 1
        else:
            st.session_state.pet_counter += 1
        return st.session_state.pet_counter
    
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

def create_calendar_reminder(pet_name, product_name, frequency, frequency_value, reminder_times, start_date, end_date, notes=""):
    """Create ICS calendar content for recurring reminder with multiple times per day"""
    
    # Calculate reminder count for RRULE
    reminder_count = calculate_reminder_count(start_date, end_date, frequency, frequency_value)
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Pet Medication Reminder//Boehringer Ingelheim//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    
    # Create separate events for each time of day
    for i, time_info in enumerate(reminder_times):
        time_str = time_info['time']
        time_label = time_info['label']
        
        # Create event
        event = Event()
        event_title = f"{pet_name} - {product_name}"
        if len(reminder_times) > 1:
            event_title += f" ({time_label})"
        
        event.add('summary', event_title)
        event.add('description', f"Medication reminder: {product_name}\nPet: {pet_name}\nTime: {time_label}\n{notes}")
        
        # Calculate start time using the provided start_date
        start_time = datetime.combine(start_date, datetime.strptime(time_str, "%H:%M").time())
        
        event.add('dtstart', start_time)
        event.add('dtend', start_time + timedelta(hours=1))
        event.add('dtstamp', datetime.now())
        event.add('uid', str(uuid.uuid4()))
        
        # Add recurrence rule with count limit
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
        
        # Always add count limit based on date range
        if reminder_count > 0:
            rrule['count'] = reminder_count
        
        event.add('rrule', rrule)
        
        # Add alarm (reminder notification)
        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('description', f'Time to give {product_name} to {pet_name}! ({time_label})')
        alarm.add('trigger', timedelta(minutes=-15))  # 15 minutes before
        event.add_component(alarm)
        
        cal.add_component(event)
    
    return cal.to_ical().decode('utf-8')

def upload_to_s3(calendar_data, file_id):
    """Upload calendar file to S3 and return public URL"""
    if not AWS_CONFIGURED:
        st.warning("⚠️ S3 not configured. Calendar file will be available for download only.")
        return None
        
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

def upload_reminder_image_to_s3(image_bytes, file_id):
    """Upload reminder image to S3 and return public URL"""
    if not AWS_CONFIGURED:
        return None
        
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"images/{file_id}_reminder_image.png",
            Body=image_bytes,
            ContentType='image/png',
            ContentDisposition=f'attachment; filename="{file_id}_reminder_image.png"'
        )
        
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/images/{file_id}_reminder_image.png"
    except Exception as e:
        st.error(f"Error uploading image to S3: {e}")
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
    
    # Format reminder times for display
    times_html_list = ""
    for t in reminder_details['times']:
        times_html_list += f"• {t['time']} - {t['label']}<br>"
    times_html_list = times_html_list.rstrip('<br>')
    
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
            flex: 1;
            text-align: right;
        }}
        
        .times-section {{
            background: rgba(0, 228, 124, 0.05);
            border: 1px dashed #00e47c;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            text-align: left;
        }}
        
        .times-title {{
            color: #00e47c;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 14px;
        }}
        
        .times-list {{
            color: #ffffff;
            font-size: 14px;
            line-height: 1.6;
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
            <div class="medication">({product_name})</div>
        </div>
        
        <div class="details">
            <div class="detail-row">
                <span class="detail-label">Frequency:</span>
                <span class="detail-value">{reminder_details['frequency']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Start Date:</span>
                <span class="detail-value">{reminder_details['start_date']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">End Date:</span>
                <span class="detail-value">{reminder_details['end_date']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Duration:</span>
                <span class="detail-value">{reminder_details['duration']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Total Reminders:</span>
                <span class="detail-value">{reminder_details['total_reminders']}</span>
            </div>
            
            <div class="times-section">
                <div class="times-title">⏰ Reminder Times:</div>
                <div class="times-list">
                    {times_html_list}
                </div>
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
        // Device detection and instructions
        function showDeviceInstructions() {{
            const userAgent = navigator.userAgent;
            
            if (/iPhone|iPad|iPod/i.test(userAgent)) {{
                document.querySelector('.ios-instructions').style.display = 'block';
            }} else if (/Android/i.test(userAgent)) {{
                document.querySelector('.android-instructions').style.display = 'block';
            }}
        }}
        
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
        
        window.addEventListener('load', function() {{
            showDeviceInstructions();
            handleMobileDownload();
        }});
    </script>
</body>
</html>
"""
    return html_content

def upload_web_page_to_s3(html_content, page_id):
    """Upload HTML page to S3 and return public URL"""
    if not AWS_CONFIGURED:
        return None
        
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

def create_reminder_image(pet_name, product_name, reminder_details, qr_code_bytes):
    """Create a professional business card style reminder image with cloud-compatible fonts"""
    
    # Business card dimensions (landscape orientation for sharing)
    width, height = 1200, 800
    
    # Colors matching your web design
    bg_color = (8, 49, 42)  # #08312a
    accent_color = (0, 228, 124)  # #00e47c
    text_color = (255, 255, 255)  # white
    light_accent = (0, 228, 124, 40)  # Semi-transparent accent
    
    # Create image with high quality
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Get fallback fonts with better sizing for cloud deployment
    try:
        large_font = get_fallback_font(48)
        title_font = get_fallback_font(32)
        subtitle_font = get_fallback_font(24)
        detail_font = get_fallback_font(20)
        small_font = get_fallback_font(18)
    except Exception as e:
        # Ultimate fallback - use default font
        base_font = ImageFont.load_default()
        large_font = base_font
        title_font = base_font
        subtitle_font = base_font
        detail_font = base_font
        small_font = base_font
    
    # Draw gradient background effect
    for i in range(height):
        color_factor = i / height
        r = int(8 + (10 - 8) * color_factor)
        g = int(49 + (61 - 49) * color_factor)
        b = int(42 + (51 - 42) * color_factor)
        draw.line([(0, i), (width, i)], fill=(r, g, b))
    
    # Draw decorative border
    border_width = 8
    draw.rectangle([0, 0, width-1, height-1], outline=accent_color, width=border_width)
    
    # Draw BI Logo at top left corner (BIGGER and better handling)
    logo_size = 172  # Increased from 70 to 120
    logo_x = 30
    logo_y = 30
    
    logo_drawn = False
    if os.path.exists("BI-Logo-2.png"):
        try:
            logo_img = Image.open("BI-Logo-2.png")
            # Use thumbnail to maintain aspect ratio properly
            logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            actual_w, actual_h = logo_img.size
            
            # Center the logo in the allocated space if it's smaller
            center_x = logo_x + (logo_size - actual_w) // 2
            center_y = logo_y + (logo_size - actual_h) // 2
            
            if logo_img.mode == 'RGBA':
                img.paste(logo_img, (center_x, center_y), logo_img)
            else:
                img.paste(logo_img, (center_x, center_y))
            logo_drawn = True
        except Exception as e:
            print(f"Error loading BI-Logo-2.png: {e}")
            pass
    
    if not logo_drawn and os.path.exists("BI-Logo.png"):
        try:
            logo_img = Image.open("BI-Logo.png")
            logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            actual_w, actual_h = logo_img.size
            
            center_x = logo_x + (logo_size - actual_w) // 2
            center_y = logo_y + (logo_size - actual_h) // 2
            
            if logo_img.mode == 'RGBA':
                img.paste(logo_img, (center_x, center_y), logo_img)
            else:
                img.paste(logo_img, (center_x, center_y))
            logo_drawn = True
        except Exception as e:
            print(f"Error loading BI-Logo.png: {e}")
            pass
    
    if not logo_drawn:
        # Fallback: draw simple text instead of emoji
        draw.text((logo_x, logo_y), "BI", fill=accent_color, font=large_font)
    
    # LEFT SIDE: Pet info and details (REDUCED SPACING)
    left_section_width = width // 2 - 50
    left_x = 60
    
    # Pet name (move up to reduce space)
    pet_y = 180  # Reduced from higher value
    draw.text((left_x, pet_y), pet_name.upper(), fill=accent_color, font=large_font)
    
    # Product name (tighter spacing)
    product_y = pet_y + 60  # Reduced spacing
    draw.text((left_x, product_y), '('+product_name+')', fill=text_color, font=title_font)
    
    # Details section (tighter spacing) - REPLACE ICONS WITH TEXT SYMBOLS
    details_y = product_y + 60  # Reduced spacing
    
    # Format frequency better
    frequency_text = reminder_details['frequency']
    if reminder_details['frequency'] == 'Custom Days':
        frequency_text = f"Every {reminder_details.get('frequency_value', 'X')} days"
    
    
    details = [
        f" ",
        f"• Frequency: {frequency_text}",
        f"• Starts: {reminder_details['start_date']}",
        f"• Ends: {reminder_details['end_date']}",
        f"• Duration: {reminder_details['duration']}",
        f"• Total: {reminder_details['total_reminders']} reminders",
        f" "
    ]
    
    for i, detail in enumerate(details):
        draw.text((left_x, details_y + i * 25), detail, fill=text_color, font=detail_font)
    
    # Times section (tighter spacing) - REPLACE ICON WITH TEXT
    times_y = details_y + len(details) * 25 + 15  # Reduced spacing
    draw.text((left_x, times_y), "Reminder Timings:", fill=accent_color, font=detail_font)
    
    times_text = " / ".join([f"{t['time']} ({t['label']})" for t in reminder_details['times']])
    draw.text((left_x + 20, times_y + 30), f"{times_text}", fill=text_color, font=small_font)
    
    # Notes if present (tighter spacing) - REPLACE ICON WITH TEXT
    if reminder_details.get('notes') and reminder_details['notes'].strip():
        notes_y = times_y + 80  # Adjusted spacing for new layout
        draw.text((left_x, notes_y), "Additional Notes:", fill=accent_color, font=detail_font)
        
        # Wrap notes text
        notes_text = reminder_details['notes']
        max_chars = 40
        if len(notes_text) > max_chars:
            notes_text = notes_text[:max_chars-3] + "..."
        
        draw.text((left_x + 20, notes_y + 30), notes_text, fill=text_color, font=small_font)
    
    # RIGHT SIDE: QR Code section
    qr_section_x = width // 2 + 50
    qr_section_width = width // 2 - 100
    
    # Load and resize QR code
    qr_img = Image.open(io.BytesIO(qr_code_bytes))
    qr_size = 280  # Slightly larger QR code
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    # Center QR code in right section
    qr_x = qr_section_x + (qr_section_width - qr_size) // 2
    qr_y = (height - qr_size) // 2 - 20  # Better centering
    
    # Draw QR code background (white rounded rectangle)
    qr_bg_padding = 25
    qr_bg_rect = [qr_x - qr_bg_padding, qr_y - qr_bg_padding, 
                  qr_x + qr_size + qr_bg_padding, qr_y + qr_size + qr_bg_padding]
    draw.rectangle(qr_bg_rect, fill=text_color, outline=accent_color, width=3)
    
    # Add QR code
    img.paste(qr_img, (qr_x, qr_y))
    
    # Instruction text below QR code
    instruction_y = qr_y + qr_size + 35
    #instruction_lines = [
    #    "Scan (or) long press using Mobile",
    #    "to add reminder to your Calendar"
    #]
    
    #for i, line in enumerate(instruction_lines):
    #    # Calculate text width for centering (improved method)
    #    try:
    #        bbox = draw.textbbox((0, 0), line, font=detail_font)
    #        line_width = bbox[2] - bbox[0]
    #    except:
    #        # Fallback calculation
    #        line_width = len(line) * 12
    #    
    #    line_x = qr_section_x + (qr_section_width - line_width) // 2
    #    draw.text((line_x, instruction_y + i * 25), line, fill=text_color, font=detail_font)
    
    # Add decorative elements
    # Top right corner accent
    corner_size = 100
    draw.rectangle([width - corner_size, 0, width, corner_size], fill=accent_color)
    
    # Bottom left corner accent
    draw.rectangle([0, height - corner_size, corner_size, height], fill=accent_color)
    
    return img

def generate_content(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes):
    """Generate all content and save to session state"""
    try:
        # Calculate reminder count
        total_reminders = calculate_reminder_count(start_date, end_date, frequency, frequency_value)
        duration_text = format_duration_text(start_date, end_date, total_reminders, frequency)
        
        calendar_data = create_calendar_reminder(
            pet_name=pet_name,
            product_name=product_name,
            frequency=frequency,
            frequency_value=frequency_value,
            reminder_times=selected_times,
            start_date=start_date,
            end_date=end_date,
            notes=notes
        )
        
        meaningful_id = generate_meaningful_id(pet_name, product_name)
        
        # Create calendar URL (may be None if S3 not configured)
        calendar_url = upload_to_s3(calendar_data, meaningful_id)
        
        reminder_details = {
            'frequency': frequency,
            'frequency_value': frequency_value,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'duration': duration_text,
            'total_reminders': total_reminders,
            'times': selected_times,
            'notes': notes
        }
        
        # Create web page (may be None if S3 not configured)
        web_page_url = None
        if calendar_url:
            html_content = create_web_page_html(pet_name, product_name, calendar_url, reminder_details)
            web_page_url = upload_web_page_to_s3(html_content, meaningful_id)
        
        # Generate QR code (use a fallback URL if web page not available)
        qr_target = web_page_url if web_page_url else f"data:text/plain,{pet_name} - {product_name} Reminder"
        qr_image_bytes = generate_qr_code(qr_target)
        
        # Generate the combined reminder image
        reminder_image = create_reminder_image(pet_name, product_name, reminder_details, qr_image_bytes)
        
        # Convert PIL image to bytes for download
        img_buffer = io.BytesIO()
        reminder_image.save(img_buffer, format='PNG', quality=95, dpi=(300, 300))
        reminder_image_bytes = img_buffer.getvalue()
        
        # Upload reminder image to S3 (optional)
        reminder_image_url = upload_reminder_image_to_s3(reminder_image_bytes, meaningful_id)
        
        # Save everything to session state
        st.session_state.generated_content = {
            'meaningful_id': meaningful_id,
            'reminder_image_bytes': reminder_image_bytes,
            'qr_image_bytes': qr_image_bytes,
            'calendar_data': calendar_data,
            'web_page_url': web_page_url,
            'calendar_url': calendar_url,
            'reminder_image_url': reminder_image_url,
            'reminder_details': reminder_details,
            'pet_name': pet_name,
            'product_name': product_name
        }
        st.session_state.content_generated = True
        return True
        
    except Exception as e:
        st.error(f"Error generating content: {str(e)}")
        return False

def display_generated_content():
    """Display the generated content from session state"""
    if not st.session_state.content_generated or not st.session_state.generated_content:
        return
    
    content = st.session_state.generated_content
    
    # Display reminder card
    st.image(content['reminder_image_bytes'], use_container_width=True)
    
    with st.expander("📥 Download Options"):
        # Download reminder Card with QR code
        st.download_button(
            label="🖼️ Download Reminder Card (with QR Code)",
            data=content['reminder_image_bytes'],
            file_name=f"{content['meaningful_id']}_reminder_image.png",
            mime="image/png",
            key="download_reminder_card"
        )
        
        st.download_button(
            label="📥 Download QR Code Only",
            data=content['qr_image_bytes'],
            file_name=f"{content['meaningful_id']}_qr.png",
            mime="image/png",
            key="download_qr_only"
        )
        
        st.download_button(
            label="📅 Download Calendar File", 
            data=content['calendar_data'],
            file_name=f"{content['meaningful_id']}.ics",
            mime="text/calendar",
            key="download_calendar"
        )
    
    # NEW EMAIL SECTION
    with st.expander("📧 Email Reminder Card"):
        if not EMAIL_USER or not EMAIL_PASSWORD:
            st.warning("⚠️ Email configuration not set. Please configure SMTP settings in environment variables.")
            st.info("""
            **Required Environment Variables:**
            - `EMAIL_USER`: Your email address
            - `EMAIL_PASSWORD`: Your email app password
            - `SMTP_SERVER`: SMTP server (default: smtp.gmail.com)
            - `SMTP_PORT`: SMTP port (default: 587)
            """)
        else:
            recipient_email = st.text_input(
                "Recipient Email Address",
                placeholder="example@email.com",
                key="recipient_email"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📧 Send Email", type="primary", key="send_email_btn"):
                    if recipient_email and validate_email(recipient_email):
                        with st.spinner("Sending email..."):
                            success, message = send_email_with_attachment(
                                recipient_email=recipient_email,
                                pet_name=content['pet_name'],
                                product_name=content['product_name'],
                                reminder_image_bytes=content['reminder_image_bytes'],
                                calendar_data=content['calendar_data'],
                                reminder_details=content['reminder_details']
                            )
                            
                            if success:
                                st.success(f"✅ {message}")
                            else:
                                st.error(f"❌ {message}")
                    elif not recipient_email:
                        st.warning("⚠️ Please enter recipient email address")
                    else:
                        st.warning("⚠️ Please enter a valid email address")
            
            with col2:
                #if st.button("📧 Send to Multiple", key="send_multiple_btn"):
                    st.text("")
                    
            # Multiple email addresses input
            if st.session_state.get('send_multiple_btn', False):
                multiple_emails = st.text_area(
                    "Multiple Email Addresses (comma-separated)",
                    placeholder="email1@example.com, email2@example.com, email3@example.com",
                    key="multiple_emails"
                )
                
                if st.button("📧 Send to All", type="primary", key="send_all_btn"):
                    if multiple_emails:
                        email_list = [email.strip() for email in multiple_emails.split(',') if email.strip()]
                        valid_emails = [email for email in email_list if validate_email(email)]
                        invalid_emails = [email for email in email_list if not validate_email(email)]
                        
                        if invalid_emails:
                            st.warning(f"⚠️ Invalid email addresses: {', '.join(invalid_emails)}")
                        
                        if valid_emails:
                            with st.spinner(f"Sending emails to {len(valid_emails)} recipients..."):
                                sent_count = 0
                                failed_count = 0
                                
                                for email in valid_emails:
                                    success, message = send_email_with_attachment(
                                        recipient_email=email,
                                        pet_name=content['pet_name'],
                                        product_name=content['product_name'],
                                        reminder_image_bytes=content['reminder_image_bytes'],
                                        calendar_data=content['calendar_data'],
                                        reminder_details=content['reminder_details']
                                    )
                                    
                                    if success:
                                        sent_count += 1
                                    else:
                                        failed_count += 1
                                        st.error(f"❌ Failed to send to {email}: {message}")
                                
                                if sent_count > 0:
                                    st.success(f"✅ Successfully sent to {sent_count} recipients!")
                                if failed_count > 0:
                                    st.error(f"❌ Failed to send to {failed_count} recipients")
                    else:
                        st.warning("⚠️ Please enter at least one email address")
    
    with st.expander("🔗 URLs"):
        if content['web_page_url']:
            st.write(f"**QR Web Page URL:** {content['web_page_url']}")
        else:
            st.write("**QR Web Page URL:** ❌ S3 not configured")
            
        if content['calendar_url']:
            st.write(f"**Calendar File URL:** {content['calendar_url']}")
        else:
            st.write("**Calendar File URL:** ❌ S3 not configured")
            
        if content['reminder_image_url']:
            st.write(f"**Reminder Card URL:** {content['reminder_image_url']}")
        elif AWS_CONFIGURED:
            st.write("**Reminder Card URL:** ❌ Upload failed")
        else:
            st.write("**Reminder Card URL:** ❌ S3 not configured")
            
    with st.expander("📋 Reminder Summary"):
        details = content['reminder_details']
        st.write(f"**Pet:** {content['pet_name']}")
        st.write(f"**Product:** {content['product_name']}")
        st.write(f"**Start Date:** {details['start_date']}")
        st.write(f"**End Date:** {details['end_date']}")
        st.write(f"**Frequency:** {details['frequency']}")
        if details.get('frequency_value'):
            st.write(f"**Every:** {details['frequency_value']} days")
        st.write(f"**Duration:** {details['duration']}")
        st.write(f"**Total Reminders:** {details['total_reminders']}")
        st.write(f"**Times per day:** {len(details['times'])}")
        for time_info in details['times']:
            st.write(f"  • {time_info['time']} - {time_info['label']}")
        if details.get('notes'):
            st.write(f"**Notes:** {details['notes']}")

def main():
    # Initialize session state
    init_session_state()
    
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
                <h5 style='margin: 0; font-weight: bold; color: #333; font-size: 15px; background-color: #f8f9fa; padding: 15px; border-radius: 8px;'>🐾 Pet Reminder 🐾</h5>
            </div>
            <div style='width: 80px;'></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='display: flex; align-items: center; margin-bottom: 10px; height: 90px;'>
            <div style='width: 80px; height: 80px; display: flex; align-items: center; justify-content: center; background: #f0f0f0; border-radius: 10px; font-size: 35px; margin-right: 20px;'>🐾</div>
            <div style='flex: 1; text-align: center;'>
                <h5 style='margin: 0; font-weight: bold; color: #333;'>🐾 Pet Reminder 🐾</h5>
            </div>
            <div style='width: 80px;'></div>
        </div>
        """, unsafe_allow_html=True)
        
    st.text("") 
    
    # Main form
    col1, spacer, col2 = st.columns([1, 0.2, 1])
    
    with col1:
        st.markdown("<h6 style='text-align: left; font-weight: bold;'>📋 Reminder Details</h6>", unsafe_allow_html=True)
        
        # Use session state values as defaults to maintain form data
        pet_name = st.text_input(
            "Pet Name", 
            placeholder="e.g., Daisy, Luna, Charlie",
            value=get_form_data('pet_name', ''),
            key="pet_name_input"
        )
        
        products = [
            "Broadline",
            "Eurican L4",
            "Heartgard Plus",
            "Metacam", 
            "NexGard",
            "NexGard SPECTRA",
            "NexGard COMBO",
            "Prascend",
            "Previcox",
            "ProZinc",
            "PUREVAX",
            "Rabisin / Imrab",
            "Rabisin / Raboral V-RG",
            "Semintra",
            "SENVELGO",
            "Vetmedin",	    
            "Other"
        ]
        
        saved_product = get_form_data('product_name', products[0])
        product_index = 0
        if saved_product in products:
            product_index = products.index(saved_product)
        
        product_name = st.selectbox(
            "BI Pet Product", 
            products, 
            index=product_index,
            key="product_select"
        )
        
        if product_name == "Other":
            product_name = st.text_input(
                "Custom Product Name", 
                placeholder="Enter product name",
                value=get_form_data('custom_product', ''),
                key="custom_product_input"
            )
        
        # Date Range Selection
        st.markdown("**📅 Reminder Period**")
        col_start, col_end = st.columns(2)
        
        with col_start:
            start_date = st.date_input(
                "Start Date",
                value=get_form_data('start_date', date.today()),
                min_value=date.today(),
                help="First day of reminders",
                key="start_date_input"
            )
        
        with col_end:
            # Default end date to end of current year
            current_year = date.today().year
            default_end_date = date(current_year, 12, 31)
            
            end_date = st.date_input(
                "End Date",
                value=get_form_data('end_date', default_end_date),
                min_value=date.today(),
                help="Last day of reminders",
                key="end_date_input"
            )
        
        # Validate date range
        if end_date < start_date:
            st.error("⚠️ End date must be on or after start date")
        
        frequency_options = ["Daily", "Weekly", "Monthly", "Custom Days"]
        saved_frequency = get_form_data('frequency', 'Daily')
        frequency_index = 0
        if saved_frequency in frequency_options:
            frequency_index = frequency_options.index(saved_frequency)
        
        frequency = st.selectbox(
            "Reminder Frequency", 
            frequency_options, 
            index=frequency_index,
            key="frequency_select"
        )
        
        frequency_value = None
        if frequency == "Custom Days":
            frequency_value = st.number_input(
                "Every X days", 
                min_value=1, 
                max_value=365, 
                value=get_form_data('frequency_value', 7),
                key="frequency_value_input"
            )
        
        # Calculate and show reminder count
        if start_date and end_date and end_date >= start_date:
            reminder_count = calculate_reminder_count(start_date, end_date, frequency, frequency_value)
            duration_text = format_duration_text(start_date, end_date, reminder_count, frequency)
            
            if reminder_count > 0:
                st.info(f"💡 This will create **{reminder_count} reminders** over {duration_text}")
            else:
                st.warning("⚠️ No reminders will be generated with these settings")
        
        # Multiple Times Per Day with Duration Limits
        st.markdown("**⏰ Reminder Times**")
        
        # Define time periods with their valid ranges
        time_periods = {
            "Morning": {
                "default": "08:00",
                "min_hour": 5,   # 5:00 AM
                "max_hour": 11,  # 11:59 AM
                "options": [f"{h:02d}:{m:02d}" for h in range(5, 12) for m in [0, 15, 30, 45]]
            },
            "Afternoon": {
                "default": "14:00", 
                "min_hour": 12,  # 12:00 PM
                "max_hour": 17,  # 5:59 PM
                "options": [f"{h:02d}:{m:02d}" for h in range(12, 18) for m in [0, 15, 30, 45]]
            },
            "Evening": {
                "default": "19:00",
                "min_hour": 18,  # 6:00 PM
                "max_hour": 21,  # 9:59 PM
                "options": [f"{h:02d}:{m:02d}" for h in range(18, 22) for m in [0, 15, 30, 45]]
            },
            "Night": {
                "default": "22:00",
                "min_hour": 22,  # 10:00 PM
                "max_hour": 4,   # 4:59 AM (next day)
                "options": [f"{h:02d}:{m:02d}" for h in range(22, 24) for m in [0, 15, 30, 45]] + 
                          [f"{h:02d}:{m:02d}" for h in range(0, 5) for m in [0, 15, 30, 45]]
            }
        }
        
        # Get saved selected times or use empty list
        saved_times = get_form_data('selected_times', [])
        saved_time_periods = [t['label'] for t in saved_times] if saved_times else []
        
        # Let user select which times they want
        selected_times = []
        
        col_time1, col_time2 = st.columns(2)
        
        with col_time1:
            morning_checked = "Morning" in saved_time_periods
            if st.checkbox("🌅 Morning", key="morning", value=morning_checked):
                morning_options = time_periods["Morning"]["options"]
                # Find saved time or use default
                saved_morning_time = next((t['time'] for t in saved_times if t['label'] == 'Morning'), time_periods["Morning"]["default"])
                default_idx = morning_options.index(saved_morning_time) if saved_morning_time in morning_options else 0
                morning_time = st.selectbox(
                    "Morning time", 
                    options=morning_options,
                    index=default_idx,
                    key="morning_time"
                )
                selected_times.append({"time": morning_time, "label": "Morning"})
                
            afternoon_checked = "Afternoon" in saved_time_periods
            if st.checkbox("☀️ Afternoon", key="afternoon", value=afternoon_checked):
                afternoon_options = time_periods["Afternoon"]["options"]
                saved_afternoon_time = next((t['time'] for t in saved_times if t['label'] == 'Afternoon'), time_periods["Afternoon"]["default"])
                default_idx = afternoon_options.index(saved_afternoon_time) if saved_afternoon_time in afternoon_options else 0
                afternoon_time = st.selectbox(
                    "Afternoon time", 
                    options=afternoon_options,
                    index=default_idx,
                    key="afternoon_time"
                )
                selected_times.append({"time": afternoon_time, "label": "Afternoon"})
        
        with col_time2:
            evening_checked = "Evening" in saved_time_periods
            if st.checkbox("🌇 Evening", key="evening", value=evening_checked):
                evening_options = time_periods["Evening"]["options"]
                saved_evening_time = next((t['time'] for t in saved_times if t['label'] == 'Evening'), time_periods["Evening"]["default"])
                default_idx = evening_options.index(saved_evening_time) if saved_evening_time in evening_options else 0
                evening_time = st.selectbox(
                    "Evening time", 
                    options=evening_options,
                    index=default_idx,
                    key="evening_time"
                )
                selected_times.append({"time": evening_time, "label": "Evening"})
                
            night_checked = "Night" in saved_time_periods
            if st.checkbox("🌙 Night", key="night", value=night_checked):
                night_options = time_periods["Night"]["options"]
                saved_night_time = next((t['time'] for t in saved_times if t['label'] == 'Night'), time_periods["Night"]["default"])
                default_idx = night_options.index(saved_night_time) if saved_night_time in night_options else 0
                night_time = st.selectbox(
                    "Night time", 
                    options=night_options,
                    index=default_idx,
                    key="night_time"
                )
                selected_times.append({"time": night_time, "label": "Night"})
        
        # Option for custom time with validation
        custom_times = [t for t in saved_times if t['label'] not in ['Morning', 'Afternoon', 'Evening', 'Night']]
        custom_checked = len(custom_times) > 0
        
        if st.checkbox("🕐 Custom Time", key="custom", value=custom_checked):
            saved_custom_time = custom_times[0]['time'] if custom_times else "12:00"
            saved_custom_label = custom_times[0]['label'] if custom_times else ""
            
            custom_time = st.time_input(
                "Custom time", 
                value=datetime.strptime(saved_custom_time, "%H:%M").time(), 
                key="custom_time"
            )
            custom_label = st.text_input(
                "Custom label", 
                placeholder="e.g., Lunch, Bedtime", 
                value=saved_custom_label,
                key="custom_label"
            )
            
            if custom_label:
                # Check if custom time overlaps with selected periods
                custom_hour = custom_time.hour
                overlap_warning = ""
                
                for period_name, period_info in time_periods.items():
                    if period_name == "Night":
                        # Special handling for night period (crosses midnight)
                        if custom_hour >= 22 or custom_hour <= 4:
                            overlap_warning = f"⚠️ This time overlaps with Night period"
                    else:
                        if period_info["min_hour"] <= custom_hour <= period_info["max_hour"]:
                            overlap_warning = f"⚠️ This time overlaps with {period_name} period"
                
                if overlap_warning:
                    st.warning(overlap_warning)
                
                selected_times.append({"time": custom_time.strftime("%H:%M"), "label": custom_label})
        
        notes = st.text_area(
            "Additional Notes (Optional)", 
            placeholder="e.g., Give with food, Check for side effects",
            value=get_form_data('notes', ''),
            key="notes_input"
        )
        
        # Show selected times summary
        if selected_times:
            times_summary = ', '.join([f"{t['time']} ({t['label']})" for t in selected_times])
            st.info(f"📅 Selected times: {times_summary}")
        
        # Save form data and generate button
        if st.button("🔄 Generate QR Reminder Card", type="primary", key="generate_btn"):
            if pet_name and product_name and selected_times and end_date >= start_date:
                # Save form data to session state
                save_form_data(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes)
                
                with st.spinner("QR Reminder Card Generation in Progress...."):
                    success = generate_content(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes)
                    if success:
                        st.success("✅ QR Reminder Card generated successfully!")
                        st.rerun()  # Refresh to show generated content
            elif not selected_times:
                st.warning("⚠️ Please select at least one reminder time")
            elif end_date < start_date:
                st.warning("⚠️ End date must be on or after start date")
            else:
                st.warning("⚠️ Please fill in Pet Name and Product Name")
        
        # Add a "Clear Form" button to reset everything
        if st.button("🗑️ Clear Form", key="clear_btn"):
            # Clear session state
            st.session_state.form_data = {}
            st.session_state.generated_content = None
            st.session_state.content_generated = False
            st.rerun()
    with col2:
        
	st.markdown("<h6 style='text-align: left; font-weight: bold;'>📱 QR Reminder Card</h6>", unsafe_allow_html=True)
	
        # Display generated content if available
        if st.session_state.content_generated and st.session_state.generated_content:
            display_generated_content()
	    
        else:
            st.info("⚠️ Please fill the form and click 'Generate QR Reminder Card'")

			
if __name__ == "__main__":
    main()
