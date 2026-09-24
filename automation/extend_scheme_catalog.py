"""Reproducible reviewed catalog update, sources checked 2026-09-25."""
import json
from services.rag.repository import CATALOG, content_hash

records = json.loads(CATALOG.read_text(encoding="utf-8"))
mapping = {"pmegp": ["S001", "S002"], "cgtmse": ["S003", "S004"],
           "mudra": ["S005", "S006", "S007", "S008"]}
for record in records:
    if record["scheme_id"] in mapping:
        record["screening_ids"] = mapping[record["scheme_id"]]
    if record["scheme_id"] == "mudra":
        record["aliases"] = list(dict.fromkeys(record["aliases"] + ["shishu", "tarun", "kishore"]))

def fact(en, hi, mr):
    return {"en": en, "hi": hi, "mr": mr}

additions = [
    dict(scheme_id="cgss", scheme_name="CGSS for DPIIT Startups", screening_ids=["S010"],
         aliases=["cgss", "credit guarantee scheme for startups", "dpiit startups"],
         tags=["startup"], rules={"startup_recognized": True},
         official_url="https://www.startupindia.gov.in/content/sih/en/credit-guarantee-scheme-for-startups.html",
         source_domain="www.startupindia.gov.in", facts={
             "reason": fact("CGSS helps eligible startups obtain debt finance by guaranteeing lending institutions, rather than paying a grant directly to startups.",
                            "CGSS ऋणदाताओं को गारंटी देकर पात्र स्टार्टअप को ऋण पाने में मदद करता है; यह स्टार्टअप को सीधे अनुदान नहीं देता।",
                            "CGSS कर्जदात्यांना हमी देऊन पात्र स्टार्टअपना कर्ज मिळवण्यास मदत करते; थेट अनुदान देत नाही."),
             "eligibility": fact("DPIIT recognition is required. The startup must not be in default or classified as a non-performing asset. A member institution must certify eligibility.",
                                 "DPIIT मान्यता आवश्यक है। स्टार्टअप डिफॉल्ट में या NPA नहीं होना चाहिए। सदस्य संस्था पात्रता प्रमाणित करती है।",
                                 "DPIIT मान्यता आवश्यक आहे. स्टार्टअप थकबाकीदार किंवा NPA नसावा. सदस्य संस्था पात्रता प्रमाणित करते."),
             "benefits": fact("Debt eligible for guarantee cover is capped at Rs 20 crore per borrower. Transaction-based cover is 85% of default for loans up to Rs 10 crore and 75% above that. Apply through Jan Samarth or a member institution; the lender assesses the proposal.",
                              "गारंटी हेतु पात्र ऋण सीमा प्रति उधारकर्ता 20 करोड़ रुपये है। लेनदेन आधारित गारंटी 10 करोड़ तक के ऋण पर डिफॉल्ट का 85%, उससे ऊपर 75% है। Jan Samarth या सदस्य संस्था से आवेदन करें; ऋणदाता प्रस्ताव की जाँच करता है।",
                              "हमीसाठी पात्र कर्जाची मर्यादा प्रति कर्जदार 20 कोटी रुपये आहे. व्यवहार आधारित हमी 10 कोटीपर्यंतच्या कर्जावरील थकबाकीच्या 85%, त्यापुढे 75% आहे. Jan Samarth किंवा सदस्य संस्थेमार्फत अर्ज करा; कर्जदाता प्रस्ताव तपासतो."),
         }),
    dict(scheme_id="stand_up_india", scheme_name="Stand-Up India", screening_ids=["S009"],
         aliases=["stand-up india", "stand up india", "standup india"], tags=["greenfield"], rules={},
         official_url="https://financialservices.gov.in/stand-india-scheme-supi",
         source_domain="financialservices.gov.in", facts={
             "reason": fact("Stand-Up India supported entrepreneurship among women and Scheduled Caste/Scheduled Tribe borrowers.",
                            "Stand-Up India महिला और अनुसूचित जाति/जनजाति उद्यमियों के लिए था।",
                            "Stand-Up India महिला आणि अनुसूचित जाती/जमाती उद्योजकांसाठी होता."),
             "eligibility": fact("The published scheme targeted entrepreneurs above 18 setting up greenfield enterprises. The Department of Financial Services states its term ran up to 31 March 2025; confirm current availability before applying. A local screening match does not establish that applications are open.",
                                 "प्रकाशित योजना 18 वर्ष से अधिक आयु के नए उद्यम स्थापित करने वालों के लिए थी। वित्तीय सेवा विभाग के अनुसार अवधि 31 मार्च 2025 तक थी। आवेदन से पहले वर्तमान उपलब्धता जाँचें; स्थानीय मिलान से आवेदन खुले होने की पुष्टि नहीं होती।",
                                 "प्रकाशित योजना 18 वर्षांवरील नवीन उद्योग सुरू करणाऱ्यांसाठी होती. वित्तीय सेवा विभागानुसार मुदत 31 मार्च 2025 पर्यंत होती. अर्जापूर्वी सध्याची उपलब्धता तपासा; स्थानिक जुळणी म्हणजे अर्ज खुले असल्याची खात्री नाही."),
             "benefits": fact("Published terms described composite bank loans from Rs 10 lakh to Rs 1 crore. These are historical terms, not confirmation of a currently available offer.",
                              "प्रकाशित अटीं में 10 लाख से 1 करोड़ रुपये तक बैंक ऋण था। ये ऐतिहासिक अटीं हैं, वर्तमान उपलब्धता की पुष्टि नहीं।",
                              "प्रकाशित अटींमध्ये 10 लाख ते 1 कोटी रुपये बँक कर्ज होते. या ऐतिहासिक अटी आहेत, सध्याच्या उपलब्धतेची खात्री नाही."),
         }),
]
for record in additions:
    record.update(last_checked_at="2026-09-25", indexed_at="2026-09-25",
                  verification_status="verified_official", language="en",
                  source_title=record["scheme_name"])
    records = [r for r in records if r["scheme_id"] != record["scheme_id"]]
    records.append(record)
for record in records:
    record["content_hash"] = content_hash(record)
CATALOG.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
