import os, re, json, requests
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ==== 환경설정 ====
# 리포지토리 Secrets에 넣어 사용 권장 (Settings → Secrets and variables → Actions)
API_KEY  = os.getenv("NEIS_API_KEY", "").strip()
ATPT     = os.getenv("NEIS_ATPT_CODE", os.getenv("ATPT_OFCDC_SC_CODE", "E10")).strip()      # 예시: E10
SCHOOL   = os.getenv("NEIS_SCHOOL_CODE", os.getenv("SD_SCHUL_CODE", "7310449")).strip()     # 예시: 7310449

OUT_DIR = Path("docs")
OUT_JSON = OUT_DIR / "meals.json"
OUT_HTML = OUT_DIR / "index.html"

KST = ZoneInfo("Asia/Seoul")

def kst_now():
    return datetime.now(KST)

def yyyymmdd(d: datetime) -> str:
    return d.strftime("%Y%m%d")

def clean_items(s: str) -> list[str]:
    if not s:
        return []
    s = s.replace("<br/>", "\n")
    s = re.sub(r"\((?:\d+\.?)+\)", "", s)  # (1.2.5.) 같은 알레르기 숫자 제거
    s = re.sub(r"<[^>]*>", "", s)
    items = [line.strip() for line in s.splitlines() if line.strip()]
    return items

def fetch_one(date_str: str, meal_code: int) -> tuple[list[str], str]:
    """
    meal_code: 1=조식, 2=중식, 3=석식
    반환: (메뉴목록, 학교명)
    """
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": ATPT,
        "SD_SCHUL_CODE": SCHOOL,
        "MLSV_YMD": date_str,
        "MMEAL_SC_CODE": str(meal_code),
    }
    if API_KEY:
        params["KEY"] = API_KEY

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = data.get("mealServiceDietInfo", [None, {"row": []}])[1]["row"]
        if not rows:
            return ([], "")
        row = rows[0]
        items = clean_items(row.get("DDISH_NM", ""))
        school = row.get("SCHUL_NM", "")
        return (items, school)
    except Exception:
        return ([], "")

def main():
    now = kst_now()
    today = yyyymmdd(now)
    tomorrow = yyyymmdd(now + timedelta(days=1))

    # 오늘: 조(1)/중(2)/석(3), 내일: 조(1)
    meals = {"today": {"date": today}, "tomorrow": {"date": tomorrow}}
    school_name = ""

    for code, key in [(1, "1"), (2, "2"), (3, "3")]:
        items, sch = fetch_one(today, code)
        meals["today"][key] = items
        school_name = school_name or sch

    items_tmr, sch2 = fetch_one(tomorrow, 1)
    meals["tomorrow"]["1"] = items_tmr
    school_name = school_name or sch2 or "학교"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "school": school_name,
                "built_at_kst": now.strftime("%Y-%m-%d %H:%M:%S"),
                "meals": meals,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # index.html 생성(접속 시점의 KST 기준으로 어느 끼니를 보여줄지 JS가 결정)
    OUT_HTML.write_text(f"""<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{school_name} 급식</title>
<style>
  :root {{ --fg:#0b0b0b; --muted:#6a6a6a; --bg:#f6f8fb; --card:#fff; }}
  html,body {{ margin:0; background:var(--bg); color:var(--fg); font-family: system-ui, -apple-system, "Segoe UI", Roboto, Pretendard, "Noto Sans KR", sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 40px 18px 80px; }}
  header h1 {{ margin:0; font-weight: 800; font-size: clamp(32px, 6vw, 56px); line-height:1.06; }}
  header .sub {{ color:var(--muted); margin-top: 6px; font-size: 15px; }}
  .bigcard {{ margin-top: 28px; background:var(--card); border-radius: 22px; padding: 26px; box-shadow: 0 20px 50px rgba(0,0,0,.08); }}
  .label {{ font-size: 18px; color:#3a6bff; font-weight:700; letter-spacing:.02em; }}
  .title {{ margin: 4px 0 12px; font-size: clamp(26px, 5vw, 40px); font-weight: 900; }}
  ul {{ font-size: clamp(18px, 2.6vw, 22px); line-height: 1.7; margin: 0; padding-left: 20px; }}
  .empty {{ color:var(--muted); font-size: 18px; }}
  footer {{ margin-top: 20px; color:var(--muted); font-size: 14px; }}
</style>
<body>
  <div class="wrap">
    <header>
      <h1 id="school">급식</h1>
      <div class="sub">접속 시점(KST) 기준으로 해당 끼니만 표시 · 데이터 갱신: <span id="built"></span> KST</div>
    </header>
    <div class="bigcard">
      <div class="label" id="slotLabel">로딩 중…</div>
      <div class="title" id="dateTitle"></div>
      <div id="content"></div>
    </div>
    <footer>Powered by GitHub Pages · GitHub Actions · NEIS OpenAPI · Copyright kkigon 2025.</footer>
  </div>

<script>
(async function() {{
  // KST 시각(사용자 로컬과 무관)
  function nowKST() {{
    const fmt = new Intl.DateTimeFormat('ko-KR', {{
      timeZone: 'Asia/Seoul', hour12:false,
      year:'numeric', month:'2-digit', day:'2-digit',
      hour:'2-digit', minute:'2-digit'
    }});
    const parts = Object.fromEntries(fmt.formatToParts(new Date()).map(p => [p.type, p.value]));
    const y = parts.year, m = parts.month, d = parts.day, hh = parts.hour, mm = parts.minute;
    return {{ y, m, d, hh: Number(hh), mm: Number(mm), ymd: y+m+d }};
  }}

  function ymdKorean(ymd){{
    return ymd.slice(0,4)+'년 '+ymd.slice(4,6)+'월 '+ymd.slice(6)+'일';
  }}

  // 정책: < 09:00 조식 / < 13:00 중식 / < 19:00 석식 / 그 이후는 내일 조식
  function decideSlot(kst, todayYMD, tomorrowYMD) {{
    const minutes = kst.hh*60 + kst.mm;
    if (minutes < 9*60)         return {{ day:'today', ymd: todayYMD, code:'1', label:'조식' }};
    if (minutes < 13*60)        return {{ day:'today', ymd: todayYMD, code:'2', label:'중식' }};
    if (minutes < 19*60)        return {{ day:'today', ymd: todayYMD, code:'3', label:'석식' }};
    return {{ day:'tomorrow', ymd: tomorrowYMD, code:'1', label:'내일 조식' }};
  }}

  try {{
    const res = await fetch('meals.json', {{ cache:'no-cache' }});
    const data = await res.json();

    document.getElementById('school').textContent = (data.school || '') + ' 급식';
    document.getElementById('built').textContent = data.built_at_kst || '';

    const todayYMD = data.meals?.today?.date;
    const tomorrowYMD = data.meals?.tomorrow?.date;
    const kst = nowKST();
    const choice = decideSlot(kst, todayYMD, tomorrowYMD);

    const items = (data.meals?.[choice.day]?.[choice.code]) || [];
    document.getElementById('slotLabel').textContent = choice.label + ' · KST ' + String(kst.hh).padStart(2,'0') + ':' + String(kst.mm).padStart(2,'0');

    // 날짜 제목
    const dateTitle = ymdKorean(choice.ymd);
    document.getElementById('dateTitle').textContent = dateTitle;

    const content = document.getElementById('content');
    if (!items.length) {{
      content.innerHTML = "<p class='empty'>해당 시간대 메뉴가 없습니다.</p>";
    }} else {{
      const lis = items.map(x => `<li>${{x}}</li>`).join('\\n');
      content.innerHTML = `<ul>${{lis}}</ul>`;
    }}
  }} catch (e) {{
    document.getElementById('slotLabel').textContent = '불러오기 오류';
    document.getElementById('content').innerHTML = "<p class='empty'>데이터를 불러올 수 없습니다.</p>";
  }}
}})();
</script>
</body></html>
""", encoding="utf-8")

if __name__ == "__main__":
    main()
