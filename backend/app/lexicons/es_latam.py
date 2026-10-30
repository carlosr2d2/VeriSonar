"""Léxico de pistas lingüísticas para español latinoamericano.

Estas listas no demuestran mentira. Capturan marcadores de
distanciamiento, carga cognitiva, muletillas regionales y
protestas de sinceridad documentados en literatura forense.
"""

HEDGES_ES = {
    "creo",
    "creo que",
    "me parece",
    "tal vez",
    "quizá",
    "quizás",
    "posiblemente",
    "probablemente",
    "más o menos",
    "como que",
    "digamos",
    "en teoría",
    "supongo",
    "no sé",
    "no estoy seguro",
    "no estoy segura",
    "si mal no recuerdo",
    "por ahí",
    "capaz",
    "a lo mejor",
    "puede ser",
}

FILLERS_ES = {
    "este",
    "eh",
    "ah",
    "pues",
    "bueno",
    "o sea",
    "entonces",
    "tipo",
    "como",
    "viste",
    "cachai",
    "po",
    "weón",
    "weon",
    "güey",
    "wey",
    "pues sí",
    "este pues",
    "mmm",
    "eee",
    "la verdad",
}

NEGATIONS_ES = {
    "no",
    "nunca",
    "jamás",
    "tampoco",
    "nadie",
    "nada",
    "ningún",
    "ninguna",
    "ni",
}

FIRST_PERSON = {"yo", "mí", "me", "mi", "conmigo", "nosotros", "nosotras", "nuestro", "nuestra"}
DISTANCING = {"uno", "alguien", "la gente", "ellos", "ellas", "se", "eso", "aquello"}

PROTESTATIONS_ES = {
    "te juro",
    "se lo juro",
    "de verdad",
    "la verdad es",
    "honestamente",
    "sinceramente",
    "te lo prometo",
    "en serio",
    "palabra de honor",
    "no miento",
    "te soy sincero",
    "te soy sincera",
}

COGNITIVE_LOAD_ES = {
    "espera",
    "a ver",
    "cómo te explico",
    "cómo le explico",
    "déjame pensar",
    "no me acuerdo",
    "no recuerdo",
    "eso fue",
    "después",
    "luego",
}

# Variantes regionales de muletillas (México, Andes, Cono Sur, Caribe)
REGIONAL_FILLERS = {
    "mx": {"este", "o sea", "güey", "como que", "la neta"},
    "co": {"pues", "entonces", "marica", "parce"},
    "ar": {"che", "tipo", "viste", "boludo"},
    "cl": {"po", "cachai", "weón", "como"},
    "pe": {"causa", "pata", "pues"},
    "ve": {"chévere", "vale", "este"},
    "uy": {"bo", "ta", "viste"},
}

# Marcadores de inglés para fase posterior
HEDGES_EN = {"i think", "maybe", "perhaps", "kind of", "sort of", "i guess", "probably"}
FILLERS_EN = {"um", "uh", "like", "you know", "well", "so"}
PROTESTATIONS_EN = {"honestly", "to be honest", "i swear", "believe me", "to tell the truth"}
