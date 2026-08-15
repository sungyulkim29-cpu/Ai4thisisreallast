import streamlit as st
import speech_recognition as sr
from openai import OpenAI
import edge_tts
import requests
import io
import base64
import asyncio


# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(
    page_title="자비스",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 자비스")
st.caption("NVIDIA AI 음성 비서")


# =========================================================
# 사이드바
# =========================================================

with st.sidebar:

    st.header("⚙️ 설정")

    nvidia_api_key = st.text_input(
        "NVIDIA API Key",
        type="password",
        placeholder="nvapi-..."
    )

    tavily_api_key = st.text_input(
        "Tavily API Key",
        type="password",
        placeholder="tvly-..."
    )

    voice = st.selectbox(
        "🔊 자비스 음성",
        [
            "ko-KR-SunHiNeural",
            "ko-KR-InJoonNeural"
        ]
    )

    st.divider()

    if st.button(
        "🗑️ 대화 초기화",
        use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()


# =========================================================
# 세션 상태
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []


# =========================================================
# 자비스 시스템 프롬프트
# =========================================================

SYSTEM_PROMPT = """
당신의 이름은 자비스입니다.

당신은 사용자를 도와주는 지능형 AI 비서입니다.

[성격]
- 친절하고 똑똑합니다.
- 자연스럽게 대화합니다.
- 지나치게 딱딱하게 말하지 않습니다.
- 사용자가 존댓말을 사용하면 존댓말로 답합니다.
- 사용자가 편하게 말하면 자연스럽게 답합니다.
- 모르는 것은 아는 척하지 않습니다.

[대화]
- 이전 대화 내용을 참고합니다.
- 앞에서 나온 정보를 이용해서 대화를 자연스럽게 이어갑니다.
- 사용자의 말을 단순히 반복하지 않습니다.
- 질문의 의도를 이해하고 직접 답합니다.

[답변]
- 기본적으로 한국어를 사용합니다.
- 간단한 질문에는 짧게 답합니다.
- 복잡한 질문은 이해하기 쉽게 설명합니다.
- 필요한 경우 목록이나 단계별 설명을 사용합니다.

[웹 검색]
- 검색 결과가 제공되면 검색 결과를 우선적으로 참고합니다.
- 검색 결과에 없는 사실을 검색 결과에 있는 것처럼 말하지 않습니다.
- 최신 정보가 필요한 경우 검색 결과의 내용을 이용합니다.
"""


# =========================================================
# 음성 → 텍스트
# =========================================================

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

        st.error(
            f"음성 인식 서비스 오류: {e}"
        )

        return None

    except Exception as e:

        st.error(
            f"오디오 처리 오류: {e}"
        )

        return None


# =========================================================
# 검색이 필요한 질문인지 판단
# =========================================================

def needs_search(question):

    keywords = [
        "오늘",
        "현재",
        "지금",
        "최신",
        "최근",
        "뉴스",
        "날씨",
        "주가",
        "가격",
        "일정",
        "결과",
        "출시",
        "업데이트",
        "언제",
        "몇 시",
        "검색",
        "인터넷",
        "이번 주",
        "이번달",
        "이번 달"
    ]

    return any(
        keyword in question
        for keyword in keywords
    )


# =========================================================
# Tavily 검색 API
# =========================================================

def web_search(query, api_key):

    if not api_key:
        return []

    try:

        response = requests.post(
            "https://api.tavily.com/search",

            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": 5,
                "include_answer": True
            },

            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        return data.get(
            "results",
            []
        )

    except Exception as e:

        st.warning(
            f"웹 검색 오류: {e}"
        )

        return []


# =========================================================
# 검색 결과 정리
# =========================================================

def format_search_results(results):

    if not results:
        return ""

    text = ""

    for i, result in enumerate(results, 1):

        title = result.get(
            "title",
            "제목 없음"
        )

        content = result.get(
            "content",
            ""
        )

        url = result.get(
            "url",
            ""
        )

        text += f"""
[검색 결과 {i}]
제목: {title}
내용: {content}
주소: {url}

"""

    return text


# =========================================================
# NVIDIA AI
# =========================================================

def get_ai_response(
    client,
    messages,
    search_results=""
):

    system_prompt = SYSTEM_PROMPT

    if search_results:

        system_prompt += f"""

[웹 검색 결과]

{search_results}

위 검색 결과를 참고해서 사용자의 질문에 답변하세요.
검색 결과에 없는 정보는 추측해서 사실처럼 말하지 마세요.
"""


    response = client.chat.completions.create(

        model="openai/gpt-oss-20b",

        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            *messages
        ],

        temperature=0.7,
        top_p=0.9,

        # gpt-oss-20b는 추론에도 토큰을 사용할 수 있음
        max_tokens=4096,

        stream=False
    )


    if not response.choices:

        return "죄송합니다. AI가 답변을 생성하지 못했습니다."


    message = response.choices[0].message


    # =====================================================
    # 일반 답변
    # =====================================================

    content = getattr(
        message,
        "content",
        None
    )


    if content:

        content = str(content).strip()

        if content:

            return content


    # =====================================================
    # NVIDIA reasoning_content 확인
    # =====================================================

    reasoning = getattr(
        message,
        "reasoning_content",
        None
    )


    # reasoning만 있는 경우
    # 사용자에게 내부 추론을 그대로 보여주지는 않고
    # 다시 한 번 짧은 답변을 요청할 수 있도록 오류 처리
    if reasoning:

        return "답변 생성 중 문제가 발생했습니다. 다시 질문해주세요."


    return "죄송합니다. NVIDIA AI에서 답변을 받지 못했습니다."


# =========================================================
# Edge TTS
# =========================================================

async def generate_tts(
    text,
    voice
):

    communicate = edge_tts.Communicate(
        text,
        voice
    )

    audio_fp = io.BytesIO()

    async for chunk in communicate.stream():

        if chunk["type"] == "audio":

            audio_fp.write(
                chunk["data"]
            )

    audio_fp.seek(0)

    return audio_fp.read()


def text_to_speech(
    text,
    voice
):

    if not text:
        return None

    text = str(text).strip()

    if not text:
        return None

    try:

        return asyncio.run(
            generate_tts(
                text,
                voice
            )
        )

    except Exception as e:

        st.warning(
            f"TTS 오류: {e}"
        )

        return None


# =========================================================
# 자동 재생
# =========================================================

def autoplay_audio(
    audio_bytes
):

    if not audio_bytes:
        return

    b64 = base64.b64encode(
        audio_bytes
    ).decode()

    st.markdown(
        f"""
        <audio autoplay>
            <source
                src="data:audio/mp3;base64,{b64}"
                type="audio/mp3"
            >
        </audio>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# 기존 대화 출력
# =========================================================

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.write(
            message["content"]
        )


# =========================================================
# 음성 입력
# =========================================================

st.write("### 🎤 자비스에게 말하기")

audio_value = st.audio_input(
    "마이크 버튼을 눌러 말씀하세요"
)

user_input = None


if audio_value is not None:

    with st.spinner(
        "🎧 음성을 인식하는 중..."
    ):

        recognized_text = speech_to_text(
            audio_value.read()
        )

    if recognized_text:

        st.success(
            f"📝 인식된 내용: {recognized_text}"
        )

        user_input = recognized_text

    else:

        st.warning(
            "음성을 인식하지 못했습니다."
        )


# =========================================================
# 텍스트 입력
# =========================================================

text_input = st.chat_input(
    "자비스에게 메시지를 입력하세요..."
)

if text_input:

    user_input = text_input


# =========================================================
# AI 처리
# =========================================================

if user_input:

    if not nvidia_api_key:

        st.error(
            "⚠️ NVIDIA API Key를 입력해주세요."
        )

        st.stop()


    # =====================================================
    # 사용자 메시지 저장
    # =====================================================

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input
        }
    )


    with st.chat_message("user"):

        st.write(user_input)


    # =====================================================
    # NVIDIA 클라이언트
    # =====================================================

    client = OpenAI(

        base_url="https://integrate.api.nvidia.com/v1",

        api_key=nvidia_api_key
    )


    # =====================================================
    # 웹 검색
    # =====================================================

    search_results = []

    if needs_search(user_input):

        if tavily_api_key:

            with st.spinner(
                "🔎 웹에서 최신 정보를 찾는 중..."
            ):

                search_results = web_search(
                    user_input,
                    tavily_api_key
                )

            if search_results:

                with st.expander(
                    "🔎 검색한 자료 보기"
                ):

                    for result in search_results:

                        title = result.get(
                            "title",
                            "제목 없음"
                        )

                        url = result.get(
                            "url",
                            ""
                        )

                        st.markdown(
                            f"**{title}**"
                        )

                        st.caption(url)

        else:

            st.info(
                "Tavily API Key가 없어 웹 검색 없이 답변합니다."
            )


    # =====================================================
    # 검색 결과 변환
    # =====================================================

    formatted_results = format_search_results(
        search_results
    )


    # =====================================================
    # 대화 기록
    # =====================================================

    ai_messages = [

        {
            "role": message["role"],
            "content": message["content"]
        }

        for message in st.session_state.messages

    ]


    # =====================================================
    # AI 응답
    # =====================================================

    with st.chat_message("assistant"):

        with st.spinner(
            "🤖 자비스가 생각 중..."
        ):

            try:

                ai_response = get_ai_response(

                    client,

                    ai_messages,

                    formatted_results
                )

            except Exception as e:

                st.error(
                    f"NVIDIA API 오류:\n\n{e}"
                )

                st.stop()


        # =================================================
        # 답변 출력
        # =================================================

        st.write(
            ai_response
        )


        # =================================================
        # 대화 저장
        # =================================================

        st.session_state.messages.append(

            {
                "role": "assistant",
                "content": ai_response
            }

        )


        # =================================================
        # TTS
        # =================================================

        with st.spinner(
            "🔊 자비스가 말하는 중..."
        ):

            speech_bytes = text_to_speech(
                ai_response,
                voice
            )


        if speech_bytes:

            autoplay_audio(
                speech_bytes
            )

            st.audio(
                speech_bytes,
                format="audio/mp3"
            )
