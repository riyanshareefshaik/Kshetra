# Kshetra — Product Requirements

**Team GenZ · AgriTech hackathon**

Kshetra rebuilds any farm field's seasonal history (2017 onward) from free
satellite data, explains why yields went up or down, and guides the next season.

## Users
- **Farmer**: wants to know what happened on their field and what to grow next, in Telugu, Hindi or English.
- **Lender / insurer (PMFBY)**: needs a trustworthy field history report.
- **Seed company**: wants aggregated, anonymized performance of crops and varieties.

## Principles
1. **100% free**: open-source software, open data, free tiers only.
2. **Honest numbers**: yields are ranges (t/ha), crop labels carry confidence
   (below 60% = "uncertain"), explanations are "likely reasons", never "cause".
3. **The database is the memory**: the LLM only answers through tool calls on our data,
   shows source numbers, and says "I don't know" otherwise.
4. **Works offline for the demo**: every external response is cached in Postgres.
5. **Farmer owns the data**: sharing is off by default; shared data is anonymized.

## Features
| ID | Feature | Acceptance |
|---|---|---|
| F1 | Field selection | Pin or drawn polygon; auto-boundary from pin |
| F2 | Field history from space | Seasons 2017→ with sowing, peak, harvest dates; Sentinel-2 NDVI, gaps filled with Sentinel-1 SAR and NISAR radar |
| F3 | Crop detection | Crop per season with confidence; < 0.60 shown as "uncertain" |
| F4 | Stress detection | Dry spells, waterlogging, sudden damage events with dates and evidence |
| F5 | Yield estimate & forecast | P10–P90 range in t/ha, never a single number |
| F6 | Why engine | Top SHAP contributors, worded as "likely reasons" |
| F7 | Field twins | 5 nearest similar fields and what they did differently |
| F8 | What-if simulator | Crop, variety, sowing date, fertilizer, irrigation → yield, risk, profit in < 1 s |
| F9 | Next season planner | Top 3 crop+variety options with yield range, risk, profit (Rs), sowing window |
| F10 | Ask your field | Voice/text Q&A (te/hi/en) through tool calls only, with sources |
| F11 | Voice farm diary | Speech → structured record; seed packet OCR |
| F12 | Field health report | One-click PDF for loans and PMFBY claims |
| F13 | Data consent | Off by default; anonymized when on |
| F14 | Seed company insights | Aggregates only, minimum group size enforced |

## Satellite sources
| Source | Type | Years | Role |
|---|---|---|---|
| Sentinel-2 | Optical, 10 m | 2017→ | NDVI backbone |
| Sentinel-1 | C-band SAR, 10 m | 2017→ | Monsoon cloud gap filling, sowing/flooding signals |
| NISAR | L-band and S-band SAR | mid-2025→ (S-band operational from Jul 2026) | Recent-season radar: crop structure, soil moisture, flooding; validation of Sentinel-1 gap filling |

NISAR cannot reach back to 2017, so history before 2025 uses Sentinel-1 for radar.

## Known data limits
- No free field-level yield ground truth in India: the yield model is trained on
  district yields (ICRISAT, data.gov.in) and applied per field, so outputs are ranges.
- Crop labels are weak (phenology rules + district crop statistics + farmer diary corrections).
