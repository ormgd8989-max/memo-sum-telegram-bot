import os
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Render 환경변수로 주입

def parse_amount_kor(num_str: str) -> int:
    """
    '25만', '150000원', '3000000', '3,000,000원' 등 대응.
    '만'이 붙으면 10,000 곱함. 콤마/원 제거.
    """
    num_str = num_str.strip()
    # '만' 표기 처리
    m = re.match(r"^([\d,]+)\s*만(?:원)?$", num_str)
    if m:
        val = int(m.group(1).replace(",", "")) * 10000
        return val
    # 일반 숫자 + 선택적 '원'
    m = re.match(r"^([\d,]+)\s*(?:원)?$", num_str)
    if m:
        val = int(m.group(1).replace(",", ""))
        return val
    # 기타: 못 읽으면 0
    return 0

def extract_and_sum(text: str) -> tuple[int, list[tuple[str,int]]]:
    """
    - 원문에서 '메모'가 등장하는 줄을 기준으로,
      그 다음 줄(= 이름 + 금액)에서 금액만 추출해 합산.
    - 사람별 금액도 같이 반환.
    """
    lines = text.splitlines()
    total = 0
    per_person: dict[str, int] = {}

    for i, line in enumerate(lines):
        if line.strip() == "메모" and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # 예: '유득경 40000', '이승한 150000원', '조현우 60000원'
            # 이름(한글/영문) + 공백 + 금액표현(숫자[,]+, 선택적 '만', 선택적 '원')
            m = re.match(r"^([가-힣A-Za-z]+)\s+([0-9][\d,]*\s*(?:만)?(?:원)?)$", next_line)
            if m:
                name = m.group(1)
                amount_str = m.group(2)
                val = parse_amount_kor(amount_str)
                total += val
                per_person[name] = per_person.get(name, 0) + val

    # 정렬: 금액 큰 순
    per_person_sorted = sorted(per_person.items(), key=lambda x: x[1], reverse=True)
    return total, per_person_sorted

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "붙여넣기만 하면 ‘메모’ 바로 밑 줄의 금액을 전부 더해드려요.\n"
        "예시 입력:\n\n"
        "메모\n이승한 150000원\n+106.68\n≈ 0\n\n"
        "메모\n유득경 40000\n..."
    )
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    total, per_person = extract_and_sum(text)
    if total == 0:
        await update.message.replyText("합산할 금액이 없어요. ‘메모’ 바로 아래 줄에 ‘이름 숫자’ 형태인지 확인해주세요.")
        return

    # 사람별 요약(상위 5명까지만)
    top = "\n".join([f"- {name}: {amt:,}원" for name, amt in per_person)
    resp = f"📊 합계: {total:,}원"
    if top:
        resp += f"\n\n👤 상위 5명:\n{top}"
    await update.message.reply_text(resp)

def main():
    token = TOKEN or ""
    if not token:
        raise RuntimeError("환경변수 TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Render에서 폴링 방식으로 실행
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
