from scripts.load_reference import aggregate, parse_apy, parse_icrisat, start_year


def test_icrisat_wide_format(tmp_path):
    p = tmp_path / "dld.csv"
    p.write_text(
        "Dist Code,Year,State Code,State Name,Dist Name,RICE AREA (1000 ha),RICE PRODUCTION (1000 tons),"
        "RICE YIELD (Kg per ha),WHEAT AREA (1000 ha)\n"
        "1,2016,2,ANDHRA PRADESH,KRISHNA,300,1650,5500,0\n")
    rows = parse_icrisat(p)
    assert rows == [{"state": "Andhra Pradesh", "district": "Krishna", "year": 2016, "season": "total",
                     "crop": "paddy", "area_ha": 300000.0, "production_t": 1650000.0, "yield_t_ha": 5.5,
                     "source": "icrisat_dld"}]


def test_apy_long_format_merges_pulses_and_converts_cotton(tmp_path):
    p = tmp_path / "apy.csv"
    p.write_text(
        "State_Name,District_Name,Crop_Year,Season,Crop,Area,Production\n"
        "Andhra Pradesh,KRISHNA,2019-20,Rabi,Urad,1000,800\n"
        "Andhra Pradesh,KRISHNA,2019-20,Rabi,Moong(Green Gram),500,400\n"
        "Andhra Pradesh,KRISHNA,2019-20,Kharif,Cotton(lint),1000,3000\n"
        "Andhra Pradesh,KRISHNA,2019-20,Kharif,Wheat,10,10\n")
    rows = {(r["crop"], r["season"]): r for r in aggregate(parse_apy(p))}
    assert set(rows) == {("pulses", "rabi"), ("cotton", "kharif")}
    assert rows[("pulses", "rabi")]["area_ha"] == 1500
    assert rows[("pulses", "rabi")]["yield_t_ha"] == 0.8
    # 3000 bales * 0.17 t lint / 0.34 ginning = 1.5 t/ha seed cotton
    assert rows[("cotton", "kharif")]["yield_t_ha"] == 1.5
    assert rows[("cotton", "kharif")]["year"] == 2019


def test_start_year():
    assert start_year("2019 - 2020") == 2019 and start_year("2021") == 2021
