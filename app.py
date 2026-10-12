import smtplib
from email.message import EmailMessage

from google import genai
from google.genai import types
import streamlit as st

from prompt import (
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
    SUMMARY_REQUEST_PROMPT,
)


# ---------------- CONFIGURATION ----------------

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GMAIL_ADDRESS = st.secrets["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = st.secrets["GMAIL_APP_PASSWORD"]

MODEL_NAME = "gemini-3.1-flash-lite"


# ---------------- CLIENT ----------------

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)


gemini_client = get_gemini_client()


# ---------------- EMAIL FUNCTION ----------------

def send_email(to_email, user_name, summary):
    try:
        if not summary or summary.startswith("Oops!"):
            return False, (
                "Nutrition summary generate aagala. "
                "Gemini quota/API error irukkalaam. Please try again later."
            )

        msg = EmailMessage()
        msg["Subject"] = "Your Macrosnap Nutrition Summary"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to_email

        msg.set_content(
            f"Hi {user_name},\n\n"
            "Here is your Macrosnap nutrition summary:\n\n"
            f"{summary}\n\n"
            "Keep tracking your meals with Macrosnap!\n"
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        return True, "Email sent successfully!"

    except Exception as error:
        print("EMAIL ERROR:", repr(error))
        return False, f"{type(error).__name__}: {error}"


# ---------------- CHAT FUNCTIONS ----------------

def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    message = {
        "role": role,
        "kind": kind,
        "content": content,
    }
    st.session_state.messages.append(message)
    render_message(message)


def ask_gemini(parts):
    try:
        response = st.session_state.chat.send_message(parts)
        return response.text or "Gemini returned an empty response."

    except Exception as error:
        print("GEMINI ERROR:", repr(error))
        return (
            "Oops! Something went wrong while processing your request. "
            "Please try again later. Check your Gemini API quota if the "
            "problem continues."
        )


# ---------------- ONBOARDING ----------------

if "onboarded" not in st.session_state:
    st.title("Macrosnap 🥗")
    st.caption("Snap it. Track it. Send your nutrition summary to Gmail.")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        email_address = st.text_input(
            "Your email address",
            placeholder="you@example.com",
        )

        submit_button = st.form_submit_button("Let's go!")

    if submit_button:
        if not name.strip() or not email_address.strip():
            st.warning("Please enter both your name and email address.")

        elif "@" not in email_address or "." not in email_address.split("@")[-1]:
            st.warning("Please enter a valid email address.")

        else:
            st.session_state.name = name.strip()
            st.session_state.email_address = email_address.strip()

            st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                ),
            )

            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()

    st.stop()


# ---------------- MAIN CHAT INTERFACE ----------------

header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center",
)

with header_col:
    st.title("Macrosnap 🥗")

with button_col:
    send_disabled = not any(
        message["role"] == "assistant"
        and message["kind"] == "text"
        for message in st.session_state.messages
    )

    if st.button(
        "📧 Send to Gmail",
        disabled=send_disabled,
        use_container_width=True,
    ):
        with st.spinner("Preparing your nutrition summary..."):
            summary = ask_gemini([SUMMARY_REQUEST_PROMPT])

        if summary.startswith("Oops!"):
            st.error(summary)
        else:
            with st.spinner("Sending email..."):
                success, info = send_email(
                    st.session_state.email_address,
                    st.session_state.name,
                    summary,
                )

            if success:
                st.success("Sent! Check your Gmail inbox 📧")
            else:
                st.error(f"Email failed: {info}")

st.caption(
    f"Logged in as {st.session_state.name} | "
    f"Email: {st.session_state.email_address}"
)


# Show chat history
if not st.session_state.messages:
    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(
            name=st.session_state.name
        ),
    )
else:
    for message in st.session_state.messages:
        render_message(message)


# ---------------- USER INPUT ----------------

user_input = st.chat_input(
    "Ask a question or attach a photo of your meal",
    accept_file=True,
    file_type=["png", "jpg", "jpeg"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()

        add_message("user", "image", photo_bytes)

        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=photo.type,
            )
        )

    if text and text.strip():
        add_message("user", "text", text)
        parts.append(text.strip())

    elif photo is not None:
        parts.append(
            "Identify this meal and estimate its calories, "
            "protein, carbohydrates, and fat."
        )

    if parts:
        with st.spinner("Crunching the numbers..."):
            answer = ask_gemini(parts)

        add_message("assistant", "text", answer)
