# Phonebot: Ways to Make Money

*Report, 2 Nov 2026. The market numbers come from web research done the same day. Many come from vendor or analyst pages that disagree with each other, so treat them as rough and check any figure you use with an investor or customer.*

---

## 1. Summary

Phonebot is an **AI agent with a real finger**. It takes a plain-English task ("cancel my subscription in app X"), looks at a real iPhone screen, and taps the glass. That combination is rare:

| | Software-only AI testers (GPT Driver, Revyl, QA Wolf) | Robot finger testers (Mobot, MATT, Tapster) | **Phonebot** |
|---|---|---|---|
| Understands plain-English tasks | Yes | No (scripted) | **Yes** |
| Touches a real screen (Face ID, Apple Pay, any touchscreen) | No | Yes | **Yes** |
| Works on screens with no API (kiosks, POS, cars) | No | Yes | **Yes** |
| Needs the app maker's code or build | Usually | Sometimes | **No** |

**The best bet is AI-driven physical testing and auditing, sold to businesses.** Other people's money already proves the demand:
- Mobot raised about $16–18M doing robot-only phone QA.
- QA Wolf raised a $36M Series B for AI testing.
- Assurant bought OptoFidelity's phone-testing robot business in 2025.
- Mobile app testing is about **$7–10B a year (2025)** and growing about 17% a year.

The second bet is **accessibility audits**. Since June 2025 the EU requires many apps to be accessible, and the US sees about 5,000 accessibility lawsuits a year. One app audit sells for **$1.3k–30k+**.

---

## 2. What makes it valuable

1. **No access needed.** It tests the App Store build as a user would. You don't need the app's source code, a test build, or developer accounts. That lets you audit *competitors' and third-party* apps too.
2. **Real hardware paths.** Simulators can only fake Face ID, Apple Pay sheets, 3-D Secure pop-ups, system permission dialogs, and haptics. A real finger on a real phone goes through the true path.
3. **Works on any touchscreen.** After calibration the same rig drives a kiosk, POS terminal, car screen, or watch, which is where software automation can't reach.
4. **Tests come from plain English.** A non-engineer writes "sign up, add a card, order the cheapest item". Nobody has to maintain a test script.
5. **Video as evidence.** Every run can be recorded with each step labeled. That's useful for regulators, lawyers, and bug reports.

---

## 3. Legal ways to make money: scenarios

Each scenario lists the idea, who pays, typical prices, and how to demo it. ★ is my rating of attractiveness (out of 5).

### 3.1 AI real-device QA as a service ★★★★★
- **Idea:** The customer writes test cases in English. The robot runs them every night on real iPhones, and the customer gets pass/fail results, video, and screenshots.
- **Who pays:** Mobile teams at fintech, e-commerce, travel, and health companies, especially ones whose flows need real Face ID, Apple Pay, or third-party SDK pop-ups.
- **Price benchmarks:**
  - AWS Device Farm: $0.17 per device-minute.
  - BrowserStack, Sauce Labs, Maestro: about $200–250 per device per month.
  - HeadSpin enterprise: $50k–100k+ a year.
  - Physical plus AI testing earns a premium. Start at **$1.5k–5k per month per customer** for nightly runs of 20 flows.
- **Demo:**
  - Split-screen video: on the left the English test ("Log in with Face ID, send €5 to Alice"), on the right the robot doing it.
  - Then deliberately break something and show the agent's bug report with screenshots.
  - That 60-second clip is your sales pitch.

### 3.2 Banking and fintech checks ★★★★★
- **Idea:** A regression pack for the flows that matter most: login, Face ID, card provisioning to Apple Wallet, 3-D Secure, transfers.
- **Why it pays:** Banks have large QA budgets, compliance demands evidence, and simulators can't complete these flows.
- **Demo:** Run a test bank account through Face ID login → transfer → 3-D Secure confirmation, recorded with timestamps.

### 3.3 Accessibility audits (EAA / ADA) ★★★★★
- **Idea:** The agent tries key tasks the way a user with limited dexterity or vision would. It checks VoiceOver labels, touch-target sizes, alternatives to gestures, and screen rotation (EN 301 549 chapter 11). It produces a report with videos.
- **Why now:**
  - The European Accessibility Act has applied since 28 Jun 2025.
  - French disability groups notified four big retailers within days.
  - The US had about 5,000 digital accessibility lawsuits in 2025, 70% of them against e-commerce.
- **Prices:** About $75–125 per iOS screen (12 screens ≈ $1,300). Full audits run $5k–30k+. Sell **monthly monitoring** as the upsell.
- **Demo:** Pick a well-known shopping app and show, on video, the agent failing at checkout because of an unlabeled button. Then show the report page. Use public apps only for demos, and don't publish named "fail lists" without legal advice.
- **Lead generation:** Agencies and law firms that defend accessibility cases need evidence, so sell to them as a channel.

### 3.4 Payment terminal and POS testing ★★★★
- **Idea:** Calibrate the rig over a card terminal or POS tablet, press PIN pads, tap test cards or phones, and run hundreds of transactions.
- **Why it pays:** Robots are already standard in this industry, but the existing ones (Abrantix T4, IntelliQA T1) are scripted. An AI that can follow a test spec in English is new.
- **Demo:** Robot runs 50 test purchases overnight and shows a success rate and timing chart.

### 3.5 Kiosks, cars, and other embedded touchscreens ★★★★
- **Targets:**
  - Airport check-in and self-order kiosks (McDonald's-style)
  - EV chargers, ticket machines
  - Car infotainment screens (Göpel and RINF TECH already sell robot testing for these)
  - Smart-home panels, medical and industrial control screens
- **Model:** A rig on site, rented monthly ($1–3k a month), plus a setup fee.
- **Demo:** Mount the rig over a cheap Android tablet running a kiosk-style app and order a burger from an English prompt.

### 3.6 Grading used phones for refurbishers ★★★★
- **Idea:** Check every touch area, the screen, Face ID setup and buttons, and produce a grade certificate. Assurant buying OptoFidelity's robots and Revendo using MATT show the demand.
- **Who pays:** Refurbishers, trade-in programs, carriers.
- **Demo:** A grid tap test across the whole screen that finds a dead touch zone on a damaged phone and produces a PDF certificate.

### 3.7 Competitive UX teardowns ★★★
- **Idea:** "How many taps to cancel Netflix vs Spotify vs Disney+?" "How long does sign-up take in 5 neobanks?" The deliverable is a video plus metrics.
- **Who pays:** Product teams, consultancies, VC due diligence (consumer app bets), journalists.
- **Price:** $2k–10k per report, or a subscription to quarterly benchmark reports.
- **Demo:** Publish one free teardown as content (see 3.11). It doubles as marketing.

### 3.8 Dark-pattern and consumer-protection evidence ★★★
- **Idea:** Record, with timestamps and repeatable steps, how hard it is to cancel, hidden fees at checkout, and pre-ticked boxes.
- **Who pays:** Consumer groups (Which?, Test-Aankoop), regulators, class-action law firms, journalists.
- **Why physical matters:** Evidence from a real, unmodified device on a real account is hard to dispute.

### 3.9 Localization and global checks ★★★
- **Idea:** Run the same flow with the phone set to 15 languages and regions, screenshot every screen, and flag cut-off text and untranslated strings.
- **Who pays:** Apps launching in new markets, localization agencies.

### 3.10 Game and app onboarding analysis ★★★
- **Idea:** Play the first 10–30 minutes of new games and measure ad frequency, pay-wall timing, and tutorial friction.
- **Who pays:** Game studios (benchmarking competitors), user-acquisition agencies, game market-intelligence firms.
- **Also:** Touch-to-screen latency and battery-drain benchmarks, the way DXOMARK and consumer groups test with robot fingers.

### 3.11 Content, demos, and prizes ★★★ (fast money, also marketing)
- "AI robot orders pizza by itself" and "AI robot vs. the hardest cancellation flow" videos.
- Hardware-build channels can get big; Stuff Made Here has about 4.3M subscribers.
- Estimates: ads earn $6–18 and tech sponsorships $30–60 per 1,000 views.
- **Hackathons** (check the official sites):
  - lablab.ai *Rise of AI Agents* ($60k pool)
  - AWS *Agents for Humans* ($40k)
  - Berlin Robotics & AI Hackathon (21–22 Nov 2026, €10k+)
  - AMD AI DevMaster Physical AI track
- Content builds trust for the B2B offers. Every video should end with "we do this for your app".

### 3.12 Assistive "phone helper" ★★★ (meaningful, slower)
- **Idea:** For people with motor disabilities, or elderly users, the robot operates their own phone for them by voice ("book my doctor's appointment", "call my daughter on WhatsApp").
- **Gap:** No commercial product exists; only research prototypes.
- **Funding paths:**
  - Medi-Cal has covered assistive robotic arms since Sep 2024 (benchmark: the Obi feeding robot costs about $8.2k).
  - NIDILRR grants on AI assistive technology (next cycle after the Jul 2026 close).
  - Microsoft AI for Accessibility (verify the deadline).
- **Demo:** A user in a wheelchair says "send my location to my brother", and the robot does it on their own phone.

### 3.13 Legacy apps with no API ("RPA for phones") ★★
- **Idea:** Some business workflows only exist in a mobile app: supplier portals, delivery-driver apps, POS admin. The robot does the repetitive data entry.
- **Caution:** Only on the customer's own accounts, and only where the app's terms allow automation.

### 3.14 Price and availability monitoring ★★ (legally risky)
- **Idea:** Check delivery fees, ride prices, and stock across cities.
- **Market:** Measurable AI, Edison Trends, and DataWeave sell this data.
- **Legal:** *Meta v. Bright Data* (2024) favored scraping public data while logged out. *hiQ v. LinkedIn* ended against hiQ over breach of terms and fake accounts. **A robot inside logged-in apps is on the risky side.** Do this only with the platform's permission or for the customer's own app.

---

## 4. Business models

| Model | What you sell | Revenue shape | Fit |
|---|---|---|---|
| **Robot lab as a service** | Rack of phones + robots in your space; customers submit English tests through a web UI or API | Monthly per device / per run | Main business (3.1–3.3) |
| **Audit projects** | One-off reports (accessibility, UX teardown, dark patterns) | $1.3k–30k per project | Fast first revenue |
| **On-site rig rental** | Rig mounted over a customer's kiosk, POS, or car screen | Setup + $1–3k a month | 3.4, 3.5 |
| **Kit + software licence** | Frame, stylus, calibration and agent software | Hardware $1–2k + software subscription | Benchmarks: Prusa kit about $949–1,100, OpenBuilds LEAD $1.8–2.3k; Tapster sold robots at about $750 |
| **Skill packs** | Ready-made app skills (banking pack, delivery pack, accessibility checks) | Per-pack or add-on subscription | Upsell on any of the above |
| **Content + sponsorship** | Videos, teardowns, hackathon wins | Ads, sponsors, prizes | Marketing channel |

---

## 5. Demo playbook

**Rule:** every demo is under 90 seconds, starts with one sentence of English, and ends with a deliverable (report, chart, certificate).

| # | Demo | Audience | What to show |
|---|---|---|---|
| 1 | "English to test" | QA buyers | Type a test → robot runs it → bug report with screenshots |
| 2 | Face ID + Apple Pay | Fintech | A flow simulators can't run, done on real hardware |
| 3 | Accessibility fail | Compliance, legal | Agent can't find an unlabeled button → EAA/WCAG report page |
| 4 | Cancel-subscription race | Public, press | Tap counts across 3 apps, side-by-side video |
| 5 | Kiosk burger order | Kiosk/POS makers | Rig on an Android tablet, order from a prompt |
| 6 | Dead-zone grading | Refurbishers | Full-screen tap grid finds a broken area → PDF grade |
| 7 | Overnight reliability | Every B2B buyer | 200 runs, success rate chart. This proves the robot is reliable, which is the first objection |

**Demo setup checklist:**
- A **second camera** filming the robot from the side, edited next to the AirPlay screen.
- Show the agent's **plan and steps** from the web page as an overlay.
- Use test accounts only; blur personal data.
- Keep a short failure clip that shows the agent noticing a missed tap and retrying. It builds trust.

---

## 6. 90-day plan

| Weeks | Goal |
|---|---|
| 1–2 | Reliability: 95%+ tap success on 10 standard flows. Record demos 1, 4, 7. |
| 3–4 | Build the reports: test report (video + steps + pass/fail) and accessibility report. |
| 5–6 | 3 free pilot audits for local fintech or e-commerce apps, in exchange for a testimonial. |
| 7–8 | Publish the "cancel-subscription race" video and enter one hackathon. |
| 9–12 | Turn pilots into paid monthly plans. Second rig on an Android tablet for the kiosk demo. Decide between lab-service and kit. |

**Things to build in the codebase:**
- Run recorder (video + step log)
- Report generator
- Scheduled test runs
- Android support
- Multi-rig queue
- Customer-facing API

---

## 7. Illegal uses: risk register (not a playbook)

These are the obvious ways a system like this gets abused for money. They're listed so you can **recognise, refuse, and design against them**, not as plans. Every one is fraud or a terms-of-service violation, and platforms catch them at scale.

| Misuse | Why it's illegal or banned | Enforcement facts |
|---|---|---|
| Fake reviews and ratings | FTC Consumer Review Rule (effective Oct 2024); UK DMCC Act (Apr 2025) | FTC: up to **$53,088 per violation**, each review counted separately. UK CMA: fines up to **10% of global turnover**. Amazon sued the review brokers AppSally and Rebatest (900k members). |
| Fake followers, views, engagement | Banned by the same FTC rule; platform terms | Apple deactivated **129M accounts** for spam and review manipulation in 2024. |
| Ad click and app-install fraud (phone farms) | Wire fraud | Methbot/3ve: 8 indicted, about $15M recovered, prison sentences. AppsFlyer and others list phone farms as a detected fraud category. |
| Streaming-royalty fraud (bot plays) | Wire fraud, money laundering | Michael Smith used bots to stream AI songs, made about $8–10M, and pleaded guilty. |
| Bonus and referral abuse, multiple accounts | Fraud; breach of contract | bet365 offer abuse: 7 people charged (UK). PayPal blamed bots for about 4.5M illegitimate accounts. |
| Logged-in data harvesting against terms | Breach of contract, possibly computer misuse | hiQ v. LinkedIn ended in a permanent injunction. |
| Getting around CAPTCHAs, identity checks, or anti-bot systems | Computer misuse laws, terms violations | Apple blocked $2B in fraud and 711M fraudulent account creations in 2024. |
| Operating someone's phone without consent | Unauthorized access, privacy law | Criminal in most countries. |

**Why it's a bad business even ignoring the law:** A physical robot is slow, about 1–2 seconds per action. Phone farms compete on scale and cost per device, so a slow robot loses on cost to the operations that get caught anyway. Phonebot's edge is **understanding and real-hardware truth**, which only pays in the legal markets above.

**Safeguards to build into the product (these also help sales):**
- The system prompt and policy refuse tasks that post reviews, inflate engagement, create accounts in bulk, claim sign-up bonuses, or get around CAPTCHAs or identity checks.
- One real customer per account; keep an **audit log** of every run (task, video, operator).
- Terms of service for customers that ban the uses above.
- Rate limits per app/account so the lab can't be used as a farm.
- A clear compliance story makes selling to banks and enterprises easier.

---

## 8. Main sources

**Market and competitors**
- Mobot funding: techcrunch.com/2022/08/15/mobot-secures-capital-to-grow-its-fleet-of-robots-that-bug-test-mobile-apps
- QA Wolf Series B: techcrunch.com/2024/07/23/qa-wolf-secures-36m-to-grow-its-app-qa-testing-suite
- Assurant / OptoFidelity: businesswire.com/news/home/20250930467656/en

**Pricing**
- AWS Device Farm: aws.amazon.com/device-farm/pricing
- Firebase Test Lab: firebase.google.com/docs/test-lab/usage-quotas-pricing
- Maestro: maestro.dev/pricing
- BrowserStack: browserstack.com (press)
- Market size: mordorintelligence.com/industry-reports/mobile-application-testing-services-market

**Physical testing references**
- MATT robot: een.ec.europa.eu/node/40106
- Abrantix T4: bisinfotech.com/?p=139826
- Göpel infotainment testing: goepel.com
- DXOMARK battery tests: dxomark.com/how-dxomark-tests-the-smartphone-battery-experience

**Accessibility**
- EAA: insideglobaltech.com/2025/06/10/european-accessibility-act-june-2025-deadline-has-arrived
- Audit pricing: accessible.org/how-much-digital-accessibility-audit-cost
- AudioEye pricing: audioeye.com/post/web-accessibility-audit-cost

**Scraping law**
- Meta v. Bright Data: fbm.com (publication)
- hiQ v. LinkedIn: proskauer.com (blog)

**Enforcement**
- FTC rule: venable.com/insights/publications/2025/12/ftc-signals-heightened-enforcement-of-new
- UK CMA: fieldfisher.com
- Apple fraud figures: appleinsider.com/articles/25/05/27/app-store-protected-users-from-9-billion-in-fraud-over-five-years
- Methbot/3ve: justice.gov/usao-edny
- Streaming fraud: musicbusinessworldwide.com

**Assistive**
- Medi-Cal robotic arms: disabilityrightsca.org/publications/how-to-get-medi-cal-to-cover-an-assistive-robotic-arm
