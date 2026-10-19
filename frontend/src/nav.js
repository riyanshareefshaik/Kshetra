import {
  BookOpen, CalendarDays, FileText, FlaskConical, History, IndianRupee, Landmark, Lightbulb, Map as MapIcon,
  MessageCircle, SlidersHorizontal, Sunrise, Users, ClipboardList,
} from "lucide-react";

// One list drives the sidebar, the phone tab bar, the "More" sheet and voice navigation.
export const NAV = [
  { group: "grp.field", items: [
    { path: "/", key: "nav.today", icon: Sunrise, words: ["today", "home", "weather", "rain", "irrigation", "pest", "ఈరోజు", "వాతావరణం", "వర్షం", "నీరు", "పురుగు", "आज", "मौसम", "बारिश", "सिंचाई", "कीट"] },
    { path: "/map", key: "nav.map", icon: MapIcon, words: ["map", "field", "మ్యాప్", "పొలం", "नक्शा", "खेत"] },
    { path: "/timeline", key: "nav.timeline", icon: History, words: ["history", "timeline", "season", "చరిత్ర", "కాలం", "इतिहास"] },
    { path: "/why", key: "nav.why", icon: Lightbulb, words: ["why", "reason", "twin", "similar", "ఎందుకు", "కారణం", "పోలిక", "क्यों", "कारण", "समान"] },
  ] },
  { group: "grp.plan", items: [
    { path: "/what-if", key: "nav.whatIf", icon: SlidersHorizontal, words: ["what if", "simulate", "ఒకవేళ", "अगर"] },
    { path: "/planner", key: "nav.planner", icon: CalendarDays, words: ["plan", "next season", "ప్రణాళిక", "योजना"] },
    { path: "/fertilizer", key: "nav.fertilizer", icon: FlaskConical, words: ["fertilizer", "fertiliser", "urea", "soil", "ఎరువు", "యూరియా", "మట్టి", "खाद", "यूरिया", "मिट्टी"] },
  ] },
  { group: "grp.money", items: [
    { path: "/market", key: "nav.market", icon: IndianRupee, words: ["market", "price", "sell", "mandi", "మార్కెట్", "ధర", "అమ్మ", "मंडी", "भाव", "बेच"] },
    { path: "/schemes", key: "nav.schemes", icon: Landmark, words: ["scheme", "subsidy", "government", "పథకం", "సబ్సిడీ", "ప్రభుత్వ", "योजनाएँ", "सरकार", "सब्सिडी"] },
    { path: "/report", key: "nav.report", icon: FileText, words: ["report", "insurance", "claim", "pdf", "నివేదిక", "బీమా", "रिपोर्ट", "बीमा"] },
  ] },
  { group: "grp.talk", items: [
    { path: "/ask", key: "nav.ask", icon: MessageCircle, words: ["ask", "question", "అడుగు", "ప్రశ్న", "पूछ", "सवाल"] },
    { path: "/diary", key: "nav.diary", icon: BookOpen, words: ["diary", "note", "డైరీ", "నోట్", "डायरी"] },
    { path: "/group", key: "nav.group", icon: Users, words: ["group", "fpo", "సమూహం", "సంఘం", "समूह"] },
  ] },
];

export const ALL_PAGES = NAV.flatMap((g) => g.items);
// Phone tab bar: the four most used pages, then "More".
export const TABS = ["/", "/map", "/timeline", "/ask"];
export const MoreIcon = ClipboardList;
