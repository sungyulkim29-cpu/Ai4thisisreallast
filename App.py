import streamlit as st
import speech_recognition as sr
from openai import OpenAI
from tavily import TavilyClient
import edge_tts
import io
import base64
import asyncio


# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(
    page_title="자비스 2.0",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 자비스 2.0")
st.caption("NVIDIA AI + 웹 검색 음성 비서")


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
        "Tavily Search API Key",
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
# 세션
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []


# =========================================================
# 자비스 시스템 프롬프트
# =========================================================

SYSTEM_PROMPT = """
당신은 '자비스'라는 이름의 지능형 AI 비서입니다.

성격:
- 친절하고 똑똑합니다.
- 자연스럽게 대화합니다.
- 지나치게 딱딱하지 않습니다.
- 사용자의 질문에 직접적으로 답합니다.
- 모르는 것은 아는 척하지 않습니다.
- 항상 한국어로 답변합니다.

대화:
- 이전 대화 내용을 참고합니다.
- 사용자가 앞에서 말한 내용을 기억하고 대화를 이어갑니다.
- 사용자의 말을 단순히 반복하지 않습니다.
- 실제로 도움이 되는 답변을 제공합니다.

웹 검색:
- 검색 결과가 제공된 경우 검색 결과를 우선적으로 참고합니다.
- 검색 결과에 없는 내용을 사실인 것처럼 만들어내지 않습니다.
- 최신 정보가 필요한 질문에는 검색 결과의 날짜와 내용을 고려합니다.
- 검색 결과가 여러 개라면 서로 비교하여 가장 신뢰할 수 있는 정보를 사용합니다.

답변:
- 간단한 질문은 간단하게 답합니다.
- 복잡한 질문은 이해하기 쉽게 설명합니다.
- 필요한 경우 목록을 사용합니다.
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
# 검색 필요 여부 판단
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
        "몇 시",
        "몇일",
        "언제",
        "2026",
        "검색",
        "인터넷"
    ]

    return any(
        keyword in question
        for keyword in keywords
    )


# =========================================================
# 웹 검색
# =========================================================

def web_search(query, api_key):

    if not api_key:
        return []

    try:

        tavily = TavilyClient(
            api_key=api_key
        )

        results = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=5
        )

        return results.get(
            "results",
            []
        )

    except Exception as e:

        st.warning(
            f"검색 오류: {e}"
        )

        return []


# =========================================================
# 검색 결과 정리
# =========================================================

def format_search_results(results):

    if not results:
        return ""

    formatted = []

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

        formatted.append(
            f"""
검색 결과 {i}
제목: {title}
내용: {content}
주소: {url}
"""
        )

    return "\n".join(formatted)


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

아래는 웹 검색 결과입니다.

-------------------------
{search_results}
-------------------------

검색 결과를 참고하여 사용자의 질문에 답변하세요.

가능하면 답변 마지막에 참고한 웹사이트의 이름이나
주소를 간단히 표시하세요.
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

        max_tokens=1024
    )

    if not response.choices:

        return "죄송합니다. 답변을 생성하지 못했습니다."

    content = response.choices[0].message.content

    if content is None:

        return "죄송합니다. 빈 응답이 반환되었습니다."

    content = str(content).strip()

    if not content:

        return "죄송합니다. 답변을 생성하지 못했습니다."

    return content


# =========================================================
# TTS
# =========================================================

async def generate_tts(text, voice):

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


def text_to_speech(text, voice):

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

def autoplay_audio(audio_bytes):

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
                type="audio/mp3">
        </audio>
        """,

        unsafe_allow_html=True
    )


# =========================================================
# 기존 대화 표시
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


    # -----------------------------------------------------
    # 사용자 메시지 저장
    # -----------------------------------------------------

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input
        }
    )


    with st.chat_message("user"):

        st.write(user_input)


    # -----------------------------------------------------
    # NVIDIA 연결
    # -----------------------------------------------------

    client = OpenAI(

        base_url="https://integrate.api.nvidia.com/v1",

        api_key=nvidia_api_key
    )


    # -----------------------------------------------------
    # 검색
    # -----------------------------------------------------

    search_results = []

    if needs_search(user_input):

        if tavily_api_key:

            with st.spinner(
                "🔎 최신 정보를 검색하는 중..."
            ):

                search_results = web_search(
                    user_input,
                    tavily_api_key
                )

            if search_results:

                with st.expander(
                    "🔎 검색 결과 보기"
                ):

                    for result in search_results:

                        st.markdown(
                            f"**{result.get('title', '제목 없음')}**"
                        )

                        st.write(
                            result.get(
                                "content",
                                ""
                            )[:500]
                        )

                        st.write(
                            result.get(
                                "url",
                                ""
                            )
                        )

        else:

            st.info(
                "검색 API 키가 없어 일반 AI 모드로 답변합니다."
            )


    # -----------------------------------------------------
    # 검색 결과 텍스트
    # -----------------------------------------------------

    formatted_results = format_search_results(
        search_results
    )


    # -----------------------------------------------------
    # AI 메시지
    # -----------------------------------------------------

    ai_messages = [

        {
            "role": message["role"],
            "content": message["content"]
        }

        for message in st.session_state.messages

    ]


    # -----------------------------------------------------
    # NVIDIA AI 응답
    # -----------------------------------------------------

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


        # -------------------------------------------------
        # AI 답변 출력
        # -------------------------------------------------

        st.write(
            ai_response
        )


        # -------------------------------------------------
        # 대화 기록 저장
        # -------------------------------------------------

        st.session_state.messages.append(

            {
                "role": "assistant",
                "content": ai_response
            }

        )


        # -------------------------------------------------
        # TTS
        # -------------------------------------------------

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
