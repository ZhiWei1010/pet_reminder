import streamlit as st
import base64
from io import BytesIO
import qrcode
from urllib.parse import urlencode
from datetime import datetime
import uuid

# ---------- Generate ICS Content ----------
def generate_ics():
    uid = str(uuid.uuid4())
    dtstamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    dtstart = "20250715T090000Z"
    dtend = "20250715T100000Z"
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//YourApp//EN
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:Pet Medicine Reminder
DESCRIPTION:Give Vitamin C
LOCATION:Home
STATUS:CONFIRMED
BEGIN:VALARM
TRIGGER:-PT30M
ACTION:DISPLAY
DESCRIPTION:Reminder to give Vitamin C
END:VALARM
END:VEVENT
END:VCALENDAR"""

# ---------- Generate QR Code ----------
def generate_qr(url: str) -> BytesIO:
    buf = BytesIO()
    qr = qrcode.make(url)
    qr.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------- Handle download trigger ----------
query_params = st.query_params
if "download" in query_params:
    ics_bytes = generate_ics().encode("utf-8")
    b64 = base64.b64encode(ics_bytes).decode()
    href = f'<a href="data:text/calendar;base64,{b64}" download="event.ics">Click here if download doesn’t start automatically</a>'
    st.markdown(href, unsafe_allow_html=True)
    st.markdown("""
        <script>
        window.onload = function(){
            const a = document.querySelector('a');
            if (a) a.click();
        }
        </script>
    """, unsafe_allow_html=True)
    st.stop()

# ---------- Main App ----------
st.title("📅 Pet Reminder Calendar QR Generator")

if "ics_generated" not in st.session_state:
    st.session_state.ics_generated = False

if st.button("📲 Generate QR Code"):
    st.session_state.ics_content = generate_ics()
    st.session_state.ics_generated = True

    # Since you're testing locally
    base_url = "https://pet-reminder-test.streamlit.app"
    download_url = f"{base_url}?{urlencode({'download': '1'})}"
    st.session_state.download_url = download_url

if st.session_state.ics_generated:
    st.download_button(
        label="⬇️ Download .ics file",
        data=st.session_state.ics_content,
        file_name="event.ics",
        mime="text/calendar"
    )

    qr_img = generate_qr(st.session_state.download_url)
    st.image(qr_img, caption="📱 Scan QR to download on your phone")
