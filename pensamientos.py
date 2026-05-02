"""Pensamiento del día: pensadores y estrategas, determinista por fecha."""

from __future__ import annotations

from datetime import date

CITAS: list[dict[str, str]] = [
    {
        "texto": "La suprema excelencia no consiste en ganar todas las batallas, sino en derrotar al enemigo sin combatir.",
        "autor": "Sun Tzu",
        "anyo": "≈500 a. C.",
    },
    {
        "texto": "Conoce a tu enemigo y conócete a ti mismo y saldrás victorioso de mil batallas.",
        "autor": "Sun Tzu",
        "anyo": "≈500 a. C.",
    },
    {
        "texto": "En medio del invierno aprendí, por fin, que dentro de mí había un verano invencible.",
        "autor": "Albert Camus",
        "anyo": "1952",
    },
    {
        "texto": "Tienes poder sobre tu mente, no sobre los acontecimientos exteriores. Date cuenta de esto y hallarás la fuerza.",
        "autor": "Marco Aurelio",
        "anyo": "≈170 d. C.",
    },
    {
        "texto": "El obstáculo es el camino.",
        "autor": "Marco Aurelio",
        "anyo": "≈170 d. C.",
    },
    {
        "texto": "Cuanto más sudemos en la paz, menos sangraremos en la guerra.",
        "autor": "Norman Schwarzkopf",
        "anyo": "1991",
    },
    {
        "texto": "La guerra es la mera continuación de la política por otros medios.",
        "autor": "Carl von Clausewitz",
        "anyo": "1832",
    },
    {
        "texto": "Lo más difícil es la decisión de actuar; el resto es mera tenacidad.",
        "autor": "Amelia Earhart",
        "anyo": "1932",
    },
    {
        "texto": "El que tiene un porqué para vivir puede soportar casi cualquier cómo.",
        "autor": "Friedrich Nietzsche",
        "anyo": "1889",
    },
    {
        "texto": "Lo que no te mata te hace más fuerte.",
        "autor": "Friedrich Nietzsche",
        "anyo": "1888",
    },
    {
        "texto": "No existe viento favorable para el que no sabe a qué puerto se dirige.",
        "autor": "Séneca",
        "anyo": "≈64 d. C.",
    },
    {
        "texto": "Mientras se está aprendiendo a vivir, ya se está viviendo.",
        "autor": "Séneca",
        "anyo": "≈64 d. C.",
    },
    {
        "texto": "Somos lo que hacemos repetidamente. La excelencia, entonces, no es un acto, sino un hábito.",
        "autor": "Aristóteles (parafraseado por Will Durant)",
        "anyo": "1926",
    },
    {
        "texto": "Es mejor ser temido que amado, si no se puede ser ambas cosas.",
        "autor": "Nicolás Maquiavelo",
        "anyo": "1532",
    },
    {
        "texto": "Nunca interrumpas a tu enemigo cuando está cometiendo un error.",
        "autor": "Napoleón Bonaparte",
        "anyo": "≈1810",
    },
    {
        "texto": "La victoria pertenece al que más persevera.",
        "autor": "Napoleón Bonaparte",
        "anyo": "≈1815",
    },
    {
        "texto": "El planeamiento es indispensable, pero los planes son inútiles.",
        "autor": "Dwight D. Eisenhower",
        "anyo": "1957",
    },
    {
        "texto": "No le digas a la gente cómo hacer las cosas, diles qué hacer y déjalos sorprenderte con sus resultados.",
        "autor": "George S. Patton",
        "anyo": "1944",
    },
    {
        "texto": "Una mente débil es como un microscopio: aumenta las cosas pequeñas, pero es incapaz de captar las grandes.",
        "autor": "Lord Chesterfield",
        "anyo": "1748",
    },
    {
        "texto": "El que sabe vencerse a sí mismo es más fuerte que el que vence a mil enemigos.",
        "autor": "Buda",
        "anyo": "≈500 a. C.",
    },
    {
        "texto": "Quien sabe que tiene suficiente es rico.",
        "autor": "Lao Tse",
        "anyo": "≈500 a. C.",
    },
    {
        "texto": "Un viaje de mil leguas comienza con un solo paso.",
        "autor": "Lao Tse",
        "anyo": "≈500 a. C.",
    },
    {
        "texto": "Domina tus pensamientos o te dominarán a ti.",
        "autor": "Horacio",
        "anyo": "≈20 a. C.",
    },
    {
        "texto": "Lo que no se puede medir, no se puede mejorar.",
        "autor": "Lord Kelvin",
        "anyo": "1883",
    },
    {
        "texto": "El conocimiento es poder.",
        "autor": "Francis Bacon",
        "anyo": "1597",
    },
    {
        "texto": "Pienso, luego existo.",
        "autor": "René Descartes",
        "anyo": "1637",
    },
    {
        "texto": "Hay una sola cosa que hace que un sueño sea imposible de alcanzar: el miedo a fracasar.",
        "autor": "Paulo Coelho",
        "anyo": "1988",
    },
    {
        "texto": "Si quieres construir un barco, no empieces por reunir madera, cortar tablas y distribuir el trabajo, sino que evoca en los hombres el anhelo del mar libre y ancho.",
        "autor": "Antoine de Saint-Exupéry",
        "anyo": "1948",
    },
    {
        "texto": "Imitar es la forma más sincera de la mediocridad.",
        "autor": "John Stuart Mill (atrib.)",
        "anyo": "1859",
    },
    {
        "texto": "El hombre nunca sabe de lo que es capaz hasta que lo intenta.",
        "autor": "Charles Dickens",
        "anyo": "1841",
    },
    {
        "texto": "El éxito es ir de fracaso en fracaso sin perder el entusiasmo.",
        "autor": "Winston Churchill",
        "anyo": "≈1942",
    },
    {
        "texto": "Si te encuentras atravesando el infierno, sigue caminando.",
        "autor": "Winston Churchill",
        "anyo": "≈1940",
    },
    {
        "texto": "El barco más seguro es el que está en el puerto, pero los barcos no se construyen para eso.",
        "autor": "Tomás de Aquino (atrib.)",
        "anyo": "≈1265",
    },
    {
        "texto": "La disciplina es el puente entre las metas y los logros.",
        "autor": "Jim Rohn",
        "anyo": "1985",
    },
    {
        "texto": "Quien no espera vencer, ya está vencido.",
        "autor": "José Joaquín de Olmedo",
        "anyo": "1825",
    },
    {
        "texto": "El secreto de la guerra reside en las comunicaciones.",
        "autor": "Napoleón Bonaparte",
        "anyo": "≈1812",
    },
    {
        "texto": "Sé como el agua: encuentra siempre el camino.",
        "autor": "Bruce Lee",
        "anyo": "1971",
    },
    {
        "texto": "El que es grande se aleja del centro y se mueve por sí mismo.",
        "autor": "Heráclito",
        "anyo": "≈500 a. C.",
    },
    {
        "texto": "Solo sé que no sé nada.",
        "autor": "Sócrates",
        "anyo": "≈399 a. C.",
    },
    {
        "texto": "Una vida sin examen no merece ser vivida.",
        "autor": "Sócrates",
        "anyo": "≈399 a. C.",
    },
    {
        "texto": "La fortuna favorece a los audaces.",
        "autor": "Virgilio",
        "anyo": "≈19 a. C.",
    },
    {
        "texto": "El silencio es uno de los argumentos más difíciles de refutar.",
        "autor": "Josh Billings",
        "anyo": "1865",
    },
    {
        "texto": "Cuando todos los caminos parecen cerrados, abre uno con tu propia voluntad.",
        "autor": "Hannibal Barca (atrib.)",
        "anyo": "≈218 a. C.",
    },
    {
        "texto": "El primero en el campo y el último en abandonarlo.",
        "autor": "Sun Bin",
        "anyo": "≈350 a. C.",
    },
    {
        "texto": "Los grandes espíritus siempre han encontrado oposición violenta de mentes mediocres.",
        "autor": "Albert Einstein",
        "anyo": "1940",
    },
    {
        "texto": "El que tiene paciencia obtendrá lo que desea.",
        "autor": "Benjamin Franklin",
        "anyo": "1758",
    },
    {
        "texto": "El precio de la grandeza es la responsabilidad.",
        "autor": "Winston Churchill",
        "anyo": "1943",
    },
    {
        "texto": "El verdadero héroe es el que conquista su ira y sus pasiones.",
        "autor": "Mahatma Gandhi",
        "anyo": "1925",
    },
    {
        "texto": "Sé el cambio que quieres ver en el mundo.",
        "autor": "Mahatma Gandhi",
        "anyo": "≈1930",
    },
    {
        "texto": "El cobarde muere mil veces antes de su muerte; el valiente prueba la muerte una sola vez.",
        "autor": "William Shakespeare",
        "anyo": "1599",
    },
    {
        "texto": "Lo que con mucho trabajo se adquiere, más se ama.",
        "autor": "Aristóteles",
        "anyo": "≈340 a. C.",
    },
    {
        "texto": "El que detiene a un solo hombre detiene a un ejército.",
        "autor": "Vegecio",
        "anyo": "≈390 d. C.",
    },
    {
        "texto": "Si vis pacem, para bellum. Si quieres la paz, prepara la guerra.",
        "autor": "Vegecio",
        "anyo": "≈390 d. C.",
    },
    {
        "texto": "El líder debe ser el primero en sentir el frío y el último en aceptar el calor.",
        "autor": "Atribuido a un general chino",
        "anyo": "≈400 a. C.",
    },
]


def cita_del_dia(d: date | None = None) -> dict[str, str]:
    if d is None:
        d = date.today()
    n = d.toordinal() % len(CITAS)
    return CITAS[n]
