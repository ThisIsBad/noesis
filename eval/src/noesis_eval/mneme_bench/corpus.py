"""Deterministic fact corpus for the Mneme Recall@k benchmark.

Each BenchPair has a canonical ``memory_content`` (stored once in Mneme) and
one ``query`` paraphrase pointing at that memory. ``generate_pairs`` is
seeded, so two calls with the same parameters produce identical output —
a requirement for reproducible acceptance runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from noesis_schemas import MemoryType


@dataclass(frozen=True)
class BenchPair:
    memory_content: str
    memory_type: MemoryType
    query: str


# ── Semantic facts ────────────────────────────────────────────────────────────

_CAPITALS: list[tuple[str, str]] = [
    ("France", "Paris"), ("Germany", "Berlin"), ("Japan", "Tokyo"),
    ("Italy", "Rome"), ("Spain", "Madrid"), ("Portugal", "Lisbon"),
    ("Greece", "Athens"), ("Egypt", "Cairo"), ("Kenya", "Nairobi"),
    ("Nigeria", "Abuja"), ("Brazil", "Brasília"), ("Argentina", "Buenos Aires"),
    ("Chile", "Santiago"), ("Peru", "Lima"), ("Colombia", "Bogotá"),
    ("Canada", "Ottawa"), ("Mexico", "Mexico City"), ("Cuba", "Havana"),
    ("Australia", "Canberra"), ("New Zealand", "Wellington"),
    ("India", "New Delhi"), ("China", "Beijing"), ("South Korea", "Seoul"),
    ("Thailand", "Bangkok"), ("Vietnam", "Hanoi"), ("Indonesia", "Jakarta"),
    ("Philippines", "Manila"), ("Turkey", "Ankara"), ("Iran", "Tehran"),
    ("Saudi Arabia", "Riyadh"), ("Israel", "Jerusalem"), ("Jordan", "Amman"),
    ("Norway", "Oslo"), ("Sweden", "Stockholm"), ("Finland", "Helsinki"),
    ("Denmark", "Copenhagen"), ("Iceland", "Reykjavík"), ("Ireland", "Dublin"),
    ("Poland", "Warsaw"), ("Ukraine", "Kyiv"),
    ("Netherlands", "Amsterdam"), ("Belgium", "Brussels"),
    ("Switzerland", "Bern"), ("Austria", "Vienna"), ("Hungary", "Budapest"),
]


def _capital_pairs() -> Iterable[BenchPair]:
    for country, capital in _CAPITALS:
        memory = f"The capital of {country} is {capital}."
        for q in (
            f"What is the capital of {country}?",
            f"Which city is {country}'s capital?",
            f"Name the capital city of {country}.",
        ):
            yield BenchPair(memory, MemoryType.SEMANTIC, q)


_ELEMENTS: list[tuple[str, str, int]] = [
    ("H", "Hydrogen", 1), ("He", "Helium", 2), ("Li", "Lithium", 3),
    ("Be", "Beryllium", 4), ("B", "Boron", 5), ("C", "Carbon", 6),
    ("N", "Nitrogen", 7), ("O", "Oxygen", 8), ("F", "Fluorine", 9),
    ("Ne", "Neon", 10), ("Na", "Sodium", 11), ("Mg", "Magnesium", 12),
    ("Al", "Aluminium", 13), ("Si", "Silicon", 14), ("P", "Phosphorus", 15),
    ("S", "Sulfur", 16), ("Cl", "Chlorine", 17), ("Ar", "Argon", 18),
    ("K", "Potassium", 19), ("Ca", "Calcium", 20), ("Fe", "Iron", 26),
    ("Cu", "Copper", 29), ("Zn", "Zinc", 30), ("Ag", "Silver", 47),
    ("Au", "Gold", 79), ("Hg", "Mercury", 80), ("Pb", "Lead", 82),
    ("U", "Uranium", 92),
]


def _element_pairs() -> Iterable[BenchPair]:
    for symbol, name, z in _ELEMENTS:
        memory = f"{name} has chemical symbol {symbol} and atomic number {z}."
        for q in (
            f"What is the atomic number of {name}?",
            f"Which element has symbol {symbol}?",
            f"Which element sits at atomic number {z}?",
        ):
            yield BenchPair(memory, MemoryType.SEMANTIC, q)


_BOOKS: list[tuple[str, str, int]] = [
    ("Pride and Prejudice", "Jane Austen", 1813),
    ("Moby-Dick", "Herman Melville", 1851),
    ("Crime and Punishment", "Fyodor Dostoevsky", 1866),
    ("War and Peace", "Leo Tolstoy", 1869),
    ("The Brothers Karamazov", "Fyodor Dostoevsky", 1880),
    ("Dracula", "Bram Stoker", 1897),
    ("Ulysses", "James Joyce", 1922),
    ("The Great Gatsby", "F. Scott Fitzgerald", 1925),
    ("The Sound and the Fury", "William Faulkner", 1929),
    ("Brave New World", "Aldous Huxley", 1932),
    ("The Hobbit", "J. R. R. Tolkien", 1937),
    ("Nineteen Eighty-Four", "George Orwell", 1949),
    ("The Catcher in the Rye", "J. D. Salinger", 1951),
    ("Fahrenheit 451", "Ray Bradbury", 1953),
    ("Lord of the Flies", "William Golding", 1954),
    ("To Kill a Mockingbird", "Harper Lee", 1960),
    ("One Hundred Years of Solitude", "Gabriel García Márquez", 1967),
    ("Slaughterhouse-Five", "Kurt Vonnegut", 1969),
    ("Gravity's Rainbow", "Thomas Pynchon", 1973),
    ("Beloved", "Toni Morrison", 1987),
    ("The Remains of the Day", "Kazuo Ishiguro", 1989),
    ("Infinite Jest", "David Foster Wallace", 1996),
    ("The God of Small Things", "Arundhati Roy", 1997),
    ("The Road", "Cormac McCarthy", 2006),
    ("Never Let Me Go", "Kazuo Ishiguro", 2005),
    ("Wolf Hall", "Hilary Mantel", 2009),
    ("A Brief History of Time", "Stephen Hawking", 1988),
    ("The Handmaid's Tale", "Margaret Atwood", 1985),
    ("Ficciones", "Jorge Luis Borges", 1944),
    ("The Stranger", "Albert Camus", 1942),
]


def _book_pairs() -> Iterable[BenchPair]:
    for title, author, year in _BOOKS:
        memory = f"{title} was written by {author}, published in {year}."
        for q in (
            f"Who wrote {title}?",
            f"When was {title} published?",
            f"What year did {author} publish {title}?",
        ):
            yield BenchPair(memory, MemoryType.SEMANTIC, q)


_INVENTIONS: list[tuple[str, str, int]] = [
    ("telephone", "Alexander Graham Bell", 1876),
    ("phonograph", "Thomas Edison", 1877),
    ("practical incandescent light bulb", "Thomas Edison", 1879),
    ("radio", "Guglielmo Marconi", 1895),
    ("aeroplane", "the Wright brothers", 1903),
    ("bakelite plastic", "Leo Baekeland", 1907),
    ("television", "Philo Farnsworth", 1927),
    ("polio vaccine", "Jonas Salk", 1955),
    ("laser", "Theodore Maiman", 1960),
    ("World Wide Web", "Tim Berners-Lee", 1989),
    ("first practical photograph", "Louis Daguerre", 1839),
    ("dynamite", "Alfred Nobel", 1867),
    ("pasteurisation", "Louis Pasteur", 1864),
    ("penicillin", "Alexander Fleming", 1928),
    ("periodic table", "Dmitri Mendeleev", 1869),
    ("general theory of relativity", "Albert Einstein", 1915),
    ("DNA double helix", "Watson and Crick", 1953),
]


def _invention_pairs() -> Iterable[BenchPair]:
    for what, who, year in _INVENTIONS:
        memory = f"{who} introduced the {what} in {year}."
        for q in (
            f"Who invented the {what}?",
            f"When was the {what} introduced?",
            f"In which year did {who} create the {what}?",
        ):
            yield BenchPair(memory, MemoryType.SEMANTIC, q)


_CONSTANTS: list[tuple[str, str, str]] = [
    ("speed of light in vacuum", "c", "299,792,458 m/s"),
    ("Planck's constant", "h", "6.62607015e-34 J·s"),
    ("gravitational constant", "G", "6.67430e-11 N·m²/kg²"),
    ("Avogadro's number", "N_A", "6.02214076e23 /mol"),
    ("elementary charge", "e", "1.602176634e-19 C"),
    ("Boltzmann constant", "k_B", "1.380649e-23 J/K"),
    ("electron mass", "m_e", "9.1093837e-31 kg"),
    ("proton mass", "m_p", "1.67262192e-27 kg"),
    ("vacuum permittivity", "ε₀", "8.8541878128e-12 F/m"),
    ("standard gravity", "g_n", "9.80665 m/s²"),
    ("molar gas constant", "R", "8.314462618 J/(mol·K)"),
    ("Stefan–Boltzmann constant", "σ", "5.670374419e-8 W/(m²·K⁴)"),
]


def _constant_pairs() -> Iterable[BenchPair]:
    for name, symbol, value in _CONSTANTS:
        memory = f"The {name} ({symbol}) equals {value}."
        for q in (
            f"What is the value of the {name}?",
            f"What does the symbol {symbol} denote in physics?",
            f"Give the numeric value of {name}.",
        ):
            yield BenchPair(memory, MemoryType.SEMANTIC, q)


# ── Episodic events ───────────────────────────────────────────────────────────

_EPISODIC: list[tuple[str, str, str]] = [
    ("1945-05-08", "Nazi Germany", "surrendered to the Allies"),
    ("1969-07-20", "Apollo 11", "landed humans on the Moon"),
    ("1989-11-09", "the Berlin Wall", "fell after 28 years"),
    ("2001-09-11", "the September 11 attacks", "struck the United States"),
    ("2008-11-04", "Barack Obama", "was elected U.S. president"),
    ("1912-04-15", "the Titanic", "sank after striking an iceberg"),
    ("1955-12-01", "Rosa Parks", "refused to give up her bus seat"),
    ("1963-08-28", "Martin Luther King Jr.", "gave his I Have a Dream speech"),
    ("1986-04-26", "the Chernobyl reactor", "exploded during a safety test"),
    ("1991-12-25", "the Soviet Union", "formally dissolved"),
    ("2019-12-31", "Chinese authorities", "first reported the novel coronavirus"),
    ("1776-07-04", "the Second Continental Congress",
     "adopted the Declaration of Independence"),
    ("1789-07-14", "Parisian revolutionaries", "stormed the Bastille"),
    ("1815-06-18", "Napoleon", "was defeated at Waterloo"),
    ("1865-04-14", "President Lincoln", "was shot at Ford's Theatre"),
    ("1914-06-28", "Archduke Franz Ferdinand", "was assassinated in Sarajevo"),
    ("1929-10-29", "the U.S. stock market", "crashed on Black Tuesday"),
    ("1941-12-07", "Japan", "attacked Pearl Harbor"),
    ("1953-05-29", "Edmund Hillary and Tenzing Norgay", "summited Mount Everest"),
    ("1957-10-04", "the Soviet Union", "launched Sputnik 1"),
    ("1961-04-12", "Yuri Gagarin", "became the first human in space"),
    ("1963-11-22", "President John F. Kennedy", "was assassinated in Dallas"),
    ("1990-02-11", "Nelson Mandela", "was released from prison"),
    ("1994-04-27", "South Africa", "held its first multiracial election"),
    ("2011-03-11", "a magnitude 9.1 earthquake", "triggered the Tōhoku tsunami"),
    ("1492-10-12", "Christopher Columbus", "made landfall in the Bahamas"),
    ("1517-10-31", "Martin Luther", "posted the Ninety-five Theses in Wittenberg"),
    ("1687-07-05", "Isaac Newton", "published the Principia Mathematica"),
    ("1776-03-09", "Adam Smith", "published The Wealth of Nations"),
    ("1859-11-24", "Charles Darwin", "published On the Origin of Species"),
    ("1871-01-18", "the German Empire", "was proclaimed at Versailles"),
    ("1927-05-20", "Charles Lindbergh", "began the first solo transatlantic flight"),
    ("1974-08-09", "Richard Nixon", "resigned the U.S. presidency"),
    ("1980-12-08", "John Lennon", "was shot in New York City"),
    ("2012-08-06", "the Curiosity rover", "landed on Mars"),
]


def _episodic_pairs() -> Iterable[BenchPair]:
    for date, agent, action in _EPISODIC:
        memory = f"On {date}, {agent} {action}."
        for q in (
            f"When did {agent} {action}?",
            f"What happened on {date}?",
            f"On what date did {agent} {action}?",
        ):
            yield BenchPair(memory, MemoryType.EPISODIC, q)


def generate_pairs(n_target: int = 500) -> list[BenchPair]:
    """Yield a deterministic list of at least ``n_target`` BenchPairs.

    Pairs are drawn round-robin across themes so truncation to smaller sizes
    still covers every fact family.
    """
    buckets: list[list[BenchPair]] = [
        list(_capital_pairs()),
        list(_element_pairs()),
        list(_book_pairs()),
        list(_invention_pairs()),
        list(_constant_pairs()),
        list(_episodic_pairs()),
    ]
    interleaved: list[BenchPair] = []
    i = 0
    while any(i < len(b) for b in buckets):
        for b in buckets:
            if i < len(b):
                interleaved.append(b[i])
        i += 1

    if n_target <= len(interleaved):
        return interleaved[:n_target]
    # Asking for more than we have is a programming error — surface it.
    raise ValueError(
        f"Corpus has {len(interleaved)} pairs; cannot satisfy n_target={n_target}"
    )


def unique_memories(pairs: list[BenchPair]) -> list[BenchPair]:
    """De-duplicate by ``memory_content`` — what actually gets stored."""
    seen: dict[str, BenchPair] = {}
    for p in pairs:
        seen.setdefault(p.memory_content, p)
    return list(seen.values())
