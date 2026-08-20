"""행정안전부 행정표준코드관리시스템에서 법정동코드 전체자료를 내려받는다 (필요할 때만 실행).

받는 곳은 https://www.code.go.kr/stdcode/regCodeL.do 의 두 버튼이다.

  전체자료   POST /etc/codeFullDown.do          codeseId=법정동코드
             -> '법정동코드 전체자료.txt' (cp949, 탭 구분, 3열: 코드/이름/폐지여부)
  조회자료   POST /stdcode/regCodeFileDown.do   폐지구분=전체 + 선택 열 전부
             -> '법정동코드 조회자료.xlsx' (같은 레코드 + 생성일/폐지일)

파이프라인이 읽는 건 조회자료 쪽이다. 연도별 코드를 풀려면 생성일·폐지일이 있어야
하고, 그 두 열은 조회자료 다운로드에만 붙는다. 전체자료는 기관이 공표한 원본
그대로라는 뜻으로 같이 보관한다.

받은 zip은 01_raw_data/행정표준코드/ 에 날짜를 붙여 저장하고, 그 폴더의 README가
출처와 받은 날짜를 적어 둔다. 사이트가 자동 다운로드를 막으면 무엇이 막았는지
그대로 출력하고 종료한다 (임의로 코드를 만들어 채우지 않는다).
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import warnings
import zipfile

import requests

from kird import RAW

RAW_DIR = os.path.join(RAW, "행정표준코드")
LIST_URL = "https://www.code.go.kr/stdcode/regCodeL.do"
FULL_URL = "https://www.code.go.kr/etc/codeFullDown.do"
QUERY_URL = "https://www.code.go.kr/stdcode/regCodeFileDown.do"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 조회 폼의 값. 체크박스는 체크된 상태가 "0"이다 (func_choice 참고).
# disuseAt=ALL 이라야 폐지된 코드까지 나오고, 폐지 코드가 있어야 옛 시군구를 푼다.
QUERY_FORM = {
    "cPage": "1", "regionCd_pk": "", "chkWantCnt": "8",
    "reqSggCd": "", "reqUmdCd": "", "reqRiCd": "", "searchOk": "",
    "codeseId": "00002", "pageSize": "10", "regionCd": "", "locataddNm": "",
    "sidoCd": "", "sggCd": "", "umdCd": "", "riCd": "",
    "disuseAt": "ALL", "stdate": "", "enddate": "",
    "chkHigh": "0", "chkOrder": "0", "chkCrtDt": "0", "chkClsDt": "0",
    "chkLocatDt": "0", "chkLow": "0", "chkJumin": "0", "chkJijuk": "0",
}


def _session():
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    s = requests.Session()
    s.verify = False          # code.go.kr 인증서 체인이 requests 기본 번들에 없다
    s.headers.update({"User-Agent": UA, "Referer": LIST_URL})
    s.get(LIST_URL, timeout=60)   # 세션 쿠키
    return s


def _save(content: bytes, path: str, expect_member: str) -> None:
    if not content[:2] == b"PK":
        raise SystemExit(f"다운로드가 zip이 아니다 ({len(content)} bytes). 사이트가 막았는지 확인:\n"
                         + content[:400].decode("cp949", errors="replace"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if not any(expect_member in n for n in names):
        raise SystemExit(f"{path}: 기대한 파일이 없다 ({names})")
    print(f"  저장 {os.path.basename(path)}  {len(content):,} bytes  {names}")


def main(stamp: str | None = None) -> None:
    stamp = stamp or _dt.date.today().strftime("%Y%m%d")
    s = _session()
    print(f"행정표준코드 법정동코드 내려받기 ({stamp}) -> {RAW_DIR}")

    r = s.post(FULL_URL, data={"codeseId": "법정동코드"}, timeout=600)
    _save(r.content, os.path.join(RAW_DIR, f"법정동코드_전체자료_{stamp}.zip"), "전체자료")

    # pageSize 는 URL 로만 먹는다. 레코드 수보다 넉넉하게 준다.
    r = s.post(QUERY_URL + "?cPage=1&pageSize=60000", data=QUERY_FORM, timeout=900)
    _save(r.content, os.path.join(RAW_DIR, f"법정동코드_조회자료_생성폐지일자포함_{stamp}.zip"), "조회자료")
    print("done.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
