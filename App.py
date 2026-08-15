import streamlit as st
import speech_recognition as sr
from gtts import gTTS
from openai import OpenAI
import io
import base64

st.set_page_config(
    page_title="자비스",
    page_icon="🤖"
)

st.title("🤖 자비스 - AI 음성 비서")

# ── 사이드바 ──────────────────────────────────────────
with st.sidebar:
    st.header("설정")

    api_key = st.text_input(
        "NVIDIA API Key",
        type="password"
    )

    voice_lang = st.selectbox(
        "음성 언어",
        ["ko", "en"],
        index=0
    )

    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.rerun()


# ── 대화 기록 ─────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []


SYSTEM_PROMPT = (
    "당신은 '자비스'라는 이름의 친절하고 똑똑한 AI 비서입니다. "
    "사용자의 질문을 이해하고 자연스럽게 대화하세요. "
    "항상 한국어로 답변하세요. "
    "답변은 너무 길지 않게 간결하고 명확하게 하세요."
)


# ── 음성 → 텍스트 ─────────────────────────────────────
def speech_to_text(audio_bytes):

    recognizer = sr.Recognizer()
    audio_file = io.BytesIO(audio_bytes)

    try:
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)

        return recognizer.recognize_google(
            audio_data,
            language="ko-KR"
        )

    except sr.UnknownValueError:
        return None

    except sr.RequestError as e:
        st.error(f"음성 인식 서비스 오류: {e}")
        return None

    except Exception as e:
        st.error(f"오디오 처리 오류: {e}")
        return None


# ── NVIDIA AI ──────────────────────────────────────────
def get_ai_response(client, messages):

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            *messages
        ],
        temperature=0.7,
        top_p=0.9,
        max_tokens=1024
    )

    return response.choices[0].message.content


# ── 텍스트 → 음성 ─────────────────────────────────────
def text_to_speech(text, lang="ko"):

    tts = gTTS(
        text=text,
        lang=lang
    )

    audio_fp = io.BytesIO()

    tts.write_to_fp(audio_fp)

    audio_fp.seek(0)

    return audio_fp.read()


# ── 자동 재생 ─────────────────────────────────────────
def autoplay_audio(audio_bytes):

    b64 = base64.b64encode(audio_bytes).decode()

    st.markdown(
        f"""
        <audio autoplay>
            <source
                src="data:audio/mp3;base64,{b64}"
                type="audio/mp3">
        </audio>
        """,
        unsafe_allow_html=True
    )


# ── 채팅 기록 표시 ────────────────────────────────────
for msg in st.session_state.messages:

    with st.chat_message(msg["role"]):
        st.write(msg["content"])


# ── 음성 입력 ─────────────────────────────────────────
st.write("🎤 아래 버튼을 눌러 말하거나 텍스트를 입력하세요.")

audio_value = st.audio_input("음성으로 말하기")

user_input = None


if audio_value is not None:

    with st.spinner("음성 인식 중..."):

        recognized_text = speech_to_text(
            audio_value.read()
        )

    if recognized_text:

        st.success(
            f"인식된 텍스트: {recognized_text}"
        )

        user_input = recognized_text

    else:

        st.warning(
            "음성을 인식하지 못했습니다. 다시 말씀해 주세요."
        )


# ── 텍스트 입력 ───────────────────────────────────────
text_input = st.chat_input("메시지를 입력하세요")

if text_input:
    user_input = text_input


# ── 응답 처리 ─────────────────────────────────────────
if user_input:

    if not api_key:

        st.error(
            "사이드바에 NVIDIA API Key를 입력해주세요."
        )

    else:

        # 사용자 메시지 저장
        st.session_state.messages.append(
            {
                "role": "user",
                "content": user_input
            }
        )

        with st.chat_message("user"):
            st.write(user_input)

        # NVIDIA 클라이언트
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )

        # 대화 기록
        ai_messages = [
            {
                "role": m["role"],
                "content": m["content"]
            }
            for m in st.session_state.messages
        ]

        # NVIDIA AI 호출
        with st.spinner("자비스가 생각 중..."):

            try:

                ai_response = get_ai_response(
                    client,
                    ai_messages
                )

            except Exception as e:

                st.error(
                    f"NVIDIA API 오류: {e}"
                )

                st.stop()

        # AI 응답 저장
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": ai_response
            }
        )

        # AI 응답 표시
        with st.chat_message("assistant"):

            st.write(ai_response)

            # 음성 생성
            with st.spinner("음성 생성 중..."):

                speech_bytes = text_to_speech(
                    ai_response,
                    lang=voice_lang
                )

            autoplay_audio(speech_bytes)

            st.audio(
                speech_bytes,
                format="audio/mp3"
            )
