import streamlit as st
import qrcode
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta
import io
import base64
from PIL import Image
import uuid
import os

# Configure page
st.set_page_config(
    page_title="Pet Medication Reminder Generator",
    page_icon="🐾",
    layout="wide"
)

def create_calendar_reminder(pet_name, product_name, frequency, frequency_value, reminder_time, end_after_count=None, notes=""):
    """Create ICS calendar content for recurring reminder"""
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Pet Medication Reminder//Boehringer Ingelheim//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    
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
            # Move to next month
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
    alarm.add('trigger', timedelta(hours=-1))  # 1 hour before
    event.add_component(alarm)
    
    cal.add_component(event)
    
    return cal.to_ical().decode('utf-8')

def generate_qr_code(calendar_data):
    """Generate QR code containing calendar data with optional BI icon"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for icon overlay
        box_size=10,
        border=4,
    )
    
    # Create data URL for calendar
    calendar_b64 = base64.b64encode(calendar_data.encode()).decode()
    data_url = f"data:text/calendar;base64,{calendar_b64}"
    
    qr.add_data(data_url)
    qr.make(fit=True)
    
    # Create black QR code image
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to RGB mode to allow color icon overlay
    qr_img = qr_img.convert('RGB')
    
    # Add icon if file exists (preserve original colors)
    if os.path.exists("BI-Icon.png"):
        try:
            # Open icon and preserve original colors
            icon = Image.open("BI-Icon.png")
            
            # Calculate icon size
            qr_width, qr_height = qr_img.size
            icon_size = min(qr_width, qr_height) // 6
            
            # Resize icon maintaining aspect ratio and original colors
            icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            
            # Create a white background for icon
            icon_bg = Image.new('RGB', (icon_size + 16, icon_size + 16), 'white')
            icon_bg_pos = ((icon_bg.size[0] - icon.size[0]) // 2, 
                          (icon_bg.size[1] - icon.size[1]) // 2)
            
            # Paste icon preserving transparency and original colors
            if icon.mode == 'RGBA':
                # Use the alpha channel as mask to preserve transparency and colors
                icon_bg.paste(icon, icon_bg_pos, icon)
            else:
                # Convert icon to RGBA if needed to preserve colors
                icon = icon.convert('RGBA')
                icon_bg.paste(icon, icon_bg_pos, icon)
            
            # Position icon in center of QR code
            icon_pos = ((qr_width - icon_bg.size[0]) // 2, 
                       (qr_height - icon_bg.size[1]) // 2)
            
            # Paste the icon background (with preserved colors) onto QR code
            qr_img.paste(icon_bg, icon_pos)
            
        except Exception as e:
            st.warning(f"Could not add icon: {str(e)}")
    
    # Convert to bytes for display
    img_buffer = io.BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer.getvalue()

def main():
    # Header
    st.markdown("<h3 style='text-align: center; font-weight: bold;'>🐾 Pet Medication Reminder 🐾</h3>", unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar for instructions
    with st.sidebar:
        if os.path.exists("BI-Logo.png"):
            icon_img = Image.open("BI-Logo.png")
            st.image(icon_img, width=100)
        st.text(" ")
        st.text(" ")
        st.text(" ")
        st.header("📱 How it works")
        st.markdown("""
        1. **Fill the form** with reminder details
        2. **Generate QR code** 
        3. **Scan QR Code** with mobile
        4. **Calendar reminder** added automatically
        
        
        
        ### 📋 Supported Devices
        - ✅ iPhone (iOS 11+)
        - ✅ Android phones
        - ✅ MS Outlook Calendar
        """)
        
        # Logo display
        st.text(" ")    
        st.text(" ") 
    
    # Main form with spacing
    col1, spacer, col2 = st.columns([1, 0.2, 1])  # Added spacer column
    
    with col1:
        st.markdown("<h5 style='text-align: left; font-weight: bold;'>📋 Reminder Details</h5>", unsafe_allow_html=True)
        
        # Pet name
        pet_name = st.text_input(
            "Pet Name",
            placeholder="e.g., Max, Luna, Charlie",
            help="The name of the pet receiving medication"
        )
        
        # Product selection
        products = [
            "NexGard (Flea & Tick)",
            "NexGard SPECTRA (Flea, Tick & Worm)",
            "Heartgard Plus (Heartworm)",
            "Metacam (Pain Relief)", 
            "Frontline Plus (Flea & Tick)",
            "Other"
        ]
        
        product_name = st.selectbox(
            "Boehringer Ingelheim Product",
            products,
            help="Select the medication product"
        )
        
        # If "Other" selected, allow custom input
        if product_name == "Other":
            product_name = st.text_input("Custom Product Name", placeholder="Enter product name")
        
        # Frequency selection
        frequency = st.selectbox(
            "Reminder Frequency",
            ["Daily", "Weekly", "Monthly", "Custom Days"],
            index=2,  # Default to Monthly
            help="How often should the reminder repeat?"
        )
        
        # Custom frequency value
        frequency_value = None
        if frequency == "Custom Days":
            frequency_value = st.number_input(
                "Every X days",
                min_value=1,
                max_value=365,
                value=30,
                help="Reminder every X days"
            )
        
        # End condition
        end_type = st.radio(
            "",
            ["Continue indefinitely", "Stop after N occurrences"]
        )
        
        end_after_count = None
        if end_type == "Stop after N occurrences":
            end_after_count = st.number_input(
                "Number of reminders",
                min_value=1,
                max_value=1000,
                value=12,
                help="Total number of reminders before stopping"
            )
            
            # Show calculation for user
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
        
        # Reminder time
        reminder_time = st.time_input(
            "Reminder Time",
            value=datetime.strptime("19:00", "%H:%M").time(),
            help="What time should the reminder appear?"
        )
        
        # Additional notes
        notes = st.text_area(
            "Additional Notes (Optional)",
            placeholder="e.g., Give with food, Check for side effects",
            help="Any special instructions"
        )
        
        # Generate button
        generate_button = st.button("🔄 Generate QR Code", type="primary")
    
    with col2:
        st.markdown("<h5 style='text-align: left; font-weight: bold;'>📱 Generated QR Code</h5>", unsafe_allow_html=True)
        
        if generate_button:
            if pet_name and product_name:
                with st.spinner("Generating QR code..."):
                    try:
                        # Create calendar data
                        calendar_data = create_calendar_reminder(
                            pet_name=pet_name,
                            product_name=product_name,
                            frequency=frequency,
                            frequency_value=frequency_value,
                            reminder_time=reminder_time.strftime("%H:%M"),
                            end_after_count=end_after_count,
                            notes=notes
                        )
                        
                        # Generate QR code
                        qr_image_bytes = generate_qr_code(calendar_data)
                        
                        # Display QR code (smaller and centered)
                        col_qr1, col_qr2, col_qr3 = st.columns([0.5, 1, 0.5])  # Center the QR code
                        with col_qr2:
                            st.image(qr_image_bytes, caption="Scan with phone camera", width=200)  # Reduced from 300 to 200
                        
                        # Show reminder summary
                        st.success("✅ QR Code Generated Successfully!")
                        
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
                        
                        # Download options
                        st.download_button(
                            label="📥 Download QR Code",
                            data=qr_image_bytes,
                            file_name=f"{pet_name}_{product_name}_reminder_qr.png",
                            mime="image/png"
                        )
                        
                        st.download_button(
                            label="📅 Download Calendar File", 
                            data=calendar_data,
                            file_name=f"{pet_name}_{product_name}_reminder.ics",
                            mime="text/calendar"
                        )
                        
                    except Exception as e:
                        st.error(f"Error generating QR code: {str(e)}")
            else:
                st.warning("⚠️ Please fill in Pet Name and Product Name")
        else:
            st.info("👈 Fill the form and click 'Generate QR Code' to create custom reminder QR code")
    
    # Footer instructions
    st.markdown("---")
    st.markdown("<h5 style='text-align: left; font-weight: bold;'>📱 Usage Instructions</h5>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.text(" ")
        st.markdown("""
        ##### iPhone Users:
        1. 📱 Open Camera app
        2. 📸 Point at QR code
        3. 🔔 Tap notification that appears
        4. 📅 Calendar will open automatically
        5. ✅ Tap "Add" to save reminder
        """)
    
    with col2:
        st.text(" ")
        st.markdown("""
        ##### Android Users:
        1. 📱 Open Camera app or Google Lens
        2. 📸 Point at QR code  
        3. 🔔 Tap the link that appears
        4. 📥 Download the calendar file
        5. 📅 Open with Calendar app
        6. ✅ Import/Add to calendar
        """)

if __name__ == "__main__":
    main()
