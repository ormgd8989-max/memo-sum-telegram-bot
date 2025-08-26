# bot.py
import os
import re
import json
import requests
from flask import Flask, request, jsonify

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # Render에서 설정할 환경변수
if not TOKEN:
    print("Warning: TELEGRAM_BOT_TOKEN not set (use Render env var).")

app = Flask(__name__)

# 간단 메모 저장 (서버 메모리). 채팅별로 마지막 보낸 텍스트 저장.
last_messages = {}  # chat_id -> text

########### 유틸: 숫자 파싱 ###########
def parse_amount_kor(num_str: str) -> int:
    s = num_str.strip().replace(",", "")
    # '만' 단위 처리 (예: 25만, 25만원)
    m = re.match(r"^(\d+)\s*만(?:원)?$", s)
    if m:
        return int(m.group(1)) * 10000
    # 일반 숫자 (예: 150000원, 3000000)
    m = re.match(r"^(\d+)\s*(?:원)?$", s)
    if m:
        return int(m.group(1))
    return 0

def extract_and_sum(text: str):
    """
    - '메모' 라인 다음 줄에서 '이름 ... 숫자' 패턴을 찾아 합계와 사람별 총합 반환
    - 전체 문서에 있는 모든 '메모' 섹션을 순회해 합산함
    """
    lines = text.splitlines()
    total = 0
    per_person = {}

    for i, line in enumerate(lines):
        if line.strip() == "메모" and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            # 이름(한글/영문) + (그 뒤에 숫자 포함 토큰) 을 찾는다
            m = re.search(r"([가-힣A-Za-z]+)[^\d\n]*?([\d,]+(?:만)?(?:원)?)", nxt)
            if m:
                name = m.group(1)
                amt_str = m.group(2)
                val = parse_amount_kor(amt_str)
                total += val
                per_person[name] = per_person.get(name, 0) + val

    # 정렬해서 리스트로 반환 (내림차순)
    per_sorted = sorted(per_person.items(), key=lambda x: x[1], reverse=True)
    return total, per_sorted

########### Telegram API 헬퍼 ###########
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    r = requests.post(url, data=payload, timeout=10)
    return r.ok, r.text

def answer_callback(callback_query_id, text=None):
    url = f"{BASE_URL}/answerCallbackQuery"
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
    requests.post(url, data=data, timeout=10)

########### Routes ###########
@app.route("/", methods=["GET"])
def index():
    return "OK - MemoSum Bot is running"

@app.route("/setwebhook", methods=["GET"])
def set_webhook():
    # 호출하면 현재 앱의 주소 기반으로 webhook을 등록 (Render URL로 접속해서 호출)
    # request.url_root 는 https://your-service.onrender.com/ 로 나옴
    webhook_url = request.url_root.rstrip("/") + "/webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    resp = requests.post(url, data={"url": webhook_url})
    return jsonify({"setWebhook_resp": resp.json(), "webhook_url": webhook_url})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    # Telegram Update 에서 message 또는 callback_query 처리
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        # 저장: 가장 최근에 보낸 텍스트로 덮어쓰기
        last_messages[chat_id] = text

        # 버튼(InlineKeyboard) 보내기
        keyboard = {"inline_keyboard": [[{"text": "계산 시작", "callback_data": "calc_start"}]]}
        send_message(chat_id, "메시지 저장 완료 ✅\n계산하려면 아래 '계산 시작' 버튼을 눌러주세요.", reply_markup=keyboard)
        return "", 200

    if "callback_query" in data:
        cq = data["callback_query"]
        data_cb = cq.get("data")
        chat_id = cq["message"]["chat"]["id"]
        cq_id = cq["id"]

        # 답장(버튼 로딩 해제)
        answer_callback(cq_id)

        if data_cb == "calc_start":
            # 계산 실행
            text = last_messages.get(chat_id)
            if not text:
                send_message(chat_id, "저장된 메시지가 없습니다. 먼저 텍스트를 붙여넣고 다시 시도하세요.")
                return "", 200

            total, per_sorted = extract_and_sum(text)
            if total == 0:
                send_message(chat_id, "합산할 금액을 찾지 못했습니다. 포맷을 확인해주세요.")
                return "", 200

            # 메시지 구성 (전체 출력)
            lines = [f"📊 합계: {total:,}원", "", "👥 전체 내역:"]
            for idx, (name, amt) in enumerate(per_sorted, start=1):
                lines.append(f"{idx}. {name}: {amt:,}원")
            result_text = "\n".join(lines)
            send_message(chat_id, result_text)
            # (선택) 계산 후 저장된 텍스트 삭제하려면 다음 줄 주석 해제:
            # last_messages.pop(chat_id, None)
            return "", 200

    return "", 200

if __name__ == "__main__":
    # 로컬 테스트용 (Render에서는 gunicorn으로 실행)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
