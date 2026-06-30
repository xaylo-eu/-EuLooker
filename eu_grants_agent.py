# ╔══════════════════════════════════════════════════════════════════╗
# ║   EuLooker – EC Funding Monitor  |  v7.1                       ║
# ║   Changes v7:                                                   ║
# ║   - Reads users.json, sends individual email per user           ║
# ║   - Respects interval: 7 / 14 / 30 days                        ║
# ║   - AND logic: area + organisation type                         ║
# ║   - Custom user keywords                                        ║
# ║   Changes v7.1:                                                 ║
# ║   - FIX: skip calls whose deadline has already passed,          ║
# ║     instead of relying only on EC API "status" field            ║
# ╚══════════════════════════════════════════════════════════════════╝

import requests, json, re, time, os, smtplib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration ─────────────────────────────────────────────────
EMAIL_SENDER   = "mecasysdata@gmail.com"
EMAIL_PASSWORD = os.environ.get('EMAIL_HESLO', 'jeze ycaa dpty cvll')
USERS_FILE     = "users.json"
HISTORY_FILE   = "seen_identifiers.json"

# ── Programme ID → name ───────────────────────────────────────────
PROGRAMME_MAP = {
    "43108390": "Horizon Europe", "44181033": "EDF",
    "43152860": "Digital Europe", "43252405": "LIFE",
    "43251567": "CEF Energy",     "43251589": "CERV",
    "43252368": "ISF",            "43252476": "SMP / COSME",
    "43252517": "ESF+",           "43298916": "Euratom",
    "43353764": "Erasmus+",       "43637601": "PPPA",
    "44416173": "Interreg / I3",
}

# ── Organisation types → keywords ────────────────────────────────
ORG_TYPE_KW = {
    "SME":                   ["sme","small and medium","smes","eic accelerator","cascade financing","for smes"],
    "Large Enterprise":      ["large enterprise","large company","large industry","for-profit","private company"],
    "University / HEI":      ["higher education","university","academic institution","hei","academia"],
    "Research Org. (RTO)":   ["research organisation","research organization","research center","rto","research institute"],
    "Public Sector":         ["public body","public authority","municipality","local authority","public administration"],
    "NGO / Association":     ["non-governmental","ngo","association","cluster","foundation","civil society"],
    "Startup / Spin-off":    ["startup","start-up","spin-off","spin-out","deep tech","eic pathfinder","scaleup"],
    "International Org.":    ["international organisation","international organization","intergovernmental","multilateral"],
}

# ── Areas of interest → keywords ─────────────────────────────────
AREAS_KW = {
    "Manufacturing / Industry 4.0": [
        "industry 4.0","industry 5.0","advanced manufacturing","smart factory",
        "digital twin","industrial automation","cobots","additive manufacturing",
        "3d printing","industrial iot","made in europe","factory of the future",
        "cyber-physical","smart manufacturing","industrial transformation",
        "manufacturing excellence","production technology","automation technology",
        "industrial robot","lean manufacturing","supply chain","quality control",
        "testing facilities","cnc","industrial digitali",
    ],
    "AI / Robotics / Deep Tech": [
        "artificial intelligence","machine learning","robotics","autonomous systems",
        "deep learning","generative ai","computer vision","edge computing",
        "quantum computing","apply ai","neural network","natural language processing",
        "nlp","large language model","trustworthy ai","explainable ai","ai safety",
        "human-robot interaction","embedded ai","foundation model","data-driven",
    ],
    "Green Energy / Climate": [
        "renewable energy","green hydrogen","carbon capture","energy storage",
        "solar energy","wind energy","net zero","decarbonisation","energy efficiency",
        "smart grid","clean energy","offshore wind","heat pump","district heating",
        "photovoltaic","battery storage","power grid","electrolysis","biofuel",
        "geothermal","tidal energy","carbon neutral","carbon footprint","emission reduction",
    ],
    "Agro / Bio / Circular": [
        "precision agriculture","smart farming","bioeconomy","bio-based","biodegradable",
        "sustainable packaging","soil health","microbiome","agritech","biomaterial",
        "food security","crop monitoring","bioreactor","fermentation","composting",
        "waste valorisation","biopolymer","green chemistry","plant-based","agroecology",
        "food system","circular bioeconomy",
    ],
    "Health / Medicine / Biotech": [
        "medical device","diagnostics","drug development","clinical trial",
        "personalised medicine","digital health","cancer research","biotechnology",
        "antimicrobial","genomics","vaccine","proteomics","wearable health",
        "mental health","telemedicine","rehabilitation","medical ai","in vitro",
        "cell therapy","rare disease","health data","patient","hospital",
    ],
    "Defence / Security / Drones": [
        "drone","uav","unmanned","defence","dual-use","counter-drone",
        "border surveillance","cbrn","naval","underwater","security technology","swarm",
        "autonomous underwater","auv","counter-uas","situational awareness",
        "cybersecurity","critical infrastructure","explosive detection",
        "surveillance","radar","military","defense",
    ],
    "Space Tech": [
        "satellite","earth observation","space exploration","copernicus","galileo",
        "new space","remote sensing","space transportation","launch vehicle",
        "reusable rocket","in-orbit","space debris","lunar","space manufacturing",
        "cubesat","nanosatellite","space economy","esa","on-orbit",
    ],
    "Mobility / Transport / Smart City": [
        "electric vehicle","autonomous driving","urban mobility","smart city",
        "zero emission vehicle","battery technology","hydrogen vehicle","sustainable transport",
        "charging infrastructure","vehicle to grid","fleet management",
        "micro-mobility","autonomous bus","rail","traffic management",
        "connected vehicle","automated mobility","ccam","logistics","last mile",
    ],
    "Water / Oceans / Environment": [
        "water purification","ocean cleaning","marine litter","water quality",
        "blue economy","wastewater","aquaculture","desalination",
        "flood risk","drought","groundwater","ocean acidification",
        "marine ecosystem","plastic recycling","wetland","river restoration",
        "water reuse","water management","marine protected",
    ],
    "Education / Social Innovation": [
        "education technology","vocational training","digital skills","social innovation",
        "edtech","reskilling","upskilling","vocational excellence",
        "lifelong learning","micro-credential","apprenticeship","youth employment",
        "inclusion","disability","rural development","stem education",
        "higher education","skills gap","community","social enterprise",
    ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════

def p(msg): print(msg, flush=True)

def _strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    return re.sub(r'\s+', ' ', text).strip()

def _summarize(text, sentences=4):
    if not text or len(text) < 40: return text or '—'
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    sents = [s.strip() for s in sents if len(s.strip()) > 20]
    if not sents: return (text[:500] + '…') if len(text) > 500 else text
    r = ' '.join(sents[:sentences])
    return (r[:800] + '…') if len(r) > 800 else r

def _contains(text, keywords):
    t = text.lower()
    for w in keywords:
        if len(w.split()) > 1:
            if w in t: return True
        else:
            if re.search(r'\b' + re.escape(w) + r's?\b', t): return True
    return False

def _find(text, keywords):
    t = text.lower()
    found = []
    for w in keywords:
        if len(w.split()) > 1:
            if w in t: found.append(w)
        else:
            if re.search(r'\b' + re.escape(w) + r's?\b', t): found.append(w)
    return found

def _programme_name(programme_id):
    return PROGRAMME_MAP.get(str(programme_id), str(programme_id))

def _ts_to_dt(ts_ms):
    try:
        return datetime(1970,1,1,tzinfo=timezone.utc) + timedelta(milliseconds=int(ts_ms))
    except:
        return None

# ── FIX v7.1: check whether a call's deadline has already passed ──
# EC API's "status" field sometimes stays "Open"/"Forthcoming" for days
# after the real deadline, so we verify locally against today's date
# (UTC) instead of trusting status alone.
def _is_past_deadline(deadline_raw):
    if not deadline_raw:
        return False  # no date available — don't block
    try:
        deadline_dt = datetime.strptime(deadline_raw[:10], "%Y-%m-%d").date()
        return deadline_dt < datetime.now(timezone.utc).date()
    except ValueError:
        return False  # unparsable date — don't block

# ══════════════════════════════════════════════════════════════════
# INTERVAL LOGIC
# ══════════════════════════════════════════════════════════════════

def should_send(user):
    """Returns True if user should receive email today."""
    interval_raw = user.get('interval', '7days')

    if '7' in str(interval_raw):
        days = 7
    elif '14' in str(interval_raw):
        days = 14
    elif '30' in str(interval_raw):
        days = 30
    else:
        days = 7

    last_sent = user.get('last_email') or user.get('posledny_email')
    if not last_sent:
        return True, days

    try:
        dt_last  = datetime.strptime(last_sent, '%Y-%m-%d').date()
        dt_today = datetime.now().date()
        diff     = (dt_today - dt_last).days
        return diff >= days, days
    except:
        return True, days

# ══════════════════════════════════════════════════════════════════
# API CALLS
# ══════════════════════════════════════════════════════════════════

def search_keyword(keyword, page=1):
    url = f"https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text={keyword}&pageSize=50&pageNumber={page}"
    files = {
        "sort"     : (None, json.dumps({"order": "DESC", "field": "startDate"}), "application/json"),
        "query"    : (None, json.dumps({"bool": {"must": [
                        {"terms": {"type": ["1","2","8"]}},
                        {"terms": {"status": ["31094501","31094502"]}}
                     ]}}), "application/json"),
        "languages": (None, json.dumps(["en"]), "application/json"),
    }
    r = requests.post(url, files=files, headers=HEADERS, timeout=30)
    return r.json()

def get_detail(identifier):
    url = f"https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{identifier.lower()}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json().get('TopicDetails', {})
    except:
        pass
    return {}

# ══════════════════════════════════════════════════════════════════
# FIND CALLS FOR USER
# ══════════════════════════════════════════════════════════════════

def find_calls_for_user(user, history):
    """Finds new relevant calls for a specific user."""
    email      = user['email']
    # Support both old (Slovak) and new (English) field names
    org_type   = user.get('org_type') or user.get('typ_org', '')
    areas      = user.get('areas') or user.get('oblasti', [])
    kw_custom  = user.get('kw_custom', [])

    # Collect keywords
    org_kw     = ORG_TYPE_KW.get(org_type, [])
    area_kw    = []
    search_kws = []

    for area in areas:
        for name, kw_list in AREAS_KW.items():
            if name in area or area in name:
                area_kw.extend(kw_list)
                search_kws.extend(kw_list)
                break

    # Add custom keywords
    area_kw.extend(kw_custom)
    search_kws.extend(kw_custom)
    search_kws.extend(org_kw[:3])
    search_kws = list(set(search_kws))

    p(f"  🔍 Searching for {email}: {len(search_kws)} keywords, {len(areas)} areas, type: {org_type}")

    # Fetch calls
    all_raw = {}
    for kw in search_kws:
        try:
            data  = search_keyword(kw)
            total = data.get('totalResults', 0)
            pages = min((total + 49) // 50, 3)
            for page in range(1, pages + 1):
                if page > 1:
                    data = search_keyword(kw, page)
                for hit in data.get('results', []):
                    ident = hit['metadata']['identifier'][0]
                    if ident not in all_raw:
                        all_raw[ident] = hit
            time.sleep(0.3)
        except Exception as e:
            p(f"    ⚠️ Error for '{kw}': {e}")

    p(f"  Calls fetched: {len(all_raw)}")

    # Filter — only new (not in history)
    new_ids = [i for i in all_raw if i not in history]
    p(f"  New (unseen): {len(new_ids)}")

    # Classify with AND filter
    results = []
    expired_skipped = 0
    for ident in new_ids:
        hit    = all_raw[ident]
        meta   = hit['metadata']

        # ── FIX v7.1: drop calls whose deadline has already passed ──
        deadline_raw = meta.get('deadlineDate', [''])[0][:10]
        if _is_past_deadline(deadline_raw):
            expired_skipped += 1
            continue

        detail = get_detail(ident)
        if not detail:
            time.sleep(0.2)
            continue

        title = hit.get('summary', '')
        desc  = _strip_html(detail.get('description', ''))
        ft    = f"{title} {desc}".lower()

        has_area = _contains(ft, area_kw)
        has_org  = _contains(ft, org_kw) if org_kw else True

        if has_area and has_org:
            prog_raw = meta.get('frameworkProgramme', [''])[0]
            results.append({
                'identifier': ident,
                'title'     : title,
                'programme' : _programme_name(prog_raw),
                'status'    : meta.get('status', [''])[0],
                'startDate' : meta.get('startDate', [''])[0][:10],
                'deadline'  : deadline_raw,
                'summary'   : _summarize(desc, 4),
                'link'      : meta.get('url', [''])[0],
                'kw_area'   : _find(ft, area_kw)[:4],
                'kw_org'    : _find(ft, org_kw)[:2],
            })
        time.sleep(0.3)

    p(f"  Relevant calls: {len(results)}  |  Skipped (expired deadline): {expired_skipped}")

    # Add all fetched to history (including those that didn't match)
    new_history = {**history, **{i: datetime.now().strftime('%Y-%m-%d') for i in all_raw}}

    return results, new_history

# ══════════════════════════════════════════════════════════════════
# EMAIL (English only)
# ══════════════════════════════════════════════════════════════════

def send_email(user, results, days):
    email     = user['email']
    org_type  = user.get('org_type') or user.get('typ_org', '')
    areas     = user.get('areas') or user.get('oblasti', [])
    areas_str = ', '.join(areas)
    date_str  = datetime.now().strftime('%d %B %Y')
    interval  = f"every {days} days"

    if not results:
        subject = f"EuLooker – {date_str} – No new calls found"
        html = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:780px;margin:auto;padding:24px;">
          <div style="background:#1a2340;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
            <h1 style="margin:0;font-size:20px;">📢 EuLooker – {date_str}</h1>
          </div>
          <div style="border:1px solid #dde3ea;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
            <p style="font-size:15px;margin-bottom:12px;">
              No new calls were found for your profile this week.
            </p>
            <p style="font-size:13px;color:#555;margin-bottom:20px;">
              <b>Organisation type:</b> {org_type} &nbsp;·&nbsp;
              <b>Areas:</b> {areas_str}
            </p>
            <hr style="border:none;border-top:1px solid #e0e6ef;margin:16px 0 12px;">
            <p style="font-size:12px;color:#888;">
              EuLooker · Interval: {interval}<br>
              <a href="https://xaylo-eu.github.io/EuLooker" style="color:#1565c0;">Change your settings</a>
            </p>
          </div>
        </body></html>"""
    else:
        subject = f"EuLooker – {date_str} – {len(results)} new calls found"
        cards = ""
        for v in results:
            kw_area = ", ".join(v['kw_area']) if v['kw_area'] else "—"
            kw_org  = ", ".join(v['kw_org'])  if v['kw_org']  else "—"
            status  = "🟢 Open" if v['status'] == "31094501" else "🟡 Forthcoming"
            cards += f"""
            <div style="border:1px solid #dde3ea;border-radius:8px;padding:16px 20px;
                        margin-bottom:16px;background:#fafbfc;">
              <h3 style="margin:0 0 6px;color:#1a2340;font-size:14px;">{v['title']}</h3>
              <p style="margin:0 0 6px;font-size:12px;color:#555;">
                <b>Programme:</b> {v['programme']} &nbsp;|&nbsp;
                {status} &nbsp;|&nbsp;
                <b>Opening:</b> {v['startDate']} &nbsp;|&nbsp;
                <b>Deadline:</b> {v['deadline']}
              </p>
              <p style="margin:0 0 8px;font-size:13px;color:#333;line-height:1.6;">{v['summary']}</p>
              <p style="margin:0 0 4px;font-size:11px;color:#777;">
                <b>Area keywords:</b> {kw_area} &nbsp;|&nbsp;
                <b>Org keywords:</b> {kw_org}
              </p>
              <a href="{v['link']}" style="color:#1565c0;font-size:12px;">🔗 View call →</a>
            </div>"""

        html = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:780px;margin:auto;padding:24px;">
          <div style="background:#1a2340;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
            <h1 style="margin:0;font-size:20px;">📢 EuLooker – {date_str}</h1>
            <p style="margin:6px 0 0;font-size:14px;opacity:.85;">
              {len(results)} new relevant calls found
            </p>
          </div>
          <div style="border:1px solid #dde3ea;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
            <p style="font-size:13px;color:#555;margin-bottom:20px;">
              <b>Organisation type:</b> {org_type} &nbsp;·&nbsp;
              <b>Areas:</b> {areas_str} &nbsp;·&nbsp;
              <b>Interval:</b> {interval}
            </p>
            {cards}
            <hr style="border:none;border-top:1px solid #e0e6ef;margin:24px 0 12px;">
            <p style="font-size:12px;color:#888;">
              EuLooker ·
              <a href="https://xaylo-eu.github.io/EuLooker" style="color:#1565c0;">Change your settings</a> ·
              <a href="https://ec.europa.eu/info/funding-tenders/opportunities/portal" style="color:#1565c0;">EC Portal</a>
            </p>
          </div>
        </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, email, msg.as_string())
        p(f"  ✅ Email sent to {email} ({len(results)} calls)")
        return True
    except Exception as e:
        p(f"  ❌ Email error for {email}: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# HISTORY & USERS
# ══════════════════════════════════════════════════════════════════

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return {i: "unknown" for i in data}
            return data
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    p("=" * 60)
    p(f"EuLooker v7 – {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    p("=" * 60)

    users   = load_users()
    history = load_history()

    p(f"\n👥 Total users: {len(users)}")

    if not users:
        p("⚠️  No users found in users.json")
        return

    today       = datetime.now().date()
    processed   = 0
    skipped     = 0
    new_history = dict(history)

    for user in users:
        email = user.get('email', '?')
        p(f"\n{'─'*50}")
        p(f"👤 {email}")

        # Check interval
        send, days = should_send(user)
        if not send:
            last = user.get('last_email') or user.get('posledny_email', '?')
            p(f"  ⏭️  Skipping — last email: {last}, interval: {days} days")
            skipped += 1
            continue

        p(f"  📨 Sending calls (interval: {days} days)")

        # Find calls
        results, new_history = find_calls_for_user(user, new_history)

        # Send email
        success = send_email(user, results, days)

        if success:
            # Update last email date
            user['last_email'] = today.strftime('%Y-%m-%d')
            processed += 1

    # Save updated users and history
    save_users(users)
    save_history(new_history)

    p(f"\n{'='*60}")
    p(f"✅ Done! Processed: {processed}, Skipped: {skipped}")
    p(f"History: {len(new_history)} calls")
    p("=" * 60)

if __name__ == "__main__":
    main()
