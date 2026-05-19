"""Transit enrichment: nearest metro/RER stations for a listing.

Uses a hardcoded table of Paris metro and RER stop locations derived from
IDFM GTFS static data. For each listing we compute straight-line distance
and estimate walk time at 80 m/min.
"""
from __future__ import annotations

import math

PARIS_METRO_STOPS: list[dict] = [
    {"name": "Châtelet", "line": "1, 4, 7, 11, 14", "lat": 48.8584, "lon": 2.3474},
    {"name": "Gare du Nord", "line": "4, 5, RER B, RER D", "lat": 48.8809, "lon": 2.3553},
    {"name": "Gare de l'Est", "line": "4, 5, 7", "lat": 48.8763, "lon": 2.3588},
    {"name": "Gare de Lyon", "line": "1, 14, RER A, RER D", "lat": 48.8448, "lon": 2.3735},
    {"name": "Gare Saint-Lazare", "line": "3, 9, 12, 13, 14", "lat": 48.8757, "lon": 2.3247},
    {"name": "Gare Montparnasse", "line": "4, 6, 12, 13", "lat": 48.8427, "lon": 2.3210},
    {"name": "République", "line": "3, 5, 8, 9, 11", "lat": 48.8675, "lon": 2.3637},
    {"name": "Bastille", "line": "1, 5, 8", "lat": 48.8531, "lon": 2.3692},
    {"name": "Nation", "line": "1, 2, 6, 9, RER A", "lat": 48.8485, "lon": 2.3960},
    {"name": "Opéra", "line": "3, 7, 8, RER A", "lat": 48.8712, "lon": 2.3318},
    {"name": "Place de Clichy", "line": "2, 13", "lat": 48.8836, "lon": 2.3274},
    {"name": "Pigalle", "line": "2, 12", "lat": 48.8821, "lon": 2.3374},
    {"name": "Barbès-Rochechouart", "line": "2, 4", "lat": 48.8838, "lon": 2.3494},
    {"name": "Stalingrad", "line": "2, 5, 7", "lat": 48.8844, "lon": 2.3654},
    {"name": "Belleville", "line": "2, 11", "lat": 48.8718, "lon": 2.3764},
    {"name": "Ménilmontant", "line": "2", "lat": 48.8667, "lon": 2.3833},
    {"name": "Père Lachaise", "line": "2, 3", "lat": 48.8627, "lon": 2.3872},
    {"name": "Oberkampf", "line": "5, 9", "lat": 48.8647, "lon": 2.3681},
    {"name": "Saint-Lazare", "line": "3, 9, 12, 13, 14", "lat": 48.8757, "lon": 2.3247},
    {"name": "Montparnasse-Bienvenüe", "line": "4, 6, 12, 13", "lat": 48.8427, "lon": 2.3210},
    {"name": "Odéon", "line": "4, 10", "lat": 48.8523, "lon": 2.3386},
    {"name": "Saint-Michel", "line": "4, RER B, RER C", "lat": 48.8539, "lon": 2.3441},
    {"name": "Cité", "line": "4", "lat": 48.8554, "lon": 2.3461},
    {"name": "Hôtel de Ville", "line": "1, 11", "lat": 48.8573, "lon": 2.3514},
    {"name": "Saint-Paul", "line": "1", "lat": 48.8551, "lon": 2.3604},
    {"name": "Voltaire", "line": "9", "lat": 48.8577, "lon": 2.3796},
    {"name": "Charonne", "line": "9", "lat": 48.8555, "lon": 2.3927},
    {"name": "Faidherbe-Chaligny", "line": "8", "lat": 48.8497, "lon": 2.3800},
    {"name": "Ledru-Rollin", "line": "8", "lat": 48.8512, "lon": 2.3756},
    {"name": "Bréguet-Sabin", "line": "5", "lat": 48.8564, "lon": 2.3704},
    {"name": "Richard-Lenoir", "line": "5", "lat": 48.8607, "lon": 2.3718},
    {"name": "Parmentier", "line": "3", "lat": 48.8653, "lon": 2.3748},
    {"name": "Rue Saint-Maur", "line": "3", "lat": 48.8641, "lon": 2.3808},
    {"name": "Gambetta", "line": "3, 3bis", "lat": 48.8650, "lon": 2.3986},
    {"name": "Couronnes", "line": "2", "lat": 48.8694, "lon": 2.3803},
    {"name": "Colonel Fabien", "line": "2", "lat": 48.8785, "lon": 2.3703},
    {"name": "Jaurès", "line": "2, 5, 7bis", "lat": 48.8822, "lon": 2.3706},
    {"name": "Laumière", "line": "5", "lat": 48.8852, "lon": 2.3794},
    {"name": "Ourcq", "line": "5", "lat": 48.8868, "lon": 2.3862},
    {"name": "Porte de Pantin", "line": "5", "lat": 48.8882, "lon": 2.3928},
    {"name": "Buttes Chaumont", "line": "7bis", "lat": 48.8783, "lon": 2.3817},
    {"name": "Botzaris", "line": "7bis", "lat": 48.8796, "lon": 2.3886},
    {"name": "Place des Fêtes", "line": "7bis, 11", "lat": 48.8769, "lon": 2.3929},
    {"name": "Télégraphe", "line": "11", "lat": 48.8758, "lon": 2.3987},
    {"name": "Jourdain", "line": "11", "lat": 48.8750, "lon": 2.3893},
    {"name": "Pyrénées", "line": "11", "lat": 48.8735, "lon": 2.3847},
    {"name": "Arts et Métiers", "line": "3, 11", "lat": 48.8654, "lon": 2.3567},
    {"name": "Temple", "line": "3", "lat": 48.8667, "lon": 2.3613},
    {"name": "Réaumur-Sébastopol", "line": "3, 4", "lat": 48.8663, "lon": 2.3522},
    {"name": "Strasbourg-Saint-Denis", "line": "4, 8, 9", "lat": 48.8693, "lon": 2.3545},
    {"name": "Bonne Nouvelle", "line": "8, 9", "lat": 48.8706, "lon": 2.3483},
    {"name": "Grands Boulevards", "line": "8, 9", "lat": 48.8717, "lon": 2.3428},
    {"name": "Richelieu-Drouot", "line": "8, 9", "lat": 48.8721, "lon": 2.3376},
    {"name": "Le Peletier", "line": "7", "lat": 48.8755, "lon": 2.3401},
    {"name": "Cadet", "line": "7", "lat": 48.8769, "lon": 2.3440},
    {"name": "Poissonnière", "line": "7", "lat": 48.8775, "lon": 2.3497},
    {"name": "Château d'Eau", "line": "4", "lat": 48.8726, "lon": 2.3565},
    {"name": "Jacques Bonsergent", "line": "5", "lat": 48.8703, "lon": 2.3611},
    {"name": "Goncourt", "line": "11", "lat": 48.8698, "lon": 2.3709},
    {"name": "Rambuteau", "line": "11", "lat": 48.8614, "lon": 2.3531},
    {"name": "Les Halles", "line": "4, RER A, RER B", "lat": 48.8622, "lon": 2.3454},
    {"name": "Étienne Marcel", "line": "4", "lat": 48.8637, "lon": 2.3488},
    {"name": "Sentier", "line": "3", "lat": 48.8674, "lon": 2.3476},
    {"name": "Bourse", "line": "3", "lat": 48.8687, "lon": 2.3412},
    {"name": "Quatre-Septembre", "line": "3", "lat": 48.8696, "lon": 2.3362},
    {"name": "Pyramides", "line": "7, 14", "lat": 48.8660, "lon": 2.3339},
    {"name": "Palais Royal", "line": "1, 7", "lat": 48.8628, "lon": 2.3368},
    {"name": "Tuileries", "line": "1", "lat": 48.8643, "lon": 2.3266},
    {"name": "Concorde", "line": "1, 8, 12", "lat": 48.8656, "lon": 2.3213},
    {"name": "Madeleine", "line": "8, 12, 14", "lat": 48.8699, "lon": 2.3255},
    {"name": "Champs-Élysées-Clemenceau", "line": "1, 13", "lat": 48.8677, "lon": 2.3141},
    {"name": "Franklin D. Roosevelt", "line": "1, 9", "lat": 48.8689, "lon": 2.3091},
    {"name": "George V", "line": "1", "lat": 48.8720, "lon": 2.3007},
    {"name": "Charles de Gaulle-Étoile", "line": "1, 2, 6, RER A", "lat": 48.8738, "lon": 2.2950},
    {"name": "Ternes", "line": "2", "lat": 48.8782, "lon": 2.2983},
    {"name": "Monceau", "line": "2", "lat": 48.8809, "lon": 2.3093},
    {"name": "Villiers", "line": "2, 3", "lat": 48.8815, "lon": 2.3153},
    {"name": "Rome", "line": "2", "lat": 48.8821, "lon": 2.3197},
    {"name": "Europe", "line": "3", "lat": 48.8789, "lon": 2.3228},
    {"name": "Liège", "line": "13", "lat": 48.8795, "lon": 2.3278},
    {"name": "Saint-Georges", "line": "12", "lat": 48.8786, "lon": 2.3373},
    {"name": "Notre-Dame-de-Lorette", "line": "12", "lat": 48.8767, "lon": 2.3383},
    {"name": "Trinité-d'Estienne d'Orves", "line": "12", "lat": 48.8766, "lon": 2.3331},
    {"name": "Saint-Germain-des-Prés", "line": "4", "lat": 48.8534, "lon": 2.3337},
    {"name": "Mabillon", "line": "10", "lat": 48.8528, "lon": 2.3351},
    {"name": "Sèvres-Babylone", "line": "10, 12", "lat": 48.8517, "lon": 2.3262},
    {"name": "Vaneau", "line": "10", "lat": 48.8490, "lon": 2.3201},
    {"name": "Duroc", "line": "10, 13", "lat": 48.8468, "lon": 2.3164},
    {"name": "Invalides", "line": "8, 13, RER C", "lat": 48.8609, "lon": 2.3138},
    {"name": "La Tour-Maubourg", "line": "8", "lat": 48.8571, "lon": 2.3102},
    {"name": "École Militaire", "line": "8", "lat": 48.8550, "lon": 2.3063},
    {"name": "La Motte-Picquet-Grenelle", "line": "6, 8, 10", "lat": 48.8494, "lon": 2.2983},
    {"name": "Dupleix", "line": "6", "lat": 48.8505, "lon": 2.2928},
    {"name": "Bir-Hakeim", "line": "6", "lat": 48.8542, "lon": 2.2890},
    {"name": "Trocadéro", "line": "6, 9", "lat": 48.8630, "lon": 2.2878},
    {"name": "Passy", "line": "6", "lat": 48.8576, "lon": 2.2854},
    {"name": "Boulainvilliers", "line": "RER C", "lat": 48.8559, "lon": 2.2755},
    {"name": "La Muette", "line": "9", "lat": 48.8582, "lon": 2.2740},
    {"name": "Ranelagh", "line": "9", "lat": 48.8558, "lon": 2.2690},
    {"name": "Jasmin", "line": "9", "lat": 48.8534, "lon": 2.2671},
    {"name": "Michel-Ange-Auteuil", "line": "9, 10", "lat": 48.8481, "lon": 2.2639},
    {"name": "Denfert-Rochereau", "line": "4, 6, RER B", "lat": 48.8339, "lon": 2.3325},
    {"name": "Alésia", "line": "4", "lat": 48.8282, "lon": 2.3268},
    {"name": "Mouton-Duvernet", "line": "4", "lat": 48.8311, "lon": 2.3297},
    {"name": "Raspail", "line": "4, 6", "lat": 48.8388, "lon": 2.3308},
    {"name": "Vavin", "line": "4", "lat": 48.8428, "lon": 2.3283},
    {"name": "Edgar Quinet", "line": "6", "lat": 48.8410, "lon": 2.3253},
    {"name": "Gaîté", "line": "13", "lat": 48.8384, "lon": 2.3228},
    {"name": "Pernety", "line": "13", "lat": 48.8340, "lon": 2.3186},
    {"name": "Plaisance", "line": "13", "lat": 48.8317, "lon": 2.3137},
    {"name": "Convention", "line": "12", "lat": 48.8370, "lon": 2.2969},
    {"name": "Vaugirard", "line": "12", "lat": 48.8395, "lon": 2.3008},
    {"name": "Volontaires", "line": "12", "lat": 48.8415, "lon": 2.3074},
    {"name": "Pasteur", "line": "6, 12", "lat": 48.8434, "lon": 2.3124},
    {"name": "Ségur", "line": "10", "lat": 48.8474, "lon": 2.3095},
    {"name": "Cambronne", "line": "6", "lat": 48.8477, "lon": 2.2984},
    {"name": "Avenue Émile Zola", "line": "10", "lat": 48.8470, "lon": 2.2950},
    {"name": "Commerce", "line": "8", "lat": 48.8446, "lon": 2.2935},
    {"name": "Félix Faure", "line": "8", "lat": 48.8425, "lon": 2.2890},
    {"name": "Boucicaut", "line": "8", "lat": 48.8408, "lon": 2.2863},
    {"name": "Lourmel", "line": "8", "lat": 48.8388, "lon": 2.2823},
    {"name": "Javel-André Citroën", "line": "10, RER C", "lat": 48.8462, "lon": 2.2781},
    {"name": "Charles Michels", "line": "10", "lat": 48.8465, "lon": 2.2856},
    {"name": "Bercy", "line": "6, 14", "lat": 48.8400, "lon": 2.3795},
    {"name": "Dugommier", "line": "6", "lat": 48.8391, "lon": 2.3890},
    {"name": "Daumesnil", "line": "6, 8", "lat": 48.8394, "lon": 2.3961},
    {"name": "Reuilly-Diderot", "line": "1, 8", "lat": 48.8474, "lon": 2.3864},
    {"name": "Montgallet", "line": "8", "lat": 48.8443, "lon": 2.3885},
    {"name": "Place d'Italie", "line": "5, 6, 7", "lat": 48.8316, "lon": 2.3559},
    {"name": "Tolbiac", "line": "7", "lat": 48.8266, "lon": 2.3568},
    {"name": "Olympiades", "line": "14", "lat": 48.8270, "lon": 2.3674},
    {"name": "Bibliothèque François Mitterrand", "line": "14, RER C", "lat": 48.8298, "lon": 2.3762},
    {"name": "Chevaleret", "line": "6", "lat": 48.8349, "lon": 2.3677},
    {"name": "Nationale", "line": "6", "lat": 48.8325, "lon": 2.3610},
    {"name": "Campo-Formio", "line": "5", "lat": 48.8357, "lon": 2.3581},
    {"name": "Les Gobelins", "line": "7", "lat": 48.8359, "lon": 2.3517},
    {"name": "Censier-Daubenton", "line": "7", "lat": 48.8405, "lon": 2.3517},
    {"name": "Jussieu", "line": "7, 10", "lat": 48.8460, "lon": 2.3548},
    {"name": "Cardinal Lemoine", "line": "10", "lat": 48.8466, "lon": 2.3507},
    {"name": "Maubert-Mutualité", "line": "10", "lat": 48.8500, "lon": 2.3486},
    {"name": "Cluny-La Sorbonne", "line": "10", "lat": 48.8510, "lon": 2.3443},
    {"name": "Luxembourg", "line": "RER B", "lat": 48.8461, "lon": 2.3393},
    {"name": "Port-Royal", "line": "RER B", "lat": 48.8397, "lon": 2.3364},
    {"name": "Porte de Versailles", "line": "12, T2, T3a", "lat": 48.8324, "lon": 2.2874},
    {"name": "Porte d'Orléans", "line": "4, T3a", "lat": 48.8234, "lon": 2.3256},
    {"name": "Porte de Clignancourt", "line": "4", "lat": 48.8977, "lon": 2.3448},
    {"name": "Porte de la Chapelle", "line": "12", "lat": 48.8976, "lon": 2.3594},
    {"name": "Marx Dormoy", "line": "12", "lat": 48.8907, "lon": 2.3600},
    {"name": "Marcadet-Poissonniers", "line": "4, 12", "lat": 48.8916, "lon": 2.3491},
    {"name": "Jules Joffrin", "line": "12", "lat": 48.8924, "lon": 2.3444},
    {"name": "Lamarck-Caulaincourt", "line": "12", "lat": 48.8892, "lon": 2.3396},
    {"name": "Abbesses", "line": "12", "lat": 48.8843, "lon": 2.3383},
    {"name": "Blanche", "line": "2", "lat": 48.8836, "lon": 2.3324},
    {"name": "Anvers", "line": "2", "lat": 48.8831, "lon": 2.3442},
    {"name": "La Chapelle", "line": "2", "lat": 48.8848, "lon": 2.3607},
    {"name": "Château Rouge", "line": "4", "lat": 48.8869, "lon": 2.3495},
    {"name": "Simplon", "line": "4", "lat": 48.8938, "lon": 2.3476},
    {"name": "Guy Môquet", "line": "13", "lat": 48.8933, "lon": 2.3274},
    {"name": "Porte de Saint-Ouen", "line": "13", "lat": 48.8975, "lon": 2.3282},
    {"name": "Brochant", "line": "13", "lat": 48.8907, "lon": 2.3204},
    {"name": "La Fourche", "line": "13", "lat": 48.8870, "lon": 2.3250},
    {"name": "Porte de Clichy", "line": "13, 14, RER C", "lat": 48.8948, "lon": 2.3133},
    {"name": "Pont de Levallois", "line": "3", "lat": 48.8973, "lon": 2.2806},
    {"name": "Wagram", "line": "3", "lat": 48.8843, "lon": 2.3053},
    {"name": "Pereire", "line": "3", "lat": 48.8852, "lon": 2.2977},
]

WALK_SPEED_M_PER_MIN = 80.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_stops(
    lat: float, lon: float, *, max_results: int = 3, max_distance_m: float = 1000
) -> list[dict]:
    """Find nearest metro/RER stops to a location."""
    stops_with_dist = []
    for stop in PARIS_METRO_STOPS:
        d = _haversine_m(lat, lon, stop["lat"], stop["lon"])
        if d <= max_distance_m:
            stops_with_dist.append((d, stop))
    stops_with_dist.sort(key=lambda x: x[0])
    results = []
    for d, stop in stops_with_dist[:max_results]:
        results.append({
            "name": stop["name"],
            "line": stop["line"],
            "distance_m": round(d, 0),
            "walk_minutes": round(d / WALK_SPEED_M_PER_MIN, 1),
        })
    return results
