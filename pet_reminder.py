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

# Configure page
st.set_page_config(
    page_title="Pet Reminder",
    page_icon="🐾",
    layout="wide"
)

# AWS Configuration
if "AWS_REGION" in st.secrets:
    AWS_REGION = st.secrets["AWS_REGION"]
    S3_BUCKET = st.secrets["S3_BUCKET_NAME"]
    aws_access_key_id = st.secrets["AWS_ACCESS_KEY_ID"]
    aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"]
    SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(st.secrets.get("SMTP_PORT", "587"))
    EMAIL_USER = st.secrets.get("EMAIL_USER", "")
    EMAIL_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "")
else:
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'pet-reminder')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
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
    s3_client.list_buckets()
    AWS_CONFIGURED = True
except Exception as e:
    AWS_CONFIGURED = False
    st.error(f"⚠️ AWS S3 not configured: {str(e)}")

# Initialize session state
def init_session_state():
    if 'pet_counter' not in st.session_state:
        st.session_state.pet_counter = 1
    if 'form_data' not in st.session_state:
        st.session_state.form_data = {}
    if 'generated_content' not in st.session_state:
        st.session_state.generated_content = None
    if 'content_generated' not in st.session_state:
        st.session_state.content_generated = False

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def send_email_with_attachment(recipient_email, pet_name, product_name, reminder_image_bytes, calendar_data, reminder_details):
    """Send email with QR code as attachment (Gmail-compatible)"""
    try:
        if not EMAIL_USER or not EMAIL_PASSWORD:
            return False, "Email configuration not set."
        
        web_page_url = st.session_state.generated_content.get('web_page_url', f"https://example.com/reminder/{pet_name}_{product_name}")
        
        msg = MIMEMultipart('related')
        msg['From'] = EMAIL_USER
        msg['To'] = recipient_email
        msg['Subject'] = f"🐾 Pet QR Reminder Card - {pet_name} ({product_name}) 🐾"
        
        # Gmail-compatible HTML without base64 images
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .email-container {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 3px solid #00e47c;
        }}
        .header h1 {{
            color: #08312a;
            margin: 0;
            font-size: 28px;
        }}
        .qr-section {{
            text-align: center;
            margin: 30px 0;
            padding: 25px;
            background: linear-gradient(135deg, #f8f9fa, #e9ecef);
            border-radius: 15px;
            border: 2px solid #00e47c;
        }}
        .qr-section h2 {{
            color: #08312a;
            margin-bottom: 15px;
            font-size: 22px;
        }}
        .qr-link {{
            margin: 20px 0;
            font-size: 18px;
        }}
        .qr-link a {{
            color: #007bff;
            text-decoration: none;
            font-weight: 600;
            background: #e3f2fd;
            padding: 15px 25px;
            border-radius: 8px;
            display: inline-block;
        }}
        .details-section {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
            margin: 25px 0;
        }}
        .detail-item {{
            margin: 8px 0;
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e9ecef;
        }}
        .detail-label {{
            font-weight: 600;
            color: #08312a;
        }}
        .times-section {{
            background: #e8f5e8;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }}
        .attachment-note {{
            background: #d1ecf1;
            border: 1px solid #bee5eb;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>🐾 Pet QR Reminder Card 🐾</h1>
            <p>Schedule for <strong>{pet_name} ({product_name})</strong></p>
        </div>
        
        <div class="qr-section">
            <h2>📱 Access Your Reminder</h2>
            <div class="qr-link">
                <a href="{web_page_url}">🔗 Click here to access your QR code and calendar</a>
            </div>
            <p><em>The QR code and full reminder card are attached to this email</em></p>
        </div>
        
        <div class="details-section">
            <h3>📋 Reminder Details</h3>
            <div class="detail-item">
                <span class="detail-label">Pet Name:</span>
                <span>{pet_name}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Product:</span>
                <span>{product_name}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Start Date:</span>
                <span>{reminder_details['start_date']}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">End Date:</span>
                <span>{reminder_details['end_date']}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Frequency:</span>
                <span>{reminder_details['frequency']}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Duration:</span>
                <span>{reminder_details['duration']}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Total Reminders:</span>
                <span>{reminder_details['total_reminders']}</span>
            </div>
            
            <div class="times-section">
                <strong>⏰ Reminder Times:</strong><br>
                {"<br>".join([f"• {time_info['time']} - {time_info['label']}" for time_info in reminder_details['times']])}
            </div>
            
            {f'<div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 15px 0;"><strong>📝 Notes:</strong><br>{reminder_details["notes"]}</div>' if reminder_details.get('notes') and reminder_details['notes'].strip() else ''}
        </div>
        
        <div class="attachment-note">
            <strong>📎 Attachments Included:</strong><br>
            • Full Reminder Card with QR Code (PNG)<br>
            • Calendar File for your calendar app (.ics)
        </div>
    </div>
</body>
</html>
        """
        
        # Plain text version
        text_body = f"""
🐾 Pet Reminder Card - {pet_name} ({product_name})

🔗 Access Link: {web_page_url}

📋 Reminder Details:
• Pet: {pet_name}
• Product: {product_name}
• Frequency: {reminder_details['frequency']}
• Start: {reminder_details['start_date']}
• End: {reminder_details['end_date']}
• Duration: {reminder_details['duration']}
• Total Reminders: {reminder_details['total_reminders']}

⏰ Times: {" / ".join([f"{t['time']} ({t['label']})" for t in reminder_details['times']])}
{f"📝 Notes: {reminder_details['notes']}" if reminder_details.get('notes') else ""}

📎 Check attached files:
- Reminder card image
- Calendar file (.ics)
        """
        
        # Create message structure
        msg_alternative = MIMEMultipart('alternative')
        msg_alternative.attach(MIMEText(text_body, 'plain'))
        msg_alternative.attach(MIMEText(html_body, 'html'))
        msg.attach(msg_alternative)
        
        # Attach reminder card
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
        server.sendmail(EMAIL_USER, recipient_email, msg.as_string())
        server.quit()
        
        return True, "Email sent successfully!"
        
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def save_form_data(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes):
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
    return st.session_state.form_data.get(key, default)

def calculate_reminder_count(start_date, end_date, frequency, frequency_value=None):
    if end_date < start_date:
        return 0
    
    total_days = (end_date - start_date).days + 1
    
    if frequency == "Daily":
        return total_days
    elif frequency == "Weekly":
        return math.ceil(total_days / 7)
    elif frequency == "Monthly":
        months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        if end_date.day >= start_date.day:
            months += 1
        return max(1, months)
    elif frequency == "Custom Days" and frequency_value:
        return math.ceil(total_days / frequency_value)
    
    return 0

def format_duration_text(start_date, end_date, reminder_count, frequency):
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

def get_font(size):
    """Get system font with fallback"""
    font_paths = [
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Arial.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    
    return ImageFont.load_default()

def get_next_sequence_number():
    if not AWS_CONFIGURED:
        if 'pet_counter' not in st.session_state:
            st.session_state.pet_counter = 1
        else:
            st.session_state.pet_counter += 1
        return st.session_state.pet_counter
    
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key='system/counter.txt')
        current_count = int(response['Body'].read().decode('utf-8'))
    except:
        current_count = 0
    
    next_count = current_count + 1
    
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key='system/counter.txt',
            Body=str(next_count).encode('utf-8'),
            ContentType='text/plain'
        )
    except:
        pass
    
    return next_count
	
def generate_meaningful_id(pet_name, product_name):
    current_count = get_next_sequence_number()
    clean_pet = ''.join(c for c in pet_name if c.isalnum())[:10]
    clean_product = ''.join(c for c in product_name.split('(')[0] if c.isalnum())[:10]
    return f"QR{current_count:04d}_{clean_pet}_{clean_product}"

def create_calendar_reminder(pet_name, product_name, frequency, frequency_value, reminder_times, start_date, end_date, notes=""):
    reminder_count = calculate_reminder_count(start_date, end_date, frequency, frequency_value)
    
    cal = Calendar()
    cal.add('prodid', '-//Pet Medication Reminder//Boehringer Ingelheim//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    
    for i, time_info in enumerate(reminder_times):
        time_str = time_info['time']
        time_label = time_info['label']
        
        event = Event()
        event_title = f"{pet_name} - {product_name}"
        if len(reminder_times) > 1:
            event_title += f" ({time_label})"
        
        event.add('summary', event_title)
        event.add('description', f"Medication reminder: {product_name}\nPet: {pet_name}\nTime: {time_label}\n{notes}")
        
        start_time = datetime.combine(start_date, datetime.strptime(time_str, "%H:%M").time())
        
        event.add('dtstart', start_time)
        event.add('dtend', start_time + timedelta(hours=1))
        event.add('dtstamp', datetime.now())
        event.add('uid', str(uuid.uuid4()))
        
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
        
        if reminder_count > 0:
            rrule['count'] = reminder_count
        
        event.add('rrule', rrule)
        
        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('description', f'Time to give {product_name} to {pet_name}! ({time_label})')
        alarm.add('trigger', timedelta(minutes=-15))
        event.add_component(alarm)
        
        cal.add_component(event)
    
    return cal.to_ical().decode('utf-8')

def upload_to_s3(calendar_data, file_id):
    if not AWS_CONFIGURED:
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
    except:
        return None

def upload_reminder_image_to_s3(image_bytes, file_id):
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
    except:
        return None

def create_web_page_html(pet_name, product_name, calendar_url, reminder_details):
    logo_data_url = ""
    if os.path.exists("BI-Logo-2.png"):
        try:
            with open("BI-Logo-2.png", "rb") as f:
                logo_bytes = f.read()
                logo_b64 = base64.b64encode(logo_bytes).decode()
                logo_data_url = f"data:image/png;base64,{logo_b64}"
        except:
            pass
    
    times_html_list = "<br>".join([f"• {t['time']} - {t['label']}" for t in reminder_details['times']])
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐾 {pet_name.upper()} - Medication Reminder</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
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
        
        .logo-container {{
            width: 100px;
            height: 100px;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .logo-img {{ max-width: 100px; max-height: 100px; object-fit: contain; }}
        .logo-fallback {{ font-size: 40px; color: #00e47c; }}
        
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
        
        .detail-label {{ color: #00e47c; font-weight: 600; }}
        .detail-value {{ color: #ffffff; flex: 1; text-align: right; }}
        
        .times-section {{
            background: rgba(0, 228, 124, 0.05);
            border: 1px dashed #00e47c;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            text-align: left;
        }}
        
        .times-title {{ color: #00e47c; font-weight: 600; margin-bottom: 8px; font-size: 14px; }}
        .times-list {{ color: #ffffff; font-size: 14px; line-height: 1.6; }}
        
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
        
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0, 228, 124, 0.3); }}
        .btn-primary {{ background: linear-gradient(45deg, #00e47c, #00b85c); color: #08312a; font-weight: 700; }}
        
        @media (max-width: 480px) {{
            body {{ padding: 15px; }}
            .container {{ padding: 25px 20px; }}
            .pet-name {{ font-size: 26px; }}
            .medication {{ font-size: 18px; }}
            .btn {{ padding: 16px; font-size: 15px; }}
            .logo-container {{ width: 80px; height: 80px; }}
            .logo-img {{ max-width: 80px; max-height: 80px; }}
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
                <div class="times-list">{times_html_list}</div>
            </div>
            
            {f'<div style="background: rgba(0, 228, 124, 0.05); border: 1px dashed #00e47c; border-radius: 10px; padding: 15px; margin-top: 15px; text-align: left;"><div style="color: #00e47c; font-weight: 600; margin-bottom: 8px; font-size: 14px;">📝 Notes:</div><div style="color: #ffffff; font-size: 14px; line-height: 1.4; opacity: 0.9;">{reminder_details["notes"]}</div></div>' if reminder_details.get('notes') and reminder_details['notes'].strip() else ''}
        </div>
        
        <a href="{calendar_url}" class="btn btn-primary" download="{pet_name.upper()}_{product_name}_reminder.ics">
            📅 Add to My Calendar
        </a>          
    </div>
</body>
</html>
"""
    return html_content

def upload_web_page_to_s3(html_content, page_id):
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
    except:
        return None

def generate_qr_code(web_page_url):
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=6,
    )
    
    qr.add_data(web_page_url)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="#00e47c")
    
    img_buffer = io.BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer.getvalue()

def create_reminder_image(pet_name, product_name, reminder_details, qr_code_bytes):
    """Create professional reminder card"""
    width, height = 1200, 800
    bg_color = (8, 49, 42)
    accent_color = (0, 228, 124)
    text_color = (255, 255, 255)
    
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Get fonts
    large_font = get_font(48)
    title_font = get_font(32)
    detail_font = get_font(20)
    small_font = get_font(18)
    
    # Gradient background
    for i in range(height):
        color_factor = i / height
        r = int(8 + (10 - 8) * color_factor)
        g = int(49 + (61 - 49) * color_factor)
        b = int(42 + (51 - 42) * color_factor)
        draw.line([(0, i), (width, i)], fill=(r, g, b))
    
    # Border
    draw.rectangle([0, 0, width-1, height-1], outline=accent_color, width=8)
    
    # Logo
    logo_size = 120
    logo_x, logo_y = 30, 30
    
    if os.path.exists("BI-Logo-2.png"):
        try:
            logo_img = Image.open("BI-Logo-2.png")
            logo_img.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            actual_w, actual_h = logo_img.size
            center_x = logo_x + (logo_size - actual_w) // 2
            center_y = logo_y + (logo_size - actual_h) // 2
            
            if logo_img.mode == 'RGBA':
                img.paste(logo_img, (center_x, center_y), logo_img)
            else:
                img.paste(logo_img, (center_x, center_y))
        except:
            draw.text((logo_x, logo_y), "BI", fill=accent_color, font=large_font)
    else:
        draw.text((logo_x, logo_y), "BI", fill=accent_color, font=large_font)
    
    # Left section - Pet info
    left_x = 60
    pet_y = 180
    draw.text((left_x, pet_y), pet_name.upper(), fill=accent_color, font=large_font)
    
    product_y = pet_y + 60
    draw.text((left_x, product_y), f'({product_name})', fill=text_color, font=title_font)
    
    # Details
    details_y = product_y + 60
    frequency_text = reminder_details['frequency']
    if reminder_details['frequency'] == 'Custom Days':
        frequency_text = f"Every {reminder_details.get('frequency_value', 'X')} days"
    
    details = [
        f"• Frequency: {frequency_text}",
        f"• Starts: {reminder_details['start_date']}",
        f"• Ends: {reminder_details['end_date']}",
        f"• Duration: {reminder_details['duration']}",
        f"• Total: {reminder_details['total_reminders']} reminders",
    ]
    
    for i, detail in enumerate(details):
        draw.text((left_x, details_y + i * 25), detail, fill=text_color, font=detail_font)
    
    # Times
    times_y = details_y + len(details) * 25 + 15
    draw.text((left_x, times_y), "Reminder Times:", fill=accent_color, font=detail_font)
    
    times_text = " / ".join([f"{t['time']} ({t['label']})" for t in reminder_details['times']])
    draw.text((left_x + 20, times_y + 30), times_text, fill=text_color, font=small_font)
    
    # Notes if present
    if reminder_details.get('notes') and reminder_details['notes'].strip():
        notes_y = times_y + 80
        draw.text((left_x, notes_y), "Notes:", fill=accent_color, font=detail_font)
        
        notes_text = reminder_details['notes']
        if len(notes_text) > 40:
            notes_text = notes_text[:37] + "..."
        
        draw.text((left_x + 20, notes_y + 30), notes_text, fill=text_color, font=small_font)
    
    # Right section - QR Code
    qr_section_x = width // 2 + 50
    qr_section_width = width // 2 - 100
    
    qr_img = Image.open(io.BytesIO(qr_code_bytes))
    qr_size = 280
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    qr_x = qr_section_x + (qr_section_width - qr_size) // 2
    qr_y = (height - qr_size) // 2 - 20
    
    # QR background
    qr_bg_padding = 25
    qr_bg_rect = [qr_x - qr_bg_padding, qr_y - qr_bg_padding, 
                  qr_x + qr_size + qr_bg_padding, qr_y + qr_size + qr_bg_padding]
    draw.rectangle(qr_bg_rect, fill=text_color, outline=accent_color, width=3)
    
    img.paste(qr_img, (qr_x, qr_y))
    
    # Instructions
    instruction_y = qr_y + qr_size + 35
    instruction_lines = [
        "Scan or long press with mobile",
        "to add reminder to calendar"
    ]
    
    for i, line in enumerate(instruction_lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=detail_font)
            line_width = bbox[2] - bbox[0]
        except:
            line_width = len(line) * 12
        
        line_x = qr_section_x + (qr_section_width - line_width) // 2
        draw.text((line_x, instruction_y + i * 25), line, fill=text_color, font=detail_font)
    
    # Decorative corners
    corner_size = 100
    draw.rectangle([width - corner_size, 0, width, corner_size], fill=accent_color)
    draw.rectangle([0, height - corner_size, corner_size, height], fill=accent_color)
    
    return img

def generate_content(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes):
    """Generate all content and save to session state"""
    try:
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
        
        web_page_url = None
        if calendar_url:
            html_content = create_web_page_html(pet_name, product_name, calendar_url, reminder_details)
            web_page_url = upload_web_page_to_s3(html_content, meaningful_id)
        
        qr_target = web_page_url if web_page_url else f"data:text/plain,{pet_name} - {product_name} Reminder"
        qr_image_bytes = generate_qr_code(qr_target)
        
        reminder_image = create_reminder_image(pet_name, product_name, reminder_details, qr_image_bytes)
        
        img_buffer = io.BytesIO()
        reminder_image.save(img_buffer, format='PNG', quality=95, dpi=(300, 300))
        reminder_image_bytes = img_buffer.getvalue()
        
        reminder_image_url = upload_reminder_image_to_s3(reminder_image_bytes, meaningful_id)
        
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
    
    st.image(content['reminder_image_bytes'], use_container_width=True)
    
    with st.expander("📥 Download Options"):
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
    
    # Email section
    with st.expander("📧 Email Reminder Card"):
        if not EMAIL_USER or not EMAIL_PASSWORD:
            st.warning("⚠️ Email configuration not set.")
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
                if st.button("📧 Send to Multiple", key="send_multiple_btn"):
                    st.info("💡 Copy and paste multiple email addresses separated by commas")
                    
            if st.session_state.get('send_multiple_btn', False):
                multiple_emails = st.text_area(
                    "Multiple Email Addresses (comma-separated)",
                    placeholder="email1@example.com, email2@example.com",
                    key="multiple_emails"
                )
                
                if st.button("📧 Send to All", type="primary", key="send_all_btn"):
                    if multiple_emails:
                        email_list = [email.strip() for email in multiple_emails.split(',') if email.strip()]
                        valid_emails = [email for email in email_list if validate_email(email)]
                        invalid_emails = [email for email in email_list if not validate_email(email)]
                        
                        if invalid_emails:
                            st.warning(f"⚠️ Invalid emails: {', '.join(invalid_emails)}")
                        
                        if valid_emails:
                            with st.spinner(f"Sending to {len(valid_emails)} recipients..."):
                                sent_count = 0
                                
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
                                        st.error(f"❌ Failed: {email}")
                                
                                if sent_count > 0:
                                    st.success(f"✅ Sent to {sent_count} recipients!")
                    else:
                        st.warning("⚠️ Please enter email addresses")
    
    with st.expander("🔗 URLs"):
        if content['web_page_url']:
            st.write(f"**QR Web Page:** {content['web_page_url']}")
        else:
            st.write("**QR Web Page:** ❌ S3 not configured")
            
        if content['calendar_url']:
            st.write(f"**Calendar File:** {content['calendar_url']}")
        else:
            st.write("**Calendar File:** ❌ S3 not configured")
            
    with st.expander("📋 Summary"):
        details = content['reminder_details']
        st.write(f"**Pet:** {content['pet_name']}")
        st.write(f"**Product:** {content['product_name']}")
        st.write(f"**Start:** {details['start_date']}")
        st.write(f"**End:** {details['end_date']}")
        st.write(f"**Frequency:** {details['frequency']}")
        st.write(f"**Duration:** {details['duration']}")
        st.write(f"**Total Reminders:** {details['total_reminders']}")
        st.write(f"**Times:** {len(details['times'])} per day")
        for time_info in details['times']:
            st.write(f"  • {time_info['time']} - {time_info['label']}")
        if details.get('notes'):
            st.write(f"**Notes:** {details['notes']}")

def main():
    init_session_state()
    
    # Mobile CSS
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
    
    .css-1d391kg { display: none; }
    </style>
    """, unsafe_allow_html=True)
    
    # Header with logo
    if os.path.exists("BI-Logo.png"):
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
        st.markdown("# 🐾 Pet Reminder 🐾")
    
    col1, spacer, col2 = st.columns([1, 0.2, 1])
    
    with col1:
        st.markdown("### 📋 Reminder Details")
        
        pet_name = st.text_input(
            "Pet Name", 
            placeholder="e.g., Max, Luna, Charlie",
            value=get_form_data('pet_name', ''),
            key="pet_name_input"
        )
        
        products = [
            "Broadline", "Eurican L4", "Heartgard Plus", "Metacam", 
            "NexGard", "NexGard SPECTRA", "NexGard COMBO", "Prascend",
            "Previcox", "ProZinc", "PUREVAX", "Rabisin / Imrab",
            "Rabisin / Raboral V-RG", "Semintra", "SENVELGO", "Vetmedin", "Other"
        ]
        
        saved_product = get_form_data('product_name', products[0])
        product_index = products.index(saved_product) if saved_product in products else 0
        
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
        
        # Date Range
        st.markdown("**📅 Reminder Period**")
        col_start, col_end = st.columns(2)
        
        with col_start:
            start_date = st.date_input(
                "Start Date",
                value=get_form_data('start_date', date.today()),
                min_value=date.today(),
                key="start_date_input"
            )
        
        with col_end:
            default_end_date = date(date.today().year, 12, 31)
            end_date = st.date_input(
                "End Date",
                value=get_form_data('end_date', default_end_date),
                min_value=date.today(),
                key="end_date_input"
            )
        
        if end_date < start_date:
            st.error("⚠️ End date must be on or after start date")
        
        frequency_options = ["Daily", "Weekly", "Monthly", "Custom Days"]
        saved_frequency = get_form_data('frequency', 'Daily')
        frequency_index = frequency_options.index(saved_frequency) if saved_frequency in frequency_options else 0
        
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
        
        # Show reminder count
        if start_date and end_date and end_date >= start_date:
            reminder_count = calculate_reminder_count(start_date, end_date, frequency, frequency_value)
            duration_text = format_duration_text(start_date, end_date, reminder_count, frequency)
            
            if reminder_count > 0:
                st.info(f"💡 **{reminder_count} reminders** over {duration_text}")
        
        # Time selection
        st.markdown("**⏰ Reminder Times**")
        
        time_periods = {
            "Morning": {
                "default": "08:00",
                "options": [f"{h:02d}:{m:02d}" for h in range(5, 12) for m in [0, 15, 30, 45]]
            },
            "Afternoon": {
                "default": "14:00", 
                "options": [f"{h:02d}:{m:02d}" for h in range(12, 18) for m in [0, 15, 30, 45]]
            },
            "Evening": {
                "default": "19:00",
                "options": [f"{h:02d}:{m:02d}" for h in range(18, 22) for m in [0, 15, 30, 45]]
            },
            "Night": {
                "default": "22:00",
                "options": [f"{h:02d}:{m:02d}" for h in range(22, 24) for m in [0, 15, 30, 45]] + 
                          [f"{h:02d}:{m:02d}" for h in range(0, 5) for m in [0, 15, 30, 45]]
            }
        }
        
        saved_times = get_form_data('selected_times', [])
        saved_time_periods = [t['label'] for t in saved_times] if saved_times else []
        
        selected_times = []
        
        col_time1, col_time2 = st.columns(2)
        
        with col_time1:
            if st.checkbox("🌅 Morning", key="morning", value="Morning" in saved_time_periods):
                morning_options = time_periods["Morning"]["options"]
                saved_morning_time = next((t['time'] for t in saved_times if t['label'] == 'Morning'), time_periods["Morning"]["default"])
                default_idx = morning_options.index(saved_morning_time) if saved_morning_time in morning_options else 0
                morning_time = st.selectbox("Morning time", options=morning_options, index=default_idx, key="morning_time")
                selected_times.append({"time": morning_time, "label": "Morning"})
                
            if st.checkbox("☀️ Afternoon", key="afternoon", value="Afternoon" in saved_time_periods):
                afternoon_options = time_periods["Afternoon"]["options"]
                saved_afternoon_time = next((t['time'] for t in saved_times if t['label'] == 'Afternoon'), time_periods["Afternoon"]["default"])
                default_idx = afternoon_options.index(saved_afternoon_time) if saved_afternoon_time in afternoon_options else 0
                afternoon_time = st.selectbox("Afternoon time", options=afternoon_options, index=default_idx, key="afternoon_time")
                selected_times.append({"time": afternoon_time, "label": "Afternoon"})
        
        with col_time2:
            if st.checkbox("🌇 Evening", key="evening", value="Evening" in saved_time_periods):
                evening_options = time_periods["Evening"]["options"]
                saved_evening_time = next((t['time'] for t in saved_times if t['label'] == 'Evening'), time_periods["Evening"]["default"])
                default_idx = evening_options.index(saved_evening_time) if saved_evening_time in evening_options else 0
                evening_time = st.selectbox("Evening time", options=evening_options, index=default_idx, key="evening_time")
                selected_times.append({"time": evening_time, "label": "Evening"})
                
            if st.checkbox("🌙 Night", key="night", value="Night" in saved_time_periods):
                night_options = time_periods["Night"]["options"]
                saved_night_time = next((t['time'] for t in saved_times if t['label'] == 'Night'), time_periods["Night"]["default"])
                default_idx = night_options.index(saved_night_time) if saved_night_time in night_options else 0
                night_time = st.selectbox("Night time", options=night_options, index=default_idx, key="night_time")
                selected_times.append({"time": night_time, "label": "Night"})
        
        # Custom time
        custom_times = [t for t in saved_times if t['label'] not in ['Morning', 'Afternoon', 'Evening', 'Night']]
        if st.checkbox("🕐 Custom Time", key="custom", value=len(custom_times) > 0):
            saved_custom_time = custom_times[0]['time'] if custom_times else "12:00"
            saved_custom_label = custom_times[0]['label'] if custom_times else ""
            
            custom_time = st.time_input("Custom time", value=datetime.strptime(saved_custom_time, "%H:%M").time(), key="custom_time")
            custom_label = st.text_input("Custom label", placeholder="e.g., Lunch, Bedtime", value=saved_custom_label, key="custom_label")
            
            if custom_label:
                selected_times.append({"time": custom_time.strftime("%H:%M"), "label": custom_label})
        
        notes = st.text_area(
            "Additional Notes (Optional)", 
            placeholder="e.g., Give with food, Check for side effects",
            value=get_form_data('notes', ''),
            key="notes_input"
        )
        
        if selected_times:
            times_summary = ', '.join([f"{t['time']} ({t['label']})" for t in selected_times])
            st.info(f"📅 Selected times: {times_summary}")
        
        if st.button("🔄 Generate QR Reminder Card", type="primary", key="generate_btn"):
            if pet_name and product_name and selected_times and end_date >= start_date:
                save_form_data(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes)
                
                with st.spinner("Generating QR Reminder Card..."):
                    success = generate_content(pet_name, product_name, start_date, end_date, frequency, frequency_value, selected_times, notes)
                    if success:
                        st.success("✅ QR Reminder Card generated!")
                        st.rerun()
            elif not selected_times:
                st.warning("⚠️ Please select at least one reminder time")
            elif end_date < start_date:
                st.warning("⚠️ End date must be on or after start date")
            else:
                st.warning("⚠️ Please fill in Pet Name and Product Name")
        
        if st.button("🗑️ Clear Form", key="clear_btn"):
            st.session_state.form_data = {}
            st.session_state.generated_content = None
            st.session_state.content_generated = False
            st.rerun()
    
    with col2:
        st.markdown("### 📱 QR Reminder Card")
        
        if st.session_state.content_generated and st.session_state.generated_content:
            display_generated_content()
        else:
            st.info("⚠️ Please fill the form and click 'Generate QR Reminder Card'")

if __name__ == "__main__":
    main()
        
