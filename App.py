import streamlit as st
import speech_recognition as sr
from openai import OpenAI
import edge_tts
import requests
from bs4 import BeautifulSoup
import io
import base64
import asyncio
import re


# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(
    page_title="자비스",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 자비스")
st.caption("NVIDIA AI · 웹 검색 · 음성 비서")


# =========================================================
# 사이드바
# =========================================================

with st.sidebar:

    st.header("⚙️ 설정")

    api_key = st.text_input(
        "NVIDIA API Key",
        type="password",
        placeholder="nvapi-..."
    )

    voice = st.selectbox(
        "🔊 자비스 음성",
        [
            "ko-KR-SunHiNeural",
            "ko-KR-InJoonNeural"
        ]
    )

    search_enabled = st.checkbox(
        "🔎 웹 검색 사용",
        value=True
    )

    st.divider()

    if st.button(
        "🗑️ 대화 초기화",
        use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()


# =========================================================
# 대화 기록
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []


# =========================================================
# 시스템 프롬프트
# =========================================================

SYSTEM_PROMPT = """
당신은 '자비스'라는 이름의 AI 비서입니다.

당신의 역할은 사용자의 질문을 이해하고
정확하고 자연스럽게 도움을 주는 것입니다.

규칙:

1. 항상 한국어로 답변합니다.
2. 사용자의 질문에 직접 답합니다.
3. 이전 대화의 내용을 참고하여 자연스럽게 대화합니다.
4. 사용자가 말한 내용을 불필요하게 반복하지 않습니다.
5. 모르는 내용은 모른다고 말합니다.
6. 사실을 지어내지 않습니다.
7. 최신 정보가 필요한 경우 제공된 웹 검색 결과를 사용합니다.
8. 웹 검색 결과가 없으면 인터넷을 검색했다고 주장하지 않습니다.
9. 간단한 질문은 간단하게 답합니다.
10. 복잡한 질문은 이해하기 쉽게 설명합니다.
11. 코드 질문에는 실행 가능한 코드를 제공합니다.

당신은 단순히 사용자의 문장을 반복하는 챗봇이 아닙니다.
사용자의 의도를 이해하고 실제로 도움이 되는 답변을 해야 합니다.
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
# 검색 여부 판단
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
        "가격",
        "주가",
        "일정",
        "결과",
        "출시",
        "업데이트",
        "패치",
        "언제",
        "몇 시",
        "검색",
        "인터넷",
        "이번 주",
        "이번달",
        "이번 달",
        "올해",
        "2026"
    ]

    return any(
        word in question
        for word in keywords
    )


# =========================================================
# 검색어 정리
# =========================================================

def make_search_query(question):

    query = re.sub(
        r"\s+",
        " ",
        question.strip()
    )

    return query[:300]


# =========================================================
# 웹 검색
# =========================================================

def web_search(query):

    try:

        response = requests.get(
            "https://html.duckduckgo.com/html/",

            params={
                "q": query
            },

            headers={
                "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            },

            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for item in soup.select(".result")[:5]:

            title_element = item.select_one(
                ".result__a"
            )

            snippet_element = item.select_one(
                ".result__snippet"
            )

            if not title_element:
                continue

            title = title_element.get_text(
                " ",
                strip=True
            )

            url = title_element.get(
                "href",
                ""
            )

            snippet = ""

            if snippet_element:

                snippet = snippet_element.get_text(
                    " ",
                    strip=True
                )

            results.append({
                "title": title,
                "url": url,
                "content": snippet
            })

        return results

    except Exception as e:

        st.warning(
            f"웹 검색을 사용할 수 없습니다: {e}"
        )

        return []


# =========================================================
# 검색 결과 정리
# =========================================================

def format_search_results(results):

    if not results:
        return ""

    output = ""

    for i, result in enumerate(
        results,
        1
    ):

        output += f"""
[검색 결과 {i}]

제목:
{result["title"]}

내용:
{result["content"]}

주소:
{result["url"]}

-------------------------
"""

    return output


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

다음은 인터넷 검색 결과입니다.

=========================
{search_results}
=========================

검색 결과를 참고하여 답변하세요.

검색 결과에 없는 최신 사실을 만들어내지 마세요.
검색 결과가 서로 다르면 차이가 있다는 것을 알려주세요.
"""


    response = client.chat.completions.create(

        model="nvidia/nemotron-3-super-120b-a12b",

        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            *messages
        ],

        temperature=1.0,

        top_p=0.95,

        max_tokens=4096,

        stream=False
    )


    if not response.choices:

        return (
            "죄송합니다. "
            "AI가 답변을 생성하지 못했습니다."
        )


    message = response.choices[0].message

    content = getattr(
        message,
        "content",
        None
    )


    if content:

        content = str(content).strip()

        if content:

            return content


    return (
        "죄송합니다. "
        "NVIDIA AI에서 답변을 받지 못했습니다."
    )


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

    audio = io.BytesIO()

    async for chunk in communicate.stream():

        if chunk["type"] == "audio":

            audio.write(
                chunk["data"]
            )

    audio.seek(0)

    return audio.read()


def text_to_speech(
    text,
    voice
):

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

    encoded = base64.b64encode(
        audio_bytes
    ).decode()

    st.markdown(
        f"""
        <audio autoplay>
            <source
                src="data:audio/mp3;base64,{encoded}"
                type="audio/mp3"
            >
        </audio>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# 이전 대화 표시
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

    if not api_key:

        st.error(
            "⚠️ NVIDIA API Key를 입력해주세요."
        )

        st.stop()


    # -----------------------------------------------------
    # 사용자 메시지 저장
    # -----------------------------------------------------

    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })


    with st.chat_message("user"):

        st.write(user_input)


    # -----------------------------------------------------
    # NVIDIA 연결
    # -----------------------------------------------------

    client = OpenAI(

        base_url="https://integrate.api.nvidia.com/v1",

        api_key=api_key
    )


    # -----------------------------------------------------
    # 웹 검색
    # -----------------------------------------------------

    search_results = []

    if (
        search_enabled
        and needs_search(user_input)
    ):

        query = make_search_query(
            user_input
        )

        with st.spinner(
            "🔎 인터넷 검색 중..."
        ):

            search_results = web_search(
                query
            )

        if search_results:

            with st.expander(
                "🔎 검색 결과 보기"
            ):

                for result in search_results:

                    st.markdown(
                        f"**{result['title']}**"
                    )

                    st.caption(
                        result["url"]
                    )

                    st.write(
                        result["content"]
                    )


    # -----------------------------------------------------
    # 검색 결과
    # -----------------------------------------------------

    formatted_results = format_search_results(
        search_results
    )


    # -----------------------------------------------------
    # 대화 기록
    # -----------------------------------------------------

    ai_messages = [

        {
            "role": m["role"],
            "content": m["content"]
        }

        for m in st.session_state.messages

    ]


    # -----------------------------------------------------
    # AI 답변
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


        st.write(
            ai_response
        )


        # -------------------------------------------------
        # 대화 저장
        # -------------------------------------------------

        st.session_state.messages.append({
            "role": "assistant",
            "content": ai_response
        })


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
