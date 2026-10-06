# Job Monitor

סורק כל 30 דקות את מערכות הגיוס של חברות היעד, מסנן משרות ג'וניור ב-Embedded / Firmware / Network בישראל,
ושולח לטלגרם רק משרות חדשות. רץ בחינם על GitHub Actions.

## איך זה עובד
1. לכל חברה ב-`companies.yaml` יש מקור: Workday, Greenhouse, Lever, Comeet, SmartRecruiters או Amazon.
   לחברות שמסומנות `detect` הכלי מזהה לבד את מערכת הגיוס מדף הקריירה (ושומר את התוצאה).
2. כל משרה נשמרת לפי ה-ID שלה במקור, אז משרה שכבר ראית לא תגיע שוב.
3. סינון: כותרת (`config.yaml`) ← מיקום בישראל ← דרישת שנות ניסיון מתוך תיאור המשרה.
   שורות שמסומנות כיתרון ("advantage", "יתרון", "Nice to have") לא נספרות.
4. 🟢 = מתאים. 🟡 = הכותרת מתאימה אבל לא צוין ותק, שווה מבט.

## הקמה (פעם אחת, ~15 דקות, עדיף ממחשב)

**1. בוט טלגרם**
- בטלגרם: פתח את `@BotFather` ← `/newbot` ← תן שם. תקבל **token**.
- שלח לבוט החדש הודעה כלשהי (למשל `hi`).
- פתח בדפדפן: `https://api.telegram.org/bot<TOKEN>/getUpdates` וחפש `"chat":{"id":...}` — זה ה-**chat id**.

**2. ריפו ב-GitHub**
- צור ריפו חדש, **Private**, בשם `job-monitor`.
- העלה את כל הקבצים מה-zip, **כולל התיקייה `.github`** (ב-Mac היא מוסתרת: Cmd+Shift+. ב-Finder).
  או מהטרמינל:
  ```bash
  cd job-monitor
  git init && git add . && git commit -m "job monitor"
  git branch -M main
  git remote add origin https://github.com/<USER>/job-monitor.git
  git push -u origin main
  ```

**3. סודות**
Settings ← Secrets and variables ← Actions ← New repository secret:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

**4. ריצה ראשונה**
Actions ← job-monitor ← Run workflow. תקבל בטלגרם:
- סיכום זיהוי מערכות הגיוס של החברות שסומנו `detect`.
- "קו בסיס נשמר" + עד 10 משרות שפתוחות כרגע ומתאימות לך.
מכאן והלאה הוא רץ לבד כל 30 דקות ושולח רק משרות חדשות. אם אין חדשות — שקט.

## כיוונון
- `config.yaml` — מילות מפתח בכותרת, מילים שפוסלות, ערים, `max_years`, ושליחת 🟡.
- `companies.yaml` — הוספת חברה: אם ידוע ה-ATS, `ats` + `board`; אחרת `status: detect` + `domain`.
- בדיקה מקומית: `pip install -r requirements.txt` ואז `python -m monitor --dry-run --only nvidia -v`.

## דקות GitHub
בריפו פרטי יש 2,000 דקות חינם בחודש, וכל ריצה נספרת כדקה לפחות. ריצה כל 30 דקות ≈ 1,440 דקות.
אחרי כמה ימים בדוק ב-Settings ← Billing. אם מתקרב לגבול: שנה את ה-cron ל-`7 * * * *` (פעם בשעה),
או הפוך את הריפו לציבורי (אז אין הגבלה, והסודות עדיין מוסתרים).

## התראות תקלה
מקור שנכשל 6 ריצות ברצף (~3 שעות) שולח ⚠️ לטלגרם פעם אחת, עד שהוא חוזר לעבוד.

## מה עוד לא מכוסה (שלב 2)
- לוחות ישראליים: דרושים, AllJobs (חברות השמה, אלביט, ACM ועוד).
- freehire API כרשת רחבה לחברות שלא ברשימה.
- adapters: Oracle (TI, Oracle), Eightfold (Microsoft), Apple, Google, SuccessFactors (Teva).
- אתרים ייעודיים: אלביט, תעשייה אווירית, רפאל, צ'ק פוינט.
