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
# 설정
# =========================================================

st.set_page_config(
    page_title="자비스",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 자비스")
st.caption("NVIDIA AI · 실시간 웹 검색 · 음성 비서")


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
        "🔊 음성",
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
# 세션
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []


# =========================================================
# 시스템 프롬프트
# =========================================================

SYSTEM_PROMPT = """
당신의 이름은 자비스입니다.

당신은 사용자를 도와주는 AI 비서입니다.

중요한 규칙:

1. 항상 한국어로 답변합니다.
2. 사용자의 질문을 정확하게 이해합니다.
3. 이전 대화의 맥락을 기억합니다.
4. 모르는 정보를 추측해서 사실처럼 말하지 않습니다.
5. 최신 정보가 필요한 질문은 반드시 제공된 웹 검색 결과를 확인합니다.
6. 웹 검색 결과가 있으면 검색 결과를 최우선으로 참고합니다.
7. 검색 결과와 알고 있던 정보를 구분합니다.
8. 검색 결과가 없으면 검색했다고 거짓말하지 않습니다.
9. 답변은 자연스럽고 이해하기 쉽게 작성합니다.
10. 사용자가 게임에 대해 질문하면 게임의 최신 정보를 우선합니다.

특히 게임의 '신캐', '최신 영웅', '현재 패치',
'최근 업데이트' 같은 질문은 과거 지식만으로 답하지 마세요.
반드시 제공된 최신 검색 결과를 확인하세요.
"""


# =========================================================
# 음성 인식
# =========================================================

def speech_to_text(audio_bytes):

    recognizer = sr.Recognizer()

    try:

        audio_file = io.BytesIO(audio_bytes)

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
            f"음성 인식 오류: {e}"
        )

        return None

    except Exception as e:

        st.error(
            f"오디오 오류: {e}"
        )

        return None


# =========================================================
# 검색이 필요한지 판단
# =========================================================

def needs_search(question):

    keywords = [

        # 최신 정보
        "최신",
        "최근",
        "현재",
        "지금",
        "오늘",
        "이번",

        # 뉴스
        "뉴스",
        "소식",

        # 게임
        "신캐",
        "신캐릭터",
        "새 캐릭터",
        "새 영웅",
        "신영웅",
        "영웅",
        "패치",
        "패치노트",
        "업데이트",
        "버프",
        "너프",
        "픽",
        "메타",

        # 시간
        "언제",
        "몇 시",
        "출시",

        # 검색
        "검색",
        "인터넷",
        "찾아",
        "찾아줘",

        # 날짜
        "2026",
        "2025"

    ]

    question_lower = question.lower()

    return any(
        word in question_lower
        for word in keywords
    )


# =========================================================
# 검색어 개선
# =========================================================

def create_search_query(question):

    query = re.sub(
        r"\s+",
        " ",
        question.strip()
    )

    # 오버워치 관련 질문이면 공식 사이트 검색을 유도
    if "오버워치" in query or "오버워치2" in query:

        query += " Overwatch Blizzard official"

    return query[:400]


# =========================================================
# 웹 검색
# =========================================================

def web_search(query):

    try:

        headers = {

            "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131 Safari/537.36"

        }

        response = requests.get(

            "https://www.google.com/search",

            params={
                "q": query,
                "hl": "ko"
            },

            headers=headers,

            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        # Google 검색 결과
        for block in soup.select(
            "div.MjjYud"
        ):

            link = block.select_one(
                "a"
            )

            title = block.select_one(
                "h3"
            )

            if not link or not title:
                continue

            url = link.get(
                "href",
                ""
            )

            title_text = title.get_text(
                " ",
                strip=True
            )

            description = ""

            for element in block.select(
                "div"
            ):

                text = element.get_text(
                    " ",
                    strip=True
                )

                if (
                    len(text) > 50
                    and title_text not in text
                ):

                    description = text
                    break

            if url.startswith("/url?q="):

                url = url.split(
                    "/url?q="
                )[1].split("&")[0]

            results.append({

                "title": title_text,

                "url": url,

                "content": description

            })

            if len(results) >= 6:
                break

        return results

    except Exception as e:

        st.warning(
            f"웹 검색 오류: {e}"
        )

        return []


# =========================================================
# 검색 결과 정리
# =========================================================

def format_results(results):

    if not results:

        return "검색 결과가 없습니다."

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

URL:
{result["url"]}

--------------------------------
"""

    return output


# =========================================================
# NVIDIA AI
# =========================================================

def ask_ai(
    client,
    messages,
    search_data
):

    prompt = SYSTEM_PROMPT

    if search_data:

        prompt += f"""

==================================================
실시간 웹 검색 결과
==================================================

{search_data}

==================================================

위 검색 결과는 현재 인터넷에서 가져온 정보입니다.

반드시 검색 결과를 먼저 확인하고 답변하세요.

특히 다음과 같은 질문이라면 검색 결과에서
가장 최신 정보를 찾아 답하세요.

- 신캐
- 최신 영웅
- 현재 메타
- 최신 패치
- 최근 업데이트
- 출시된 캐릭터

검색 결과에 여러 날짜의 정보가 있다면
가장 최근 정보를 우선하세요.

검색 결과가 서로 충돌하면
그 사실을 사용자에게 알려주세요.

==================================================
"""


    response = client.chat.completions.create(

        model="nvidia/nemotron-3-super-120b-a12b",

        messages=[

            {
                "role": "system",
                "content": prompt
            },

            *messages

        ],

        temperature=0.7,

        top_p=0.9,

        max_tokens=4096,

        stream=False

    )


    if not response.choices:

        return (
            "AI가 답변을 생성하지 못했습니다."
        )


    message = response.choices[0].message

    content = getattr(
        message,
        "content",
        None
    )


    if content:

        content = str(
            content
        ).strip()

        if content:

            return content


    return (
        "NVIDIA AI에서 "
        "답변을 받지 못했습니다."
    )


# =========================================================
# TTS
# =========================================================

async def make_audio(
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
            make_audio(
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
# 대화 출력
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


if audio_value:

    with st.spinner(
        "🎧 음성을 인식하는 중..."
    ):

        text = speech_to_text(
            audio_value.read()
        )

    if text:

        st.success(
            f"📝 {text}"
        )

        user_input = text

    else:

        st.warning(
            "음성을 인식하지 못했습니다."
        )


# =========================================================
# 텍스트 입력
# =========================================================

text_input = st.chat_input(
    "자비스에게 물어보세요..."
)

if text_input:

    user_input = text_input


# =========================================================
# 실행
# =========================================================

if user_input:

    if not api_key:

        st.error(
            "NVIDIA API Key를 입력해주세요."
        )

        st.stop()


    # 사용자 메시지 저장
    st.session_state.messages.append({

        "role": "user",

        "content": user_input

    })


    with st.chat_message("user"):

        st.write(
            user_input
        )


    # NVIDIA 연결
    client = OpenAI(

        base_url=(
            "https://integrate.api.nvidia.com/v1"
        ),

        api_key=api_key

    )


    # =====================================================
    # 웹 검색
    # =====================================================

    results = []

    if (
        search_enabled
        and needs_search(user_input)
    ):

        search_query = create_search_query(
            user_input
        )

        with st.spinner(
            "🔎 최신 정보를 검색하는 중..."
        ):

            results = web_search(
                search_query
            )


        if results:

            with st.expander(
                "🔎 자비스가 검색한 정보"
            ):

                for result in results:

                    st.markdown(
                        f"### {result['title']}"
                    )

                    st.write(
                        result["content"]
                    )

                    st.caption(
                        result["url"]
                    )


    search_data = format_results(
        results
    )


    # =====================================================
    # AI에 전달할 대화
    # =====================================================

    ai_messages = [

        {

            "role": message["role"],

            "content": message["content"]

        }

        for message
        in st.session_state.messages

    ]


    # =====================================================
    # AI 답변
    # =====================================================

    with st.chat_message("assistant"):

        with st.spinner(
            "🤖 자비스가 생각 중..."
        ):

            try:

                answer = ask_ai(

                    client,

                    ai_messages,

                    search_data

                )

            except Exception as e:

                st.error(
                    f"NVIDIA API 오류:\n\n{e}"
                )

                st.stop()


        st.write(
            answer
        )


        # 답변 저장
        st.session_state.messages.append({

            "role": "assistant",

            "content": answer

        })


        # =================================================
        # TTS
        # =================================================

        with st.spinner(
            "🔊 음성 생성 중..."
        ):

            audio = text_to_speech(

                answer,

                voice

            )


        if audio:

            autoplay_audio(
                audio
            )

            st.audio(
                audio,
                format="audio/mp3"
            )