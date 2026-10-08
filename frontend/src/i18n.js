// UI words in English, Telugu and Hindi. Data values (numbers, crop keys) stay as they are.
export const LANGS = { en: "English", te: "తెలుగు", hi: "हिन्दी" };

const T = {
  map: { en: "Map", te: "మ్యాప్", hi: "नक्शा" },
  timeline: { en: "Timeline", te: "చరిత్ర", hi: "इतिहास" },
  why: { en: "Why & Twins", te: "ఎందుకు & పోలికలు", hi: "क्यों और समान खेत" },
  whatIf: { en: "What-If", te: "ఒకవేళ", hi: "अगर ऐसा हो" },
  planner: { en: "Planner", te: "ప్రణాళిక", hi: "योजना" },
  ask: { en: "Ask Your Field", te: "మీ పొలాన్ని అడగండి", hi: "अपने खेत से पूछें" },
  diary: { en: "Diary", te: "డైరీ", hi: "डायरी" },
  report: { en: "Report", te: "నివేదిక", hi: "रिपोर्ट" },
  insights: { en: "Insights", te: "అంతర్దృష్టులు", hi: "जानकारी" },
  chooseField: { en: "Choose a field", te: "పొలం ఎంచుకోండి", hi: "खेत चुनें" },
  noField: { en: "Select or add a field on the Map first.", te: "ముందుగా మ్యాప్‌లో పొలాన్ని ఎంచుకోండి లేదా జోడించండి.", hi: "पहले नक्शे पर खेत चुनें या जोड़ें।" },
  yieldRange: { en: "Yield range", te: "దిగుబడి పరిధి", hi: "उपज सीमा" },
  risk: { en: "Risk", te: "ప్రమాదం", hi: "जोखिम" },
  profit: { en: "Profit", te: "లాభం", hi: "मुनाफ़ा" },
  sowing: { en: "Sowing", te: "విత్తడం", hi: "बुवाई" },
  harvest: { en: "Harvest", te: "కోత", hi: "कटाई" },
  crop: { en: "Crop", te: "పంట", hi: "फसल" },
  uncertain: { en: "uncertain", te: "అనిశ్చితం", hi: "अनिश्चित" },
  likelyReasons: { en: "Likely reasons", te: "సంభావ్య కారణాలు", hi: "संभावित कारण" },
  send: { en: "Ask", te: "అడగండి", hi: "पूछें" },
  speak: { en: "Speak", te: "మాట్లాడండి", hi: "बोलें" },
  listening: { en: "Listening…", te: "వింటున్నాను…", hi: "सुन रहा हूँ…" },
  sources: { en: "Sources", te: "ఆధారాలు", hi: "स्रोत" },
  save: { en: "Save", te: "సేవ్ చేయండి", hi: "सहेजें" },
  download: { en: "Download PDF", te: "PDF డౌన్‌లోడ్", hi: "PDF डाउनलोड" },
  sharing: { en: "Share my data anonymously", te: "నా డేటాను అనామకంగా పంచుకోండి", hi: "मेरा डेटा गुमनाम रूप से साझा करें" },
  loading: { en: "Loading…", te: "లోడ్ అవుతోంది…", hi: "लोड हो रहा है…" },
};

export function t(key, lang) {
  return T[key]?.[lang] ?? T[key]?.en ?? key;
}
