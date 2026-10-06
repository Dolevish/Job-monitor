# אימות כיסוי חברות

בדיקת רשת מלאה בוצעה ב-2026-10-06 באמצעות `python -m monitor --dry-run -v`.
לא נשלחו הודעות לטלגרם ולא שונה state קיים. 105 בדיקות קוד עברו.

מתוך 72 רשומות חברה: נוסתה שליפה עבור 70 רשומות דרך 68 מקורות נפרדים.
67 רשומות החזירו משרות ללא כשל בהורדת תיאורי המשרות שעברו את הסינון הראשוני; 2 מקורות ריקים, 1 כשלו ו-2 נותרו ללא מקור פעיל.
במקורות הנפרדים נמשכו 7,261 משרות לפני סינון. המספר כולל משרות שאינן בישראל ואינו מספר ההתאמות.

הטבלה היא צילום מצב של הבדיקה, לא הבטחה לזמינות עתידית. `coverage.json` המצורף לכל ריצת Actions הוא הדוח העדכני לאותה ריצה.
מקור חלופי עשוי להיות חלקי או להתעדכן באיחור. בדיקת רשימה תקינה אינה מאמתת פרטי משרות שנפסלו כבר לפי כותרת/מיקום.

| חברה | מקור | תוצאה | משרות |
|---|---|---|---:|
| NVIDIA | workday | משרות נמשכו | 415 |
| Intel | workday | משרות נמשכו | 24 |
| Marvell | workday | משרות נמשכו | 10 |
| Broadcom | workday | משרות נמשכו | 1 |
| Qualcomm | eightfold | משרות נמשכו | 35 |
| KLA | workday | משרות נמשכו | 76 |
| Applied Materials | workday | משרות נמשכו | 65 |
| Texas Instruments | oracle_hcm | משרות נמשכו | 6 |
| SanDisk | smartrecruiters | ריק — דורש אימות | 0 |
| Astera Labs | greenhouse | משרות נמשכו | 182 |
| Astera Labs (Early Career) | greenhouse | משרות נמשכו | 3 |
| Annapurna Labs | amazon | משרות נמשכו | 166 |
| Amazon | amazon (משותף ל-Annapurna) | משרות נמשכו | 166 |
| Apple | apple | משרות נמשכו | 100 |
| Google | google | משרות נמשכו | 98 |
| Mobileye | lever | משרות נמשכו | 182 |
| Hailo | comeet | ללא מקור פעיל | — |
| Xsight Labs | אתר החברה: xsight | משרות נמשכו | 23 |
| NextSilicon | comeet | משרות נמשכו | 33 |
| Ceva | comeet | משרות נמשכו | 28 |
| Nova | אתר החברה: nova | משרות נמשכו | 96 |
| Nuvoton | comeet | משרות נמשכו | 16 |
| Sony Semiconductor Israel | comeet | משרות נמשכו | 7 |
| Samsung Israel R&D | jobify (חלופי) | משרות נמשכו | 18 |
| SolarEdge | jobify (חלופי) | משרות נמשכו | 48 |
| Wiliot | comeet | משרות נמשכו | 21 |
| Valens | אתר החברה: valens | משרות נמשכו | 4 |
| Arbe | comeet | משרות נמשכו | 8 |
| Innoviz | comeet | משרות נמשכו | 2 |
| Cardo | comeet | משרות נמשכו | 16 |
| Maytronics | comeet | משרות נמשכו | 44 |
| Unitronics | אתר החברה: unitronics | משרות נמשכו | 7 |
| XTEND | אתר החברה: xtend | משרות נמשכו | 33 |
| Mentee Robotics | comeet | משרות נמשכו | 8 |
| ACM | ללא מקור | ללא מקור פעיל | — |
| Elbit Systems | elbit | משרות נמשכו | 566 |
| IAI | jobify (חלופי) | משרות נמשכו | 878 |
| Rafael | jobify (חלופי) | משרות נמשכו | 315 |
| DRS RADA | comeet | משרות נמשכו | 52 |
| Cisco | workday | משרות נמשכו | 34 |
| Palo Alto Networks | workday | משרות נמשכו | 149 |
| Cato Networks | greenhouse | משרות נמשכו | 92 |
| DriveNets | comeet | משרות נמשכו | 43 |
| Check Point | jobnet (חלופי) | ריק — דורש אימות | 0 |
| Ceragon | comeet | משרות נמשכו | 47 |
| RAD | אתר החברה: rad | משרות נמשכו | 8 |
| Allot | jobify (חלופי) | משרות נמשכו | 1 |
| AudioCodes | comeet | משרות נמשכו | 14 |
| Gilat | jobify (חלופי) | משרות נמשכו | 1 |
| Silicom | אתר החברה: silicom | משרות נמשכו | 1 |
| Radware | taleo | משרות נמשכו | 33 |
| Microsoft | eightfold | משרות נמשכו | 19 |
| Oracle | oracle_hcm | משרות נמשכו | 32 |
| Nebius | greenhouse | משרות נמשכו | 362 |
| Wix | smartrecruiters | משרות נמשכו | 70 |
| Teva | successfactors | כשל | 0 |
| CyberArk | workday (משותף ל-Palo Alto) | משרות נמשכו | 149 |
| ScaleOps | greenhouse | משרות נמשכו | 57 |
| monday.com | ashby | משרות נמשכו | 93 |
| HiBob | hibob | משרות נמשכו | 79 |
| Matrix | jobify (חלופי) | משרות נמשכו | 482 |
| Ness Technologies | ness | משרות נמשכו | 225 |
| ONE Technologies | jobnet (חלופי) | משרות נמשכו | 35 |
| GAV Systems | wordpress | משרות נמשכו | 117 |
| abra | אתר החברה: abra | משרות נמשכו | 82 |
| Commit | comeet | משרות נמשכו | 155 |
| QualityAI | successfactors | משרות נמשכו | 174 |
| Aman Group | אתר החברה: aman | משרות נמשכו | 154 |
| G-STAT | אתר החברה: gstat | משרות נמשכו | 36 |
| Experis | experis | משרות נמשכו | 976 |
| Bynet | אתר החברה: bynet | משרות נמשכו | 36 |
| Deloitte | אתר החברה: deloitte | משרות נמשכו | 68 |

## מגבלות שנותרו

- **ACM:** קישור Drushim שסופק בעבר אינו מזהה עוד את המעסיק; נדרש קישור רשמי. לא הוחלפה בחברה בעלת שם דומה.
- **Hailo:** חשבון Comeet הישן הושבת. הגלאי עדיין בודק את אתר הקריירה, אך לא נמצא מקור רשימות תקין.
- **Teva:** אתר הקריירה הציבורי מפנה לדף כניסה; הניסיון מוצג ככשל, ולא כאפס משרות.
- **SanDisk ו-Check Point:** המקורות שנבדקו ריקים. עבור Check Point מדובר ב-Jobnet; האתר הרשמי חסום לסורק.
- **Unitronics:** האתר מפרסם גם משרות מחוץ לישראל, ולחלק מהמשרות חסר מיקום מפורש. המסנן אינו מניח שהן בישראל.
- **Experis:** הרשימה כוללת רשומה ללא כותרת. היא נשמרת עם מזהה המקור וכותרת המסמנת מידע חסר ואינה יוצרת התאמה לפי תחום.

Apple, Google, Oracle HCM, SuccessFactors, Taleo, Jobify, Jobnet, WordPress, Ness, Experis, abra ו-Deloitte כוללים מעבר בין עמודים עם בדיקות לסיום מוקדם ולחזרת עמודים.
מקור שנקטע אינו נשמר כקו בסיס מוצלח. ב-Jobify הספירה מתייחסת גם לשורות כפולות שמופיעות בלוח, והתוצאות מנוכות לפי מזהה משרה.

מזהים קודמים נשמרו עבור המקורות הפעילים הקיימים. אין צורך באיפוס בסיס הנתונים לאחר העדכון.
