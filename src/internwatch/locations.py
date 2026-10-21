"""Decide which countries a free-text job location refers to."""
from __future__ import annotations

import re
from functools import lru_cache

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC", "puerto rico": "PR",
}
US_CODES = set(US_STATES.values())
CA_PROVINCES = {"ontario": "ON", "british columbia": "BC", "quebec": "QC", "québec": "QC", "alberta": "AB",
                "manitoba": "MB", "saskatchewan": "SK", "nova scotia": "NS", "new brunswick": "NB",
                "newfoundland": "NL", "prince edward island": "PE"}
CA_CODES = set(CA_PROVINCES.values())

US_WORDS = ["united states", "united states of america", "usa", "u.s.", "u.s.a.", "us",
            "nationwide", "nyc", "sf bay area", "bay area", "silicon valley", "washington dc", "washington d.c.",
            "new york city", "new york", "san francisco", "seattle", "chicago", "boston", "austin", "los angeles",
            "mountain view", "sunnyvale", "palo alto", "menlo park", "redmond", "bellevue", "kirkland",
            "atlanta", "denver", "boulder", "dallas", "houston", "pittsburgh", "philadelphia", "madison",
            "miami", "jersey city", "san jose", "santa clara", "cupertino", "san mateo", "redwood city",
            "san diego", "irvine", "portland", "salt lake city", "lehi", "draper", "provo", "phoenix",
            "tempe", "scottsdale", "minneapolis", "st. louis", "saint louis", "kansas city", "nashville",
            "charlotte", "raleigh", "durham", "research triangle", "richmond", "mclean", "arlington",
            "reston", "herndon", "plano", "irving", "columbus", "cincinnati", "cleveland", "detroit",
            "ann arbor", "indianapolis", "milwaukee", "verona", "bala cynwyd", "stamford", "greenwich",
            "hoboken", "princeton", "baltimore", "tampa", "orlando", "jupiter", "west palm beach",
            "las vegas", "sacramento", "oakland", "emeryville", "fremont", "milpitas", "foster city",
            "burlingame", "south san francisco", "santa monica", "culver city", "playa vista", "pasadena",
            "hillsboro", "beaverton", "chandler", "folsom", "boise", "omaha", "des moines", "moline",
            "urbandale", "johnston", "chevy chase", "bethesda", "fort worth", "frisco", "round rock",
            "san antonio", "louisville", "lexington", "warren", "dearborn", "auburn hills", "milford",
            "framingham", "waltham", "cambridge, ma", "somerville", "burlington, ma", "andover", "hartford",
            "new haven", "albany", "rochester", "buffalo", "syracuse", "remote us", "remote - us",
            "remote, us", "us remote", "us-remote", "remote (us)", "remote-us", "u.s. remote"]
CA_WORDS = ["canada", "toronto", "vancouver", "montreal", "montréal", "ottawa", "waterloo", "kitchener",
            "calgary", "edmonton", "quebec city", "markham", "mississauga", "burnaby", "victoria, bc",
            "remote canada", "remote - canada", "canada remote"]
OTHER_WORDS = {
    "GB": ["united kingdom", "uk", "u.k.", "england", "scotland", "wales", "london", "manchester", "edinburgh",
           "glasgow", "bristol", "cambridge, uk", "cambridge, england", "oxford", "belfast", "leeds", "reading, uk"],
    "IE": ["ireland", "dublin", "cork"], "DE": ["germany", "berlin", "munich", "münchen", "hamburg", "frankfurt",
                                                  "stuttgart", "cologne", "düsseldorf", "dusseldorf"],
    "FR": ["france", "paris", "lyon", "grenoble", "sophia antipolis"], "NL": ["netherlands", "amsterdam", "rotterdam", "eindhoven", "utrecht"],
    "IN": ["india", "bangalore", "bengaluru", "hyderabad", "pune", "chennai", "gurgaon", "gurugram", "noida",
           "mumbai", "delhi", "new delhi", "kolkata", "ahmedabad", "kochi", "trivandrum", "jaipur"],
    "CN": ["china", "shanghai", "beijing", "shenzhen", "guangzhou", "hangzhou", "chengdu", "nanjing", "suzhou", "wuhan", "xi'an"],
    "HK": ["hong kong"], "SG": ["singapore"], "JP": ["japan", "tokyo", "osaka"], "KR": ["korea", "seoul"],
    "TW": ["taiwan", "taipei", "hsinchu"], "AU": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "BR": ["brazil", "brasil", "são paulo", "sao paulo", "rio de janeiro"], "MX": ["mexico", "méxico", "guadalajara", "monterrey"],
    "IL": ["israel", "tel aviv", "haifa", "herzliya", "jerusalem"], "PL": ["poland", "warsaw", "krakow", "kraków", "wroclaw", "gdansk"],
    "ES": ["spain", "madrid", "barcelona"], "IT": ["italy", "milan", "milano", "rome", "turin"],
    "CH": ["switzerland", "zurich", "zürich", "geneva", "genève", "lausanne", "zug"],
    "SE": ["sweden", "stockholm"], "DK": ["denmark", "copenhagen"], "NO": ["norway", "oslo"], "FI": ["finland", "helsinki"],
    "BE": ["belgium", "brussels"], "AT": ["austria", "vienna"], "CZ": ["czech", "czechia", "prague", "brno"],
    "RO": ["romania", "bucharest", "cluj"], "HU": ["hungary", "budapest"], "PT": ["portugal", "lisbon", "porto"],
    "GR": ["greece", "athens"], "TR": ["turkey", "türkiye", "istanbul"], "AE": ["united arab emirates", "uae", "dubai", "abu dhabi"],
    "SA": ["saudi arabia", "riyadh"], "ZA": ["south africa", "cape town", "johannesburg"], "AR": ["argentina", "buenos aires"],
    "CL": ["chile", "santiago"], "CO": ["colombia", "bogota", "bogotá", "medellin", "medellín"], "CR": ["costa rica", "san jose, costa rica"],
    "PH": ["philippines", "manila"], "VN": ["vietnam", "ho chi minh", "hanoi"], "TH": ["thailand", "bangkok"],
    "MY": ["malaysia", "kuala lumpur", "penang"], "ID": ["indonesia", "jakarta"], "NZ": ["new zealand", "auckland"],
    "LU": ["luxembourg"], "EE": ["estonia", "tallinn"], "UA": ["ukraine", "kyiv"], "RS": ["serbia", "belgrade"],
    "BG": ["bulgaria", "sofia"], "LT": ["lithuania", "vilnius"], "HR": ["croatia", "zagreb"], "SK": ["slovakia", "bratislava"],
    "EG": ["egypt", "cairo"], "NG": ["nigeria", "lagos"], "KE": ["kenya", "nairobi"], "PE": ["peru", "lima"],
    "PK": ["pakistan"], "BD": ["bangladesh"], "LK": ["sri lanka"], "CY": ["cyprus", "limassol"], "MT": ["malta"],
    "EMEA": ["emea", "europe", "apac", "asia", "latam", "latin america"],
}
# The rest of the world (country names are "strong"; the cities listed are "weak", overruled by a US state code).
MORE_COUNTRIES = {
    "QA": ["qatar", "doha"], "KW": ["kuwait", "kuwait city"], "BH": ["bahrain", "manama"], "OM": ["oman", "muscat"],
    "JO": ["jordan", "amman"], "LB": ["lebanon", "beirut"], "MA": ["morocco", "casablanca", "rabat"],
    "TN": ["tunisia", "tunis"], "DZ": ["algeria", "algiers"], "GH": ["ghana", "accra"], "ET": ["ethiopia", "addis ababa"],
    "UG": ["uganda", "kampala"], "TZ": ["tanzania", "dar es salaam"], "RW": ["rwanda", "kigali"], "SN": ["senegal", "dakar"],
    "CI": ["ivory coast", "côte d'ivoire", "cote d'ivoire", "abidjan"], "CM": ["cameroon"], "ZW": ["zimbabwe", "harare"],
    "ZM": ["zambia", "lusaka"], "MU": ["mauritius"], "BW": ["botswana"], "NA": ["namibia"], "AO": ["angola", "luanda"],
    "MZ": ["mozambique"], "IS": ["iceland", "reykjavik"], "LV": ["latvia", "riga"], "SI": ["slovenia", "ljubljana"],
    "BA": ["bosnia", "bosnia and herzegovina", "sarajevo"], "MK": ["north macedonia", "macedonia", "skopje"],
    "AL": ["albania", "tirana"], "ME": ["montenegro"], "MD": ["moldova", "chisinau"], "BY": ["belarus", "minsk"],
    "RU": ["russia", "russian federation", "moscow", "saint petersburg"], "AM": ["armenia", "yerevan"],
    "AZ": ["azerbaijan", "baku"], "KZ": ["kazakhstan", "almaty", "astana"], "UZ": ["uzbekistan", "tashkent"],
    "NP": ["nepal", "kathmandu"], "MM": ["myanmar"], "KH": ["cambodia", "phnom penh"], "MN": ["mongolia"],
    "MO": ["macau", "macao"], "DO": ["dominican republic", "santo domingo"], "JM": ["jamaica", "kingston, jamaica"],
    "TT": ["trinidad", "trinidad and tobago"], "PA": ["panama"], "GT": ["guatemala"], "HN": ["honduras"],
    "SV": ["el salvador", "san salvador"], "NI": ["nicaragua"], "EC": ["ecuador", "quito", "guayaquil"],
    "BO": ["bolivia"], "PY": ["paraguay", "asuncion", "asunción"], "UY": ["uruguay", "montevideo"],
    "VE": ["venezuela", "caracas"], "BS": ["bahamas"], "BB": ["barbados"], "KY": ["cayman islands"], "BM": ["bermuda"],
    "LI": ["liechtenstein"], "MC": ["monaco"], "AD": ["andorra"], "GI": ["gibraltar"], "IM": ["isle of man"],
    "GG": ["guernsey"], "FJ": ["fiji"], "IQ": ["iraq", "baghdad", "erbil"], "PK2": ["karachi", "lahore", "islamabad"],
    "BD2": ["dhaka"], "LK2": ["colombo"], "SA2": ["jeddah", "dammam"], "VN2": ["da nang"], "IN2": ["coimbatore", "indore", "mysore"],
}
for _cc, _words in MORE_COUNTRIES.items():
    OTHER_WORDS.setdefault(_cc[:2], []).extend(_words)
REMOTE_RE = re.compile(r"\b(remote|anywhere|virtual|distributed|work from home|wfh)\b", re.I)


def _words_re(words):
    pats = sorted({re.escape(w.lower()) for w in words}, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(pats) + r")(?![a-z0-9])", re.I)


_US_RE = _words_re(US_WORDS + list(US_STATES))
_CA_RE = _words_re(CA_WORDS + list(CA_PROVINCES))
_OTHER_RES = {cc: _words_re(ws) for cc, ws in OTHER_WORDS.items()}
# "Austin, TX", "San Jose, CA 95134", "TX - Austin", "US-CA-San Jose", "USA - California"
_STATE_CODE_RE = re.compile(r"(?:,\s*|\b(?:us|usa)[\s\-,]+|^)(" + "|".join(sorted(US_CODES)) + r")(?:\s+\d{5})?(?=\s*(?:$|[,;|)/\-]|\s+-|\s+united|\s+us))", re.I)
_PROVINCE_CODE_RE = re.compile(r",\s*(" + "|".join(sorted(CA_CODES)) + r")(?=\s*(?:$|[,;|)/]|\s+canada|\s+ca\b))", re.I)
_SPLIT_RE = re.compile(r"\s*(?:;|\||\n|•| or |\s/\s)\s*", re.I)


@lru_cache(maxsize=20000)
def countries(location: str) -> tuple[frozenset, bool]:
    """Return (country codes found, unknown_part_present).

    unknown_part_present is True if the string is empty, only "Remote", or has a part we could
    not place in any country.
    """
    loc = (location or "").strip()
    if not loc:
        return frozenset(), True
    found: set[str] = set()
    unknown = False
    for part in _SPLIT_RE.split(loc):
        part = part.strip(" ,-")
        if not part:
            continue
        cs = _part_countries(part)
        if cs:
            found |= cs
        elif re.fullmatch(r"\d+\s+locations?|multiple locations?|various locations?|flexible|hybrid|onsite|on-site", part, re.I):
            unknown = True
        elif REMOTE_RE.search(part):
            unknown = True  # bare "Remote": country not stated
        else:
            unknown = True
    return frozenset(found), unknown


COUNTRY_NAMES = {
    "united kingdom", "uk", "u.k.", "england", "scotland", "wales", "ireland", "germany", "france", "netherlands",
    "india", "china", "hong kong", "singapore", "japan", "korea", "taiwan", "australia", "brazil", "brasil",
    "mexico", "méxico", "israel", "poland", "spain", "italy", "switzerland", "sweden", "denmark", "norway",
    "finland", "belgium", "austria", "czech", "czechia", "romania", "hungary", "portugal", "greece", "turkey",
    "türkiye", "united arab emirates", "uae", "saudi arabia", "south africa", "argentina", "chile", "colombia",
    "costa rica", "philippines", "vietnam", "thailand", "malaysia", "indonesia", "new zealand", "luxembourg",
    "estonia", "ukraine", "serbia", "bulgaria", "lithuania", "croatia", "slovakia", "egypt", "nigeria", "kenya",
    "peru", "pakistan", "bangladesh", "sri lanka", "cyprus", "malta",
    "united arab emirates", "united kingdom of great britain and northern ireland", "republic of korea", "south korea",
    "people's republic of china", "russian federation", "czech republic",
    "qatar", "kuwait", "bahrain", "oman", "jordan", "lebanon", "morocco", "tunisia", "algeria", "ghana", "ethiopia",
    "uganda", "tanzania", "rwanda", "senegal", "ivory coast", "côte d'ivoire", "cote d'ivoire", "cameroon", "zimbabwe",
    "zambia", "mauritius", "botswana", "namibia", "angola", "mozambique", "iceland", "latvia", "slovenia", "bosnia",
    "bosnia and herzegovina", "north macedonia", "macedonia", "albania", "montenegro", "moldova", "belarus", "russia",
    "armenia", "azerbaijan", "kazakhstan", "uzbekistan", "nepal", "myanmar", "cambodia", "mongolia", "macau", "macao",
    "dominican republic", "jamaica", "trinidad", "trinidad and tobago", "panama", "guatemala", "honduras", "el salvador",
    "nicaragua", "ecuador", "bolivia", "paraguay", "uruguay", "venezuela", "bahamas", "barbados", "cayman islands",
    "bermuda", "liechtenstein", "monaco", "andorra", "gibraltar", "isle of man", "guernsey", "fiji", "iraq",
}
ISO2 = {"US": "US", "CA": "CA", "GB": "GB", "UK": "GB", "IE": "IE", "DE": "DE", "FR": "FR", "NL": "NL", "IN": "IN",
        "CN": "CN", "HK": "HK", "SG": "SG", "JP": "JP", "KR": "KR", "TW": "TW", "AU": "AU", "BR": "BR", "MX": "MX",
        "IL": "IL", "PL": "PL", "ES": "ES", "IT": "IT", "CH": "CH", "SE": "SE", "DK": "DK", "NO": "NO", "FI": "FI",
        "BE": "BE", "AT": "AT", "CZ": "CZ", "RO": "RO", "HU": "HU", "PT": "PT", "GR": "GR", "TR": "TR", "AE": "AE",
        "ZA": "ZA", "AR": "AR", "CL": "CL", "CO": "CO", "CR": "CR", "PH": "PH", "VN": "VN", "MY": "MY", "ID": "ID",
        "NZ": "NZ", "LU": "LU", "EE": "EE", "UA": "UA", "RS": "RS", "BG": "BG", "LT": "LT", "HR": "HR", "SK": "SK"}
# "Bengaluru, KA, IN" / "Toronto, ON, CA" / "San Jose, CA, US": the last code is a country.
_ISO_TAIL_RE = re.compile(r",\s*[A-Z]{2}\s*,\s*([A-Z]{2})\s*$")
# "Tel Aviv-Yafo, Tel Aviv District, IL" / "Doha, Doha Municipality, QA": a region that is not a US state, then
# a country code (that would otherwise read as a state code: IL, IN, GA …).
_REGION_TAIL_RE = re.compile(r"^[^,]+,\s*([^,]{3,}?)\s*,\s*([A-Z]{2})\s*$")
ISO2.update({cc: cc for cc in OTHER_WORDS if len(cc) == 2 and cc != "EMEA"})
# words that name a region abroad, so a final code after them is a country even when it is also a US state code
_FOREIGN_REGION = re.compile(r"\b(?:district|municipality|province|prefecture|governorate|voivodeship|oblast|canton|"
                             r"region|department)\b", re.I)



# ISO 3166 alpha-3 country codes as a location's last part ("Zaragoza, Aragon, ESP", "Seattle, Washington, USA").
ISO3 = {
    "USA": "US", "PRI": "US", "CAN": "CA", "GBR": "GB", "IRL": "IE", "DEU": "DE", "FRA": "FR", "NLD": "NL", "IND": "IN",
    "CHN": "CN", "HKG": "HK", "SGP": "SG", "JPN": "JP", "KOR": "KR", "TWN": "TW", "AUS": "AU", "BRA": "BR", "MEX": "MX",
    "ISR": "IL", "POL": "PL", "ESP": "ES", "ITA": "IT", "CHE": "CH", "SWE": "SE", "DNK": "DK", "NOR": "NO", "FIN": "FI",
    "BEL": "BE", "AUT": "AT", "CZE": "CZ", "ROU": "RO", "HUN": "HU", "PRT": "PT", "GRC": "GR", "TUR": "TR", "ARE": "AE",
    "SAU": "SA", "ZAF": "ZA", "ARG": "AR", "CHL": "CL", "COL": "CO", "CRI": "CR", "PHL": "PH", "VNM": "VN", "THA": "TH",
    "MYS": "MY", "IDN": "ID", "NZL": "NZ", "LUX": "LU", "EST": "EE", "UKR": "UA", "SRB": "RS", "BGR": "BG", "LTU": "LT",
    "HRV": "HR", "SVK": "SK", "EGY": "EG", "NGA": "NG", "KEN": "KE", "PER": "PE", "PAK": "PK", "BGD": "BD", "LKA": "LK",
    "CYP": "CY", "MLT": "MT", "QAT": "QA", "KWT": "KW", "BHR": "BH", "OMN": "OM", "JOR": "JO", "LBN": "LB", "MAR": "MA",
    "TUN": "TN", "DZA": "DZ", "GHA": "GH", "ETH": "ET", "UGA": "UG", "TZA": "TZ", "RWA": "RW", "SEN": "SN", "CIV": "CI",
    "CMR": "CM", "ZWE": "ZW", "ZMB": "ZM", "MUS": "MU", "BWA": "BW", "NAM": "NA", "AGO": "AO", "MOZ": "MZ", "ISL": "IS",
    "LVA": "LV", "SVN": "SI", "BIH": "BA", "MKD": "MK", "ALB": "AL", "MNE": "ME", "MDA": "MD", "BLR": "BY", "RUS": "RU",
    "ARM": "AM", "AZE": "AZ", "KAZ": "KZ", "UZB": "UZ", "NPL": "NP", "MMR": "MM", "KHM": "KH", "MNG": "MN", "MAC": "MO",
    "DOM": "DO", "JAM": "JM", "TTO": "TT", "PAN": "PA", "GTM": "GT", "HND": "HN", "SLV": "SV", "NIC": "NI", "ECU": "EC",
    "BOL": "BO", "PRY": "PY", "URY": "UY", "VEN": "VE", "BHS": "BS", "BRB": "BB", "CYM": "KY", "BMU": "BM", "LIE": "LI",
    "MCO": "MC", "AND": "AD", "GIB": "GI", "IMN": "IM", "GGY": "GG", "FJI": "FJ", "IRQ": "IQ",
}
_ISO3_TAIL_RE = re.compile(r",\s*([A-Z]{3})\s*$")

US_SHORT = {"sf", "la", "nyc", "dc", "sea", "atl", "chi", "bos", "socal", "norcal", "us"}


def _part_countries(part: str) -> set[str]:
    t3 = _ISO3_TAIL_RE.search(part.strip())
    if t3 and t3.group(1) in ISO3:
        return {ISO3[t3.group(1)]}
    p = part.lower()
    if p.strip(" .") in US_SHORT:  # Simplify-style shorthand: "SF", "LA", "NYC"
        return {"US"}
    strong: set[str] = set()   # foreign country names ("India")
    weak: set[str] = set()     # foreign city names ("Dublin"), overruled by a US state code
    region_only = False
    for cc, r in _OTHER_RES.items():
        for m in r.findall(p):
            if cc == "EMEA":
                region_only = True
            elif m in COUNTRY_NAMES:
                strong.add(cc)
            else:
                weak.add(cc)
    is_ca = bool(_CA_RE.search(p) or _PROVINCE_CODE_RE.search(part))
    out: set[str] = set()
    tail = _ISO_TAIL_RE.search(part.strip())
    scan, tail_foreign = part, False
    if tail and tail.group(1) in ISO2:
        out.add(ISO2[tail.group(1)])
        tail_foreign = ISO2[tail.group(1)] != "US"
        scan = part[: tail.start(1)].rstrip(" ,")
    else:
        rt = _REGION_TAIL_RE.match(part.strip())
        if (rt and rt.group(2) in ISO2 and rt.group(1).strip().lower() not in US_STATES
                and rt.group(1).strip().upper() not in US_CODES
                # a code that is also a US state ("Hunt Valley, Cockeysville, MD") is that state unless something
                # foreign appears ("Chisinau, Chisinau Municipality, MD", "Tel Aviv-Yafo, Tel Aviv District, IL")
                and not (rt.group(2) in US_CODES
                         and not (strong or weak or is_ca or _FOREIGN_REGION.search(rt.group(1))))):
            out.add(ISO2[rt.group(2)])
            tail_foreign = ISO2[rt.group(2)] != "US"
            scan = part[: part.rfind(",")]
    last = part.strip().rsplit(",", 1)
    state = last[1].strip() if len(last) == 2 else ""
    if strong and state in US_CODES and ISO2.get(state) not in strong and not tail_foreign:
        weak |= strong  # a town named after a country, then a state: "Malta, NY", "Lebanon, NH", "Panama City, FL"
        strong = set()
    codes = {m.upper() for m in _STATE_CODE_RE.findall(scan)}
    if is_ca:
        out.add("CA")
        strong.discard("GB")
        weak.discard("GB")  # London, Ontario
    if _US_RE.search(p):
        out.add("US")  # US state/city names, "USA", "United States"
    elif codes and not (is_ca and codes <= {"CA"}) and not strong and not tail_foreign:
        out.add("US")  # "Geneva, IL", "Dublin, CA", "Paris, TX"
    out |= strong
    if "US" not in out:
        out |= weak
    if not out and region_only:
        out.add("EMEA")  # "Europe", "APAC": a region outside the US
    return out


def location_decision(location: str, allowed: list[str]) -> tuple[bool, bool, str]:
    """(include, unsure, reason) for a location against the allowed country list."""
    allowed_set = {a.upper() for a in allowed}
    if "ANY" in allowed_set:
        return True, False, ""
    found, unknown = countries(location)
    if found & allowed_set:
        return True, False, ""
    if not found:
        why = "no location given" if not location.strip() else f"location '{location[:60]}' not recognised"
        return True, True, why
    if unknown:
        return True, True, f"location '{location[:60]}' partly unrecognised"
    return False, False, f"location outside {'/'.join(sorted(allowed_set))}: {location[:80]}"
