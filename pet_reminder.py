import streamlit as st
import qrcode
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta, date, time
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import uuid
import os
import urllib.parse
import hashlib
import boto3
import math
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
    
else:
    # Development: Use environment variables
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'pet-reminder')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')

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

def save_form_data(pet_name, product_name, start_date, dosage, selected_time, notes):
    """Save current form data to session state"""
    st.session_state.form_data = {
        'pet_name': pet_name,
        'product_name': product_name,
        'start_date': start_date,
        'dosage': dosage,
        'selected_time': selected_time,
        'notes': notes
    }

def get_form_data(key, default=None):
    """Get form data from session state"""
    return st.session_state.form_data.get(key, default)

def format_duration_text(start_date, dosage):
    """Format duration text for display"""
    total_days = dosage * 30
    
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

def create_calendar_reminder(pet_name, product_name, dosage, reminder_time, start_date, notes=""):
    
    # Calculate reminder count for RRULE
    reminder_count = dosage
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Pet Medication Reminder//Boehringer Ingelheim//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')

    # Create event
    event = Event()
    event_title = f"{pet_name} - {product_name}"
    
    event.add('summary', event_title)
    event.add('description', f"Nexgard reminder: {product_name}\nPet: {pet_name}\nTime: {reminder_time}\n{notes}")
    
    # Calculate start time using the provided start_date
    start_time = datetime.combine(start_date, datetime.strptime(reminder_time, "%H:%M").time())
    
    event.add('dtstart', start_time)
    event.add('dtend', start_time + timedelta(hours=1))
    event.add('dtstamp', datetime.now())
    event.add('uid', str(uuid.uuid4()))
    
    # Add recurrence rule with count limit
    rrule = {}
    rrule['freq'] = 'monthly'
    
    if reminder_count > 0:
        rrule['count'] = reminder_count
    
    event.add('rrule', rrule)
    
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', f'Time to give {product_name} to {pet_name}!')
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
    times_html_list += f"• {reminder_details['times']}<br>"
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

    details = [
        f" ",
        f"• Frequency: {frequency_text}",
        f"• Starts: {reminder_details['start_date']}",
        f"• Duration: {reminder_details['duration']}",
        f"• Total: {reminder_details['total_reminders']} reminders",
        f" "
    ]
    
    for i, detail in enumerate(details):
        draw.text((left_x, details_y + i * 25), detail, fill=text_color, font=detail_font)
    
    # Times section (tighter spacing) - REPLACE ICON WITH TEXT
    times_y = details_y + len(details) * 25 + 15  # Reduced spacing
    draw.text((left_x, times_y), "Reminder Time:", fill=accent_color, font=detail_font)
    
    times_text = reminder_details['times']
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

def generate_content(pet_name, product_name, start_date, dosage, selected_time, notes):
    """Generate all content and save to session state"""
    try:
        # Calculate reminder count
        duration_text = format_duration_text(start_date, dosage=12)
        
        calendar_data = create_calendar_reminder(
            pet_name=pet_name,
            product_name=product_name,
            dosage=dosage,
            reminder_time=selected_time,
            start_date=start_date,
            notes=notes
        )
        
        meaningful_id = generate_meaningful_id(pet_name, product_name)
        
        # Create calendar URL (may be None if S3 not configured)
        calendar_url = upload_to_s3(calendar_data, meaningful_id)
        
        reminder_details = {
            'frequency': 'Monthly',
            'start_date': start_date.strftime('%Y-%m-%d'),
            'duration': duration_text,
            'total_reminders': dosage,
            'times': selected_time,
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
    if not st.session_state.content_generated or not st.session_state.generated_content:
        return
    
    content = st.session_state.generated_content
    
    # Display reminder card
    st.image(content['reminder_image_bytes'], use_container_width=True)
            
    with st.expander("📋 Reminder Summary"):
        details = content['reminder_details']
        st.write(f"**Pet:** {content['pet_name']}")
        st.write(f"**Product:** {content['product_name']}")
        st.write(f"**Start Date:** {details['start_date']}")
        st.write(f"**Frequency:** {details['frequency']}")
        st.write(f"**Duration:** {details['duration']}")
        st.write(f"**Total Reminders:** {details['total_reminders']}")
        st.write(f"**Reminder Time:** {details['times']}")
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
            "NexGard",
            "NexGard SPECTRA",
            "NexGard COMBO",
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
            dosage = st.number_input(
                "Number of Dosages",
                value = get_form_data('dosage', 12),
                min_value = 12,
                help = "Number of Capsules you have",
                key="number_of_dosage"
            )
        
        # Multiple Times Per Day with Duration Limits
        st.markdown("**⏰ Reminder Time (Optional)**")
        
        # Get saved selected times or use empty list
        saved_times = get_form_data('selected_time', [])
        
        # Option for custom time with validation
        custom_time_data = saved_times[0] if saved_times else None
        custom_checked = custom_time_data is not None

        use_custom_time = st.checkbox("🕐 Custom Time", key="custom", value=custom_checked)

        default_time = default_time = datetime.strptime("12:00", "%H:%M").time()

        # Determine the reminder time
        if use_custom_time:
            custom_time = st.time_input("Select custom time", value=default_time, key="custom_time")
            selected_time = custom_time.strftime("%H:%M")
        else:
            selected_time = default_time.strftime("%H:%M")

        notes = st.text_area(
            "Additional Notes (Optional)", 
            placeholder="e.g., Give with food, Check for side effects",
            value=get_form_data('notes', ''),
            key="notes_input"
        )
        
        st.info(f"📅 Reminder Frequency: **Monthly** \t\t 🕛 Reminder time: **{selected_time}**")
        
        # Save form data and generate button
        if st.button("🔄 Submit", type="primary", key="submit_btn"):
            if pet_name and product_name:
                # Save form data to session state
                save_form_data(pet_name, product_name, start_date, dosage, selected_time, notes)
                
                with st.spinner("Submitting ...."):
                    success = generate_content(pet_name, product_name, start_date, dosage, selected_time, notes)
                    if success:
                        st.success("✅ Calendar reminder generated successfully!")
                        st.rerun()  # Refresh to show generated content
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
