"""Store today's Agmarknet mandi prices (data.gov.in, free key) in mandi_prices.

    python -m scripts.fetch_prices                    # Andhra Pradesh
    python -m scripts.fetch_prices --state Telangana

The data.gov.in resource only holds the latest day, so run this daily
(cron, or a free GitHub Actions schedule) to build up price history.
"""
import argparse

import httpx

from app.config import get_settings
from app.db.session import get_conn
from app.services.prices import crop_for_commodity, fetch_agmarknet


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", default="Andhra Pradesh")
    args = ap.parse_args()
    key = get_settings().data_gov_api_key
    if not key:
        raise SystemExit("DATA_GOV_API_KEY is not set (free at data.gov.in)")
    with httpx.Client() as client:
        rows = [r for r in fetch_agmarknet(client, key, args.state) if crop_for_commodity(r["commodity"])]
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO mandi_prices (arrival_date, state, district, market, commodity, variety,
                                         min_price, max_price, modal_price)
               VALUES (%(arrival_date)s, %(state)s, %(district)s, %(market)s, %(commodity)s, %(variety)s,
                       %(min_price)s, %(max_price)s, %(modal_price)s)
               ON CONFLICT (arrival_date, state, district, market, commodity, variety) DO UPDATE
                  SET modal_price = EXCLUDED.modal_price, min_price = EXCLUDED.min_price,
                      max_price = EXCLUDED.max_price""",
            rows,
        )
        conn.commit()
    print(f"stored {len(rows)} prices for crops Kshetra models")


if __name__ == "__main__":
    main()
