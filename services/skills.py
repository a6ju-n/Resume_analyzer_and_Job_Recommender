"""
Skill vocabulary and detection.

One place that knows what a "skill" is, so the resume parser, the skill chips
and the job matcher can never disagree with each other.

Detection is plain text matching (no AI), so the same resume always gives the
same skills.
"""
from __future__ import annotations

import re

# kind: language | framework | tool | database | cloud | concept
# aliases are matched case-insensitively as whole words anywhere in the resume.
# strict aliases are ambiguous English words ("go", "r", "express" ...), so they
# only count when they appear as an item in the skills list (e.g. "Python, Go, R").
_VOCAB: dict[str, dict] = {
    # --- languages ---
    "Python":     {"kind": "language", "aliases": ["python", "python3"]},
    "Java":       {"kind": "language", "aliases": ["java"]},
    "JavaScript": {"kind": "language", "aliases": ["javascript", "js", "es6"]},
    "TypeScript": {"kind": "language", "aliases": ["typescript"]},
    "C":          {"kind": "language", "strict": ["c"]},
    "C++":        {"kind": "language", "aliases": ["c++", "cpp"]},
    "C#":         {"kind": "language", "aliases": ["c#", "csharp"]},
    "Kotlin":     {"kind": "language", "aliases": ["kotlin"]},
    "Swift":      {"kind": "language", "aliases": ["swift", "swiftui"]},
    "Dart":       {"kind": "language", "aliases": ["dart"]},
    "Go":         {"kind": "language", "aliases": ["golang"], "strict": ["go"]},
    "Rust":       {"kind": "language", "aliases": ["rust"]},
    "Ruby":       {"kind": "language", "aliases": ["ruby"]},
    "PHP":        {"kind": "language", "aliases": ["php"]},
    "Scala":      {"kind": "language", "aliases": ["scala"]},
    "R":          {"kind": "language", "strict": ["r"]},
    "MATLAB":     {"kind": "language", "aliases": ["matlab"]},
    "Bash":       {"kind": "language", "aliases": ["bash"], "strict": ["shell"]},
    "SQL":        {"kind": "language", "aliases": ["sql", "t-sql", "pl/sql"]},
    "HTML":       {"kind": "language", "aliases": ["html", "html5"]},
    "CSS":        {"kind": "language", "aliases": ["css", "css3"]},
    # --- frameworks / libraries ---
    "Flask":        {"kind": "framework", "aliases": ["flask"]},
    "Django":       {"kind": "framework", "aliases": ["django"]},
    "FastAPI":      {"kind": "framework", "aliases": ["fastapi"]},
    "Spring Boot":  {"kind": "framework", "aliases": ["spring boot", "springboot"]},
    "Spring":       {"kind": "framework", "strict": ["spring"]},
    "React":        {"kind": "framework", "aliases": ["react", "react.js", "reactjs"]},
    "Angular":      {"kind": "framework", "aliases": ["angular", "angularjs"]},
    "Vue":          {"kind": "framework", "aliases": ["vue", "vue.js", "vuejs"]},
    "Next.js":      {"kind": "framework", "aliases": ["next.js", "nextjs"]},
    "Node.js":      {"kind": "framework", "aliases": ["node.js", "nodejs"], "strict": ["node"]},
    "Express":      {"kind": "framework", "aliases": ["express.js", "expressjs"], "strict": ["express"]},
    "TensorFlow":   {"kind": "framework", "aliases": ["tensorflow"]},
    "PyTorch":      {"kind": "framework", "aliases": ["pytorch"]},
    "Keras":        {"kind": "framework", "aliases": ["keras"]},
    "scikit-learn": {"kind": "framework", "aliases": ["scikit-learn", "scikit learn", "sklearn"]},
    "Pandas":       {"kind": "framework", "aliases": ["pandas"]},
    "NumPy":        {"kind": "framework", "aliases": ["numpy"]},
    "Matplotlib":   {"kind": "framework", "aliases": ["matplotlib", "seaborn"]},
    "Flutter":      {"kind": "framework", "aliases": ["flutter"]},
    "Android":      {"kind": "framework", "aliases": ["android", "android studio"]},
    "iOS":          {"kind": "framework", "aliases": ["ios", "xcode"]},
    "Bootstrap":    {"kind": "framework", "aliases": ["bootstrap"]},
    "Tailwind CSS": {"kind": "framework", "aliases": ["tailwind", "tailwindcss", "tailwind css"]},
    "GraphQL":      {"kind": "framework", "aliases": ["graphql"]},
    "REST APIs":    {"kind": "framework", "aliases": ["rest api", "rest apis", "restful", "restful api", "restful apis"],
                     "strict": ["rest"]},
    # --- tools ---
    "Git":          {"kind": "tool", "aliases": ["git", "github", "gitlab", "bitbucket"]},
    "Docker":       {"kind": "tool", "aliases": ["docker"]},
    "Kubernetes":   {"kind": "tool", "aliases": ["kubernetes", "k8s"]},
    "Linux":        {"kind": "tool", "aliases": ["linux", "ubuntu"]},
    "CI/CD":        {"kind": "tool", "aliases": ["ci/cd", "jenkins", "github actions", "gitlab ci"]},
    "Terraform":    {"kind": "tool", "aliases": ["terraform", "ansible"]},
    "Testing":      {"kind": "tool", "aliases": ["pytest", "unittest", "junit", "unit testing", "selenium", "jest"]},
    "Postman":      {"kind": "tool", "aliases": ["postman"]},
    "Jupyter":      {"kind": "tool", "aliases": ["jupyter"]},
    "Tableau":      {"kind": "tool", "aliases": ["tableau"]},
    "Power BI":     {"kind": "tool", "aliases": ["power bi", "powerbi"]},
    "Excel":        {"kind": "tool", "aliases": ["microsoft excel", "ms excel", "advanced excel"], "strict": ["excel"]},
    # --- databases ---
    "MongoDB":       {"kind": "database", "aliases": ["mongodb", "mongo"]},
    "PostgreSQL":    {"kind": "database", "aliases": ["postgresql", "postgres"]},
    "MySQL":         {"kind": "database", "aliases": ["mysql"]},
    "SQLite":        {"kind": "database", "aliases": ["sqlite", "sqlite3"]},
    "Redis":         {"kind": "database", "aliases": ["redis"]},
    "Elasticsearch": {"kind": "database", "aliases": ["elasticsearch"]},
    "Firebase":      {"kind": "database", "aliases": ["firebase", "firestore"]},
    # --- cloud ---
    "AWS":   {"kind": "cloud", "aliases": ["aws", "amazon web services", "ec2", "s3"]},
    "Azure": {"kind": "cloud", "aliases": ["azure"]},
    "GCP":   {"kind": "cloud", "aliases": ["gcp", "google cloud"]},
    # --- concepts ---
    "Machine Learning":   {"kind": "concept", "aliases": ["machine learning", "ml"]},
    "Deep Learning":      {"kind": "concept", "aliases": ["deep learning", "neural networks", "cnn"]},
    "NLP":                {"kind": "concept", "aliases": ["nlp", "natural language processing"]},
    "Data Analysis":      {"kind": "concept", "aliases": ["data analysis", "data analytics"]},
    "Data Visualization": {"kind": "concept", "aliases": ["data visualization", "data visualisation"]},
    "OOP":                {"kind": "concept", "aliases": ["oop", "object-oriented", "object oriented"]},
    "Data Structures":    {"kind": "concept", "aliases": ["data structures", "algorithms", "dsa"]},
    "Agile":              {"kind": "concept", "aliases": ["agile", "scrum"]},
}

LANGUAGE_KINDS = {"language"}
TOOLING_KINDS = {"framework", "tool", "database", "cloud"}


def _alias_pattern(alias: str) -> re.Pattern:
    # Not preceded/followed by a word char, '+' or '#' so "java" never matches
    # inside "javascript" and "c" never matches inside "c++".
    return re.compile(rf"(?<![\w+#.]){re.escape(alias)}(?![\w+#])", re.I)


_PATTERNS: dict[str, list[re.Pattern]] = {
    name: [_alias_pattern(a) for a in meta.get("aliases", [])]
    for name, meta in _VOCAB.items()
}
_STRICT: dict[str, set[str]] = {
    name: {a.lower() for a in meta["strict"]}
    for name, meta in _VOCAB.items() if meta.get("strict")
}


def list_items(text: str) -> set[str]:
    """Lower-cased list items of a resume ('Languages: Python, Go' -> {'python', 'go'})."""
    items: set[str] = set()
    for tok in re.split(r"[,•|·;\n\t/\\()]+", text):
        tok = tok.rsplit(":", 1)[-1].strip().strip(".-– ").lower()
        if tok:
            items.add(tok)
    return items


def detect_skills(text: str, skills_section: str = "") -> list[str]:
    """
    Return the canonical names of every skill found in *text*, in vocabulary order.
    Ambiguous one-word skills (Go, R, C ...) are only accepted from list items
    in the skills section (or the whole text when there is no such section).
    """
    if not text:
        return []
    items = list_items(skills_section or text)
    found = []
    for name, patterns in _PATTERNS.items():
        if any(p.search(text) for p in patterns):
            found.append(name)
        elif name in _STRICT and (_STRICT[name] & items):
            found.append(name)
    return found


def kind_of(skill: str) -> str:
    return _VOCAB.get(skill, {}).get("kind", "concept")


def detect_by_kind(text: str, kinds: set[str], skills_section: str = "") -> list[str]:
    return [s for s in detect_skills(text, skills_section) if kind_of(s) in kinds]
