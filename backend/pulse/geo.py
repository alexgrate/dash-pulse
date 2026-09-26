from math import cos, radians, sqrt

NIGERIA_BOUNDS = {"lat_min": 4.0, "lat_max": 14.0, "lon_min": 2.6, "lon_max": 14.8}

CITY_RADIUS_KM = 60

CITIES = [
    ("Lagos", 6.524, 3.379),
    ("Abuja", 9.076, 7.399),
    ("Port Harcourt", 4.816, 7.050),
    ("Ibadan", 7.378, 3.947),
    ("Kano", 12.002, 8.592),
    ("Benin City", 6.335, 5.604),
    ("Enugu", 6.524, 7.517),
    ("Kaduna", 10.511, 7.417),
    ("Owerri", 5.484, 7.035),
    ("Jos", 9.897, 8.858),
    ("Ilorin", 8.497, 4.543),
    ("Abeokuta", 7.148, 3.362),
    ("Warri", 5.516, 5.750),
    ("Uyo", 5.038, 7.913),
    ("Calabar", 4.958, 8.327),
    ("Onitsha", 6.145, 6.788),
    ("Aba", 5.107, 7.367),
    ("Maiduguri", 11.831, 13.151),
    ("Sokoto", 13.006, 5.248),
    ("Akure", 7.250, 5.195),
    ("Asaba", 6.198, 6.731),
    ("Makurdi", 7.733, 8.522),
    ("Yola", 9.203, 12.495),
    ("Bauchi", 10.314, 9.846),
    ("Osogbo", 7.771, 4.557),
    ("Zaria", 11.086, 7.719),
    ("Minna", 9.583, 6.547),
    ("Lokoja", 7.802, 6.743),
    ("Ado-Ekiti", 7.621, 5.221),
    ("Awka", 6.212, 7.072),
    ("Abakaliki", 6.325, 8.113),
    ("Katsina", 12.990, 7.601),
    ("Gombe", 10.290, 11.167),
    ("Lafia", 8.494, 8.515),
    ("Jalingo", 8.893, 11.360),
    ("Umuahia", 5.526, 7.492),
    ("Yenagoa", 4.924, 6.264),
    ("Dutse", 11.756, 9.339),
    ("Damaturu", 11.747, 11.961),
    ("Birnin Kebbi", 12.454, 4.197),
    ("Gusau", 12.170, 6.664),
]


CITY_COORDS = {name: (lat, lon) for name, lat, lon in CITIES}


def distance_km(lat1, lon1, lat2, lon2):
    x = radians(lon2 - lon1) * cos(radians((lat1 + lat2) / 2))
    y = radians(lat2 - lat1)
    return 6371 * sqrt(x * x + y * y)


def nearest_city(lat, lon):
    name, km = min(((c, distance_km(lat, lon, clat, clon)) for c, clat, clon in CITIES), key=lambda t: t[1])
    return name if km <= CITY_RADIUS_KM else None
